"""BESS Sizing Tool — Iterative Convergence Solver

Resolves the circular dependency between CP-rate and SOC:
  CP-rate → SOC(H)/SOC(L) → Applied DoD → Battery Loss → Battery Sizing → CP-rate

Uses fixed-point iteration with damping to converge on a stable CP-rate/SOC pair.
Typically converges in 3-5 iterations. Divergence is physically unlikely (negative
feedback loop), but adaptive damping handles edge cases defensively.
"""
from dataclasses import dataclass, field
from typing import Optional

from .efficiency import (
    SystemEfficiencyInput,
    AuxEfficiencyInput,
    BatteryLossInput,
    EfficiencyResult,
    calculate_all,
)
from .pcs_sizing import PCSSizingInput, PCSSizingResult, calculate_pcs_sizing
from .battery_sizing import BatterySizingInput, BatterySizingResult, calculate_battery_sizing

# soc.py is created concurrently — import with fallback
try:
    from .soc import calculate_soc, SOCInput, SOCResult  # type: ignore[import]
    _SOC_AVAILABLE = True
except ImportError:
    _SOC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceConfig:
    """Tuning parameters for the fixed-point iteration solver."""
    max_iterations: int = 20
    convergence_threshold: float = 1e-6       # |delta CP-rate| to declare convergence
    damping_factor: float = 0.7               # Blend weight: new = old + damping*(candidate - old)
    strong_damping_factor: float = 0.5        # Used when consecutive divergence detected
    divergence_consecutive_limit: int = 3     # Consecutive delta increases before stronger damping


# ---------------------------------------------------------------------------
# Input / Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceInput:
    """All parameters needed to run the iterative sizing solver.

    Pass ``application`` as an empty string or None to skip convergence and
    run a single-pass calculation instead.
    """
    # Project requirements
    required_power_poi_mw: float
    required_energy_poi_mwh: float
    project_life_yr: int
    application: str  # e.g. "Peak Shifting", "FR". Empty/None → single-pass mode.

    # Efficiency sub-inputs (passed through each iteration)
    system_efficiency: SystemEfficiencyInput
    aux_efficiency: AuxEfficiencyInput
    base_battery_loss: BatteryLossInput   # applied_dod is overridden each iteration

    # PCS inputs
    pcs_config_name: str
    temperature_c: int
    altitude: str
    mv_voltage_tolerance: float

    # Battery inputs
    product_type: str
    aux_power_source: str = "Battery"

    # Optional
    rest_soc: str = "Mid"
    measurement_method: str = "Both CP"  # "Both CP", "CPCV/CP", or "Both CPCV"
    link_override: int = 0               # Manual LINK count override (0 = auto)
    oversizing_year: int = 0             # Year for retention oversizing (0 = no oversizing)
    config: Optional[ConvergenceConfig] = None  # Uses ConvergenceConfig defaults if None


@dataclass
class ConvergenceResult:
    """Output of the convergence solver, bundling all sub-results plus metadata."""
    # Final converged sub-results
    efficiency_result: EfficiencyResult
    pcs_result: PCSSizingResult
    battery_result: BatterySizingResult
    soc_result: Optional[object]  # SOCResult when soc.py is available, else None

    # Convergence metadata
    converged: bool
    iterations: int
    final_delta: float
    cp_rate_history: list  # [(iteration: int, cp_rate: float), ...]
    warning: str = ""      # Non-empty string when convergence issues occurred


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_pcs_input(inp: ConvergenceInput) -> PCSSizingInput:
    return PCSSizingInput(
        pcs_config_name=inp.pcs_config_name,
        temperature_c=inp.temperature_c,
        altitude=inp.altitude,
        mv_voltage_tolerance=inp.mv_voltage_tolerance,
    )


def run_sizing_pass(
    inp: ConvergenceInput,
    applied_dod: float,
    oversizing_retention_rate: float = 1.0,
) -> tuple:
    """Run one complete sizing pass: efficiency → pcs → battery.

    The applied_dod argument overrides inp.base_battery_loss.applied_dod for
    this pass. All other parameters come from inp unchanged.

    Args:
        inp: Full convergence input parameters.
        applied_dod: Depth of discharge for this iteration.
        oversizing_retention_rate: Retention rate at oversizing year (0-1).
            Default 1.0 means no oversizing adjustment.

    Returns:
        (efficiency_result, pcs_result, battery_result)
    """
    # Build BatteryLossInput with the current applied_dod
    bat_loss = BatteryLossInput(
        applied_dod=applied_dod,
        loss_factors=inp.base_battery_loss.loss_factors,
        mbms_consumption=inp.base_battery_loss.mbms_consumption,
    )

    eff_result: EfficiencyResult = calculate_all(
        inp.system_efficiency, inp.aux_efficiency, bat_loss
    )

    # PCS sizing requires req_power_dc which comes from efficiency; compute it
    req_power_dc = inp.required_power_poi_mw / eff_result.total_dc_to_aux_eff

    pcs_result: PCSSizingResult = calculate_pcs_sizing(
        _make_pcs_input(inp),
        required_power_dc_mw=req_power_dc,
    )

    bat_inp = BatterySizingInput(
        required_power_poi_mw=inp.required_power_poi_mw,
        required_energy_poi_mwh=inp.required_energy_poi_mwh,
        total_bat_poi_eff=eff_result.total_bat_poi_eff,
        total_battery_loss_factor=eff_result.total_battery_loss_factor,
        total_dc_to_aux_eff=eff_result.total_dc_to_aux_eff,
        product_type=inp.product_type,
        pcs_unit_power_mw=pcs_result.pcs_unit_power_mw,
        links_per_pcs=pcs_result.links_per_pcs,
        aux_power_source=inp.aux_power_source,
        link_override=inp.link_override,
        oversizing_retention_rate=oversizing_retention_rate,
    )
    bat_result: BatterySizingResult = calculate_battery_sizing(bat_inp)

    return eff_result, pcs_result, bat_result


def _get_applied_dod_from_soc(soc_result: object) -> Optional[float]:
    """Extract applied_dod from a SOCResult object.

    Tries common attribute names. Returns None if extraction fails so the
    caller can fall back to the previous applied_dod.
    """
    for attr in ("applied_dod", "dod", "depth_of_discharge"):
        if hasattr(soc_result, attr):
            val = getattr(soc_result, attr)
            if isinstance(val, (int, float)) and 0 < val <= 1:
                return float(val)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_without_convergence(inp: ConvergenceInput) -> ConvergenceResult:
    """Single-pass calculation when application is not provided.

    Runs efficiency → pcs → battery exactly once using the original applied_dod
    from inp.base_battery_loss. No SOC calculation is performed.

    If oversizing_year > 0, performs retention-aware iterative sizing to converge
    on a stable LINK count that accounts for degradation at the oversizing year.

    Returns a ConvergenceResult with converged=True, iterations=1, soc_result=None.
    """
    oversizing_year = inp.oversizing_year
    oversizing_retention_rate = 1.0
    applied_dod = inp.base_battery_loss.applied_dod

    if oversizing_year > 0:
        # Iteratively converge on LINK count with retention
        prev_links_history: list = []
        max_iter = 20

        for _ in range(max_iter):
            eff_result, pcs_result, bat_result = run_sizing_pass(
                inp, applied_dod=applied_dod,
                oversizing_retention_rate=oversizing_retention_rate,
            )

            # Look up retention for the new CP-rate
            from .retention import lookup_retention_curve
            _, retention_curve = lookup_retention_curve(
                bat_result.cp_rate, inp.product_type, inp.project_life_yr,
                rest_soc=getattr(inp, 'rest_soc', 'Mid'),
            )
            yr_key = oversizing_year
            if yr_key in retention_curve:
                oversizing_retention_rate = retention_curve[yr_key] / 100.0

            current_links = bat_result.no_of_links

            # Convergence check: stable LINK count
            if len(prev_links_history) >= 1 and current_links == prev_links_history[-1]:
                break

            # Oscillation detection: if current LINK count was seen before
            if current_links in prev_links_history and len(prev_links_history) >= 2:
                # Pick the larger value and do a final pass
                no_of_links = max(set(prev_links_history) | {current_links})
                eff_result, pcs_result, bat_result = run_sizing_pass(
                    inp, applied_dod=applied_dod,
                    oversizing_retention_rate=oversizing_retention_rate,
                )
                # Force the larger link count if needed
                if bat_result.no_of_links < no_of_links:
                    bat_inp_override = BatterySizingInput(
                        required_power_poi_mw=inp.required_power_poi_mw,
                        required_energy_poi_mwh=inp.required_energy_poi_mwh,
                        total_bat_poi_eff=eff_result.total_bat_poi_eff,
                        total_battery_loss_factor=eff_result.total_battery_loss_factor,
                        total_dc_to_aux_eff=eff_result.total_dc_to_aux_eff,
                        product_type=inp.product_type,
                        pcs_unit_power_mw=pcs_result.pcs_unit_power_mw,
                        links_per_pcs=pcs_result.links_per_pcs,
                        aux_power_source=inp.aux_power_source,
                        link_override=no_of_links,
                        oversizing_retention_rate=oversizing_retention_rate,
                    )
                    bat_result = calculate_battery_sizing(bat_inp_override)
                break

            prev_links_history.append(current_links)
    else:
        eff_result, pcs_result, bat_result = run_sizing_pass(
            inp, applied_dod=applied_dod,
            oversizing_retention_rate=oversizing_retention_rate,
        )

    return ConvergenceResult(
        efficiency_result=eff_result,
        pcs_result=pcs_result,
        battery_result=bat_result,
        soc_result=None,
        converged=True,
        iterations=1,
        final_delta=0.0,
        cp_rate_history=[(1, bat_result.cp_rate)],
        warning="",
    )


def iterative_sizing_with_soc(inp: ConvergenceInput) -> ConvergenceResult:
    """Resolve the CP-rate / SOC circular dependency via fixed-point iteration.

    Algorithm
    ---------
    1. Initial CP-rate = 0.25 (typical product maximum)
    2. Each iteration:
       a. calculate_soc(cp_rate, application, product_type) → SOCResult → applied_dod
       b. Build BatteryLossInput with updated applied_dod
       c. calculate_all(...) → EfficiencyResult
       d. calculate_pcs_sizing(...) → PCSSizingResult
       e. calculate_battery_sizing(...) → BatterySizingResult → new CP-rate
       f. Apply damping: cp_rate_next = cp_rate + damping * (new_cp_rate - cp_rate)
       g. Check convergence: |cp_rate_next - cp_rate| < threshold → done
       h. Divergence guard: if |delta| increased 3 consecutive iterations,
          switch to strong_damping_factor for the remainder
       i. Structural convergence: if no_of_links is unchanged for 2 consecutive
          iterations, declare converged (discrete integer counts stabilise faster
          than the continuous CP-rate)
    3. Return ConvergenceResult with full metadata

    If soc.py is not available, falls back to calculate_without_convergence().
    """
    if not _SOC_AVAILABLE:
        result = calculate_without_convergence(inp)
        result.warning = (
            "soc.py not available; ran single-pass without SOC convergence."
        )
        return result

    cfg = inp.config if inp.config is not None else ConvergenceConfig()

    cp_rate = 0.25          # Initial guess: typical product max C-rate
    applied_dod = inp.base_battery_loss.applied_dod
    cp_rate_history: list = []
    warning = ""

    # Oversizing retention tracking
    oversizing_year = inp.oversizing_year
    oversizing_retention_rate = 1.0  # Initial: no retention penalty

    # Tracking variables for divergence / structural convergence
    prev_delta = None
    consecutive_divergence = 0
    current_damping = cfg.damping_factor
    prev_no_of_links: Optional[int] = None
    stable_links_count = 0
    links_history_set: set = set()  # Track oscillation of LINK counts

    # Final sub-results (updated each iteration; last good values returned)
    eff_result: Optional[EfficiencyResult] = None
    pcs_result: Optional[PCSSizingResult] = None
    bat_result: Optional[BatterySizingResult] = None
    soc_result: Optional[object] = None

    converged = False
    final_delta = float("inf")
    iteration = 0

    for iteration in range(1, cfg.max_iterations + 1):
        # Step a: compute SOC from current CP-rate
        try:
            soc_inp = SOCInput(
                cp_rate=cp_rate,
                application=inp.application,
                product_type=inp.product_type,
                measurement_method=getattr(inp, 'measurement_method', 'Both CP'),
            )
            soc_result = calculate_soc(soc_inp)
            new_applied_dod = _get_applied_dod_from_soc(soc_result)
            if new_applied_dod is not None:
                applied_dod = new_applied_dod
        except Exception:
            # SOC calculation failure — keep previous applied_dod, continue
            pass

        # Steps b–e: full sizing pass with current applied_dod and retention rate
        eff_result, pcs_result, bat_result = run_sizing_pass(
            inp, applied_dod, oversizing_retention_rate
        )
        new_cp_rate = bat_result.cp_rate

        # Step: look up retention for this CP-rate at the oversizing year
        if oversizing_year > 0:
            try:
                from .retention import lookup_retention_curve
                _, retention_curve = lookup_retention_curve(
                    new_cp_rate, inp.product_type, inp.project_life_yr,
                    rest_soc=getattr(inp, 'rest_soc', 'Mid'),
                )
                yr_key = oversizing_year
                if yr_key in retention_curve:
                    oversizing_retention_rate = retention_curve[yr_key] / 100.0
            except (ValueError, FileNotFoundError):
                pass  # Keep previous oversizing_retention_rate

        cp_rate_history.append((iteration, new_cp_rate))

        # Step f: damped update
        delta = new_cp_rate - cp_rate
        cp_rate_next = cp_rate + current_damping * delta
        abs_delta = abs(cp_rate_next - cp_rate)

        # Step h: divergence detection — compare |delta| with previous
        if prev_delta is not None:
            if abs_delta > prev_delta:
                consecutive_divergence += 1
                if consecutive_divergence >= cfg.divergence_consecutive_limit:
                    current_damping = cfg.strong_damping_factor
                    warning = (
                        f"Divergence detected at iteration {iteration}; "
                        f"strengthened damping to {current_damping}."
                    )
            else:
                consecutive_divergence = 0

        prev_delta = abs_delta

        # Step i: structural convergence check (no_of_links integer stability)
        current_links = bat_result.no_of_links
        if prev_no_of_links is not None and current_links == prev_no_of_links:
            stable_links_count += 1
            if stable_links_count >= 2:
                cp_rate = cp_rate_next
                final_delta = abs_delta
                converged = True
                break
        else:
            stable_links_count = 0

        # Oscillation detection for LINK count
        if current_links in links_history_set and len(links_history_set) >= 2:
            # Oscillating between values — pick the larger one
            larger_links = max(links_history_set | {current_links})
            # Force the larger count via link_override and do a final pass
            saved_override = inp.link_override
            try:
                inp.link_override = larger_links
                eff_result, pcs_result, bat_result = run_sizing_pass(
                    inp, applied_dod, oversizing_retention_rate
                )
            finally:
                inp.link_override = saved_override
            cp_rate = bat_result.cp_rate
            final_delta = abs_delta
            converged = True
            cp_rate_history.append((iteration, bat_result.cp_rate))
            break

        links_history_set.add(current_links)
        prev_no_of_links = current_links

        # Step g: continuous convergence check
        if abs_delta < cfg.convergence_threshold:
            cp_rate = cp_rate_next
            final_delta = abs_delta
            converged = True
            break

        cp_rate = cp_rate_next

    else:
        # Exhausted max_iterations without formal convergence
        final_delta = abs(cp_rate - (bat_result.cp_rate if bat_result else cp_rate))
        if not warning:
            warning = (
                f"Did not converge within {cfg.max_iterations} iterations. "
                f"Final |delta CP-rate| = {final_delta:.2e}. "
                "Results reflect the last iteration."
            )

    return ConvergenceResult(
        efficiency_result=eff_result,
        pcs_result=pcs_result,
        battery_result=bat_result,
        soc_result=soc_result,
        converged=converged,
        iterations=iteration,
        final_delta=final_delta,
        cp_rate_history=cp_rate_history,
        warning=warning,
    )


def solve(inp: ConvergenceInput) -> ConvergenceResult:
    """Top-level entry point.

    Routes to iterative_sizing_with_soc() when application is given,
    or calculate_without_convergence() when it is not.
    """
    if not inp.application or not inp.application.strip():
        return calculate_without_convergence(inp)
    return iterative_sizing_with_soc(inp)
