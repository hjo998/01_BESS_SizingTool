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


def _rte_with_aux_at_mv(
    chain_dc_to_mv: float,
    chain_mv_to_poi: float,
    dc_rte_y: float,
    t_disch: float,
    t_rest: float,
    aux_at_mv_mw: float,
    p_rated_at_poi_mw: float,
) -> float:
    """Energy-balance RTE at POI, with aux consumed at MV junction.

    Matches the sizing approach: aux branches off at MV, so the energy
    balance is computed at MV first, then converted to POI.

    Discharge (Battery → POI):
        P_mv_out = P_poi / mv_to_poi_eff       (what MV must deliver)
        P_mv_net = P_mv_out + aux_at_mv         (MV must also feed aux)
        P_dc_needed = P_mv_net / dc_to_mv_eff   (DC must supply this)
        E_discharge_at_dc = P_dc_needed × t_disch

    Charge (POI → Battery):
        P_mv_in = P_poi × mv_to_poi_eff         (POI power arriving at MV, charge direction uses same eff)
        Actually for charge, POI supplies, MV receives:
        P_mv_from_poi = P_poi_charge × mv_to_poi_eff  — wait this isn't right.

    Simpler energy-balance approach at POI:
        E_out_poi = P_poi × t_disch

        During discharge, at MV: need (P_poi/mv_to_poi + aux) from DC side
        During charge, at MV: need to push (P_poi/mv_to_poi + aux) into DC side
        So charge at POI:
            P_mv_charge = P_poi/mv_to_poi + aux (MV must receive this to charge battery + feed aux)
            P_poi_charge = P_mv_charge / mv_to_poi (POI must supply more to reach MV)
                         = (P_poi/mv_to_poi + aux) / mv_to_poi

    Actually, let's use a clean MV-centric energy balance:

        E_out @MV  = P_mv_rated × t_disch
            where P_mv_rated = P_poi / mv_to_poi_eff

        E_in @MV   = E_out_mv / (dc_to_mv² × dc_rte)
            (round-trip through DC→MV→DC, pure chain without aux)

        During discharge: aux consumes aux_mw × t_disch at MV
        During charge:    aux consumes aux_mw × t_charge at MV
        During rest:      aux consumes aux_mw × t_rest at MV

        t_charge ≈ t_disch / dc_rte (charging takes longer)

        Total aux energy @MV = aux_mw × (t_disch + t_charge + t_rest)

    But what goes to POI:
        E_out_poi = (P_mv_rated - aux_mw) × mv_to_poi × t_disch
                  ... no, POI gets P_poi. The aux is subtracted before POI.

    Let me just use the straightforward approach:

    Discharge path:
        DC delivers: P_dc × t_disch
        At MV: P_dc × dc_to_mv - aux  →  then × mv_to_poi = P_poi
        So: P_poi = (P_dc × dc_to_mv - aux) × mv_to_poi

    Charge path:
        POI supplies: P_poi_in
        At MV: P_poi_in / mv_to_poi  (arriving at MV from POI)
        But aux also needs feeding: MV net to DC = P_poi_in/mv_to_poi - aux
        Into DC: (P_poi_in/mv_to_poi - aux) × dc_to_mv
        To store 1 unit of DC energy, charge must equal discharge/dc_rte

    This is getting complex. Use the simple, correct formula:

        E_out_poi = P_poi × t_disch

        E_in_poi = ?
        At MV during charge: need to store E_dc = E_out_poi / (dc_to_mv × mv_to_poi × battery_loss)
                            but battery_loss here = dc_rte (round-trip at DC level)
        Hmm, let me think differently.

    Clean approach: compute everything at MV, then convert to POI at the end.
    """
    if chain_dc_to_mv <= 0 or chain_mv_to_poi <= 0 or dc_rte_y <= 0:
        return 0.0

    rte_no_aux = (chain_dc_to_mv * chain_mv_to_poi) ** 2 * dc_rte_y

    if aux_at_mv_mw <= 0 or p_rated_at_poi_mw <= 0:
        return rte_no_aux

    # --- MV-centric energy balance ---
    # Rated power at MV = POI power / MV→POI efficiency
    p_mv = p_rated_at_poi_mw / chain_mv_to_poi

    # Discharge: MV delivers p_mv to POI path, but aux also draws from MV
    # So DC must supply: (p_mv + aux) to MV junction
    # DC power needed = (p_mv + aux) / dc_to_mv_eff
    p_dc_discharge = (p_mv + aux_at_mv_mw) / chain_dc_to_mv

    # Charge: POI pushes power to MV, MV feeds aux + pushes rest to DC
    # At MV: power arriving from POI goes to (a) aux and (b) charging DC
    # DC receives: p_mv_charge × dc_to_mv_eff (MV→DC direction, same efficiency)
    # To charge the battery, DC must receive p_dc_discharge worth of energy
    # over charge time, but charge time = t_disch / dc_rte
    # Actually, energy balance:
    #   E_stored_dc = p_dc_discharge × t_disch  (this is what DC delivered during discharge)
    #   To recharge this: E_charge_dc = E_stored_dc / dc_rte
    #   DC needs to receive: E_charge_dc worth of energy
    #   At MV: must push E_charge_dc / dc_to_mv_eff into DC + feed aux during charge
    t_charge = t_disch / dc_rte_y  # charge takes longer than discharge

    e_stored_dc = p_dc_discharge * t_disch
    e_charge_dc = e_stored_dc / dc_rte_y  # energy needed at DC terminals for recharge
    e_charge_at_mv = e_charge_dc / chain_dc_to_mv  # energy needed at MV to push into DC
    e_aux_charge = aux_at_mv_mw * t_charge          # aux during charge
    e_aux_discharge = aux_at_mv_mw * t_disch         # aux during discharge
    e_aux_rest = aux_at_mv_mw * t_rest               # aux during rest

    # Total energy input at MV = charge energy to DC + all aux
    e_in_at_mv = e_charge_at_mv + e_aux_charge + e_aux_rest

    # Convert MV input to POI: E_in_poi = E_in_mv / mv_to_poi_eff
    e_in_poi = e_in_at_mv / chain_mv_to_poi

    # E_out at POI = P_poi × t_disch
    # But during discharge, aux also comes from MV, reducing what reaches POI
    # Actually no: P_poi is what the grid receives. The aux is already accounted
    # for in p_dc_discharge above. Let me reconsider.
    #
    # During discharge:
    #   DC outputs: p_dc_discharge × dc_to_mv = p_mv + aux  (at MV)
    #   MV splits: aux goes to aux load, p_mv goes to POI path
    #   POI receives: p_mv × mv_to_poi = p_rated_at_poi  ← correct, POI gets full rated
    #
    # So E_out_poi = p_rated_at_poi × t_disch (the grid gets full power)
    e_out_poi = p_rated_at_poi_mw * t_disch

    if e_in_poi <= 0:
        return 0.0

    return e_out_poi / e_in_poi


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

        # --- RTE with aux (MV-centric energy balance) ---
        # Aux is consumed at MV junction. This affects all reference points
        # downstream of MV (i.e., POI). At DC and PCS, aux has no direct impact.
        total_aux_at_mv = (inp.aux_power_at_mv_mw
                           + inp.aux_power_at_pcs_mw
                           + inp.aux_power_at_poi_mw)

        # DC and PCS: no aux impact (aux branches off downstream at MV)
        rte_dc_aux = rte_dc
        rte_pcs_aux = rte_pcs

        # MV: aux comes off here, use MV-centric balance
        chain_mv_to_poi = inp.chain_eff_to_poi / inp.chain_eff_to_mv if inp.chain_eff_to_mv > 0 else 1.0
        rte_mv_aux = _rte_with_aux_at_mv(
            chain_dc_to_mv=inp.chain_eff_to_mv,
            chain_mv_to_poi=1.0,  # MV reference point: mv_to_poi = 1
            dc_rte_y=dc_rte_y,
            t_disch=inp.t_discharge_hr,
            t_rest=inp.t_rest_hr,
            aux_at_mv_mw=total_aux_at_mv,
            p_rated_at_poi_mw=p_mv,  # "POI" here is MV itself
        )

        # POI: full chain including MV→POI segment
        rte_poi_aux = _rte_with_aux_at_mv(
            chain_dc_to_mv=inp.chain_eff_to_mv,
            chain_mv_to_poi=chain_mv_to_poi,
            dc_rte_y=dc_rte_y,
            t_disch=inp.t_discharge_hr,
            t_rest=inp.t_rest_hr,
            aux_at_mv_mw=total_aux_at_mv,
            p_rated_at_poi_mw=p_poi,
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
