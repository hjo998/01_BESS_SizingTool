"""BESS Sizing Tool — Flask Blueprint with all API endpoints."""
import dataclasses
import json
import math
import os

from flask import Blueprint, current_app, jsonify, render_template, request

# Core engine (extracted from this file — pure Python, no Flask)
from ..calculators.engine import run_calculation
from ..calculators.battery_sizing import get_product_specs
from ..calculators.retention import (
    AugmentationWave,
    RetentionInput,
    calculate_retention,
    calculate_with_augmentation,
    recommend_augmentation,
)
from ..calculators.soc import SOCInput, calculate_soc

try:
    from ..calculators.reactive_power import ReactivePowerInput, calculate_reactive_power
    _HAS_REACTIVE_POWER = True
except ImportError:
    _HAS_REACTIVE_POWER = False

try:
    from ..calculators.power_flow import PowerFlowInput, calculate_power_flow
    _HAS_POWER_FLOW = True
except ImportError:
    _HAS_POWER_FLOW = False

try:
    from ..calculators.rte import RTEInput, RTEResult, calculate_rte
    _HAS_RTE = True
except ImportError:
    _HAS_RTE = False

from .models import (
    get_project, list_projects, save_project,
    list_cases, get_case, create_case, update_case, delete_case, clone_case,
    get_cases_for_comparison, _resolve_pcs_product,
)

bp = Blueprint('main', __name__)


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

# ---------------------------------------------------------------------------
# Full sizing calculation (engine in calculators/engine.py)
# ---------------------------------------------------------------------------


@bp.route('/api/calculate', methods=['POST'])
def api_calculate():
    """Run the full sizing calculation chain and return all results."""
    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        result = run_calculation(body)
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


@bp.route('/api/power-flow', methods=['POST'])
def api_power_flow():
    """Run standalone power flow calculation."""
    if not _HAS_POWER_FLOW:
        return jsonify({'error': 'power_flow module not available'}), 503

    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        inp = PowerFlowInput(
            pcs_active_power_mw=float(body.get('pcs_active_power_mw', 0)),
            pcs_reactive_power_mvar=float(body.get('pcs_reactive_power_mvar', 0)),
            pcs_voltage_kv=float(body.get('pcs_voltage_kv', 0.69)),
            num_pcs=int(body['num_pcs']),
            pcs_unit_kva=float(body['pcs_unit_kva']),
            lv_r_ohm_per_km=float(body.get('lv_r_ohm_per_km', 0.012)),
            lv_x_ohm_per_km=float(body.get('lv_x_ohm_per_km', 0.018)),
            lv_length_km=float(body.get('lv_length_km', 0.005)),
            mvt_capacity_mva=float(body.get('mvt_capacity_mva', 100.0)),
            mvt_efficiency_pct=float(body.get('mvt_efficiency_pct', 98.9)),
            mvt_impedance_pct=float(body.get('mvt_impedance_pct', 6.0)),
            num_mvt=int(body.get('num_mvt', 1)),
            mv_r_ohm_per_km=float(body.get('mv_r_ohm_per_km', 0.115)),
            mv_x_ohm_per_km=float(body.get('mv_x_ohm_per_km', 0.125)),
            mv_length_km=float(body.get('mv_length_km', 2.0)),
            mv_voltage_kv=float(body.get('mv_voltage_kv', 34.5)),
            mpt_capacity_mva=float(body.get('mpt_capacity_mva', 300.0)),
            mpt_efficiency_pct=float(body.get('mpt_efficiency_pct', 99.65)),
            mpt_impedance_pct=float(body.get('mpt_impedance_pct', 14.5)),
            mpt_voltage_hv_kv=float(body.get('mpt_voltage_hv_kv', 154.0)),
            aux_power_mw=float(body.get('aux_power_mw', 0.0)),
            aux_tr_efficiency_pct=float(body.get('aux_tr_efficiency_pct', 98.5)),
            direction=str(body.get('direction', 'discharge')),
            buffer_pct=float(body.get('buffer_pct', 0.0)),
            calculation_mode=str(body.get('calculation_mode', 'bottom_up')),
            required_p_at_poi_mw=float(body.get('required_p_at_poi_mw', 0.0)),
            required_q_at_poi_mvar=float(body.get('required_q_at_poi_mvar', 0.0)),
        )
        result = calculate_power_flow(inp)
        result_dict = dataclasses.asdict(result)
        result_dict['stages'] = [dataclasses.asdict(s) for s in result.stages]
        return jsonify(result_dict), 200
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
    """Calculate RTE. Supports both new (v2) and legacy input formats."""
    if not _HAS_RTE:
        return jsonify({'error': 'rte module not available'}), 503

    body = request.get_json(force=True, silent=True)
    if body is None:
        return jsonify({'error': 'Invalid JSON body'}), 400

    try:
        # Check if new-style input (has chain_eff fields)
        if 'chain_eff_to_poi' in body:
            dc_rte_array = body.get('dc_rte_by_year', [float(body.get('battery_dc_rte', 0.94))])
            if not isinstance(dc_rte_array, list):
                dc_rte_array = [float(dc_rte_array)]

            inp = RTEInput(
                chain_eff_to_pcs=float(body.get('chain_eff_to_pcs', 0.99)),
                chain_eff_to_mv=float(body.get('chain_eff_to_mv', 0.96)),
                chain_eff_to_poi=float(body['chain_eff_to_poi']),
                dc_rte_by_year=[float(x) for x in dc_rte_array],
                t_discharge_hr=float(body.get('t_discharge_hr', 4.0)),
                t_rest_hr=float(body.get('t_rest_hr', 0.25)),
                aux_power_at_pcs_mw=float(body.get('aux_power_at_pcs_mw', 0.0)),
                aux_power_at_mv_mw=float(body.get('aux_power_at_mv_mw', 0.0)),
                aux_power_at_poi_mw=float(body.get('aux_power_at_poi_mw', 0.0)),
                p_rated_at_poi_mw=float(body.get('p_rated_at_poi_mw', 100.0)),
            )
            result = calculate_rte(inp)
            return jsonify({
                'system_rte': result.system_rte,
                'system_rte_with_aux': result.system_rte_with_aux,
                't_discharge_hr': result.t_discharge_hr,
                't_charge_hr_year0': result.t_charge_hr_year0,
                't_rest_hr': result.t_rest_hr,
                't_cycle_hr_year0': result.t_cycle_hr_year0,
                'rte_table': [dataclasses.asdict(row) for row in result.rte_table],
            }), 200
        else:
            # Legacy format: compute simple RTE from chain_eff
            eff = float(body.get('total_bat_poi_eff', 0.96))
            dc_rte = float(body.get('battery_dc_rte', 0.95))
            rte = eff ** 2 * dc_rte
            return jsonify({
                'charge_efficiency': eff,
                'discharge_efficiency': eff,
                'system_rte': rte,
                'battery_dc_rte': dc_rte,
            }), 200
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
        result = run_calculation(input_data)

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
            if not isinstance(val, dict) or ('sizing_kw' not in val and 'peak_kw' not in val):
                return jsonify({'error': f'Each product must have sizing_kw (or peak_kw): {key}'}), 400
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
