"""Test Flask API endpoints."""
import json, pathlib, sys
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import create_app

def get_client():
    app = create_app()
    return app.test_client()

def test_products_endpoint():
    client = get_client()
    resp = client.get('/api/products')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data['product_types']) >= 3
    assert len(data['pcs_configs']) >= 7

def test_calculate_golden():
    client = get_client()
    path = REPO_ROOT / "backend" / "data" / "test_case_jf3_100mw_400mwh.json"
    with open(path) as f:
        tc = json.load(f)
    inp = tc["input"]
    payload = {
        'required_power_mw': inp['required_power_mw'],
        'required_energy_mwh': inp['required_energy_mwh'],
        'product_type': inp['product_type_a'],
        'pcs_type': inp['pcs_type'],
        'temperature_c': inp['temperature_c'],
        'altitude': inp['altitude'],
        'project_life_yr': inp['project_life_yr'],
        'aux_power_source': inp['aux_power_source'],
        'efficiency': {k: v for k, v in inp['efficiency'].items() if k != 'total_bat_poi'},
        'aux_efficiency': {'branching_point': inp['aux_efficiency']['branching_point']},
        'battery_loss': {
            'applied_dod': inp['battery_loss']['applied_dod'],
            'loss_factors': inp['battery_loss']['loss_factors'],
            'mbms_consumption': inp['battery_loss']['mbms_consumption'],
        }
    }
    resp = client.post('/api/calculate', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['battery']['no_of_pcs'] == tc['expected_design_tool']['no_of_pcs']

def test_project_crud():
    client = get_client()
    # Create
    resp = client.post('/api/projects', data=json.dumps({
        'title': 'Test CRUD', 'input_data': {'x': 1}, 'result_data': {'y': 2}
    }), content_type='application/json')
    assert resp.status_code == 201
    pid = json.loads(resp.data)['id']
    # Read
    resp = client.get(f'/api/projects/{pid}')
    assert resp.status_code == 200
    # Delete
    resp = client.delete(f'/api/projects/{pid}')
    assert resp.status_code == 200
    # Verify deleted
    resp = client.get(f'/api/projects/{pid}')
    assert resp.status_code == 404

def test_invalid_json():
    client = get_client()
    resp = client.post('/api/calculate', data='not json', content_type='text/plain')
    assert resp.status_code == 400

if __name__ == "__main__":
    test_products_endpoint()
    test_calculate_golden()
    test_project_crud()
    test_invalid_json()
    print("All API tests passed!")
