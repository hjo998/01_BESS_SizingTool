"""Test PCS sizing calculator."""
import pathlib, sys
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.pcs_sizing import *

def test_pcs_config_lookup():
    cfg = get_pcs_config("EPC Power M 6stc + JF3 5.5 x 2sets")
    assert cfg.manufacturer == "EPC Power"
    assert cfg.model == "M6"
    assert cfg.strings_per_pcs == 6
    assert cfg.links_per_pcs == 2

def test_pcs_unit_power_45c():
    cfg = get_pcs_config("EPC Power M 6stc + JF3 5.5 x 2sets")
    base, alt, derated, unit_mw = calculate_pcs_unit_power(cfg, 45, "<1000", 0.02)
    assert base == 537.0
    assert alt == 1.0
    assert abs(unit_mw - 3.15756) < 0.001

def test_invalid_config():
    import pytest
    with pytest.raises(ValueError):
        get_pcs_config("NONEXISTENT CONFIG")

def test_invalid_temperature():
    import pytest
    cfg = get_pcs_config("EPC Power M 6stc + JF3 5.5 x 2sets")
    with pytest.raises(ValueError):
        get_temp_derated_power("M6", 99)

if __name__ == "__main__":
    test_pcs_config_lookup()
    test_pcs_unit_power_45c()
    print("All PCS sizing tests passed!")
