"""Tests for power_flow calculator."""
import math
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.power_flow import PowerFlowInput, PowerFlowResult, calculate_power_flow


class TestBottomUp:
    """Bottom-up (PCS -> POI) calculation tests."""

    def test_basic_discharge(self):
        """Single PCS, no aux, discharge."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=10.0,
            pcs_reactive_power_mvar=3.0,
            pcs_voltage_kv=0.69,
            num_pcs=1,
            pcs_unit_kva=12000,
            num_mvt=1,
            direction='discharge',
        ))
        assert r.p_at_pcs == 10.0
        assert r.q_at_pcs == 3.0
        assert r.p_at_poi < 10.0  # losses reduce P
        assert r.p_at_poi > 9.0   # but not too much
        assert len(r.stages) == 8
        assert r.calculation_mode == 'bottom_up'

    def test_multi_pcs_multi_mvt(self):
        """20 PCS, 4 MVT system."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=5.0,
            pcs_reactive_power_mvar=1.5,
            pcs_voltage_kv=0.69,
            num_pcs=20,
            pcs_unit_kva=6000,
            num_mvt=4,
            mvt_capacity_mva=30.0,
            mpt_capacity_mva=120.0,
            direction='discharge',
        ))
        assert abs(r.p_at_pcs - 100.0) < 0.001
        assert abs(r.q_at_pcs - 30.0) < 0.001
        assert r.p_at_poi < 100.0
        assert r.system_efficiency_pct < 100.0

    def test_aux_reduces_poi_power(self):
        """Aux power should reduce P at POI in discharge."""
        common = dict(
            pcs_active_power_mw=5.0, pcs_reactive_power_mvar=1.0,
            pcs_voltage_kv=0.69, num_pcs=10, pcs_unit_kva=6000,
            num_mvt=2, mvt_capacity_mva=30.0, mpt_capacity_mva=60.0,
            direction='discharge',
        )
        r_no_aux = calculate_power_flow(PowerFlowInput(**common, aux_power_mw=0.0))
        r_aux = calculate_power_flow(PowerFlowInput(**common, aux_power_mw=2.0))
        assert r_aux.p_at_poi < r_no_aux.p_at_poi
        # aux_at_mv = aux_power / aux_tr_eff => greater than raw aux_power
        assert r_aux.aux_power_at_mv_mw > 2.0

    def test_charge_vs_discharge_symmetry_no_aux(self):
        """With aux=0, charge and discharge give same P at POI."""
        common = dict(
            pcs_active_power_mw=5.0, pcs_reactive_power_mvar=1.0,
            pcs_voltage_kv=0.69, num_pcs=10, pcs_unit_kva=6000,
            num_mvt=2, mvt_capacity_mva=30.0, mpt_capacity_mva=60.0,
            aux_power_mw=0.0,
        )
        r_d = calculate_power_flow(PowerFlowInput(**common, direction='discharge'))
        r_c = calculate_power_flow(PowerFlowInput(**common, direction='charge'))
        assert abs(r_d.p_at_poi - r_c.p_at_poi) < 1e-9

    def test_zero_losses(self):
        """With zero impedance and 100% efficiency, P at POI = P at PCS."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=10.0, pcs_reactive_power_mvar=0.0,
            pcs_voltage_kv=0.69, num_pcs=1, pcs_unit_kva=12000,
            num_mvt=1,
            lv_length_km=0.0, mv_length_km=0.0,
            mvt_efficiency_pct=100.0, mpt_efficiency_pct=100.0,
            mvt_impedance_pct=0.0, mpt_impedance_pct=0.0,
        ))
        assert abs(r.p_at_poi - 10.0) < 1e-6

    def test_capacity_ratio(self):
        """Capacity ratio = available / required x 100."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=5.0, pcs_reactive_power_mvar=1.5,
            pcs_voltage_kv=0.69, num_pcs=20, pcs_unit_kva=6000,
            num_mvt=4, buffer_pct=5.0,
        ))
        # available = 20 * 6000 / 1000 = 120 MVA
        expected_ratio = 120.0 / r.s_at_pcs * 100
        assert abs(r.capacity_ratio_pct - expected_ratio) < 0.1
        # With 5% buffer: sufficient if ratio >= 105%
        assert r.is_pcs_sufficient == (r.capacity_ratio_pct >= 105.0)

    def test_stage_names(self):
        """Verify all 8 stages are present with the expected names."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=5.0, pcs_reactive_power_mvar=1.0,
            pcs_voltage_kv=0.69, num_pcs=4, pcs_unit_kva=6000,
            num_mvt=1,
        ))
        expected_names = [
            "PCS_OUTPUT", "LV_LINE", "MVT", "MV_BUS",
            "AUX_BRANCH", "MV_LINE", "MPT", "POI",
        ]
        actual_names = [s.name for s in r.stages]
        assert actual_names == expected_names

    def test_pf_in_valid_range(self):
        """Power factor should be in (0, 1] at all stages."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=5.0, pcs_reactive_power_mvar=2.0,
            pcs_voltage_kv=0.69, num_pcs=10, pcs_unit_kva=6000,
            num_mvt=2, mvt_capacity_mva=30.0, mpt_capacity_mva=60.0,
        ))
        for stage in r.stages:
            assert 0.0 <= stage.pf <= 1.0, f"PF out of range at {stage.name}: {stage.pf}"

    def test_losses_are_positive(self):
        """P losses at physical stages (LV, MVT, MV, MPT) should be non-negative."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=5.0, pcs_reactive_power_mvar=1.0,
            pcs_voltage_kv=0.69, num_pcs=10, pcs_unit_kva=6000,
            num_mvt=2, mvt_capacity_mva=30.0, mpt_capacity_mva=60.0,
        ))
        for stage in r.stages:
            if stage.name in ("LV_LINE", "MVT", "MV_LINE", "MPT"):
                assert stage.p_loss_mw >= 0, f"Negative P loss at {stage.name}"
                assert stage.q_loss_mvar >= 0, f"Negative Q loss at {stage.name}"

    def test_uneven_pcs_distribution(self):
        """PCS count not evenly divisible by MVT count."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=5.0, pcs_reactive_power_mvar=1.0,
            pcs_voltage_kv=0.69, num_pcs=7, pcs_unit_kva=6000,
            num_mvt=3, mvt_capacity_mva=30.0, mpt_capacity_mva=120.0,
        ))
        assert abs(r.p_at_pcs - 35.0) < 0.001  # 7 * 5.0
        assert r.p_at_poi < 35.0
        assert r.p_at_poi > 0


class TestTopDown:
    """Top-down (POI -> PCS) calculation tests."""

    def test_basic_top_down(self):
        """Top-down should converge to target P at POI."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=0, pcs_reactive_power_mvar=0,
            pcs_voltage_kv=0.69, num_pcs=20, pcs_unit_kva=6000,
            num_mvt=4, mvt_capacity_mva=30.0, mpt_capacity_mva=120.0,
            calculation_mode='top_down',
            required_p_at_poi_mw=100.0,
            required_q_at_poi_mvar=15.0,
        ))
        assert abs(r.p_at_poi - 100.0) < 0.001
        assert abs(r.q_at_poi - 15.0) < 0.001
        assert r.calculation_mode == 'top_down'
        assert r.required_pcs_p_per_unit_mw > 0

    def test_round_trip_consistency(self):
        """Bottom-up -> get POI -> top-down should recover PCS values."""
        pcs_p, pcs_q = 5.5, 1.8
        common = dict(
            pcs_voltage_kv=0.69, num_pcs=20, pcs_unit_kva=6000,
            num_mvt=4, mvt_capacity_mva=30.0, mpt_capacity_mva=120.0,
            aux_power_mw=2.0, direction='discharge',
        )
        r_bu = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=pcs_p, pcs_reactive_power_mvar=pcs_q, **common,
        ))
        r_td = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=0, pcs_reactive_power_mvar=0,
            calculation_mode='top_down',
            required_p_at_poi_mw=r_bu.p_at_poi,
            required_q_at_poi_mvar=r_bu.q_at_poi,
            **common,
        ))
        assert abs(r_td.required_pcs_p_per_unit_mw - pcs_p) < 0.001
        assert abs(r_td.required_pcs_q_per_unit_mvar - pcs_q) < 0.001

    def test_top_down_zero_q(self):
        """Top-down with Q=0 at POI (PCS must still inject Q for transformer consumption)."""
        r = calculate_power_flow(PowerFlowInput(
            pcs_active_power_mw=0, pcs_reactive_power_mvar=0,
            pcs_voltage_kv=0.69, num_pcs=10, pcs_unit_kva=12000,
            num_mvt=2, mvt_capacity_mva=60.0, mpt_capacity_mva=150.0,
            calculation_mode='top_down',
            required_p_at_poi_mw=80.0,
            required_q_at_poi_mvar=0.0,
        ))
        assert abs(r.p_at_poi - 80.0) < 0.001
        assert abs(r.q_at_poi - 0.0) < 0.001
        # PCS must inject positive Q to compensate transformer consumption
        assert r.required_pcs_q_per_unit_mvar > 0

    def test_top_down_with_large_aux(self):
        """Top-down should account for aux in PCS requirement."""
        common = dict(
            pcs_active_power_mw=0, pcs_reactive_power_mvar=0,
            pcs_voltage_kv=0.69, num_pcs=20, pcs_unit_kva=6000,
            num_mvt=4, mvt_capacity_mva=30.0, mpt_capacity_mva=120.0,
            calculation_mode='top_down',
            required_p_at_poi_mw=100.0,
            required_q_at_poi_mvar=10.0,
            direction='discharge',
        )
        r_no_aux = calculate_power_flow(PowerFlowInput(**common, aux_power_mw=0.0))
        r_aux = calculate_power_flow(PowerFlowInput(**common, aux_power_mw=5.0))
        # With aux, each PCS must produce more P to meet the same POI target
        assert r_aux.required_pcs_p_per_unit_mw > r_no_aux.required_pcs_p_per_unit_mw


class TestValidation:
    """Input validation tests."""

    def test_invalid_num_pcs(self):
        with pytest.raises(ValueError, match="num_pcs"):
            calculate_power_flow(PowerFlowInput(
                pcs_active_power_mw=10, pcs_reactive_power_mvar=0,
                pcs_voltage_kv=0.69, num_pcs=0, pcs_unit_kva=12000, num_mvt=1,
            ))

    def test_invalid_direction(self):
        with pytest.raises(ValueError, match="direction"):
            calculate_power_flow(PowerFlowInput(
                pcs_active_power_mw=10, pcs_reactive_power_mvar=0,
                pcs_voltage_kv=0.69, num_pcs=1, pcs_unit_kva=12000,
                num_mvt=1, direction='invalid',
            ))

    def test_top_down_requires_poi_power(self):
        with pytest.raises(ValueError, match="required_p_at_poi_mw"):
            calculate_power_flow(PowerFlowInput(
                pcs_active_power_mw=0, pcs_reactive_power_mvar=0,
                pcs_voltage_kv=0.69, num_pcs=1, pcs_unit_kva=12000,
                num_mvt=1, calculation_mode='top_down',
                required_p_at_poi_mw=0,
            ))

    def test_invalid_num_mvt(self):
        with pytest.raises(ValueError, match="num_mvt"):
            calculate_power_flow(PowerFlowInput(
                pcs_active_power_mw=10, pcs_reactive_power_mvar=0,
                pcs_voltage_kv=0.69, num_pcs=1, pcs_unit_kva=12000,
                num_mvt=0,
            ))

    def test_invalid_efficiency(self):
        with pytest.raises(ValueError, match="mvt_efficiency_pct"):
            calculate_power_flow(PowerFlowInput(
                pcs_active_power_mw=10, pcs_reactive_power_mvar=0,
                pcs_voltage_kv=0.69, num_pcs=1, pcs_unit_kva=12000,
                num_mvt=1, mvt_efficiency_pct=101.0,
            ))

    def test_invalid_calculation_mode(self):
        with pytest.raises(ValueError, match="calculation_mode"):
            calculate_power_flow(PowerFlowInput(
                pcs_active_power_mw=10, pcs_reactive_power_mvar=0,
                pcs_voltage_kv=0.69, num_pcs=1, pcs_unit_kva=12000,
                num_mvt=1, calculation_mode='invalid',
            ))


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python", "-m", "pytest", __file__, "-v"]))
