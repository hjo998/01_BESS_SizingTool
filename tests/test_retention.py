"""Test retention calculator."""
import pathlib, sys
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.calculators.retention import RetentionInput, calculate_retention

def test_jf3_retention_curve():
    inp = RetentionInput(
        cp_rate=0.2409,
        product_type="JF3 0.25 DC LINK",
        project_life_yr=20,
    )
    result = calculate_retention(inp)
    assert result.lookup_source == "jf3_golden"
    assert result.retention_by_year[0].retention_pct == 100.0
    assert result.retention_by_year[1].retention_pct == 98.1
    assert result.retention_by_year[10].retention_pct == 83.2
    assert result.retention_by_year[20].retention_pct == 72.6

def test_retention_curve_length():
    inp = RetentionInput(
        cp_rate=0.24,
        product_type="JF3 0.25 DC LINK",
        project_life_yr=15,
    )
    result = calculate_retention(inp)
    assert len(result.curve) == 16  # 0..15

if __name__ == "__main__":
    test_jf3_retention_curve()
    test_retention_curve_length()
    print("All retention tests passed!")
