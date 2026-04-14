"""Tests for RTE v2 calculator."""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.rte import RTEInput, RTEResult, calculate_rte


class TestRTENoAux:
    """RTE without aux power."""

    def test_basic_rte(self):
        """RTE = chain_eff^2 * dc_rte at each level."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0,
        ))
        assert len(r.rte_table) == 1
        row = r.rte_table[0]
        assert abs(row.rte_at_dc - 0.94) < 1e-6
        assert abs(row.rte_at_pcs - 0.99**2 * 0.94) < 1e-6
        assert abs(row.rte_at_mv - 0.96**2 * 0.94) < 1e-6
        assert abs(row.rte_at_poi - 0.947**2 * 0.94) < 1e-6

    def test_yearly_degradation(self):
        """RTE decreases year over year as dc_rte degrades."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
            dc_rte_by_year=[0.94, 0.938, 0.936, 0.934, 0.932],
            t_discharge_hr=4.0,
        ))
        assert len(r.rte_table) == 5
        for i in range(1, 5):
            assert r.rte_table[i].rte_at_poi < r.rte_table[i-1].rte_at_poi

    def test_chain_eff_one(self):
        """With chain_eff=1 everywhere, RTE = dc_rte."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=1.0, chain_eff_to_mv=1.0, chain_eff_to_poi=1.0,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0,
        ))
        assert abs(r.rte_table[0].rte_at_poi - 0.94) < 1e-6

    def test_year_indices(self):
        """Each row should have the correct year index."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
            dc_rte_by_year=[0.94, 0.93, 0.92],
            t_discharge_hr=4.0,
        ))
        for i, row in enumerate(r.rte_table):
            assert row.year == i

    def test_system_rte_equals_year0_poi(self):
        """system_rte convenience field should equal rte_table[0].rte_at_poi."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94, 0.93],
            t_discharge_hr=4.0,
        ))
        assert abs(r.system_rte - r.rte_table[0].rte_at_poi) < 1e-10

    def test_rte_monotone_across_levels(self):
        """RTE should decrease from DC -> PCS -> MV -> POI (chain_eff decreasing)."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.94,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0,
        ))
        row = r.rte_table[0]
        assert row.rte_at_dc >= row.rte_at_pcs >= row.rte_at_mv >= row.rte_at_poi


class TestRTEWithAux:
    """RTE with aux power."""

    def test_aux_reduces_rte(self):
        """Aux power should reduce RTE compared to no-aux."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0, t_rest_hr=0.25,
            aux_power_at_poi_mw=2.0,
            p_rated_at_poi_mw=100.0,
        ))
        row = r.rte_table[0]
        assert row.rte_at_poi_with_aux < row.rte_at_poi

    def test_zero_aux_equals_no_aux(self):
        """With aux=0, with_aux values equal no_aux values."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0,
            aux_power_at_poi_mw=0.0,
            p_rated_at_poi_mw=100.0,
        ))
        row = r.rte_table[0]
        assert abs(row.rte_at_poi - row.rte_at_poi_with_aux) < 1e-10

    def test_timing_values(self):
        """Verify T_charge = T_discharge / dc_rte."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0, t_rest_hr=0.25,
        ))
        expected_t_charge = 4.0 / 0.94
        assert abs(r.t_charge_hr_year0 - expected_t_charge) < 1e-6
        assert abs(r.t_cycle_hr_year0 - (expected_t_charge + 0.25 + 4.0)) < 1e-6

    def test_dc_with_aux_equals_dc_without_aux(self):
        """At DC level, aux has no effect (aux_at_dc is always 0 in the code)."""
        r = calculate_rte(RTEInput(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0, t_rest_hr=0.25,
            aux_power_at_poi_mw=5.0,
            p_rated_at_poi_mw=100.0,
        ))
        row = r.rte_table[0]
        assert abs(row.rte_at_dc - row.rte_at_dc_with_aux) < 1e-10

    def test_larger_aux_means_lower_rte(self):
        """Increasing aux power should decrease RTE at POI."""
        common = dict(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0, t_rest_hr=0.5,
            p_rated_at_poi_mw=100.0,
        )
        r_small = calculate_rte(RTEInput(**common, aux_power_at_poi_mw=1.0))
        r_large = calculate_rte(RTEInput(**common, aux_power_at_poi_mw=5.0))
        assert r_large.rte_table[0].rte_at_poi_with_aux < r_small.rte_table[0].rte_at_poi_with_aux

    def test_longer_rest_increases_aux_penalty(self):
        """Longer rest period means more aux energy consumed, lower RTE."""
        common = dict(
            chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.947,
            dc_rte_by_year=[0.94],
            t_discharge_hr=4.0,
            aux_power_at_poi_mw=2.0,
            p_rated_at_poi_mw=100.0,
        )
        r_short = calculate_rte(RTEInput(**common, t_rest_hr=0.25))
        r_long = calculate_rte(RTEInput(**common, t_rest_hr=2.0))
        assert r_long.rte_table[0].rte_at_poi_with_aux < r_short.rte_table[0].rte_at_poi_with_aux


class TestRTEValidation:
    """Validation tests."""

    def test_empty_dc_rte_array(self):
        with pytest.raises(ValueError, match="dc_rte_by_year"):
            calculate_rte(RTEInput(
                chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
                dc_rte_by_year=[], t_discharge_hr=4.0,
            ))

    def test_invalid_chain_eff(self):
        with pytest.raises(ValueError, match="chain_eff"):
            calculate_rte(RTEInput(
                chain_eff_to_pcs=1.5, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
                dc_rte_by_year=[0.94], t_discharge_hr=4.0,
            ))

    def test_aux_requires_p_rated(self):
        with pytest.raises(ValueError, match="p_rated_at_poi_mw"):
            calculate_rte(RTEInput(
                chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
                dc_rte_by_year=[0.94], t_discharge_hr=4.0,
                aux_power_at_poi_mw=2.0, p_rated_at_poi_mw=0.0,
            ))

    def test_invalid_dc_rte_value(self):
        with pytest.raises(ValueError, match="dc_rte_by_year"):
            calculate_rte(RTEInput(
                chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
                dc_rte_by_year=[1.1], t_discharge_hr=4.0,
            ))

    def test_negative_t_discharge(self):
        with pytest.raises(ValueError, match="t_discharge_hr"):
            calculate_rte(RTEInput(
                chain_eff_to_pcs=0.99, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
                dc_rte_by_year=[0.94], t_discharge_hr=-1.0,
            ))

    def test_zero_chain_eff(self):
        with pytest.raises(ValueError, match="chain_eff"):
            calculate_rte(RTEInput(
                chain_eff_to_pcs=0.0, chain_eff_to_mv=0.96, chain_eff_to_poi=0.95,
                dc_rte_by_year=[0.94], t_discharge_hr=4.0,
            ))


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python", "-m", "pytest", __file__, "-v"]))
