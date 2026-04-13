"""BESS Sizing Tool — Power Flow Calculator

Impedance-based power flow model that traces active and reactive power
from the PCS output through LV busway, MVT step-up transformer, MV
collector line, and MPT to the grid Point of Interconnection (POI).

Topology (single line):
  Battery -- DC Cable -- PCS --+-- LV Busway -- MVT --+-- MV Collector -- MPT -- POI
                               |                       |
                    (per powerblock)            MV Bus (+ Aux Branch)

Unlike the simplified efficiency-based model in reactive_power.py, this
module calculates I^2R and I^2X losses explicitly at each stage and
tracks both P and Q through the entire chain.
"""
import math
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Input / Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PowerFlowInput:
    """All parameters needed for a full power-flow calculation."""

    # --- PCS Output ---
    pcs_active_power_mw: float        # P per PCS unit (MW)
    pcs_reactive_power_mvar: float    # Q per PCS unit (MVAr)
    pcs_voltage_kv: float             # PCS output voltage (e.g. 0.69)
    num_pcs: int                      # Total number of PCS
    pcs_unit_kva: float               # Nameplate apparent power per PCS (for capacity check)

    # --- LV Connection (PCS -> MVT, per powerblock) ---
    lv_r_ohm_per_km: float = 0.012
    lv_x_ohm_per_km: float = 0.018
    lv_length_km: float = 0.005       # Default 5 m

    # --- MVT (Step-up Transformer, per unit) ---
    mvt_capacity_mva: float = 100.0
    mvt_efficiency_pct: float = 98.9
    mvt_impedance_pct: float = 6.0
    num_mvt: int = 1

    # --- MV Collector Line ---
    mv_r_ohm_per_km: float = 0.115
    mv_x_ohm_per_km: float = 0.125
    mv_length_km: float = 2.0
    mv_voltage_kv: float = 34.5

    # --- MPT (Main Power Transformer) ---
    mpt_capacity_mva: float = 300.0
    mpt_efficiency_pct: float = 99.65
    mpt_impedance_pct: float = 14.5
    mpt_voltage_hv_kv: float = 154.0

    # --- Aux Branch ---
    aux_power_mw: float = 0.0          # Aux load at 480 V (0 = no aux)
    aux_tr_efficiency_pct: float = 98.5  # Aux transformer efficiency

    # --- Options ---
    direction: str = "discharge"        # "discharge" or "charge"
    buffer_pct: float = 0.0            # PCS capacity buffer (%)


@dataclass
class PowerFlowStage:
    """Result for one stage of the power flow."""

    name: str              # "PCS_OUTPUT", "LV_LINE", "MVT", "MV_BUS", "AUX_BRANCH",
                           # "MV_LINE", "MPT", "POI"
    voltage_kv: float
    p_mw: float            # Active power AFTER this stage
    q_mvar: float          # Reactive power AFTER this stage
    s_mva: float           # Apparent power AFTER this stage
    current_a: float       # Current at this stage
    pf: float              # Power factor at this stage
    p_loss_mw: float       # Active power lost IN this stage
    q_loss_mvar: float     # Reactive power consumed IN this stage


@dataclass
class PowerFlowResult:
    """Comprehensive results of the power-flow calculation."""

    # Stage-by-stage detail (for UI display)
    stages: List[PowerFlowStage]
    direction: str          # "discharge" or "charge"

    # Reference-point summary (for RTE and other modules)
    p_at_pcs: float         # Total P at PCS output (MW)
    q_at_pcs: float
    s_at_pcs: float
    p_at_mv: float          # P at MV bus (after aux deduction if discharge)
    q_at_mv: float
    s_at_mv: float
    p_at_poi: float         # P at grid POI
    q_at_poi: float
    s_at_poi: float

    pf_at_mv: float
    pf_at_poi: float

    # Aux
    aux_power_at_mv_mw: float    # Aux as seen at MV bus (= aux_power / aux_tr_eff)

    # Derived chain efficiencies (P_at_ref / P_at_pcs)
    chain_eff_to_mv: float       # From PCS output to MV bus (after aux)
    chain_eff_to_poi: float      # From PCS output to POI

    # PCS Capacity Check
    total_s_required_mva: float   # Required S from all inverters
    available_s_total_mva: float  # num_pcs * pcs_unit_kva / 1000
    capacity_ratio_pct: float     # (available / required) * 100
    is_pcs_sufficient: bool       # capacity_ratio >= (100 + buffer_pct)

    # Total losses
    total_p_loss_mw: float
    total_q_consumed_mvar: float
    system_efficiency_pct: float  # (P_poi / P_pcs) * 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pf(p: float, s: float) -> float:
    """Return power factor = |P| / S, clamped to [0, 1]."""
    if s == 0.0:
        return 1.0
    return min(abs(p) / s, 1.0)


def _apparent(p: float, q: float) -> float:
    """Return apparent power S = sqrt(P^2 + Q^2)."""
    return math.sqrt(p ** 2 + q ** 2)


def _current_3ph(s_mva: float, v_kv: float) -> float:
    """Three-phase current (A) from apparent power (MVA) and line voltage (kV).

    I = S / (sqrt(3) * V)   where S in VA, V in V
    """
    if v_kv == 0.0:
        return 0.0
    return (s_mva * 1_000_000) / (math.sqrt(3) * v_kv * 1_000)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(inp: PowerFlowInput) -> None:
    """Raise ValueError if any input is out of acceptable range."""
    # Positive-only power values
    if inp.pcs_active_power_mw < 0:
        raise ValueError(
            f"pcs_active_power_mw must be >= 0, got {inp.pcs_active_power_mw}"
        )
    if inp.pcs_unit_kva < 0:
        raise ValueError(
            f"pcs_unit_kva must be >= 0, got {inp.pcs_unit_kva}"
        )
    if inp.aux_power_mw < 0:
        raise ValueError(
            f"aux_power_mw must be >= 0, got {inp.aux_power_mw}"
        )

    # Strictly positive counts and voltages
    if inp.num_pcs <= 0:
        raise ValueError(
            f"num_pcs must be > 0, got {inp.num_pcs}"
        )
    if inp.num_mvt <= 0:
        raise ValueError(
            f"num_mvt must be > 0, got {inp.num_mvt}"
        )
    if inp.pcs_voltage_kv <= 0:
        raise ValueError(
            f"pcs_voltage_kv must be > 0, got {inp.pcs_voltage_kv}"
        )

    # Efficiencies: 0 < val <= 100 (percentage)
    for name, val in [
        ("mvt_efficiency_pct", inp.mvt_efficiency_pct),
        ("mpt_efficiency_pct", inp.mpt_efficiency_pct),
        ("aux_tr_efficiency_pct", inp.aux_tr_efficiency_pct),
    ]:
        if not (0 < val <= 100):
            raise ValueError(
                f"{name} must be between 0 (exclusive) and 100 (inclusive), got {val}"
            )

    # Impedances: >= 0 (percentage)
    for name, val in [
        ("mvt_impedance_pct", inp.mvt_impedance_pct),
        ("mpt_impedance_pct", inp.mpt_impedance_pct),
    ]:
        if val < 0:
            raise ValueError(
                f"{name} must be >= 0, got {val}"
            )

    # Lengths: >= 0
    for name, val in [
        ("lv_length_km", inp.lv_length_km),
        ("mv_length_km", inp.mv_length_km),
    ]:
        if val < 0:
            raise ValueError(
                f"{name} must be >= 0, got {val}"
            )

    # Resistance / reactance: >= 0
    for name, val in [
        ("lv_r_ohm_per_km", inp.lv_r_ohm_per_km),
        ("lv_x_ohm_per_km", inp.lv_x_ohm_per_km),
        ("mv_r_ohm_per_km", inp.mv_r_ohm_per_km),
        ("mv_x_ohm_per_km", inp.mv_x_ohm_per_km),
    ]:
        if val < 0:
            raise ValueError(
                f"{name} must be >= 0, got {val}"
            )

    # Transformer capacities: > 0
    for name, val in [
        ("mvt_capacity_mva", inp.mvt_capacity_mva),
        ("mpt_capacity_mva", inp.mpt_capacity_mva),
    ]:
        if val <= 0:
            raise ValueError(
                f"{name} must be > 0, got {val}"
            )

    # Voltages: > 0
    for name, val in [
        ("mv_voltage_kv", inp.mv_voltage_kv),
        ("mpt_voltage_hv_kv", inp.mpt_voltage_hv_kv),
    ]:
        if val <= 0:
            raise ValueError(
                f"{name} must be > 0, got {val}"
            )

    # Direction
    if inp.direction not in ("discharge", "charge"):
        raise ValueError(
            f"direction must be 'discharge' or 'charge', got '{inp.direction}'"
        )

    # Buffer
    if inp.buffer_pct < 0:
        raise ValueError(
            f"buffer_pct must be >= 0, got {inp.buffer_pct}"
        )


# ---------------------------------------------------------------------------
# Main calculation
# ---------------------------------------------------------------------------

def calculate_power_flow(inp: PowerFlowInput) -> PowerFlowResult:
    """Run a full power-flow calculation from PCS output to POI.

    Stages (discharge direction):
        1. PCS_OUTPUT  — aggregate all PCS units
        2. LV_LINE     — per-powerblock LV busway I^2R / I^2X losses
        3. MVT         — per-powerblock step-up transformer losses
        4. MV_BUS      — aggregate powerblocks at MV bus
        5. AUX_BRANCH  — aux load deduction (discharge) / addition (charge)
        6. MV_LINE     — MV collector line I^2R / I^2X losses
        7. MPT         — main power transformer losses
        8. POI         — final grid injection point

    For charge direction the stages are identical; only the aux branch
    treatment differs (aux adds to the power the grid must supply).
    """
    _validate(inp)

    stages: List[PowerFlowStage] = []

    # ---------------------------------------------------------------
    # Stage 1: PCS Output (aggregation)
    # ---------------------------------------------------------------
    total_pcs_p = inp.pcs_active_power_mw * inp.num_pcs
    total_pcs_q = inp.pcs_reactive_power_mvar * inp.num_pcs
    total_pcs_s = _apparent(total_pcs_p, total_pcs_q)
    pcs_current = _current_3ph(total_pcs_s, inp.pcs_voltage_kv)

    stages.append(PowerFlowStage(
        name="PCS_OUTPUT",
        voltage_kv=inp.pcs_voltage_kv,
        p_mw=total_pcs_p,
        q_mvar=total_pcs_q,
        s_mva=total_pcs_s,
        current_a=pcs_current,
        pf=_safe_pf(total_pcs_p, total_pcs_s),
        p_loss_mw=0.0,
        q_loss_mvar=0.0,
    ))

    # ---------------------------------------------------------------
    # Per-powerblock calculations (LV + MVT)
    # ---------------------------------------------------------------
    # Distribute PCS across MVTs.  If num_pcs is not evenly divisible
    # by num_mvt, the first (num_pcs % num_mvt) powerblocks get one
    # extra PCS each.
    base_pcs_per_mvt = inp.num_pcs // inp.num_mvt
    remainder_pcs = inp.num_pcs % inp.num_mvt

    # Accumulators for aggregate after MVT
    agg_lv_p_loss = 0.0
    agg_lv_q_loss = 0.0
    agg_mvt_p_loss = 0.0
    agg_mvt_q_loss = 0.0
    agg_mvt_out_p = 0.0
    agg_mvt_out_q = 0.0

    for i in range(inp.num_mvt):
        pcs_in_this_pb = base_pcs_per_mvt + (1 if i < remainder_pcs else 0)

        # Per-powerblock PCS output
        pb_p = inp.pcs_active_power_mw * pcs_in_this_pb
        pb_q = inp.pcs_reactive_power_mvar * pcs_in_this_pb
        pb_s = _apparent(pb_p, pb_q)

        # --- LV Busway losses ---
        i_lv = _current_3ph(pb_s, inp.pcs_voltage_kv)

        lv_p_loss = (3.0 * i_lv ** 2 * inp.lv_r_ohm_per_km * inp.lv_length_km) / 1_000_000
        lv_q_loss = (3.0 * i_lv ** 2 * inp.lv_x_ohm_per_km * inp.lv_length_km) / 1_000_000

        lv_out_p = pb_p - lv_p_loss
        lv_out_q = pb_q - lv_q_loss
        lv_out_s = _apparent(lv_out_p, lv_out_q)

        # --- MVT losses ---
        mvt_out_p = lv_out_p * (inp.mvt_efficiency_pct / 100.0)
        mvt_p_loss = lv_out_p - mvt_out_p

        # Q consumption: load-dependent quadratic (Z% model)
        loading_ratio = lv_out_s / inp.mvt_capacity_mva
        mvt_q_loss = (inp.mvt_impedance_pct / 100.0) * inp.mvt_capacity_mva * (loading_ratio ** 2)

        mvt_out_q = lv_out_q - mvt_q_loss
        mvt_out_s = _apparent(mvt_out_p, mvt_out_q)

        # Accumulate
        agg_lv_p_loss += lv_p_loss
        agg_lv_q_loss += lv_q_loss
        agg_mvt_p_loss += mvt_p_loss
        agg_mvt_q_loss += mvt_q_loss
        agg_mvt_out_p += mvt_out_p
        agg_mvt_out_q += mvt_out_q

    # Aggregated post-LV values (for the stage record)
    lv_total_out_p = total_pcs_p - agg_lv_p_loss
    lv_total_out_q = total_pcs_q - agg_lv_q_loss
    lv_total_out_s = _apparent(lv_total_out_p, lv_total_out_q)
    lv_total_current = _current_3ph(lv_total_out_s, inp.pcs_voltage_kv)

    stages.append(PowerFlowStage(
        name="LV_LINE",
        voltage_kv=inp.pcs_voltage_kv,
        p_mw=lv_total_out_p,
        q_mvar=lv_total_out_q,
        s_mva=lv_total_out_s,
        current_a=lv_total_current,
        pf=_safe_pf(lv_total_out_p, lv_total_out_s),
        p_loss_mw=agg_lv_p_loss,
        q_loss_mvar=agg_lv_q_loss,
    ))

    # Aggregated post-MVT values
    mvt_total_out_s = _apparent(agg_mvt_out_p, agg_mvt_out_q)
    mvt_total_current = _current_3ph(mvt_total_out_s, inp.mv_voltage_kv)

    stages.append(PowerFlowStage(
        name="MVT",
        voltage_kv=inp.mv_voltage_kv,
        p_mw=agg_mvt_out_p,
        q_mvar=agg_mvt_out_q,
        s_mva=mvt_total_out_s,
        current_a=mvt_total_current,
        pf=_safe_pf(agg_mvt_out_p, mvt_total_out_s),
        p_loss_mw=agg_mvt_p_loss,
        q_loss_mvar=agg_mvt_q_loss,
    ))

    # ---------------------------------------------------------------
    # Stage 4: MV Bus aggregation (already aggregated above)
    # ---------------------------------------------------------------
    mv_bus_p = agg_mvt_out_p
    mv_bus_q = agg_mvt_out_q
    mv_bus_s = _apparent(mv_bus_p, mv_bus_q)
    mv_bus_current = _current_3ph(mv_bus_s, inp.mv_voltage_kv)

    stages.append(PowerFlowStage(
        name="MV_BUS",
        voltage_kv=inp.mv_voltage_kv,
        p_mw=mv_bus_p,
        q_mvar=mv_bus_q,
        s_mva=mv_bus_s,
        current_a=mv_bus_current,
        pf=_safe_pf(mv_bus_p, mv_bus_s),
        p_loss_mw=0.0,
        q_loss_mvar=0.0,
    ))

    # ---------------------------------------------------------------
    # Stage 5: Aux Branch
    # ---------------------------------------------------------------
    if inp.aux_power_mw > 0.0:
        aux_at_mv = inp.aux_power_mw / (inp.aux_tr_efficiency_pct / 100.0)
    else:
        aux_at_mv = 0.0

    if inp.direction == "discharge":
        mv_after_aux_p = mv_bus_p - aux_at_mv
    else:  # charge
        mv_after_aux_p = mv_bus_p + aux_at_mv

    mv_after_aux_q = mv_bus_q  # Aux is treated as pure P load
    mv_after_aux_s = _apparent(mv_after_aux_p, mv_after_aux_q)
    mv_after_aux_current = _current_3ph(mv_after_aux_s, inp.mv_voltage_kv)

    stages.append(PowerFlowStage(
        name="AUX_BRANCH",
        voltage_kv=inp.mv_voltage_kv,
        p_mw=mv_after_aux_p,
        q_mvar=mv_after_aux_q,
        s_mva=mv_after_aux_s,
        current_a=mv_after_aux_current,
        pf=_safe_pf(mv_after_aux_p, mv_after_aux_s),
        p_loss_mw=aux_at_mv if inp.direction == "discharge" else -aux_at_mv,
        q_loss_mvar=0.0,
    ))

    # ---------------------------------------------------------------
    # Stage 6: MV Collector Line
    # ---------------------------------------------------------------
    i_mv = _current_3ph(mv_after_aux_s, inp.mv_voltage_kv)

    mv_line_p_loss = (3.0 * i_mv ** 2 * inp.mv_r_ohm_per_km * inp.mv_length_km) / 1_000_000
    mv_line_q_loss = (3.0 * i_mv ** 2 * inp.mv_x_ohm_per_km * inp.mv_length_km) / 1_000_000

    mv_out_p = mv_after_aux_p - mv_line_p_loss
    mv_out_q = mv_after_aux_q - mv_line_q_loss
    mv_out_s = _apparent(mv_out_p, mv_out_q)
    mv_out_current = _current_3ph(mv_out_s, inp.mv_voltage_kv)

    stages.append(PowerFlowStage(
        name="MV_LINE",
        voltage_kv=inp.mv_voltage_kv,
        p_mw=mv_out_p,
        q_mvar=mv_out_q,
        s_mva=mv_out_s,
        current_a=mv_out_current,
        pf=_safe_pf(mv_out_p, mv_out_s),
        p_loss_mw=mv_line_p_loss,
        q_loss_mvar=mv_line_q_loss,
    ))

    # ---------------------------------------------------------------
    # Stage 7: MPT (Main Power Transformer)
    # ---------------------------------------------------------------
    mpt_out_p = mv_out_p * (inp.mpt_efficiency_pct / 100.0)
    mpt_p_loss = mv_out_p - mpt_out_p

    mpt_loading_ratio = mv_out_s / inp.mpt_capacity_mva
    mpt_q_loss = (inp.mpt_impedance_pct / 100.0) * inp.mpt_capacity_mva * (mpt_loading_ratio ** 2)

    mpt_out_q = mv_out_q - mpt_q_loss
    mpt_out_s = _apparent(mpt_out_p, mpt_out_q)
    mpt_out_current = _current_3ph(mpt_out_s, inp.mpt_voltage_hv_kv)

    stages.append(PowerFlowStage(
        name="MPT",
        voltage_kv=inp.mpt_voltage_hv_kv,
        p_mw=mpt_out_p,
        q_mvar=mpt_out_q,
        s_mva=mpt_out_s,
        current_a=mpt_out_current,
        pf=_safe_pf(mpt_out_p, mpt_out_s),
        p_loss_mw=mpt_p_loss,
        q_loss_mvar=mpt_q_loss,
    ))

    # ---------------------------------------------------------------
    # Stage 8: POI (grid injection / withdrawal point)
    # ---------------------------------------------------------------
    p_at_poi = mpt_out_p
    q_at_poi = mpt_out_q
    s_at_poi = mpt_out_s
    poi_current = mpt_out_current  # Same as MPT HV side

    stages.append(PowerFlowStage(
        name="POI",
        voltage_kv=inp.mpt_voltage_hv_kv,
        p_mw=p_at_poi,
        q_mvar=q_at_poi,
        s_mva=s_at_poi,
        current_a=poi_current,
        pf=_safe_pf(p_at_poi, s_at_poi),
        p_loss_mw=0.0,
        q_loss_mvar=0.0,
    ))

    # ---------------------------------------------------------------
    # Summary values
    # ---------------------------------------------------------------
    pf_at_mv = _safe_pf(mv_after_aux_p, mv_after_aux_s)
    pf_at_poi = _safe_pf(p_at_poi, s_at_poi)

    # Chain efficiencies
    if total_pcs_p > 0:
        chain_eff_to_mv = mv_after_aux_p / total_pcs_p
        chain_eff_to_poi = p_at_poi / total_pcs_p
    else:
        chain_eff_to_mv = 0.0
        chain_eff_to_poi = 0.0

    # PCS capacity check
    total_s_required_mva = total_pcs_s
    available_s_total_mva = inp.num_pcs * inp.pcs_unit_kva / 1000.0
    if total_s_required_mva > 0:
        capacity_ratio_pct = (available_s_total_mva / total_s_required_mva) * 100.0
    else:
        capacity_ratio_pct = 100.0
    is_pcs_sufficient = capacity_ratio_pct >= (100.0 + inp.buffer_pct)

    # Total losses (sum from all stages, excluding AUX_BRANCH sign flip for charge)
    total_p_loss = agg_lv_p_loss + agg_mvt_p_loss + mv_line_p_loss + mpt_p_loss
    total_q_consumed = agg_lv_q_loss + agg_mvt_q_loss + mv_line_q_loss + mpt_q_loss

    # System efficiency: P at POI / P at PCS
    if total_pcs_p > 0:
        system_efficiency_pct = (p_at_poi / total_pcs_p) * 100.0
    else:
        system_efficiency_pct = 0.0

    return PowerFlowResult(
        stages=stages,
        direction=inp.direction,
        p_at_pcs=total_pcs_p,
        q_at_pcs=total_pcs_q,
        s_at_pcs=total_pcs_s,
        p_at_mv=mv_after_aux_p,
        q_at_mv=mv_after_aux_q,
        s_at_mv=mv_after_aux_s,
        p_at_poi=p_at_poi,
        q_at_poi=q_at_poi,
        s_at_poi=s_at_poi,
        pf_at_mv=pf_at_mv,
        pf_at_poi=pf_at_poi,
        aux_power_at_mv_mw=aux_at_mv,
        chain_eff_to_mv=chain_eff_to_mv,
        chain_eff_to_poi=chain_eff_to_poi,
        total_s_required_mva=total_s_required_mva,
        available_s_total_mva=available_s_total_mva,
        capacity_ratio_pct=capacity_ratio_pct,
        is_pcs_sufficient=is_pcs_sufficient,
        total_p_loss_mw=total_p_loss,
        total_q_consumed_mvar=total_q_consumed,
        system_efficiency_pct=system_efficiency_pct,
    )
