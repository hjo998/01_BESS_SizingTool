"""BESS Sizing Tool — Core Calculation Engine

Pure Python entry point for the full sizing calculation chain.
No Flask dependencies — can be called directly or via the API.
"""
import dataclasses
import json
import math
import os

from .efficiency import (
    AuxEfficiencyInput,
    BatteryLossInput,
    SystemEfficiencyInput,
    calculate_all as calc_efficiency,
)
from .pcs_sizing import PCSSizingInput, calculate_pcs_sizing
from .battery_sizing import BatterySizingInput, calculate_battery_sizing, get_product_specs
from .retention import (
    AugmentationWave,
    AugmentationRecommendation,
    RetentionInput,
    calculate_retention,
    calculate_with_augmentation,
    recommend_augmentation,
)
from .soc import SOCInput, calculate_soc

try:
    from .convergence import ConvergenceInput, solve as convergence_solve
    from .efficiency import BatteryLossInput as _BatteryLossInput
    _HAS_CONVERGENCE = True
except ImportError:
    _HAS_CONVERGENCE = False

try:
    from .reactive_power import ReactivePowerInput, calculate_reactive_power
    _HAS_REACTIVE_POWER = True
except ImportError:
    _HAS_REACTIVE_POWER = False

try:
    from .power_flow import PowerFlowInput, calculate_power_flow
    _HAS_POWER_FLOW = True
except ImportError:
    _HAS_POWER_FLOW = False

try:
    from .rte import RTEInput, RTEResult, calculate_rte
    _HAS_RTE = True
except ImportError:
    _HAS_RTE = False


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


def run_calculation(body: dict) -> dict:
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

    # --- Power Flow (impedance-based, replaces reactive_power for detailed analysis) ---
    power_flow_result = None
    if _HAS_POWER_FLOW:
        # Get PCS per-unit active power from battery sizing
        # Total P at PCS = required_power_poi / system_efficiency (approximate)
        # But for top-down, we specify the POI requirement directly
        pf_inp = PowerFlowInput(
            pcs_active_power_mw=0,  # ignored in top_down
            pcs_reactive_power_mvar=0,
            pcs_voltage_kv=float(body.get('pf_pcs_voltage_kv', 0.69)),
            num_pcs=bat_result.no_of_pcs,
            pcs_unit_kva=pcs_result.derated_power_kva,
            # LV
            lv_r_ohm_per_km=float(body.get('pf_lv_r_ohm_per_km', 0.012)),
            lv_x_ohm_per_km=float(body.get('pf_lv_x_ohm_per_km', 0.018)),
            lv_length_km=float(body.get('pf_lv_length_km', 0.005)),
            # MVT
            mvt_capacity_mva=float(body.get('pf_mvt_capacity_mva', 100.0)),
            mvt_efficiency_pct=float(body.get('pf_mvt_efficiency_pct', 98.9)),
            mvt_impedance_pct=float(body.get('pf_mvt_impedance_pct', 6.0)),
            num_mvt=int(bat_result.no_of_mvt) if hasattr(bat_result, 'no_of_mvt') else 1,
            # MV Line
            mv_r_ohm_per_km=float(body.get('pf_mv_r_ohm_per_km', 0.115)),
            mv_x_ohm_per_km=float(body.get('pf_mv_x_ohm_per_km', 0.125)),
            mv_length_km=float(body.get('pf_mv_length_km', 2.0)),
            mv_voltage_kv=float(body.get('pf_mv_voltage_kv', 34.5)),
            # MPT
            mpt_capacity_mva=float(body.get('pf_mpt_capacity_mva', 300.0)),
            mpt_efficiency_pct=float(body.get('pf_mpt_efficiency_pct', 99.65)),
            mpt_impedance_pct=float(body.get('pf_mpt_impedance_pct', 14.5)),
            mpt_voltage_hv_kv=float(body.get('pf_mpt_voltage_hv_kv', 154.0)),
            # Aux
            aux_power_mw=bat_result.aux_power_peak_mw,
            aux_tr_efficiency_pct=float(body.get('pf_aux_tr_eff_pct', 98.5)),
            # Mode: top_down from POI requirements
            direction='discharge',
            buffer_pct=float(body.get('rp_buffer_pct', 0.0)),
            calculation_mode='top_down',
            required_p_at_poi_mw=required_power_poi,
            required_q_at_poi_mvar=required_power_poi * math.tan(math.acos(
                min(max(float(body.get('power_factor', 0.95)), 0.01), 1.0)
            )),
        )
        pf_result = calculate_power_flow(pf_inp)
        power_flow_result = dataclasses.asdict(pf_result)
        # Convert stages list of dataclass instances
        power_flow_result['stages'] = [dataclasses.asdict(s) for s in pf_result.stages]

    # --- RTE (v2: 4 reference points + yearly table) ---
    rte_result = None
    if _HAS_RTE and _HAS_POWER_FLOW and power_flow_result is not None:
        # Build dc_rte_by_year: accept array from body, or default linear degradation
        dc_rte_array = body.get('dc_rte_by_year', None)
        if not dc_rte_array:
            # Default: start at 0.94, degrade 0.002/year for 20 years
            dc_rte_start = float(body.get('battery_dc_rte', 0.94))
            dc_rte_decay = float(body.get('dc_rte_annual_decay', 0.002))
            project_years = int(body.get('project_lifetime_years', 20))
            dc_rte_array = [
                max(dc_rte_start - dc_rte_decay * y, 0.5)
                for y in range(project_years + 1)
            ]

        # RTE uses PURE chain efficiency (without aux deduction) from efficiency.py.
        # power_flow's chain_eff already has aux subtracted — don't use it for RTE.
        # Aux is handled separately in the MV-centric energy balance inside rte.py.
        eff_chain = eff_result.total_bat_poi_eff  # pure 7-stage product
        # Segment efficiencies for DC→MV and MV→POI
        _dc_to_mv = (sys_inp.dc_cabling * sys_inp.pcs_efficiency *
                      sys_inp.lv_cabling * sys_inp.mv_transformer *
                      sys_inp.mv_ac_cabling)
        _mv_to_poi = sys_inp.hv_transformer * sys_inp.hv_ac_cabling
        _dc_to_pcs = sys_inp.dc_cabling * sys_inp.pcs_efficiency

        rte_inp = RTEInput(
            chain_eff_to_pcs=_dc_to_pcs,
            chain_eff_to_mv=_dc_to_mv,
            chain_eff_to_poi=eff_chain,
            dc_rte_by_year=[float(x) for x in dc_rte_array],
            t_discharge_hr=float(body.get('duration_hours', 4)),
            t_rest_hr=float(body.get('rte_rest_hours', 0.25)),
            aux_power_at_pcs_mw=0.0,
            aux_power_at_mv_mw=pf_result.aux_power_at_mv_mw,
            aux_power_at_poi_mw=0.0,  # aux only at MV, not duplicated
            p_rated_at_poi_mw=required_power_poi,
        )
        rte_calc = calculate_rte(rte_inp)
        rte_result = {
            'system_rte': rte_calc.system_rte,
            'system_rte_with_aux': rte_calc.system_rte_with_aux,
            't_discharge_hr': rte_calc.t_discharge_hr,
            't_charge_hr_year0': rte_calc.t_charge_hr_year0,
            't_rest_hr': rte_calc.t_rest_hr,
            't_cycle_hr_year0': rte_calc.t_cycle_hr_year0,
            'rte_table': [dataclasses.asdict(row) for row in rte_calc.rte_table],
        }
    elif _HAS_RTE:
        # Fallback: old-style RTE if power_flow not available
        # Can't use old RTEInput since it was rewritten -- skip gracefully
        rte_result = None

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
        'power_flow': power_flow_result,
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
            'required_epc_m10_qty': _calc_m10_order(pcs_result, bat_result.no_of_pcs),
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
