"""Integration test: Full calculation pipeline vs Excel golden test case.

Validates all Phase 1 calculator modules against
test_case_jf3_100mw_400mwh.json with ±0.1% tolerance.
"""
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.efficiency import (
    AuxEfficiencyInput, BatteryLossInput, SystemEfficiencyInput, calculate_all,
)
from backend.calculators.pcs_sizing import PCSSizingInput, calculate_pcs_sizing
from backend.calculators.battery_sizing import BatterySizingInput, calculate_battery_sizing
from backend.calculators.retention import RetentionInput, calculate_retention

TOLERANCE = 0.001  # ±0.1%


def _assert_close(label, actual, expected, tol=TOLERANCE):
    if expected == 0:
        assert actual == 0, f"{label}: expected 0 but got {actual}"
        return
    rel_err = abs(actual - expected) / abs(expected)
    status = "PASS" if rel_err <= tol else "FAIL"
    print(f"  [{status}] {label}: actual={actual:.6f}  expected={expected:.6f}  err={rel_err:.2e}")
    assert rel_err <= tol, f"{label}: {actual} vs {expected} ({rel_err:.4%} > {tol:.4%})"


def _assert_exact(label, actual, expected):
    status = "PASS" if actual == expected else "FAIL"
    print(f"  [{status}] {label}: actual={actual}  expected={expected}")
    assert actual == expected, f"{label}: {actual} != {expected}"


def load_test_case():
    path = REPO_ROOT / "backend" / "data" / "test_case_jf3_100mw_400mwh.json"
    with open(path) as f:
        return json.load(f)


def test_full_pipeline():
    tc = load_test_case()
    inp = tc["input"]
    eff_inp = inp["efficiency"]
    aux_inp_data = inp["aux_efficiency"]
    bat_inp_data = inp["battery_loss"]
    expected_dt = tc["expected_design_tool"]
    expected = tc["expected_result"]

    print("\n" + "=" * 70)
    print("GOLDEN TEST: JF3 DC LINK, 100MW/400MWh @POI, 45°C, Peak Shifting")
    print("=" * 70)

    # --- Step 1: Efficiency ---
    print("\n--- Step 1: Efficiency Chain ---")
    sys_inp = SystemEfficiencyInput(
        hv_ac_cabling=eff_inp["hv_ac_cabling"],
        hv_transformer=eff_inp["hv_transformer"],
        mv_ac_cabling=eff_inp["mv_ac_cabling"],
        mv_transformer=eff_inp["mv_transformer"],
        lv_cabling=eff_inp["lv_cabling"],
        pcs_efficiency=eff_inp["pcs_efficiency"],
        dc_cabling=eff_inp["dc_cabling"],
    )
    aux_in = AuxEfficiencyInput(
        branching_point=aux_inp_data["branching_point"],
        aux_tr_lv=0.985,
        aux_line_lv=0.999,
    )
    bat_in = BatteryLossInput(
        applied_dod=bat_inp_data["applied_dod"],
        loss_factors=bat_inp_data["loss_factors"],
        mbms_consumption=bat_inp_data["mbms_consumption"],
    )
    eff_result = calculate_all(sys_inp, aux_in, bat_in)

    _assert_close("total_bat_poi_eff", eff_result.total_bat_poi_eff, eff_inp["total_bat_poi"])
    _assert_close("total_battery_loss", eff_result.total_battery_loss_factor, bat_inp_data["total_battery_loss_factor"])
    _assert_close("total_dc_to_aux", eff_result.total_dc_to_aux_eff, aux_inp_data["total_dc_to_aux_eff"])

    # --- Step 2: PCS Sizing ---
    print("\n--- Step 2: PCS Sizing ---")
    pcs_inp = PCSSizingInput(
        pcs_config_name=inp["pcs_type"],
        temperature_c=inp["temperature_c"],
        altitude=inp["altitude"],
        mv_voltage_tolerance=0.02,
    )
    # PCS sizing needs req_power_dc, but we pass a dummy here since
    # the actual PCS count is determined in battery_sizing
    pcs_result = calculate_pcs_sizing(pcs_inp, 104.345)

    _assert_close("pcs_unit_power_mw", pcs_result.pcs_unit_power_mw, expected_dt["pcs_unit_power_mw"])

    # --- Step 3: Battery Sizing ---
    print("\n--- Step 3: Battery Sizing ---")
    bat_sizing_inp = BatterySizingInput(
        required_power_poi_mw=inp["required_power_mw"],
        required_energy_poi_mwh=inp["required_energy_mwh"],
        total_bat_poi_eff=eff_result.total_bat_poi_eff,
        total_battery_loss_factor=eff_result.total_battery_loss_factor,
        total_dc_to_aux_eff=eff_result.total_dc_to_aux_eff,
        product_type=inp["product_type_a"],
        pcs_unit_power_mw=pcs_result.pcs_unit_power_mw,
        links_per_pcs=pcs_result.links_per_pcs,
        aux_power_source=inp["aux_power_source"],
    )
    bat_result = calculate_battery_sizing(bat_sizing_inp)

    _assert_close("req_power_dc", bat_result.req_power_dc_mw, expected["req_power_dc"])
    _assert_exact("no_of_pcs", bat_result.no_of_pcs, expected_dt["no_of_pcs"])
    _assert_exact("no_of_links", bat_result.no_of_links, expected["no_of_links"])
    _assert_exact("no_of_racks", bat_result.no_of_racks, expected["qty_of_racks"])
    _assert_close("installation_energy_dc", bat_result.installation_energy_dc_mwh, expected["installation_energy_dc"])
    _assert_close("cp_rate", bat_result.cp_rate, expected["cp_rate_dc"])
    _assert_close("dischargeable_energy_poi", bat_result.dischargeable_energy_poi_mwh, expected["dischargeable_energy_poi"])

    # --- Step 4: Retention ---
    print("\n--- Step 4: Retention Curve ---")
    ret_inp = RetentionInput(
        cp_rate=bat_result.cp_rate,
        product_type=inp["product_type_a"],
        project_life_yr=inp["project_life_yr"],
        installation_energy_dc_mwh=bat_result.installation_energy_dc_mwh,
        total_bat_poi_eff=eff_result.total_bat_poi_eff,
        total_battery_loss_factor=eff_result.total_battery_loss_factor,
        total_dc_to_aux_eff=eff_result.total_dc_to_aux_eff,
    )
    ret_result = calculate_retention(ret_inp)

    # Check key retention years
    expected_ret = expected["retention_by_year"]
    for year_str, exp_data in expected_ret.items():
        year = int(year_str)
        if year in ret_result.retention_by_year:
            actual_ret = ret_result.retention_by_year[year]
            _assert_close(
                f"retention Y{year}",
                actual_ret.retention_pct,
                exp_data["retention_pct"],
            )

    print("\n" + "=" * 70)
    print("ALL GOLDEN TEST ASSERTIONS PASSED")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    test_full_pipeline()
