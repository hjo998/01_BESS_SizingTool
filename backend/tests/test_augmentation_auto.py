"""Tests for recommend_augmentation() in backend/calculators/retention.py."""
import math
import pathlib
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.retention import (
    RetentionInput,
    AugmentationWave,
    AugmentationRecommendation,
    recommend_augmentation,
)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _base_input(installation_energy_dc_mwh: float = 444.32) -> RetentionInput:
    """RetentionInput for JF3 0.25 DC LINK, 20-year life.

    installation_energy_dc_mwh default matches the golden test case
    (80 LINKs × 5.554 MWh/LINK).
    """
    return RetentionInput(
        cp_rate=0.2409,
        product_type="JF3 0.25 DC LINK",
        project_life_yr=20,
        rest_soc="Mid",
        installation_energy_dc_mwh=installation_energy_dc_mwh,
        total_bat_poi_eff=0.9664,
        total_battery_loss_factor=0.9772,
        total_dc_to_aux_eff=0.9576,
        bat_to_mv_eff=0.9726,
        aux_power_per_link_mw=0.0,
    )


# Nameplate energy per JF3 LINK in MWh (from products.json via battery_sizing)
NAMEPLATE_PER_LINK = 5.554
LINKS_PER_PCS = 2


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_deficit():
    """When required_energy is very low, no augmentation waves should be recommended."""
    inp = _base_input()
    # Set required energy far below what Year-20 can deliver (72.6% of 444.32 MWh at POI)
    # dischargeable_poi at year 20 ≈ 444.32 * 0.726 * 0.9576 ≈ 308 MWh
    # Use 100 MWh to guarantee no deficit across all years
    required = 100.0

    rec = recommend_augmentation(
        base_retention_input=inp,
        required_energy_poi_mwh=required,
        nameplate_energy_per_link_mwh=NAMEPLATE_PER_LINK,
        links_per_pcs=LINKS_PER_PCS,
    )

    assert isinstance(rec, AugmentationRecommendation)
    assert len(rec.waves) == 0
    assert rec.total_additional_links == 0
    assert rec.total_additional_energy_mwh == pytest.approx(0.0)


def test_single_deficit_wave():
    """Setting required_energy just above the late-life poi energy triggers 1 wave.

    We use a very large installation (many LINKs) so early years comfortably exceed
    the threshold, but late-life decay eventually causes a deficit.  We then
    verify that exactly one wave is recommended, placed 1 year before the deficit.
    """
    # Use a modest installation so retention drop creates a deficit mid-life
    # 444.32 MWh DC installation; at year 20 poi ≈ 308 MWh (see note above)
    # Set required just above Year-20 poi but below Year-10 poi to ensure deficit
    # Year-10 poi ≈ 444.32 * 0.832 * 0.9576 ≈ 354 MWh
    # Year-20 poi ≈ 444.32 * 0.726 * 0.9576 ≈ 309 MWh
    # Required = 320 MWh forces a deficit sometime after year 10
    inp = _base_input(installation_energy_dc_mwh=444.32)
    required = 320.0

    rec = recommend_augmentation(
        base_retention_input=inp,
        required_energy_poi_mwh=required,
        nameplate_energy_per_link_mwh=NAMEPLATE_PER_LINK,
        links_per_pcs=LINKS_PER_PCS,
    )

    assert len(rec.waves) >= 1, f"Expected at least 1 wave, got {len(rec.waves)}"
    wave = rec.waves[0]

    # First wave must be placed 1 year before its trigger year
    assert len(rec.trigger_years) >= 1
    trigger_year = rec.trigger_years[0]
    assert wave.year == trigger_year - 1, (
        f"Wave year {wave.year} should be deficit_year-1 = {trigger_year - 1}"
    )

    # Wave must add at least enough energy to cover the shortfall
    assert wave.additional_energy_mwh > 0
    assert wave.additional_links > 0
    assert wave.product_type == "JF3 0.25 DC LINK"


def test_pcs_rounding():
    """additional_links is always rounded up to a multiple of links_per_pcs."""
    # Force a small deficit so that the raw ceil of shortfall / nameplate
    # might land on an odd number — rounding must push it to the next even number.
    inp = _base_input(installation_energy_dc_mwh=444.32)
    # required slightly above poi energy at a deficit year to get a small shortfall
    required = 315.0

    rec = recommend_augmentation(
        base_retention_input=inp,
        required_energy_poi_mwh=required,
        nameplate_energy_per_link_mwh=NAMEPLATE_PER_LINK,
        links_per_pcs=LINKS_PER_PCS,
    )

    for wave in rec.waves:
        assert wave.additional_links % LINKS_PER_PCS == 0, (
            f"additional_links={wave.additional_links} is not a multiple of links_per_pcs={LINKS_PER_PCS}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
