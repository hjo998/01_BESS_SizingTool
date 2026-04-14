"""BESS Sizing Tool — Round-Trip Efficiency Calculator (v2)

Calculates RTE at 4 reference points (DC, PCS, MV, POI) with:
  - Yearly degradation via dc_rte_by_year array
  - Aux power impact via energy balance (rest-period penalty)
  - System-level RTE without aux (chain_eff squared model)

Reference points along the power path:
    Battery DC ─── PCS AC ─── MV Bus ─── POI (Grid)

This module is self-contained and does NOT import from power_flow.py.
The caller (routes.py) bridges PowerFlowResult values into RTEInput.
"""
from dataclasses import dataclass
from typing import List


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RTEInput:
    """Input parameters for the expanded RTE calculation."""

    # --- Efficiency chain at each reference point ---
    # One-way chain efficiency from DC terminals to the given point.
    # These come from PowerFlowResult.chain_eff_to_* or are derived.
    chain_eff_to_pcs: float        # DC -> PCS  (= dc_cabling * pcs_eff, approx)
    chain_eff_to_mv: float         # DC -> MV bus (after aux, from power flow)
    chain_eff_to_poi: float        # DC -> POI  (from power flow)

    # --- Battery DC RTE per year ---
    dc_rte_by_year: List[float]    # e.g. [0.94, 0.938, 0.936, ...] for years 0..N

    # --- Time parameters ---
    t_discharge_hr: float          # Discharge duration (hours)
    t_rest_hr: float = 0.25       # Rest period between charge and discharge (hours)

    # --- Aux power at each reference point (MW) ---
    # During rest, aux still runs from grid.  Need aux power at each metering
    # point to compute the rest-period energy penalty.
    aux_power_at_pcs_mw: float = 0.0
    aux_power_at_mv_mw: float = 0.0
    aux_power_at_poi_mw: float = 0.0

    # --- Rated power at POI (MW) ---
    # Needed to convert RTE energy balance into absolute energies when aux > 0.
    p_rated_at_poi_mw: float = 0.0


@dataclass
class RTEYearRow:
    """RTE results for a single year."""

    year: int
    dc_rte: float                    # Battery DC RTE for this year

    # Without aux (pure system efficiency)
    rte_at_dc: float                 # = dc_rte (trivial, input == output at DC)
    rte_at_pcs: float                # chain_eff_to_pcs ** 2 * dc_rte
    rte_at_mv: float                 # chain_eff_to_mv  ** 2 * dc_rte
    rte_at_poi: float                # chain_eff_to_poi ** 2 * dc_rte

    # With aux (energy balance including aux during rest)
    rte_at_dc_with_aux: float
    rte_at_pcs_with_aux: float
    rte_at_mv_with_aux: float
    rte_at_poi_with_aux: float


@dataclass
class RTEResult:
    """Complete RTE calculation result."""

    rte_table: List[RTEYearRow]

    # Year 0 summary (convenience / backward compatibility)
    system_rte: float                # = rte_table[0].rte_at_poi
    system_rte_with_aux: float       # = rte_table[0].rte_at_poi_with_aux

    # Time parameters used (echo back for transparency)
    t_discharge_hr: float
    t_charge_hr_year0: float         # T_charge for year 0
    t_rest_hr: float
    t_cycle_hr_year0: float          # Total cycle time for year 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rte_no_aux(chain_eff: float, dc_rte_y: float) -> float:
    """RTE at a reference point without considering aux power.

    RTE = chain_eff^2 * dc_rte
    chain_eff^2 accounts for both charge (grid -> battery) and discharge
    (battery -> grid) paths.
    """
    return chain_eff ** 2 * dc_rte_y


def _rte_with_aux(
    chain_eff: float,
    dc_rte_y: float,
    t_disch: float,
    t_rest: float,
    aux_at_ref: float,
    p_rated_at_ref: float,
) -> float:
    """Energy-balance RTE at a reference point including aux power.

    During discharge the grid receives energy:
        E_out = p_rated_at_ref * t_disch

    During charge the grid must supply energy (derived from the no-aux RTE):
        E_charge = E_out / rte_no_aux

    During rest only aux power is consumed:
        E_rest = aux_at_ref * t_rest

    RTE_with_aux = E_out / (E_charge + E_rest)

    Parameters
    ----------
    chain_eff : float
        One-way chain efficiency from DC to this reference point.
    dc_rte_y : float
        Battery DC RTE for this year.
    t_disch : float
        Discharge duration in hours.
    t_rest : float
        Rest duration in hours.
    aux_at_ref : float
        Aux power at this reference point (MW).
    p_rated_at_ref : float
        Rated discharge power at this reference point (MW).
    """
    rte_base = _rte_no_aux(chain_eff, dc_rte_y)

    # If aux is zero or negligible, fall back to the simple formula.
    if aux_at_ref <= 0 or p_rated_at_ref <= 0:
        return rte_base

    e_out = p_rated_at_ref * t_disch
    if e_out <= 0:
        return 0.0

    # Charge energy: derived from the "no aux" RTE relationship.
    # E_charge = E_out / rte_no_aux  (i.e. what the grid must supply)
    if rte_base <= 0:
        return 0.0
    e_charge = e_out / rte_base

    # Rest energy penalty
    e_rest = aux_at_ref * t_rest

    total_in = e_charge + e_rest
    if total_in <= 0:
        return 0.0

    return e_out / total_in


def _derive_p_rated(
    p_rated_at_poi: float,
    chain_eff_to_poi: float,
    chain_eff_target: float,
) -> float:
    """Derive the rated power at another reference point from the POI rating.

    P at any reference point scales with the ratio of chain efficiencies:
        P_at_ref = P_at_poi * (chain_eff_target / chain_eff_to_poi)

    At DC (chain_eff = 1): P_dc = P_poi / chain_eff_to_poi
    At PCS: P_pcs = P_poi * (chain_eff_to_pcs / chain_eff_to_poi)
    """
    if chain_eff_to_poi <= 0:
        return 0.0
    return p_rated_at_poi * (chain_eff_target / chain_eff_to_poi)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate(inp: RTEInput) -> None:
    """Raise ValueError if any input is out of range."""

    # Chain efficiencies must be in (0, 1]
    for name, val in [
        ("chain_eff_to_pcs", inp.chain_eff_to_pcs),
        ("chain_eff_to_mv", inp.chain_eff_to_mv),
        ("chain_eff_to_poi", inp.chain_eff_to_poi),
    ]:
        if not (0 < val <= 1):
            raise ValueError(
                f"{name} must be between 0 (exclusive) and 1 (inclusive), got {val}"
            )

    # DC RTE array
    if not inp.dc_rte_by_year:
        raise ValueError("dc_rte_by_year must contain at least one element")
    for i, val in enumerate(inp.dc_rte_by_year):
        if not (0 < val <= 1):
            raise ValueError(
                f"dc_rte_by_year[{i}] must be between 0 (exclusive) and 1 (inclusive), "
                f"got {val}"
            )

    # Time parameters
    if inp.t_discharge_hr <= 0:
        raise ValueError(
            f"t_discharge_hr must be > 0, got {inp.t_discharge_hr}"
        )
    if inp.t_rest_hr < 0:
        raise ValueError(
            f"t_rest_hr must be >= 0, got {inp.t_rest_hr}"
        )

    # Aux power values must be non-negative
    for name, val in [
        ("aux_power_at_pcs_mw", inp.aux_power_at_pcs_mw),
        ("aux_power_at_mv_mw", inp.aux_power_at_mv_mw),
        ("aux_power_at_poi_mw", inp.aux_power_at_poi_mw),
    ]:
        if val < 0:
            raise ValueError(f"{name} must be >= 0, got {val}")

    # If any aux > 0, p_rated_at_poi must be positive
    has_aux = (
        inp.aux_power_at_pcs_mw > 0
        or inp.aux_power_at_mv_mw > 0
        or inp.aux_power_at_poi_mw > 0
    )
    if has_aux and inp.p_rated_at_poi_mw <= 0:
        raise ValueError(
            "p_rated_at_poi_mw must be > 0 when any aux_power is > 0, "
            f"got {inp.p_rated_at_poi_mw}"
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def calculate_rte(inp: RTEInput) -> RTEResult:
    """Calculate RTE at 4 reference points for each year.

    Steps
    -----
    1. Validate inputs.
    2. For each year in dc_rte_by_year:
       a. Compute rte_no_aux at DC, PCS, MV, POI.
       b. Compute rte_with_aux at DC, PCS, MV, POI.
       c. Create RTEYearRow.
    3. Build RTEResult with the table + year 0 summary.
    """
    _validate(inp)

    # Pre-compute rated powers at each reference point (used by with-aux calc)
    p_poi = inp.p_rated_at_poi_mw
    p_mv = _derive_p_rated(p_poi, inp.chain_eff_to_poi, inp.chain_eff_to_mv)
    p_pcs = _derive_p_rated(p_poi, inp.chain_eff_to_poi, inp.chain_eff_to_pcs)
    # At DC, chain_eff = 1.0  =>  P_dc = P_poi / chain_eff_to_poi
    p_dc = _derive_p_rated(p_poi, inp.chain_eff_to_poi, 1.0)

    table: List[RTEYearRow] = []

    for year, dc_rte_y in enumerate(inp.dc_rte_by_year):
        # --- RTE without aux ---
        rte_dc  = _rte_no_aux(1.0,                  dc_rte_y)
        rte_pcs = _rte_no_aux(inp.chain_eff_to_pcs, dc_rte_y)
        rte_mv  = _rte_no_aux(inp.chain_eff_to_mv,  dc_rte_y)
        rte_poi = _rte_no_aux(inp.chain_eff_to_poi, dc_rte_y)

        # --- RTE with aux (energy balance) ---
        common = dict(dc_rte_y=dc_rte_y,
                      t_disch=inp.t_discharge_hr,
                      t_rest=inp.t_rest_hr)

        rte_dc_aux  = _rte_with_aux(
            chain_eff=1.0,
            aux_at_ref=0.0,
            p_rated_at_ref=p_dc,
            **common,
        )
        rte_pcs_aux = _rte_with_aux(
            chain_eff=inp.chain_eff_to_pcs,
            aux_at_ref=inp.aux_power_at_pcs_mw,
            p_rated_at_ref=p_pcs,
            **common,
        )
        rte_mv_aux  = _rte_with_aux(
            chain_eff=inp.chain_eff_to_mv,
            aux_at_ref=inp.aux_power_at_mv_mw,
            p_rated_at_ref=p_mv,
            **common,
        )
        rte_poi_aux = _rte_with_aux(
            chain_eff=inp.chain_eff_to_poi,
            aux_at_ref=inp.aux_power_at_poi_mw,
            p_rated_at_ref=p_poi,
            **common,
        )

        table.append(RTEYearRow(
            year=year,
            dc_rte=dc_rte_y,
            rte_at_dc=rte_dc,
            rte_at_pcs=rte_pcs,
            rte_at_mv=rte_mv,
            rte_at_poi=rte_poi,
            rte_at_dc_with_aux=rte_dc_aux,
            rte_at_pcs_with_aux=rte_pcs_aux,
            rte_at_mv_with_aux=rte_mv_aux,
            rte_at_poi_with_aux=rte_poi_aux,
        ))

    # Year 0 timing
    dc_rte_0 = inp.dc_rte_by_year[0]
    t_charge_0 = inp.t_discharge_hr / dc_rte_0
    t_cycle_0 = t_charge_0 + inp.t_rest_hr + inp.t_discharge_hr

    return RTEResult(
        rte_table=table,
        system_rte=table[0].rte_at_poi,
        system_rte_with_aux=table[0].rte_at_poi_with_aux,
        t_discharge_hr=inp.t_discharge_hr,
        t_charge_hr_year0=t_charge_0,
        t_rest_hr=inp.t_rest_hr,
        t_cycle_hr_year0=t_cycle_0,
    )
