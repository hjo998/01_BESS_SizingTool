"""BESS Sizing Tool — SOC Range Calculator

Determines SOC operating range (High/Low/Rest) based on:
- Application type (Peak Shifting, Frequency Regulation, etc.)
- CP Rate (from battery_sizing.py)
- Product type (product-specific SOC limits)

The Applied DoD (= SOC_H - SOC_L) feeds back into efficiency.py's
BatteryLossInput.applied_dod, creating a circular dependency with CP-rate
that is resolved by convergence.py's iterative solver.
"""
import json
import os
from dataclasses import dataclass

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def _load_json(filename: str):
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'r') as f:
        return json.load(f)


@dataclass
class SOCInput:
    cp_rate: float              # from battery_sizing.py; must be > 0
    application: str            # e.g. "Peak Shifting", "FR", "Default"
    product_type: str           # e.g. "JF3 0.25 DC LINK"
    measurement_method: str = "Both CP"  # "Both CP", "CPCV/CP", or "Both CPCV"
    cycle_per_day: int = 1      # number of charge/discharge cycles per day
    rest_time_hr: float = 2.0   # rest period between cycles (hours)


@dataclass
class SOCResult:
    soc_high: float             # upper SOC operating limit (0–1)
    soc_low: float              # lower SOC operating limit (0–1)
    soc_rest: float             # resting/standby SOC (0–1)
    applied_dod: float          # soc_high - soc_low
    effective_dod: float        # applied_dod * product correction factor (= 1.0 for now)


def _lookup_application(data: dict, application: str) -> dict:
    """Look up application entry by name (case-insensitive), fallback to Default."""
    applications = data.get("applications", {})

    # Exact match first
    if application in applications:
        return applications[application]

    # Case-insensitive match
    application_lower = application.lower()
    for key, val in applications.items():
        if key.lower() == application_lower:
            return val

    # Fallback to Default
    if "Default" in applications:
        return applications["Default"]

    raise ValueError(
        f"Application '{application}' not found in soc_ranges.json and no Default entry exists."
    )


def _lookup_product_limits(data: dict, product_type: str) -> dict:
    """Look up product SOC limits, fallback to Default."""
    product_limits = data.get("product_limits", {})

    if product_type in product_limits:
        return product_limits[product_type]

    # Fallback to Default
    if "Default" in product_limits:
        return product_limits["Default"]

    # If no product limits at all, use full range
    return {"soc_max": 1.00, "soc_min": 0.00}


def calculate_soc(inp: SOCInput) -> SOCResult:
    """Calculate SOC operating range for given application and product type.

    Lookup priority:
    1. Exact application name match
    2. Case-insensitive application name match
    3. "Default" application entry

    Product limits clamp soc_high and soc_low to the allowed hardware range.
    applied_dod = soc_high - soc_low
    effective_dod = applied_dod * 1.0 (product correction factor placeholder)
    """
    # --- Input validation ---
    if inp.cp_rate <= 0:
        raise ValueError(
            f"cp_rate must be positive, got {inp.cp_rate}"
        )
    if not inp.application or not inp.application.strip():
        raise ValueError("application must be a non-empty string")
    # --- End validation ---

    data = _load_json('soc_ranges.json')

    app_entry = _lookup_application(data, inp.application)
    product_limits = _lookup_product_limits(data, inp.product_type)

    soc_max = product_limits["soc_max"]
    soc_min = product_limits["soc_min"]

    # Apply product limits by clamping application SOC bounds
    soc_high = min(app_entry["soc_high"], soc_max)
    soc_low = max(app_entry["soc_low"], soc_min)
    soc_rest = app_entry["soc_rest"]

    # ── Measurement Method adjustment ──────────────────────────
    # Measurement Method affects SOC boundaries:
    #   Both CP:   Standard CP charge / CP discharge (default, no adjustment)
    #   CPCV/CP:   CPCV charge / CP discharge — higher effective SOC_H
    #   Both CPCV: CPCV charge / CPCV discharge — both boundaries tighter
    #
    # NOTE: These adjustments are placeholders. When the Excel SI Design
    # Tool (SOC sheet B1:C7) is available, replace with exact lookup values.
    method = getattr(inp, 'measurement_method', 'Both CP') or 'Both CP'
    if method == "CPCV/CP":
        # CPCV charging allows reaching higher SOC more safely
        soc_high = min(soc_high + 0.02, soc_max)
    elif method == "Both CPCV":
        # Both CPCV: higher SOC_H, also higher SOC_L (tighter low-end)
        soc_high = min(soc_high + 0.02, soc_max)
        soc_low = max(soc_low + 0.03, soc_min)

    # ── CP-rate adjustment ─────────────────────────────────────
    # Higher CP-rate → narrower SOC window to protect cell longevity.
    # NOTE: Placeholder linear scaling. Replace with Excel B1:C7 lookup
    # when available.
    if inp.cp_rate > 0.3:
        # Aggressive CP-rate: tighten SOC window
        cp_penalty = min((inp.cp_rate - 0.3) * 0.1, 0.05)
        soc_high = max(soc_high - cp_penalty, soc_low + 0.10)
        soc_low = min(soc_low + cp_penalty, soc_high - 0.10)

    applied_dod = soc_high - soc_low

    # Product correction factor is 1.0 (placeholder for future product-specific adjustments)
    _product_correction_factor = 1.0
    effective_dod = applied_dod * _product_correction_factor

    return SOCResult(
        soc_high=soc_high,
        soc_low=soc_low,
        soc_rest=soc_rest,
        applied_dod=round(applied_dod, 6),
        effective_dod=round(effective_dod, 6),
    )


def get_applied_dod(application: str, product_type: str) -> float:
    """Quick accessor returning just the applied_dod for the given application and product.

    Uses cp_rate=0.25 as a neutral placeholder (typical product max C-rate).
    """
    result = calculate_soc(SOCInput(
        cp_rate=0.25,
        application=application,
        product_type=product_type,
    ))
    return result.applied_dod
