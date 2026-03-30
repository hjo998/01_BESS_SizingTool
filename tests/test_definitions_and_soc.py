"""Tests for F4 (definitions API) and F6 (average SOC calculation)."""
import json
import os
import pytest


# ---------------------------------------------------------------------------
# F4: Definitions API
# ---------------------------------------------------------------------------

def test_definitions_api_returns_all_fields():
    """GET /api/definitions returns 200 with expected fields, _meta stripped."""
    from backend.app import create_app
    app = create_app()
    with app.test_client() as c:
        r = c.get('/api/definitions')
        assert r.status_code == 200
        defs = r.get_json()
        # _meta should be stripped
        assert '_meta' not in defs
        # Spot-check key fields exist
        for key in ['required_power_mw', 'dischargeable_energy_poi_mwh',
                     'avg_soc', 'cp_rate', 'temperature_c', 'aux_line_lv']:
            assert key in defs, f'Missing definition: {key}'
            assert 'name' in defs[key]
            assert 'formula' in defs[key]


def test_definitions_json_is_valid():
    """definitions.json is valid JSON with no duplicate keys."""
    path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'definitions.json')
    with open(path, 'r') as f:
        data = json.load(f)
    # At least 40 definitions (currently 46)
    non_meta = {k: v for k, v in data.items() if k != '_meta'}
    assert len(non_meta) >= 40


# ---------------------------------------------------------------------------
# F6: Average SOC Calculation
# ---------------------------------------------------------------------------

def _calc_avg_soc(soc_min, soc_max, charge_hr, discharge_hr, rest_soc):
    """Pure Python replica of the JS calcAvgSoc formula."""
    cycle_mid = (soc_min + soc_max) / 2
    duty_hours = charge_hr + discharge_hr
    rest_hours = max(24 - duty_hours, 0)
    return (cycle_mid * duty_hours + rest_soc * rest_hours) / 24


def test_avg_soc_standard_case():
    """Standard case from design doc: 36.7%."""
    result = _calc_avg_soc(soc_min=1, soc_max=99, charge_hr=4,
                           discharge_hr=4, rest_soc=30)
    assert abs(result - 36.7) < 0.1


def test_avg_soc_full_duty():
    """Edge: 24hr duty (12hr charge + 12hr discharge) = no rest time."""
    result = _calc_avg_soc(soc_min=10, soc_max=90, charge_hr=12,
                           discharge_hr=12, rest_soc=30)
    # cycle_mid = 50, duty = 24, rest = 0 → avg = 50
    assert abs(result - 50.0) < 0.1


def test_avg_soc_over_24hr_duty():
    """Edge: duty > 24hr should clamp rest to 0, not go negative."""
    result = _calc_avg_soc(soc_min=0, soc_max=100, charge_hr=14,
                           discharge_hr=14, rest_soc=30)
    # duty = 28 > 24, rest clamped to 0 → avg = cycle_mid * 28 / 24 = 58.3
    assert result > 0  # no negative or NaN


def test_avg_soc_all_rest():
    """Edge: 0hr duty = all rest time."""
    result = _calc_avg_soc(soc_min=50, soc_max=50, charge_hr=0,
                           discharge_hr=0, rest_soc=40)
    # cycle_mid = 50, duty = 0, rest = 24 → avg = 40
    assert abs(result - 40.0) < 0.1
