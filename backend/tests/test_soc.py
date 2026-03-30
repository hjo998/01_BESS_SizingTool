"""Tests for SOC range calculator (backend/calculators/soc.py)."""
import pathlib
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.soc import SOCInput, SOCResult, calculate_soc, get_applied_dod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_input(application: str, product_type: str = "JF3 0.25 DC LINK", cp_rate: float = 0.25) -> SOCInput:
    return SOCInput(
        cp_rate=cp_rate,
        application=application,
        product_type=product_type,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_peak_shifting():
    """Peak Shifting → soc_high=0.95, soc_low=0.05, applied_dod=0.9."""
    result = calculate_soc(_make_input("Peak Shifting"))
    assert result.soc_high == 0.95
    assert result.soc_low == 0.05
    assert result.applied_dod == pytest.approx(0.9, abs=1e-6)


def test_frequency_regulation_alias():
    """FR alias → soc_high=0.90, soc_low=0.10, applied_dod=0.8."""
    result = calculate_soc(_make_input("FR"))
    assert result.soc_high == 0.90
    assert result.soc_low == 0.10
    assert result.applied_dod == pytest.approx(0.8, abs=1e-6)


def test_case_insensitive():
    """Lowercase 'peak shifting' should resolve to the same values as 'Peak Shifting'."""
    result_lower = calculate_soc(_make_input("peak shifting"))
    result_canonical = calculate_soc(_make_input("Peak Shifting"))
    assert result_lower.soc_high == result_canonical.soc_high
    assert result_lower.soc_low == result_canonical.soc_low
    assert result_lower.applied_dod == result_canonical.applied_dod


def test_default_fallback():
    """Unknown application falls back to Default entry (same values as Peak Shifting)."""
    result = calculate_soc(_make_input("UnknownApp"))
    # Default entry in soc_ranges.json mirrors Peak Shifting
    assert result.soc_high == 0.95
    assert result.soc_low == 0.05
    assert result.applied_dod == pytest.approx(0.9, abs=1e-6)


def test_get_applied_dod():
    """get_applied_dod convenience function returns correct DoD for Peak Shifting / JF3."""
    dod = get_applied_dod("Peak Shifting", "JF3 0.25 DC LINK")
    assert dod == pytest.approx(0.9, abs=1e-6)


def test_invalid_cp_rate():
    """cp_rate <= 0 raises ValueError."""
    with pytest.raises(ValueError, match="cp_rate"):
        calculate_soc(SOCInput(cp_rate=0, application="Peak Shifting", product_type="JF3 0.25 DC LINK"))


def test_empty_application():
    """Empty application string raises ValueError."""
    with pytest.raises(ValueError, match="application"):
        calculate_soc(SOCInput(cp_rate=1.0, application="", product_type="JF3 0.25 DC LINK"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
