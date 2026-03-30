"""BESS Sizing Tool — PCS Sizing Calculator

Calculates PCS derating and unit power based on temperature, altitude,
and configuration matching the Excel SI Design Tool v1.6.7.

Note on PCS count:
    This module calculates pcs_unit_power_mw and a power-based no_of_pcs.
    The final no_of_pcs used in system sizing is determined by the caller
    (battery_sizing) which takes max(power_based_pcs, energy_based_pcs).
"""
import json
import math
import os
from dataclasses import dataclass
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


@dataclass
class PCSConfig:
    config_name: str
    manufacturer: str
    model: str
    strings_per_pcs: int  # inverter strings per PCS (for power calculation)
    links_per_pcs: int    # battery LINKs per PCS (from "x Nsets" in config name)


@dataclass
class PCSSizingInput:
    pcs_config_name: str      # e.g. "EPC Power M 6stc + JF3 5.5 x 2sets"
    temperature_c: int        # 25-50
    altitude: str             # "<1000", "1000-1500", "1500-2000"
    mv_voltage_tolerance: float  # default 0.02 (2%)


@dataclass
class PCSSizingResult:
    config: PCSConfig
    base_power_kva: float        # Per-string power from temp derating table (kVA)
    temp_derated_kva: float      # Same as base_power_kva (already derated by temp)
    alt_factor: float            # Altitude derating factor (0-1)
    derated_power_kva: float     # Per-PCS power after all derating (kVA)
    pcs_unit_power_mw: float     # Final per-PCS power in MW
    no_of_pcs: int               # Power-based PCS count (ceil of required/unit)
    links_per_pcs: int           # strings_per_pcs from config


def _load_json(filename: str):
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'r') as f:
        return json.load(f)


def get_pcs_config(config_name: str) -> PCSConfig:
    """Look up PCS configuration by config_name."""
    configs = _load_json('pcs_config_map.json')
    _pcs_fields = {f.name for f in PCSConfig.__dataclass_fields__.values()}
    for cfg in configs:
        if cfg['config_name'] == config_name:
            filtered = {k: v for k, v in cfg.items() if k in _pcs_fields}
            return PCSConfig(**filtered)
    raise ValueError(f"PCS config not found: {config_name!r}")


def get_temp_derated_power(model: str, temperature_c: int) -> float:
    """Get temperature-derated PCS power per inverter string in kVA.

    The table covers 25-50°C. M-series stays at 537 kVA until 46°C,
    then derate linearly.
    """
    temp_data = _load_json('pcs_temp_derating.json')
    temp_key = str(temperature_c)
    if temp_key not in temp_data:
        raise ValueError(
            f"Temperature {temperature_c}°C not in derating table. "
            f"Valid range: 25-50°C."
        )
    row = temp_data[temp_key]
    # Try exact model, then fall back to family (e.g. M5/M6 → M-series)
    lookup = model
    if model not in row and model in ('M5', 'M6'):
        lookup = 'M-series'
    if lookup not in row:
        raise ValueError(
            f"Model {model!r} not found in temperature derating table at {temperature_c}°C."
        )
    return float(row[lookup])


def get_altitude_factor(model: str, altitude: str) -> float:
    """Get altitude derating factor for the given model and altitude band.

    The altitude table keys use a '<model>_<voltage>' format, e.g. 'M-series_690'.
    We scan each altitude-band dict for a key that starts with the model name.
    Falls back to 1.0 (no derating) if no matching key is found.
    """
    alt_data = _load_json('pcs_alt_derating.json')
    # Normalize altitude: "<1000m" → "<1000", "1000-1500m" → "1000-1500"
    alt_key = altitude.rstrip('m').strip()
    if alt_key not in alt_data:
        # Try fuzzy match
        for key in alt_data:
            if alt_key.replace('<', '').replace('>', '') in key.replace('<', '').replace('>', ''):
                alt_key = key
                break
        else:
            raise ValueError(
                f"Altitude band {altitude!r} not found. "
                f"Valid values: {list(alt_data.keys())}"
            )
    altitude = alt_key
    # Fall back from specific model (M5/M6) to family (M-series) for key matching
    search_model = model
    if model in ('M5', 'M6'):
        search_model = 'M-series'
    alt_models = alt_data[altitude]
    for key, factor in alt_models.items():
        if key.startswith(search_model):
            return float(factor)
    # No matching entry — assume no altitude derating
    return 1.0


def calculate_pcs_unit_power(
    config: PCSConfig,
    temperature_c: int,
    altitude: str,
    mv_voltage_tolerance: float,
) -> tuple[float, float, float, float]:
    """Compute per-PCS derated power.

    Returns:
        (base_power_kva, alt_factor, derated_power_kva, pcs_unit_power_mw)

    Formula:
        base_power_kva  = temp_derating_table[temp][model]   (per string)
        derated_kva     = base * strings_per_pcs * alt_factor * (1 - mv_tolerance)
        pcs_unit_power  = derated_kva / 1000  [MW]
    """
    base_kva = get_temp_derated_power(config.model, temperature_c)
    alt_factor = get_altitude_factor(config.model, altitude)
    derated_kva = (
        base_kva
        * config.strings_per_pcs
        * alt_factor
        * (1 - mv_voltage_tolerance)
    )
    unit_power_mw = derated_kva / 1000.0
    return base_kva, alt_factor, derated_kva, unit_power_mw


def calculate_pcs_sizing(
    inp: PCSSizingInput,
    required_power_dc_mw: float,
) -> PCSSizingResult:
    """Calculate PCS unit power and a power-constraint-based PCS count.

    Power-based count:
        no_of_pcs = ceil(required_power_dc_mw / pcs_unit_power_mw)

    Important: the caller (battery_sizing) should take
        max(power_based_pcs, energy_based_pcs)
    to arrive at the final system PCS count.
    """
    # --- Input validation ---
    valid_altitudes = {"<1000", "1000-1500", "1500-2000"}
    if not (25 <= inp.temperature_c <= 50):
        raise ValueError(
            f"temperature_c must be between 25 and 50, got {inp.temperature_c}"
        )
    alt_key = inp.altitude.rstrip('m').strip()
    if alt_key not in valid_altitudes:
        raise ValueError(
            f"altitude must be one of {valid_altitudes}, got {inp.altitude!r}"
        )
    if not (0 <= inp.mv_voltage_tolerance <= 1):
        raise ValueError(
            f"mv_voltage_tolerance must be between 0 and 1, got {inp.mv_voltage_tolerance}"
        )
    if required_power_dc_mw <= 0:
        raise ValueError(
            f"required_power_dc_mw must be positive, got {required_power_dc_mw}"
        )
    # --- End validation ---
    config = get_pcs_config(inp.pcs_config_name)

    base_kva, alt_factor, derated_kva, unit_mw = calculate_pcs_unit_power(
        config,
        inp.temperature_c,
        inp.altitude,
        inp.mv_voltage_tolerance,
    )

    no_of_pcs = math.ceil(required_power_dc_mw / unit_mw)

    return PCSSizingResult(
        config=config,
        base_power_kva=base_kva,
        temp_derated_kva=base_kva,
        alt_factor=alt_factor,
        derated_power_kva=derated_kva,
        pcs_unit_power_mw=unit_mw,
        no_of_pcs=no_of_pcs,
        links_per_pcs=config.links_per_pcs,
    )
