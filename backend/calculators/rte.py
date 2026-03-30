"""BESS Sizing Tool — Round-Trip Efficiency Calculator

Calculates charge, discharge, and system round-trip efficiency
matching the Excel SI Design Tool v1.6.7.
"""
from dataclasses import dataclass


@dataclass
class RTEInput:
    total_bat_poi_eff: float          # System efficiency (battery to POI), from efficiency.py
    total_battery_loss_factor: float  # Battery loss factor, from efficiency.py
    battery_dc_rte: float = 0.95     # Battery DC-side round-trip efficiency


@dataclass
class RTEResult:
    charge_efficiency: float     # Grid → Battery (one-way path efficiency)
    discharge_efficiency: float  # Battery → Grid (one-way path efficiency)
    system_rte: float            # Overall round-trip efficiency
    battery_dc_rte: float        # DC-side RTE (pass-through from input)


def calculate_rte(inp: RTEInput) -> RTEResult:
    """Calculate round-trip efficiency for the BESS system.

    Both charge and discharge paths traverse the same efficiency chain:
        Grid ↔ HV ↔ MV ↔ PCS ↔ DC ↔ Battery

    total_bat_poi_eff represents the one-way chain efficiency.

    System RTE formula:
        charge_eff    = total_bat_poi_eff
        discharge_eff = total_bat_poi_eff
        system_rte    = charge_eff * discharge_eff
                        * battery_dc_rte
                        * total_battery_loss_factor
    """
    # --- Input validation ---
    for name, val in [
        ("total_bat_poi_eff", inp.total_bat_poi_eff),
        ("total_battery_loss_factor", inp.total_battery_loss_factor),
        ("battery_dc_rte", inp.battery_dc_rte),
    ]:
        if not (0 < val <= 1):
            raise ValueError(
                f"{name} must be between 0 and 1 (exclusive), got {val}"
            )
    # --- End validation ---
    charge_eff = inp.total_bat_poi_eff
    discharge_eff = inp.total_bat_poi_eff
    system_rte = (
        charge_eff
        * discharge_eff
        * inp.battery_dc_rte
        * inp.total_battery_loss_factor
    )

    return RTEResult(
        charge_efficiency=charge_eff,
        discharge_efficiency=discharge_eff,
        system_rte=system_rte,
        battery_dc_rte=inp.battery_dc_rte,
    )
