"""Golden-test validation for the efficiency calculator.

Loads test_case_jf3_100mw_400mwh.json and asserts each output is within
±0.1% of the expected values from the Excel SI Design Tool v1.6.7.
"""
import json
import pathlib
import sys

# Allow running directly: python tests/test_efficiency.py
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.efficiency import (
    AuxEfficiencyInput,
    BatteryLossInput,
    SystemEfficiencyInput,
    calculate_all,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOLERANCE = 0.001  # ±0.1 %


def _assert_close(label: str, actual: float, expected: float, tol: float = TOLERANCE) -> None:
    rel_err = abs(actual - expected) / abs(expected)
    status = "PASS" if rel_err <= tol else "FAIL"
    print(f"  [{status}] {label}: actual={actual:.10f}  expected={expected:.10f}  rel_err={rel_err:.2e}")
    assert rel_err <= tol, (
        f"{label}: {actual} differs from {expected} by {rel_err:.4%} (limit {tol:.4%})"
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_golden_jf3_100mw_400mwh() -> None:
    data_path = REPO_ROOT / "backend" / "data" / "test_case_jf3_100mw_400mwh.json"
    with open(data_path) as f:
        tc = json.load(f)

    inp = tc["input"]
    eff = inp["efficiency"]
    aux = inp["aux_efficiency"]
    bat = inp["battery_loss"]

    sys_inp = SystemEfficiencyInput(
        hv_ac_cabling=eff["hv_ac_cabling"],
        hv_transformer=eff["hv_transformer"],
        mv_ac_cabling=eff["mv_ac_cabling"],
        mv_transformer=eff["mv_transformer"],
        lv_cabling=eff["lv_cabling"],
        pcs_efficiency=eff["pcs_efficiency"],
        dc_cabling=eff["dc_cabling"],
    )

    aux_inp = AuxEfficiencyInput(
        branching_point=aux["branching_point"],
        aux_tr_lv=0.985,   # MV-branch default (not stored in JSON)
        aux_line_lv=0.999, # default
    )

    bat_inp = BatteryLossInput(
        applied_dod=bat["applied_dod"],
        loss_factors=bat["loss_factors"],
        mbms_consumption=bat["mbms_consumption"],
    )

    result = calculate_all(sys_inp, aux_inp, bat_inp)

    print("\nGolden-test: JF3 100 MW / 400 MWh")
    _assert_close("total_bat_poi_eff",         result.total_bat_poi_eff,         eff["total_bat_poi"])
    _assert_close("total_aux_eff",             result.total_aux_eff,             aux["total_aux_eff_mv"])
    _assert_close("total_dc_to_aux_eff",       result.total_dc_to_aux_eff,       aux["total_dc_to_aux_eff"])
    _assert_close("total_battery_loss_factor", result.total_battery_loss_factor, bat["total_battery_loss_factor"])
    _assert_close("total_efficiency",          result.total_efficiency,          inp["total_efficiency_up_to_poi"])
    print("  All assertions passed.\n")


if __name__ == "__main__":
    test_golden_jf3_100mw_400mwh()
