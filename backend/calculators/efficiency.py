"""BESS Sizing Tool — Efficiency Chain Calculator

Calculates system efficiency, auxiliary efficiency, and battery loss factor
matching the Excel SI Design Tool v1.6.7.
"""
from dataclasses import dataclass
from typing import Literal


@dataclass
class SystemEfficiencyInput:
    hv_ac_cabling: float      # default 0.999
    hv_transformer: float     # default 0.995
    mv_ac_cabling: float      # default 0.999
    mv_transformer: float     # default 0.993
    lv_cabling: float         # default 0.996
    pcs_efficiency: float     # default 0.985
    dc_cabling: float         # default 0.999


@dataclass
class AuxEfficiencyInput:
    branching_point: Literal["HV", "MV"]  # Where aux power branches off
    aux_tr_lv: float          # default 0.985 (for MV branching)
    aux_line_lv: float        # default 0.999


@dataclass
class BatteryLossInput:
    applied_dod: float        # default 0.99
    loss_factors: float       # default 0.98802
    mbms_consumption: float   # default 0.999


@dataclass
class EfficiencyResult:
    total_bat_poi_eff: float          # System efficiency chain product
    total_aux_eff: float              # Aux efficiency based on branching point
    total_dc_to_aux_eff: float        # DC to Aux combined efficiency
    total_battery_loss_factor: float  # Battery loss factor
    total_efficiency: float           # total_bat_poi * total_battery_loss


def calculate_system_efficiency(inp: SystemEfficiencyInput) -> float:
    """Calculate total Battery-to-POI system efficiency.
    Product of all 6 efficiency stages.
    """
    return (inp.hv_ac_cabling * inp.hv_transformer * inp.mv_ac_cabling *
            inp.mv_transformer * inp.lv_cabling * inp.pcs_efficiency * inp.dc_cabling)


def calculate_aux_efficiency(aux_inp: AuxEfficiencyInput, sys_inp: SystemEfficiencyInput) -> tuple:
    """Calculate auxiliary power efficiency based on branching point.

    Returns: (total_aux_eff, total_dc_to_aux_eff)

    MV branching: aux_tr_lv * aux_line_lv
    HV branching: hv_transformer * mv_ac_cabling * mv_tr * aux_tr_lv * aux_line_lv

    total_dc_to_aux = dc_cabling * pcs * ... * total_aux_eff
    """
    if aux_inp.branching_point == "MV":
        total_aux_eff = aux_inp.aux_tr_lv * aux_inp.aux_line_lv
        # DC to Aux: DC → PCS → LV Cable → MV TR → Aux TR → Aux Line
        total_dc_to_aux = (sys_inp.dc_cabling * sys_inp.pcs_efficiency *
                           sys_inp.lv_cabling * sys_inp.mv_transformer *
                           aux_inp.aux_tr_lv * aux_inp.aux_line_lv)
    else:  # HV
        total_aux_eff = (sys_inp.hv_transformer * sys_inp.mv_ac_cabling *
                         sys_inp.mv_transformer * sys_inp.lv_cabling *
                         aux_inp.aux_tr_lv * aux_inp.aux_line_lv)
        # DC to Aux: DC → PCS → LV Cable → MV TR → MV Cable → HV TR → Aux TR → Aux Line
        total_dc_to_aux = (sys_inp.dc_cabling * sys_inp.pcs_efficiency *
                           sys_inp.lv_cabling * sys_inp.mv_transformer *
                           sys_inp.mv_ac_cabling *
                           sys_inp.hv_transformer *
                           aux_inp.aux_tr_lv * aux_inp.aux_line_lv)

    return total_aux_eff, total_dc_to_aux


def calculate_battery_loss(inp: BatteryLossInput) -> float:
    """Calculate total battery loss factor."""
    return inp.applied_dod * inp.loss_factors * inp.mbms_consumption


def calculate_all(sys_inp: SystemEfficiencyInput,
                  aux_inp: AuxEfficiencyInput,
                  bat_inp: BatteryLossInput) -> EfficiencyResult:
    """Calculate all efficiency values."""
    # --- Input validation ---
    for name, val in [
        ("hv_ac_cabling", sys_inp.hv_ac_cabling),
        ("hv_transformer", sys_inp.hv_transformer),
        ("mv_ac_cabling", sys_inp.mv_ac_cabling),
        ("mv_transformer", sys_inp.mv_transformer),
        ("lv_cabling", sys_inp.lv_cabling),
        ("pcs_efficiency", sys_inp.pcs_efficiency),
        ("dc_cabling", sys_inp.dc_cabling),
        ("aux_tr_lv", aux_inp.aux_tr_lv),
        ("aux_line_lv", aux_inp.aux_line_lv),
        ("applied_dod", bat_inp.applied_dod),
        ("loss_factors", bat_inp.loss_factors),
        ("mbms_consumption", bat_inp.mbms_consumption),
    ]:
        if not (0 < val <= 1):
            raise ValueError(
                f"{name} must be between 0 and 1 (exclusive), got {val}"
            )
    # --- End validation ---
    total_bat_poi = calculate_system_efficiency(sys_inp)
    total_aux, total_dc_to_aux = calculate_aux_efficiency(aux_inp, sys_inp)
    total_bat_loss = calculate_battery_loss(bat_inp)
    total_eff = total_bat_poi * total_bat_loss

    return EfficiencyResult(
        total_bat_poi_eff=total_bat_poi,
        total_aux_eff=total_aux,
        total_dc_to_aux_eff=total_dc_to_aux,
        total_battery_loss_factor=total_bat_loss,
        total_efficiency=total_eff
    )
