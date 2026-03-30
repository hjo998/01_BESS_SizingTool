"""BESS Sizing Tool — Reactive Power Calculator

Calculates reactive power at HV, MV, and Inverter levels,
verifying PCS capacity sufficiency matching the Excel SI Design Tool v1.6.7.
"""
import math
from dataclasses import dataclass


@dataclass
class ReactivePowerInput:
    required_power_poi_mw: float       # e.g. 100 MW
    power_factor: float                # e.g. 0.95
    no_of_pcs: int                     # from battery_sizing.py
    pcs_unit_kva: float                # nameplate kVA per PCS (e.g. 3222 = 6 strings * 537 kVA)
    hv_transformer_eff: float          # e.g. 0.995
    mv_transformer_eff: float           # e.g. 0.993
    lv_cabling_eff: float               # e.g. 0.996
    mv_ac_cabling_eff: float           # e.g. 0.999
    pcs_efficiency: float              # e.g. 0.985
    dc_cabling_eff: float              # e.g. 0.999
    aux_power_peak_mw: float           # from battery_sizing.py
    impedance_hv: float = 0.14        # HV transformer impedance (per-unit)
    impedance_mv: float = 0.08        # MV transformer impedance (per-unit)


@dataclass
class ReactivePowerResult:
    # HV Level
    total_apparent_power_poi_kva: float   # S_poi = P_poi / PF
    grid_kvar: float                      # Q_grid = sqrt(S^2 - P^2)
    hv_tr_kvar: float                     # Q_hv = S_poi * impedance_hv
    p_loss_hv_kw: float                   # P_loss_hv = S_poi * (1 - hv_eff)
    # MV Level
    pf_at_mv: float                       # Power factor at MV bus
    # Inverter Level
    total_s_inverter_kva: float           # Required apparent power from inverters
    available_s_total_kva: float          # Nameplate capacity: no_of_pcs * pcs_unit_kva
    is_pcs_sufficient: bool               # available >= required


def calculate_reactive_power(inp: ReactivePowerInput) -> ReactivePowerResult:
    """Calculate reactive power requirements at HV, MV, and Inverter levels.

    HV Level:
        S_poi = P_poi / PF
        Q_grid = sqrt(S_poi^2 - P_poi^2)
        Q_hv_tr = S_poi * impedance_hv
        P_loss_hv = S_poi * (1 - hv_transformer_eff)

    MV Level:
        P_mv = P_poi + P_loss_hv + P_aux
        Q_mv = Q_grid + Q_hv_tr + Q_mv_tr
        S_mv = sqrt(P_mv^2 + Q_mv^2)
        PF_mv = P_mv / S_mv

    Inverter Level:
        S_inverter = S_mv / (mv_transformer_eff * lv_cabling_eff * mv_ac_cabling_eff)
        available_s = no_of_pcs * pcs_unit_kva
    """
    # --- Input validation ---
    if inp.required_power_poi_mw <= 0:
        raise ValueError(
            f"required_power_poi_mw must be positive, got {inp.required_power_poi_mw}"
        )
    if not (0 < inp.power_factor <= 1):
        raise ValueError(
            f"power_factor must be between 0 and 1 (exclusive), got {inp.power_factor}"
        )
    # --- End validation ---
    p_poi_kw = inp.required_power_poi_mw * 1000.0

    # --- HV Level ---
    s_poi_kva = p_poi_kw / inp.power_factor
    q_grid_kvar = math.sqrt(s_poi_kva ** 2 - p_poi_kw ** 2)
    q_hv_tr_kvar = s_poi_kva * inp.impedance_hv
    p_loss_hv_kw = s_poi_kva * (1.0 - inp.hv_transformer_eff)

    # --- MV Level ---
    p_aux_kw = inp.aux_power_peak_mw * 1000.0
    p_mv_kw = p_poi_kw + p_loss_hv_kw + p_aux_kw

    q_mv_tr_kvar = s_poi_kva * inp.impedance_mv
    q_mv_kvar = q_grid_kvar + q_hv_tr_kvar + q_mv_tr_kvar

    s_mv_kva = math.sqrt(p_mv_kw ** 2 + q_mv_kvar ** 2)
    pf_at_mv = p_mv_kw / s_mv_kva

    # --- Inverter Level ---
    # Back-calculate from MV bus through MV transformer and cabling
    mv_combined_eff = inp.mv_transformer_eff * inp.lv_cabling_eff * inp.mv_ac_cabling_eff
    total_s_inverter_kva = s_mv_kva / mv_combined_eff

    available_s_total_kva = inp.no_of_pcs * inp.pcs_unit_kva

    return ReactivePowerResult(
        total_apparent_power_poi_kva=s_poi_kva,
        grid_kvar=q_grid_kvar,
        hv_tr_kvar=q_hv_tr_kvar,
        p_loss_hv_kw=p_loss_hv_kw,
        pf_at_mv=pf_at_mv,
        total_s_inverter_kva=total_s_inverter_kva,
        available_s_total_kva=available_s_total_kva,
        is_pcs_sufficient=available_s_total_kva >= total_s_inverter_kva,
    )
