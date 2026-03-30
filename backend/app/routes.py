"""BESS Sizing Tool — Flask Blueprint with all API endpoints."""
import dataclasses
import json
import os

from flask import Blueprint, current_app, jsonify, render_template, request

from ..calculators.efficiency import (
    AuxEfficiencyInput,
    BatteryLossInput,
    SystemEfficiencyInput,
    calculate_all as calc_efficiency,
)
from ..calculators.pcs_sizing import PCSSizingInput, calculate_pcs_sizing
from ..calculators.battery_sizing import BatterySizingInput, calculate_battery_sizing, get_product_specs
from ..calculators.retention import (
    AugmentationWave,
    AugmentationRecommendation,
    RetentionInput,
    calculate_retention,
    calculate_with_augmentation,
    recommend_augmentation,
)
from ..calculators.soc import SOCInput, calculate_soc

try:
    from ..calculators.convergence import ConvergenceInput, solve as convergence_solve
    from ..calculators.efficiency import BatteryLossInput as _BatteryLossInput
    _HAS_CONVERGENCE = True
except ImportError:
    _HAS_CONVERGENCE = False

try:
    from ..calculators.reactive_power import ReactivePowerInput, calculate_reactive_power
    _HAS_REACTIVE_POWER = True
except ImportError:
    _HAS_REACTIVE_POWER = False

try:
    from ..calculators.rte import RTEInput, calculate_rte
    _HAS_RTE = True
except ImportError:
    _HAS_RTE = False

from .models import (
    get_project, list_projects, save_project,
    list_cases, get_case, create_case, update_case, delete_case, clone_case,
    get_cases_for_comparison, _resolve_pcs_product,
)

bp = Blueprint('main', __name__)


def _calc_m10_order(pcs_result, no_of_pcs):
    """Calculate M10 order quantity for EPC Power M-system.

    M10 = 2 PCS slots. M5/M6 are not sold individually.
    For non-EPC manufacturers, returns None (not applicable).
    """
    import math
    if pcs_result.config.manufacturer == 'EPC Power' and pcs_result.config.model.startswith('M'):
        return math.ceil(no_of_pcs / 2)
    return None


def _asdict(obj) -> dict:
    """Recursively convert dataclass instances (and nested ones) to dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _asdict(v) for k, v in dataclasses.asdict(obj).items()}
    return obj


# ---------------------------------------------------------------------------
# HTML views
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    """Render the main sizing input page."""
    try:
        return render_template('input.html')
    except Exception:
        # Graceful fallback when frontend templates are not yet present
        return '<h1>BESS Sizing Tool API</h1><p>Frontend not yet deployed.</p>', 200


@bp.route('/rte')
def rte_page():
    """Render the standalone RTE calculator page."""
    return render_template('rte.html')


@bp.route('/api/rte/designs', methods=['GET'])
def api_rte_designs():
    """Public read-only list of designs for RTE page (no login required).

    Unlike /api/shared/designs, this includes input_data (needed for
    loading efficiency values) and requires no authentication.
    """
    from .shared_models import get_db
    db_path = current_app.config['DATABASE']
    try:
        conn = get_db(db_path)
        rows = conn.execute(
            "SELECT id, project_name, created_at, input_data FROM designs ORDER BY updated_at DESC LIMIT 50"
        ).fetchall()
        designs = []
        for r in rows:
            d = dict(r)
            try:
                d['input_data'] = json.loads(d['input_data']) if d.get('input_data') else {}
            except (json.JSONDecodeError, TypeError):
                d['input_data'] = {}
            designs.append(d)
        conn.close()
        return jsonify(designs), 200
    except Exception:
        return jsonify([]), 200


@bp.route('/projects')
def view_projects():
    """Render the projects list page."""
    return render_template('projects.html')


# ---------------------------------------------------------------------------
# Full sizing calculation
# ---------------------------------------------------------------------------

def _run_calculation(body: dict) -> dict:
    """Core calculation logic. Takes input body dict, returns result dict.

    Raises KeyError/ValueError/TypeError on bad input, Exception on internal error.
    """
    # --- Normalize frontend flat format → nested format ---
    # Frontend sends flat keys; API core expects nested dicts.
    # Accept both: if nested keys exist, use them; otherwise build from flat.
    if 'efficiency' not in body and 'hv_transformer' in body:
        body['efficiency'] = {
            'hv_ac_cabling': body.get('hv_ac_cabling', 0.999),
            'hv_transformer': body.get('hv_transformer', 0.995),
            'mv_ac_cabling': body.get('mv_ac_cabling', 0.999),
            'mv_transformer': body.get('mv_transformer', 0.993),
            'lv_cabling': body.get('lv_cabling', 0.996),
            'pcs_efficiency': body.get('pcs_efficiency', 0.985),
            'dc_cabling': body.get('dc_cabling', 0.999),
        }
    if 'aux_efficiency' not in body and 'branching_point' in body:
        body['aux_efficiency'] = {
            'branching_point': body.get('branching_point', 'MV'),
            'aux_tr_lv': body.get('aux_tr_lv', 0.985),
            'aux_line_lv': body.get('aux_line_lv', 0.999),
        }
    if 'battery_loss' not in body and 'applied_dod' in body:
        body['battery_loss'] = {
            'applied_dod': body.get('applied_dod', 0.99),
            'loss_factors': body.get('loss_factors', 0.98802),
            'mbms_consumption': body.get('mbms_consumption', 0.999),
        }
    # Field name aliases: frontend → API
    if 'product_type' not in body and 'battery_product_type' in body:
        body['product_type'] = body['battery_product_type']
    if 'pcs_type' not in body and 'pcs_configuration' in body:
        body['pcs_type'] = body['pcs_configuration']
    if 'project_life_yr' not in body and 'project_life' in body:
        body['project_life_yr'] = body['project_life']
    if 'rest_soc' not in body:
        body['rest_soc'] = body.get('rest_soc', 'Mid')
    # Normalize altitude: frontend "lt1000" → "<1000", "1000_1500" → "1000-1500"
    alt_map = {'lt1000': '<1000', '1000_1500': '1000-1500', '1500_2000': '1500-2000'}
    raw_alt = body.get('altitude', '<1000')
    body['altitude'] = alt_map.get(raw_alt, raw_alt)
    # Map frontend augmentation array to expected format
    if 'augmentation_waves' not in body and 'augmentation' in body:
        waves = []
        for w in body.get('augmentation', []):
            waves.append({
                'year': w.get('year', 0),
                'additional_links': w.get('additional_links', 0),
                'additional_energy_mwh': w.get('additional_energy_mwh', 0),
                'product_type': w.get('product_type', body.get('product_type', '')),
            })
        body['augmentation_waves'] = waves

    # --- Efficiency ---
    eff_cfg = body.get('efficiency', {})
    aux_cfg = body.get('aux_efficiency', {})
    bat_cfg = body.get('battery_loss', {})

    sys_inp = SystemEfficiencyInput(
        hv_ac_cabling=float(eff_cfg.get('hv_ac_cabling', 0.999)),
        hv_transformer=float(eff_cfg.get('hv_transformer', 0.995)),
        mv_ac_cabling=float(eff_cfg.get('mv_ac_cabling', 0.999)),
        mv_transformer=float(eff_cfg.get('mv_transformer', 0.993)),
        lv_cabling=float(eff_cfg.get('lv_cabling', 0.996)),
        pcs_efficiency=float(eff_cfg.get('pcs_efficiency', 0.985)),
        dc_cabling=float(eff_cfg.get('dc_cabling', 0.999)),
    )
    aux_inp = AuxEfficiencyInput(
        branching_point=str(aux_cfg.get('branching_point', 'MV')),
        aux_tr_lv=float(aux_cfg.get('aux_tr_lv', 0.985)),
        aux_line_lv=float(aux_cfg.get('aux_line_lv', 0.999)),
    )
    # loss_factors can be a single float (pre-computed product) or a list
    raw_lf = bat_cfg.get('loss_factors', 0.98802)
    if isinstance(raw_lf, list):
        import math
        loss_factors_val = math.prod(raw_lf)
    else:
        loss_factors_val = float(raw_lf)
    bat_loss_inp = BatteryLossInput(
        applied_dod=float(bat_cfg.get('applied_dod', 0.99)),
        loss_factors=loss_factors_val,
        mbms_consumption=float(bat_cfg.get('mbms_consumption', 0.999)),
    )
    eff_result = calc_efficiency(sys_inp, aux_inp, bat_loss_inp)

    # --- PCS Sizing ---
    required_power_poi = float(body.get('required_power_mw', 0))
    pcs_inp = PCSSizingInput(
        pcs_config_name=str(body.get('pcs_type', '')),
        temperature_c=int(body.get('temperature_c', 25)),
        altitude=str(body.get('altitude', '<1000m')),
        mv_voltage_tolerance=float(body.get('mv_voltage_tolerance', 0.02)),
    )
    # PCS needs DC power; approximate with POI / bat_poi_eff for first pass
    req_power_dc_approx = required_power_poi / eff_result.total_dc_to_aux_eff
    pcs_result = calculate_pcs_sizing(pcs_inp, req_power_dc_approx)

    # --- Battery Sizing (with optional convergence) ---
    application = str(body.get('application', '')).strip()
    convergence_result = None

    if application and _HAS_CONVERGENCE:
        # Build base BatteryLossInput from already-parsed values
        base_bat_loss = _BatteryLossInput(
            applied_dod=float(bat_cfg.get('applied_dod', 0.99)),
            loss_factors=loss_factors_val,
            mbms_consumption=float(bat_cfg.get('mbms_consumption', 0.999)),
        )
        conv_inp = ConvergenceInput(
            required_power_poi_mw=required_power_poi,
            required_energy_poi_mwh=float(body.get('required_energy_mwh', 0)),
            project_life_yr=int(body.get('project_life_yr', 20)),
            application=application,
            system_efficiency=sys_inp,
            aux_efficiency=aux_inp,
            base_battery_loss=base_bat_loss,
            pcs_config_name=str(body.get('pcs_type', '')),
            temperature_c=int(body.get('temperature_c', 25)),
            altitude=str(body.get('altitude', '<1000')),
            mv_voltage_tolerance=float(body.get('mv_voltage_tolerance', 0.02)),
            product_type=str(body.get('product_type', '')),
            aux_power_source=str(body.get('aux_power_source', 'Battery')),
            rest_soc=str(body.get('rest_soc', 'Mid')),
            measurement_method=str(body.get('measurement_method', 'Both CP')),
            link_override=int(body.get('link_override', 0) or 0),
        )
        convergence_result = convergence_solve(conv_inp)
        # Use converged sub-results for all downstream calculations
        eff_result = convergence_result.efficiency_result
        pcs_result = convergence_result.pcs_result
        bat_result = convergence_result.battery_result
    else:
        bat_inp = BatterySizingInput(
            required_power_poi_mw=required_power_poi,
            required_energy_poi_mwh=float(body.get('required_energy_mwh', 0)),
            total_bat_poi_eff=eff_result.total_bat_poi_eff,
            total_battery_loss_factor=eff_result.total_battery_loss_factor,
            total_dc_to_aux_eff=eff_result.total_dc_to_aux_eff,
            product_type=str(body.get('product_type', '')),
            pcs_unit_power_mw=pcs_result.pcs_unit_power_mw,
            links_per_pcs=pcs_result.links_per_pcs,
            aux_power_source=str(body.get('aux_power_source', 'Battery')),
            link_override=int(body.get('link_override', 0) or 0),
        )
        bat_result = calculate_battery_sizing(bat_inp)

    # --- Retention ---
    aug_waves_raw = body.get('augmentation_waves', [])
    aug_waves = [
        AugmentationWave(
            year=int(w['year']),
            additional_links=int(w.get('additional_links', 0)),
            additional_energy_mwh=float(w.get('additional_energy_mwh', 0)),
            product_type=str(w.get('product_type', body.get('product_type', ''))),
        )
        for w in aug_waves_raw
    ]
    # Compute energy from links × nameplate when energy is not provided
    nameplate_per_link = bat_result.nameplate_energy_per_link_mwh
    for wave in aug_waves:
        if wave.additional_energy_mwh <= 0 and wave.additional_links > 0:
            wave.additional_energy_mwh = wave.additional_links * nameplate_per_link

    # Intermediate efficiency: DC → MV (dc_cabling * pcs * lv_cabling * mv_transformer * mv_ac_cabling)
    bat_to_mv_eff = (sys_inp.dc_cabling * sys_inp.pcs_efficiency *
                     sys_inp.lv_cabling * sys_inp.mv_transformer * sys_inp.mv_ac_cabling)
    # MV → POI (hv_ac_cabling * hv_transformer)
    mv_to_poi_eff = sys_inp.hv_ac_cabling * sys_inp.hv_transformer

    def _build_ret_inp(b_result):
        return RetentionInput(
            cp_rate=b_result.cp_rate,
            product_type=str(body.get('product_type', '')),
            project_life_yr=int(body.get('project_life_yr', 20)),
            rest_soc=str(body.get('rest_soc', 'Mid')),
            installation_energy_dc_mwh=b_result.installation_energy_dc_mwh,
            total_bat_poi_eff=eff_result.total_bat_poi_eff,
            total_battery_loss_factor=eff_result.total_battery_loss_factor,
            total_dc_to_aux_eff=eff_result.total_dc_to_aux_eff,
            bat_to_mv_eff=bat_to_mv_eff,
            mv_to_poi_eff=mv_to_poi_eff,
            aux_power_per_link_mw=b_result.aux_power_peak_mw / b_result.no_of_links if b_result.no_of_links > 0 else 0,
            no_of_links=b_result.no_of_links,
            duration_hr=b_result.duration_bol_hr,
        )

    def _recalc_bat(override_links):
        """Re-run battery sizing with a specific link override."""
        inp = BatterySizingInput(
            required_power_poi_mw=required_power_poi,
            required_energy_poi_mwh=float(body.get('required_energy_mwh', 0)),
            total_bat_poi_eff=eff_result.total_bat_poi_eff,
            total_battery_loss_factor=eff_result.total_battery_loss_factor,
            total_dc_to_aux_eff=eff_result.total_dc_to_aux_eff,
            product_type=str(body.get('product_type', '')),
            pcs_unit_power_mw=pcs_result.pcs_unit_power_mw,
            links_per_pcs=pcs_result.links_per_pcs,
            aux_power_source=str(body.get('aux_power_source', 'Battery')),
            link_override=override_links,
        )
        return calculate_battery_sizing(inp)

    def _poi_at_year(b_result, year):
        """Get Disch.@POI at a specific year from BASE retention only.

        Oversizing optimization must use base retention (no augmentation)
        so that initial link count is independent of augmentation waves.
        Augmentation is applied separately after initial sizing is finalized.
        """
        r_inp = _build_ret_inp(b_result)
        r_result = calculate_retention(r_inp)
        by_year = r_result.retention_by_year
        if year in by_year:
            return by_year[year].dischargeable_energy_poi_mwh
        return 0.0

    # --- Oversizing Optimization ---
    oversizing_year = int(body.get('oversizing_year', 0) or 0)
    required_energy_mwh = float(body.get('required_energy_mwh', 0))
    link_step = pcs_result.links_per_pcs  # minimum increment (e.g. 2 for 2-link PCS)
    user_link_override = int(body.get('link_override', 0) or 0)

    if oversizing_year > 0 and required_energy_mwh > 0 and user_link_override <= 0:
        # Check POI at oversizing year with current sizing
        poi_val = _poi_at_year(bat_result, oversizing_year)
        max_iterations = 50  # safety limit

        if poi_val < required_energy_mwh:
            # --- Upward search: increase links until target met ---
            current_links = bat_result.no_of_links
            for _ in range(max_iterations):
                current_links += link_step
                bat_result = _recalc_bat(current_links)
                poi_val = _poi_at_year(bat_result, oversizing_year)
                if poi_val >= required_energy_mwh:
                    break
        elif poi_val >= required_energy_mwh:
            # --- Downward search: check if we can reduce links ---
            # Minimum capacity = 1 PCS worth at POI
            min_capacity_poi = link_step * nameplate_per_link * (
                eff_result.total_battery_loss_factor * bat_to_mv_eff * mv_to_poi_eff
            )
            excess = poi_val - required_energy_mwh
            if excess > min_capacity_poi:
                current_links = bat_result.no_of_links
                for _ in range(max_iterations):
                    trial_links = current_links - link_step
                    if trial_links < link_step:
                        break
                    trial_bat = _recalc_bat(trial_links)
                    trial_poi = _poi_at_year(trial_bat, oversizing_year)
                    if trial_poi >= required_energy_mwh:
                        # Still meets target — adopt reduction
                        current_links = trial_links
                        bat_result = trial_bat
                    else:
                        break  # Can't reduce further

    ret_inp = _build_ret_inp(bat_result)
    ret_result = calculate_with_augmentation(ret_inp, aug_waves)

    # Compute base retention (no augmentation) for comparison when augmentation active
    base_ret_by_year = None
    if aug_waves:
        base_ret_result = calculate_retention(ret_inp)
        base_ret_by_year = {
            str(yr): dataclasses.asdict(ry)
            for yr, ry in base_ret_result.retention_by_year.items()
        }

    # --- Reactive Power ---
    reactive_result = None
    if _HAS_REACTIVE_POWER:
        rp_inp = ReactivePowerInput(
            required_power_poi_mw=required_power_poi,
            power_factor=float(body.get('power_factor', 0.95)),
            no_of_pcs=bat_result.no_of_pcs,
            pcs_unit_kva=pcs_result.derated_power_kva,
            hv_transformer_eff=sys_inp.hv_transformer,
            mv_transformer_eff=sys_inp.mv_transformer,
            lv_cabling_eff=sys_inp.lv_cabling,
            mv_ac_cabling_eff=sys_inp.mv_ac_cabling,
            pcs_efficiency=sys_inp.pcs_efficiency,
            dc_cabling_eff=sys_inp.dc_cabling,
            aux_power_peak_mw=bat_result.aux_power_peak_mw,
        )
        reactive_result = _asdict(calculate_reactive_power(rp_inp))

    # --- RTE ---
    rte_result = None
    if _HAS_RTE:
        rte_inp = RTEInput(
            total_bat_poi_eff=eff_result.total_bat_poi_eff,
            total_battery_loss_factor=eff_result.total_battery_loss_factor,
        )
        rte_result = _asdict(calculate_rte(rte_inp))

    # --- Build response ---
    ret_by_year = {
        str(yr): dataclasses.asdict(ry)
        for yr, ry in ret_result.retention_by_year.items()
    }

    return {
        'efficiency': _asdict(eff_result),
        'pcs': {
            'pcs_unit_power_mw': pcs_result.pcs_unit_power_mw,
            'no_of_pcs': bat_result.no_of_pcs,  # final (max of power/energy)
            'links_per_pcs': pcs_result.links_per_pcs,
            'derated_power_kva': pcs_result.derated_power_kva,
            'alt_factor': pcs_result.alt_factor,
            'base_power_kva': pcs_result.base_power_kva,
            'manufacturer': pcs_result.config.manufacturer,
            'model': pcs_result.config.model,
            'config_name': pcs_result.config.config_name,
            'strings_per_pcs': pcs_result.config.strings_per_pcs,
        },
        'battery': _asdict(bat_result),
        'retention': {
            'cp_rate': ret_result.cp_rate,
            'lookup_source': ret_result.lookup_source,
            'curve': ret_result.curve,
            'retention_by_year': ret_by_year,
            'base_retention_by_year': base_ret_by_year,
            'wave_details': {
                str(k): {
                    "start_year": v["start_year"],
                    "installed_energy_mwh": v["installed_energy_mwh"],
                    "links": v["links"],
                    "by_year": {str(yr): yd for yr, yd in v["by_year"].items()},
                }
                for k, v in ret_result.wave_details.items()
            } if ret_result.wave_details else None,
        },
        'reactive_power': reactive_result,
        'rte': rte_result,
        'convergence': {
            'converged': convergence_result.converged,
            'iterations': convergence_result.iterations,
            'final_delta': convergence_result.final_delta,
            'cp_rate_history': convergence_result.cp_rate_history,
            'warning': convergence_result.warning,
            'soc': _asdict(convergence_result.soc_result) if convergence_result.soc_result is not None else None,
        } if convergence_result is not None else None,
        'summary': {
            'project_title': body.get('project_title', ''),
            'required_power_mw': required_power_poi,
            'required_energy_mwh': body.get('required_energy_mwh'),
            'duration_hours': float(body.get('duration_hours', 4)),
            'aux_power_source': str(body.get('aux_power_source', 'Grid')),
            'aux_included': str(body.get('aux_power_source', 'Grid')).strip().lower() == 'battery',
            'augmentation_included': len(aug_waves_raw) > 0,
            'product_type': str(body.get('product_type', '')),
            'pcs_config_name': str(body.get('pcs_type', '')),
            'no_of_pcs': bat_result.no_of_pcs,
            'no_of_links': bat_result.no_of_links,
            'no_of_racks': bat_result.no_of_racks,
            'no_of_mvt': bat_result.no_of_mvt,
            'no_of_skid': bat_result.no_of_pcs,
            'no_of_m10_order': _calc_m10_order(pcs_result, bat_result.no_of_pcs),
            'no_of_transformer_blocks': bat_result.no_of_mvt,
            'installation_energy_dc_mwh': bat_result.installation_energy_dc_mwh,
            'dischargeable_energy_poi_mwh': bat_result.dischargeable_energy_poi_mwh,
            'duration_bol_hr': bat_result.duration_bol_hr,
            'system_rte': rte_result['system_rte'] if rte_result else None,
            'temperature_c': int(body.get('temperature_c', 25)),
            'altitude': str(body.get('altitude', '<1000')),
            'oversizing_year': oversizing_year,
            'link_step': link_step,
            'bat_to_mv_eff': bat_to_mv_eff,
            'mv_to_poi_eff': mv_to_poi_eff,
        },
    }


@bp.route('/api/calculate', methods=['POST'])
def api_calculate():
    """Run the full sizing calculation chain and return all results."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        result = _run_calculation(body)
        return jsonify(result), 200
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


# ---------------------------------------------------------------------------
# SOC range calculation
# ---------------------------------------------------------------------------

@bp.route('/api/soc', methods=['POST'])
def api_soc():
    """Calculate SOC range for a given application and product."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        inp = SOCInput(
            cp_rate=float(body['cp_rate']),
            application=str(body['application']),
            product_type=str(body['product_type']),
            measurement_method=str(body.get('measurement_method', 'Both CP')),
        )
        result = calculate_soc(inp)
        return jsonify({
            'soc_high': result.soc_high,
            'soc_low': result.soc_low,
            'soc_rest': result.soc_rest,
            'applied_dod': result.applied_dod,
            'effective_dod': result.effective_dod,
        }), 200
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


# ---------------------------------------------------------------------------
# Augmentation recommendation
# ---------------------------------------------------------------------------

@bp.route('/api/augmentation/recommend', methods=['POST'])
def api_augmentation_recommend():
    """Auto-recommend augmentation waves based on energy deficit."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        ret_inp = RetentionInput(
            cp_rate=float(body['cp_rate']),
            product_type=str(body['product_type']),
            project_life_yr=int(body['project_life_yr']),
            installation_energy_dc_mwh=float(body['installation_energy_dc_mwh']),
            total_dc_to_aux_eff=float(body['total_dc_to_aux_eff']),
            total_bat_poi_eff=float(body.get('total_bat_poi_eff', 1.0)),
            total_battery_loss_factor=float(body.get('total_battery_loss_factor', 1.0)),
            rest_soc=str(body.get('rest_soc', 'Mid')),
            bat_to_mv_eff=float(body.get('bat_to_mv_eff', 1.0)),
            mv_to_poi_eff=float(body.get('mv_to_poi_eff', 1.0)),
            no_of_links=int(body.get('no_of_links', 0)),
            duration_hr=float(body.get('duration_hr', 0.0)),
            aux_power_per_link_mw=float(body.get('aux_power_per_link_mw', 0.0)),
        )
        recommendation = recommend_augmentation(
            base_retention_input=ret_inp,
            required_energy_poi_mwh=float(body['required_energy_poi_mwh']),
            nameplate_energy_per_link_mwh=float(body['nameplate_energy_per_link_mwh']),
            links_per_pcs=int(body.get('links_per_pcs', 2)),
            max_augmentations=int(body.get('max_augmentations', 3)),
        )
        waves_out = [
            {
                'year': w.year,
                'additional_links': w.additional_links,
                'additional_energy_mwh': w.additional_energy_mwh,
                'product_type': w.product_type,
            }
            for w in recommendation.waves
        ]
        return jsonify({
            'waves': waves_out,
            'total_additional_links': recommendation.total_additional_links,
            'total_additional_energy_mwh': recommendation.total_additional_energy_mwh,
            'trigger_years': recommendation.trigger_years,
        }), 200
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


# ---------------------------------------------------------------------------
# Partial recalculation endpoints
# ---------------------------------------------------------------------------

@bp.route('/api/retention', methods=['POST'])
def api_retention():
    """Recalculate retention curve only."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        aug_waves_raw = body.get('augmentation_waves', [])
        product_type = str(body.get('product_type', ''))
        aug_waves = [
            AugmentationWave(
                year=int(w['year']),
                additional_links=int(w.get('additional_links', 0)),
                additional_energy_mwh=float(w.get('additional_energy_mwh', 0)),
                product_type=str(w.get('product_type', product_type)),
            )
            for w in aug_waves_raw
        ]
        inp = RetentionInput(
            cp_rate=float(body['cp_rate']),
            product_type=product_type,
            project_life_yr=int(body.get('project_life_yr', 20)),
            rest_soc=str(body.get('rest_soc', 'Mid')),
            installation_energy_dc_mwh=float(body.get('installation_energy_dc_mwh', 0.0)),
            total_bat_poi_eff=float(body.get('total_bat_poi_eff', 1.0)),
            total_battery_loss_factor=float(body.get('total_battery_loss_factor', 1.0)),
            total_dc_to_aux_eff=float(body.get('total_dc_to_aux_eff', 1.0)),
            bat_to_mv_eff=float(body.get('bat_to_mv_eff', 1.0)),
            mv_to_poi_eff=float(body.get('mv_to_poi_eff', 1.0)),
            no_of_links=int(body.get('no_of_links', 0)),
            duration_hr=float(body.get('duration_hr', 0.0)),
            aux_power_per_link_mw=float(body.get('aux_power_per_link_mw', 0.0)),
        )
        result = calculate_with_augmentation(inp, aug_waves)
        ret_by_year = {
            str(yr): dataclasses.asdict(ry)
            for yr, ry in result.retention_by_year.items()
        }
        return jsonify({
            'cp_rate': result.cp_rate,
            'lookup_source': result.lookup_source,
            'curve': result.curve,
            'retention_by_year': ret_by_year,
        }), 200
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/reactive-power', methods=['POST'])
def api_reactive_power():
    """Calculate reactive power only."""
    if not _HAS_REACTIVE_POWER:
        return jsonify({'error': 'reactive_power module not available'}), 503

    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        inp = ReactivePowerInput(
            required_power_poi_mw=float(body['required_power_poi_mw']),
            power_factor=float(body.get('power_factor', 0.95)),
            no_of_pcs=int(body['no_of_pcs']),
            pcs_unit_kva=float(body['pcs_unit_kva']),
            hv_transformer_eff=float(body.get('hv_transformer_eff', 0.995)),
            mv_transformer_eff=float(body.get('mv_transformer_eff', 0.993)),
            lv_cabling_eff=float(body.get('lv_cabling_eff', 0.996)),
            mv_ac_cabling_eff=float(body.get('mv_ac_cabling_eff', 0.999)),
            pcs_efficiency=float(body.get('pcs_efficiency', 0.985)),
            dc_cabling_eff=float(body.get('dc_cabling_eff', 0.999)),
            aux_power_peak_mw=float(body.get('aux_power_peak_mw', 0.0)),
        )
        result = calculate_reactive_power(inp)
        return jsonify(_asdict(result)), 200
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/definitions', methods=['GET'])
def api_definitions():
    """Return field definitions for tooltips."""
    import json as _json
    defs_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'definitions.json')
    try:
        with open(defs_path, 'r') as f:
            data = _json.load(f)
        data.pop('_meta', None)
        return jsonify(data), 200
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@bp.route('/api/rte', methods=['POST'])
def api_rte():
    """Calculate RTE only."""
    if not _HAS_RTE:
        return jsonify({'error': 'rte module not available'}), 503

    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        inp = RTEInput(
            total_bat_poi_eff=float(body['total_bat_poi_eff']),
            total_battery_loss_factor=float(body['total_battery_loss_factor']),
            battery_dc_rte=float(body.get('battery_dc_rte', 0.95)),
        )
        result = calculate_rte(inp)
        return jsonify(_asdict(result)), 200
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


# ---------------------------------------------------------------------------
# Product catalogue endpoints
# ---------------------------------------------------------------------------

@bp.route('/api/products', methods=['GET'])
def api_products_list():
    """Return all available product types and PCS configurations."""
    import json, os
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

    try:
        with open(os.path.join(data_dir, 'products.json')) as f:
            products = json.load(f)
        with open(os.path.join(data_dir, 'pcs_config_map.json')) as f:
            pcs_configs = json.load(f)
        with open(os.path.join(data_dir, 'aux_consumption.json')) as f:
            aux_consumption = json.load(f)

        # Format for frontend dropdowns
        battery_products = []
        for name, specs in products.items():
            battery_products.append({
                'id': name,
                'name': name,
                'specs': specs,
            })

        pcs_configurations = []
        for cfg in pcs_configs:
            entry = {
                'id': cfg['config_name'],
                'name': cfg['config_name'],
                'manufacturer': cfg.get('manufacturer', ''),
                'model': cfg.get('model', ''),
                'strings_per_pcs': cfg.get('strings_per_pcs', 0),
                'links_per_pcs': cfg.get('links_per_pcs', 0),
            }
            if cfg.get('ac_link'):
                entry['ac_link'] = True
            if cfg.get('battery'):
                entry['battery'] = cfg['battery']
            pcs_configurations.append(entry)

        return jsonify({
            'product_types': list(products.keys()),
            'pcs_configs': [c['config_name'] for c in pcs_configs],
            'battery_products': battery_products,
            'pcs_configurations': pcs_configurations,
            '_aux_consumption': aux_consumption,
        }), 200
    except FileNotFoundError as exc:
        return jsonify({'error': f'Data file not found: {exc}'}), 500


@bp.route('/api/products/<product_type>', methods=['GET'])
def api_product_detail(product_type: str):
    """Return specification for a specific product type."""
    try:
        specs = get_product_specs(product_type)
        return jsonify({'product_type': product_type, 'specs': specs}), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


# ---------------------------------------------------------------------------
# Project persistence endpoints
# ---------------------------------------------------------------------------

@bp.route('/api/projects', methods=['GET'])
def api_projects_list():
    """List all saved projects."""
    db_path = current_app.config['DATABASE']
    try:
        projects = list_projects(db_path)
        return jsonify({'projects': projects}), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/projects', methods=['POST'])
def api_projects_save():
    """Save a project (input + result data)."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    title = body.get('title') or body.get('project_title', '')
    if not title:
        return jsonify({'error': 'title is required'}), 400

    db_path = current_app.config['DATABASE']
    try:
        project_id = save_project(
            db_path,
            title,
            body.get('input_data', {}),
            body.get('result_data', {}),
        )
        return jsonify({'id': project_id, 'title': title}), 201
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/projects/<int:project_id>', methods=['GET'])
def api_project_get(project_id: int):
    """Load a saved project by id."""
    db_path = current_app.config['DATABASE']
    try:
        project = get_project(db_path, project_id)
        if project is None:
            return jsonify({'error': 'Project not found'}), 404
        return jsonify(project), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


# ---------------------------------------------------------------------------
# Project deletion
# ---------------------------------------------------------------------------

@bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
def api_project_delete(project_id: int):
    """Delete a saved project by id."""
    from .models import delete_project
    db_path = current_app.config['DATABASE']
    try:
        deleted = delete_project(db_path, project_id)
        if not deleted:
            return jsonify({'error': 'Project not found'}), 404
        return jsonify({'deleted': True, 'id': project_id}), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

@bp.route('/api/export/excel', methods=['POST'])
def api_export_excel():
    """Generate Excel report from calculation results."""
    from flask import send_file
    from .export import generate_excel_report

    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        buf = generate_excel_report(body)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='BESS_Sizing_Report.xlsx',
        )
    except Exception as exc:
        return jsonify({'error': f'Export failed: {exc}'}), 500


# ---------------------------------------------------------------------------
# Cases HTML views
# ---------------------------------------------------------------------------

@bp.route('/project/<int:project_id>/cases')
def project_cases(project_id):
    """Render the cases management page for a project."""
    return render_template('cases.html', project_id=project_id)


@bp.route('/project/<int:project_id>/compare')
def project_compare(project_id):
    """Render the comparison page for a project."""
    return render_template('compare.html', project_id=project_id)


# ---------------------------------------------------------------------------
# Cases API
# ---------------------------------------------------------------------------

@bp.route('/api/projects/<int:project_id>/cases', methods=['GET'])
def api_cases_list(project_id: int):
    """List all cases for a project."""
    db_path = current_app.config['DATABASE']
    try:
        cases = list_cases(db_path, project_id)
        # Attach result_summary for case cards
        for c in cases:
            full = get_case(db_path, c['id'])
            inp = full.get('input_data', {}) if full else {}
            rd = full.get('result_data') if full else None
            summary_obj = rd.get('summary', {}) if rd else {}
            bat = rd.get('battery', {}) if rd else {}
            # Oversizing year = first augmentation wave year, or project_life
            aug_waves = inp.get('augmentation_waves') or inp.get('augmentation', [])
            oversizing_year = aug_waves[0]['year'] if aug_waves else inp.get('project_life')
            has_calc = bool(bat and bat.get('no_of_pcs') is not None)
            if c.get('has_result') and not has_calc:
                c['has_result'] = 0
            c['result_summary'] = {
                'battery_product_type': inp.get('battery_product_type'),
                'pcs_product': _resolve_pcs_product(inp.get('pcs_configuration')),
                'required_power_mw': summary_obj.get('required_power_mw') or inp.get('required_power_mw'),
                'installation_energy_dc_mwh': round(bat.get('installation_energy_dc_mwh', 0), 2) if bat.get('installation_energy_dc_mwh') else inp.get('required_energy_mwh'),
                'power_factor': inp.get('power_factor', 0.95),
                'oversizing_year': oversizing_year,
                'no_of_pcs': summary_obj.get('no_of_pcs') or bat.get('no_of_pcs'),
                'no_of_links': summary_obj.get('no_of_links') or bat.get('no_of_links'),
                'has_calc': has_calc,
            }
        return jsonify({'cases': cases}), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/projects/<int:project_id>/cases', methods=['POST'])
def api_cases_create(project_id: int):
    """Create a new case for a project."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    case_name = body.get('case_name', '')
    if not case_name:
        return jsonify({'error': 'case_name is required'}), 400

    db_path = current_app.config['DATABASE']
    try:
        # Enforce max 10 cases per project
        existing = list_cases(db_path, project_id)
        if len(existing) >= 10:
            return jsonify({'error': 'Maximum 10 cases per project reached'}), 400

        case_id = create_case(
            db_path,
            project_id,
            case_name,
            body.get('input_data', {}),
            body.get('case_memo', ''),
        )
        return jsonify({'id': case_id, 'case_name': case_name}), 201
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/cases/<int:case_id>', methods=['GET'])
def api_case_get(case_id: int):
    """Get a single case with full data."""
    db_path = current_app.config['DATABASE']
    try:
        case = get_case(db_path, case_id)
        if case is None:
            return jsonify({'error': 'Case not found'}), 404
        return jsonify(case), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/cases/<int:case_id>', methods=['PUT'])
def api_case_update(case_id: int):
    """Update a case."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    db_path = current_app.config['DATABASE']
    try:
        updated = update_case(
            db_path,
            case_id,
            case_name=body.get('case_name'),
            case_memo=body.get('case_memo'),
            input_data=body.get('input_data'),
            result_data=body.get('result_data'),
        )
        if not updated:
            return jsonify({'error': 'Case not found'}), 404
        return jsonify({'updated': True, 'id': case_id}), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/cases/<int:case_id>', methods=['DELETE'])
def api_case_delete(case_id: int):
    """Delete a case."""
    db_path = current_app.config['DATABASE']
    try:
        deleted = delete_case(db_path, case_id)
        if not deleted:
            return jsonify({'error': 'Case not found'}), 404
        return jsonify({'deleted': True, 'id': case_id}), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/cases/<int:case_id>/clone', methods=['POST'])
def api_case_clone(case_id: int):
    """Clone a case."""
    body = request.get_json(force=True, silent=True) or {}
    db_path = current_app.config['DATABASE']
    try:
        new_id = clone_case(db_path, case_id, new_name=body.get('new_name'))
        if new_id is None:
            return jsonify({'error': 'Case not found'}), 404
        return jsonify({'id': new_id}), 201
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/cases/<int:case_id>/calculate', methods=['POST'])
def api_case_calculate(case_id: int):
    """Run the full calculation for a case and save the result back."""
    db_path = current_app.config['DATABASE']
    try:
        case = get_case(db_path, case_id)
        if case is None:
            return jsonify({'error': 'Case not found'}), 404

        input_data = case.get('input_data') or {}
        result = _run_calculation(input_data)

        update_case(db_path, case_id, result_data=result)
        return jsonify(result), 200
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/projects/<int:project_id>/compare', methods=['POST'])
def api_cases_compare(project_id: int):
    """Compare multiple cases side by side."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    case_ids = body.get('case_ids', [])
    if not case_ids:
        return jsonify({'error': 'case_ids is required'}), 400
    if len(case_ids) > 5:
        return jsonify({'error': 'Maximum 5 cases can be compared at once'}), 400

    db_path = current_app.config['DATABASE']
    try:
        cases = get_cases_for_comparison(db_path, case_ids)

        # Build side-by-side metrics from each case's result_data summary
        metric_keys = [
            'installation_energy_dc_mwh',
            'dischargeable_energy_poi_mwh',
            'no_of_pcs',
            'no_of_links',
            'no_of_racks',
            'no_of_mvt',
            'duration_bol_hr',
            'system_rte',
            'required_power_mw',
            'required_energy_mwh',
        ]
        metrics: dict = {k: {} for k in metric_keys}
        for case in cases:
            label = case.get('case_name', str(case.get('id', '')))
            result_data = case.get('result_data') or {}
            summary = result_data.get('summary') or {}
            for k in metric_keys:
                metrics[k][label] = summary.get(k)

        return jsonify({'cases': cases, 'metrics': metrics}), 200
    except Exception as exc:
        return jsonify({'error': f'Internal error: {exc}'}), 500


@bp.route('/api/projects/<int:project_id>/export/comparison', methods=['POST'])
def api_export_comparison(project_id: int):
    """Export a comparison of multiple cases as Excel."""
    from flask import send_file
    from .export import generate_comparison_excel

    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    case_ids = body.get('case_ids', [])
    if not case_ids:
        return jsonify({'error': 'case_ids is required'}), 400

    db_path = current_app.config['DATABASE']
    try:
        cases = get_cases_for_comparison(db_path, case_ids)
        buf = generate_comparison_excel(cases)
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='BESS_Case_Comparison.xlsx',
        )
    except Exception as exc:
        return jsonify({'error': f'Export failed: {exc}'}), 500


# ---------------------------------------------------------------------------
# Admin Parameter Editor
# ---------------------------------------------------------------------------

from .decorators import admin_required

_PARAM_CATEGORIES = {
    'aux_consumption': 'aux_consumption.json',
    'products': 'products.json',
    'pcs_config': 'pcs_config_map.json',
}


def _data_dir():
    return os.path.join(os.path.dirname(__file__), '..', 'data')


@bp.route('/admin/parameters')
@admin_required
def admin_parameters():
    """Render the admin parameter editor page."""
    return render_template('admin_params.html')


@bp.route('/api/admin/params/<category>', methods=['GET'])
@admin_required
def api_admin_params_get(category: str):
    """Get current data for a parameter category."""
    filename = _PARAM_CATEGORIES.get(category)
    if not filename:
        return jsonify({'error': f'Unknown category: {category}'}), 400

    filepath = os.path.join(_data_dir(), filename)
    try:
        with open(filepath) as f:
            data = json.load(f)
        mtime = os.path.getmtime(filepath)
        return jsonify({'data': data, 'last_modified': mtime}), 200
    except FileNotFoundError:
        return jsonify({'error': f'Data file not found: {filename}'}), 404


@bp.route('/api/admin/params/<category>', methods=['PUT'])
@admin_required
def api_admin_params_update(category: str):
    """Update data for a parameter category. Writes back to JSON file."""
    filename = _PARAM_CATEGORIES.get(category)
    if not filename:
        return jsonify({'error': f'Unknown category: {category}'}), 400

    body = request.get_json(force=True, silent=True)
    if body is None or 'data' not in body:
        return jsonify({'error': 'Request must include "data" field'}), 400

    new_data = body['data']

    # Basic structure validation
    if category == 'aux_consumption':
        if not isinstance(new_data, dict):
            return jsonify({'error': 'aux_consumption must be an object'}), 400
        for key, val in new_data.items():
            if not isinstance(val, dict) or 'peak_kw' not in val or 'standby_kw' not in val:
                return jsonify({'error': f'Each product must have peak_kw and standby_kw: {key}'}), 400
    elif category == 'products':
        if not isinstance(new_data, dict):
            return jsonify({'error': 'products must be an object'}), 400
    elif category == 'pcs_config':
        if not isinstance(new_data, list):
            return jsonify({'error': 'pcs_config must be an array'}), 400
        for item in new_data:
            if not isinstance(item, dict) or 'config_name' not in item:
                return jsonify({'error': 'Each PCS config must have config_name'}), 400

    filepath = os.path.join(_data_dir(), filename)
    try:
        with open(filepath, 'w') as f:
            json.dump(new_data, f, indent=2)
        mtime = os.path.getmtime(filepath)
        return jsonify({'success': True, 'last_modified': mtime}), 200
    except Exception as exc:
        return jsonify({'error': f'Failed to write: {exc}'}), 500
