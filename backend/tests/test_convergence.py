"""Tests for iterative convergence solver (backend/calculators/convergence.py)."""
import pathlib
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.efficiency import (
    SystemEfficiencyInput,
    AuxEfficiencyInput,
    BatteryLossInput,
)
from backend.calculators.convergence import (
    ConvergenceConfig,
    ConvergenceInput,
    ConvergenceResult,
    calculate_without_convergence,
    iterative_sizing_with_soc,
    solve,
)


# ---------------------------------------------------------------------------
# Shared fixture-like helper
# ---------------------------------------------------------------------------

def _make_convergence_input(application: str = "") -> ConvergenceInput:
    """Return a realistic ConvergenceInput for JF3 100 MW / 400 MWh."""
    return ConvergenceInput(
        required_power_poi_mw=100.0,
        required_energy_poi_mwh=400.0,
        project_life_yr=20,
        application=application,
        system_efficiency=SystemEfficiencyInput(
            hv_ac_cabling=0.999,
            hv_transformer=0.995,
            mv_ac_cabling=0.999,
            mv_transformer=0.993,
            lv_cabling=0.996,
            pcs_efficiency=0.985,
            dc_cabling=0.999,
        ),
        aux_efficiency=AuxEfficiencyInput(
            branching_point="MV",
            aux_tr_lv=0.985,
            aux_line_lv=0.999,
        ),
        base_battery_loss=BatteryLossInput(
            applied_dod=0.9,
            loss_factors=0.98802,
            mbms_consumption=0.999,
        ),
        pcs_config_name="EPC Power M 6stc + JF3 5.5 x 2sets",
        temperature_c=25,
        altitude="<1000",
        mv_voltage_tolerance=0.02,
        product_type="JF3 0.25 DC LINK",
        aux_power_source="Battery",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_pass_no_application():
    """Empty application → single-pass: converged=True, iterations=1, soc_result=None."""
    inp = _make_convergence_input(application="")
    result = calculate_without_convergence(inp)

    assert isinstance(result, ConvergenceResult)
    assert result.converged is True
    assert result.iterations == 1
    assert result.soc_result is None
    # Sub-results should be populated
    assert result.efficiency_result is not None
    assert result.pcs_result is not None
    assert result.battery_result is not None


def test_iterative_convergence():
    """Peak Shifting application → iterative solver converges within 10 iterations."""
    inp = _make_convergence_input(application="Peak Shifting")
    result = iterative_sizing_with_soc(inp)

    assert isinstance(result, ConvergenceResult)
    assert result.converged is True
    assert result.iterations <= 10
    # SOC result should be populated when soc.py is available
    assert result.soc_result is not None
    # Battery result should have a sensible CP rate
    assert result.battery_result.cp_rate > 0


def test_convergence_config_respected():
    """Custom ConvergenceConfig with max_iterations=2 → at most 2 iterations recorded."""
    inp = _make_convergence_input(application="Peak Shifting")
    inp.config = ConvergenceConfig(max_iterations=2)
    result = iterative_sizing_with_soc(inp)

    assert result.iterations <= 2
    # Whether it converged or not, history length must not exceed max_iterations
    assert len(result.cp_rate_history) <= 2


def test_solve_routes_correctly():
    """solve() dispatches to single-pass when application is empty, iterative otherwise."""
    # Single-pass route
    inp_empty = _make_convergence_input(application="")
    result_empty = solve(inp_empty)
    assert result_empty.iterations == 1
    assert result_empty.soc_result is None

    # Iterative route
    inp_ps = _make_convergence_input(application="Peak Shifting")
    result_ps = solve(inp_ps)
    assert result_ps.iterations >= 1
    assert result_ps.soc_result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
