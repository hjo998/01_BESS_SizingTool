"""Test battery sizing calculator."""
import json, pathlib, sys
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.battery_sizing import BatterySizingInput, calculate_battery_sizing

TOLERANCE = 0.001

def test_golden_battery_sizing():
    path = REPO_ROOT / "backend" / "data" / "test_case_jf3_100mw_400mwh.json"
    with open(path) as f:
        tc = json.load(f)
    expected = tc["expected_result"]
    expected_dt = tc["expected_design_tool"]

    inp = BatterySizingInput(
        required_power_poi_mw=100,
        required_energy_poi_mwh=400,
        total_bat_poi_eff=0.9663891993882308,
        total_battery_loss_factor=0.9771616602,
        total_dc_to_aux_eff=0.9576343795025248,
        product_type="JF3 0.25 DC LINK",
        pcs_unit_power_mw=3.15756,
        links_per_pcs=2,
        aux_power_source="Battery",
    )
    result = calculate_battery_sizing(inp)

    assert result.no_of_pcs == expected_dt["no_of_pcs"]
    assert result.no_of_links == expected["no_of_links"]
    assert result.no_of_racks == expected["qty_of_racks"]
    rel_err = abs(result.installation_energy_dc_mwh - expected["installation_energy_dc"]) / expected["installation_energy_dc"]
    assert rel_err < TOLERANCE

if __name__ == "__main__":
    test_golden_battery_sizing()
    print("All battery sizing tests passed!")
