# BESS Sizing Tool — 설계 문서 (Design)

> 참조 계획서: `/docs/01-plan/features/bess-sizing-tool.plan.md`
> 작성일: 2026-03-19
> PDCA Phase: Design

---

## Executive Summary

| 관점 | 설명 |
|------|------|
| **Problem** | 사내 BESS 사이징 엑셀(SI Design Tool v1.6.7)이 복잡한 수식 체인, 버전 관리 어려움, 동시 사용 불가 등의 한계. 30개+ 프로젝트에서 수작업으로 반복 사용 중 |
| **Solution** | Python 계산 엔진 + Flask 웹 UI로 전환. 오프라인 우선 설계로 본사 클라우드 PC(Windows, 인터넷 차단)에서 완결적 동작 |
| **Function UX Effect** | 브라우저 기반 탭 입력 → 실시간 계산 → Retention 그래프 시각화 → Excel/PDF 출력. 프로젝트 이력 SQLite 저장/로드 |
| **Core Value** | 엑셀 대비 입력 검증 자동화, 프로젝트 이력 관리, 다중 케이스 비교, 시각적 Augmentation 분석으로 BESS 설계 생산성 향상 |

---

## 1. Module Interface Specifications

### 1.1 공통 타입 및 기반 Dataclass

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ProductType(str, Enum):
    JF2 = "JF2"
    JF3 = "JF3"


class BranchingPoint(str, Enum):
    HV = "HV"
    MV = "MV"


class AltitudeRange(str, Enum):
    BELOW_1000M = "<1000m"
    FROM_1000M  = "1000-2000m"
    ABOVE_2000M = ">2000m"


@dataclass
class EfficiencyChainInput:
    """efficiency.py 입력: 6단계 효율값 + Aux 분기 + Battery Loss 요소"""
    hv_cabling: float          # HV 케이블링 효율 (예: 0.999)
    hv_tr: float               # HV 변압기 효율 (예: 0.995)
    mv_cabling: float          # MV 케이블링 효율 (예: 0.999)
    mv_tr: float               # MV 변압기 효율 (예: 0.989)
    pcs: float                 # PCS 효율 (예: 0.985)
    dc_cabling: float          # DC 케이블링 효율 (예: 0.999)
    branching_point: BranchingPoint  # Aux 분기점 (HV 또는 MV)
    aux_tr: float              # Aux 변압기 효율 (예: 0.985)
    aux_line: float            # Aux 라인 효율 (예: 0.999)
    applied_dod: float         # 적용 DoD (예: 0.99)
    loss_factors: float        # 배터리 손실 계수 (예: 0.98802)
    mbms_consumption: float    # MBMS 소비 계수 (예: 0.999)


@dataclass
class EfficiencyChainOutput:
    """efficiency.py 출력: 효율 체인 전체 결과"""
    total_bat_poi_eff: float           # 배터리-POI 총 효율 (예: 0.96639)
    total_aux_eff: float               # Aux 총 효율
    total_dc_to_aux_eff: float         # DC → Aux 경로 효율 (예: 0.957634)
    total_battery_loss_factor: float   # 배터리 손실 인수 (예: 0.97716)
    total_efficiency: float            # 최종 총 효율 (예: 0.94432)


@dataclass
class PcsSizingInput:
    """pcs_sizing.py 입력"""
    config_name: str           # pcs_config_map.json 키 (예: "EPC_M_JF3_5.5_x2")
    temperature: float         # 운전 온도 °C (25~50 범위)
    altitude: AltitudeRange    # 고도 범위
    mv_voltage_tolerance: float  # MV 전압 허용오차 (예: 0.0)
    required_power_dc: float   # DC 측 필요 출력 MW


@dataclass
class PcsSizingOutput:
    """pcs_sizing.py 출력"""
    manufacturer: str          # 제조사명
    model: str                 # 모델명
    strings_per_pcs: int       # PCS 당 LINK(String) 수
    temp_derated_kva: float    # 온도 디레이팅 후 용량 kVA
    alt_derated_factor: float  # 고도 디레이팅 계수
    pcs_unit_power_mw: float   # PCS 단위 출력 MW (예: 3.15756)
    no_of_pcs: int             # 필요 PCS 수 (예: 39)


@dataclass
class BatterySizingInput:
    """battery_sizing.py 입력"""
    req_power_poi: float           # 요구 출력 @POI MW (예: 100)
    req_energy_poi: float          # 요구 에너지 @POI MWh (예: 400)
    efficiency: EfficiencyChainOutput
    pcs: PcsSizingOutput
    product_type: ProductType      # 배터리 제품 타입
    retention_rate_pct: float      # 초기 Retention 비율 % (예: 60 또는 100)


@dataclass
class BatterySizingOutput:
    """battery_sizing.py 출력"""
    req_power_dc: float            # DC 측 필요 출력 MW (예: 104.345)
    req_energy_dc: float           # DC 측 필요 에너지 MWh (예: 433.21)
    no_of_links: int               # LINK 수 (예: 78)
    no_of_racks: int               # Rack 수 (예: 468)
    installation_energy_dc: float  # 설치 에너지 @DC MWh (예: 433.212)
    cp_rate: float                 # C/P Rate (예: 0.24086)
    dischargeable_energy_poi: float  # 방전 가능 에너지 @POI MWh (예: 405.69)


@dataclass
class RetentionInput:
    """retention.py 입력"""
    cp_rate: float             # C/P Rate (battery_sizing 출력)
    product_type: ProductType  # 배터리 제품 타입
    rest_soc: int              # Rest SOC % (30 또는 40)
    project_life: int          # 프로젝트 수명 년 (예: 20)
    installation_energy_dc: float  # 설치 에너지 @DC MWh
    total_bat_poi_eff: float   # 배터리-POI 효율
    augmentation_schedule: Optional[list[dict]] = field(default_factory=list)
    # 예: [{"year": 10, "type": "A", "qty": 1}, ...]


@dataclass
class RetentionYearEntry:
    """특정 연도의 Retention 데이터"""
    year: int
    retention_pct: float           # Retention % (예: 83.2)
    total_energy_dc: float         # 총 에너지 @DC MWh
    dischargeable_energy_poi: float  # 방전 가능 에너지 @POI MWh
    augmented: bool = False        # 해당 연도에 증설 여부


@dataclass
class RetentionOutput:
    """retention.py 출력"""
    retention_by_year: list[RetentionYearEntry]
    augmentation_events: list[dict]  # 증설 이벤트 목록


@dataclass
class ReactvePowerInput:
    """reactive_power.py 입력"""
    power_poi_mw: float        # POI 유효전력 MW
    power_factor: float        # 역률 (예: 0.95)
    hv_tr_impedance: float     # HV 변압기 임피던스 (예: 0.14)
    mv_tr_impedance: float     # MV 변압기 임피던스
    power_aux_kw: float        # 보조전력 kW
    no_of_pcs: int             # PCS 수
    pcs_unit_kva: float        # PCS 단위 용량 kVA


@dataclass
class ReactivePowerOutput:
    """reactive_power.py 출력"""
    total_s_poi_kva: float     # POI 피상전력 kVA (예: 105,263)
    q_grid_kvar: float         # 계통 무효전력 kVAR (예: 32,868)
    q_hv_tr_kvar: float        # HV 변압기 무효전력 kVAR
    p_mv_kw: float             # MV 유효전력 kW
    q_mv_kvar: float           # MV 무효전력 kVAR
    s_mv_kva: float            # MV 피상전력 kVA
    pf_at_mv: float            # MV 역률 (예: 0.9030)
    total_s_inverter_kva: float  # 인버터 총 피상전력 kVA (예: 116,669)
    available_s_total_kva: float  # PCS 가용 피상전력 kVA (예: 125,658)
    margin_ok: bool            # S_available > S_inverter 여부


@dataclass
class RteInput:
    """rte.py 입력"""
    efficiency: EfficiencyChainOutput
    charge_aux_kw: float       # 충전 시 보조전력 kW
    discharge_aux_kw: float    # 방전 시 보조전력 kW
    energy_throughput_mwh: float  # 에너지 처리량 MWh


@dataclass
class RteOutput:
    """rte.py 출력"""
    charge_efficiency: float   # 충전 경로 효율
    discharge_efficiency: float  # 방전 경로 효율
    rte: float                 # Round-Trip Efficiency (예: 0.8922)


@dataclass
class SocInput:
    """soc.py 입력"""
    cp_rate: float             # C/P Rate
    product_type: ProductType  # 배터리 제품 타입
    rest_soc_pct: int          # Rest SOC 설정 % (30 또는 40)


@dataclass
class SocOutput:
    """soc.py 출력"""
    soc_high: float            # SOC 상한 % (예: 95)
    soc_low: float             # SOC 하한 % (예: 5)
    soc_rest: float            # Rest SOC % (예: 30 또는 40)
    applied_dod: float         # 적용 DoD (soc_high - soc_low) / 100
```

---

### 1.2 efficiency.py

#### 함수 시그니처

```python
def calculate_system_efficiency(
    hv_cabling: float,
    hv_tr: float,
    mv_cabling: float,
    mv_tr: float,
    pcs: float,
    dc_cabling: float,
) -> float:
    """배터리-POI 시스템 효율 계산 (6단계 곱).

    Returns:
        total_bat_poi_eff: 0.0 ~ 1.0 범위의 효율값
    Raises:
        ValueError: 임의 단계 효율이 0.0 이하이거나 1.0 초과인 경우
    """

def calculate_aux_efficiency(
    branching_point: BranchingPoint,
    pcs: float,
    dc_cabling: float,
    aux_tr: float,
    aux_line: float,
    system_eff: float,
) -> tuple[float, float]:
    """Aux 효율 계산. 분기점에 따라 경로가 달라짐.

    Args:
        branching_point: HV 분기 시 전체 체인 포함, MV 분기 시 PCS+DC 경로 포함
    Returns:
        (total_aux_eff, total_dc_to_aux_eff)
    Raises:
        ValueError: branching_point가 HV/MV 외의 값인 경우
    """

def calculate_battery_loss(
    applied_dod: float,
    loss_factors: float,
    mbms_consumption: float,
) -> float:
    """배터리 손실 인수 계산.

    Returns:
        total_battery_loss_factor: 0.0 ~ 1.0 범위
    Raises:
        ValueError: 인수가 0.0 이하이거나 1.0 초과인 경우
    """

def calculate_total_efficiency(
    system_eff: float,
    battery_loss: float,
) -> float:
    """최종 총 효율 계산.

    Returns:
        total_efficiency = system_eff * battery_loss
    """

def calculate_efficiency_chain(inp: EfficiencyChainInput) -> EfficiencyChainOutput:
    """효율 체인 전체를 한 번에 계산하는 통합 진입점."""
```

#### 에러 처리 전략

| 오류 상황 | 예외 타입 | 메시지 패턴 |
|-----------|-----------|-------------|
| 효율값 범위 초과 (≤0 또는 >1) | `ValueError` | `"efficiency '{name}' must be in (0, 1], got {value}"` |
| 알 수 없는 branching_point | `ValueError` | `"Unknown branching_point: {value}"` |

---

### 1.3 pcs_sizing.py

#### 함수 시그니처

```python
def get_pcs_config(config_name: str) -> dict:
    """pcs_config_map.json에서 PCS 구성 조회.

    Returns:
        {"manufacturer": str, "model": str, "strings_per_pcs": int, "unit_kva": float}
    Raises:
        KeyError: config_name이 JSON에 없는 경우
    """

def get_temp_derated_power(
    manufacturer: str,
    temperature: float,
) -> float:
    """온도 디레이팅된 PCS 출력 조회 (kVA).

    Args:
        temperature: 25.0, 30.0, 35.0, 40.0, 45.0, 50.0 중 하나
    Returns:
        온도 디레이팅 후 kVA 용량
    Raises:
        KeyError: manufacturer가 없거나 temperature가 테이블에 없는 경우
        ValueError: temperature가 지원 범위(25~50°C) 밖인 경우
    """

def get_alt_derated_factor(
    manufacturer: str,
    altitude: AltitudeRange,
) -> float:
    """고도 디레이팅 계수 조회.

    Returns:
        0.0 ~ 1.0 범위의 디레이팅 계수 (예: <1000m → 1.0)
    Raises:
        KeyError: manufacturer 또는 altitude_range가 없는 경우
    """

def get_derated_power(
    manufacturer: str,
    model: str,
    temperature: float,
    altitude: AltitudeRange,
    mv_voltage_tolerance: float,
) -> float:
    """온도, 고도, MV 전압 허용오차를 모두 적용한 PCS 단위 출력 MW.

    Returns:
        pcs_unit_power_mw (예: 3.15756)
    Raises:
        ValueError: mv_voltage_tolerance가 0.0 미만이거나 1.0 이상인 경우
    """

def calculate_pcs_count(
    required_power_dc: float,
    pcs_unit_power_mw: float,
    strings_per_pcs: int,
) -> int:
    """LINK 구성을 고려한 PCS 수량 계산.

    Note:
        단순 ceil(required_power / unit_power)가 아님.
        strings_per_pcs(LINKs per PCS)를 고려하여 LINK 단위로 올림 후 PCS 수 결정.
    Returns:
        no_of_pcs (예: 39)
    Raises:
        ValueError: required_power_dc <= 0 또는 pcs_unit_power_mw <= 0인 경우
    """

def size_pcs(inp: PcsSizingInput) -> PcsSizingOutput:
    """PCS 사이징 전체를 한 번에 계산하는 통합 진입점."""
```

#### 에러 처리 전략

| 오류 상황 | 예외 타입 | 메시지 패턴 |
|-----------|-----------|-------------|
| 알 수 없는 config_name | `KeyError` | `"PCS config '{name}' not found in pcs_config_map"` |
| temperature 범위 초과 | `ValueError` | `"temperature {t}°C not in supported range 25-50°C"` |
| 알 수 없는 altitude_range | `KeyError` | `"altitude '{alt}' not found for manufacturer '{mfr}'"` |

---

### 1.4 battery_sizing.py

#### 함수 시그니처

```python
def convert_poi_to_dc(
    power_poi: float,
    energy_poi: float,
    system_eff: float,
    battery_loss: float,
    retention_rate_pct: float = 100.0,
) -> tuple[float, float]:
    """POI 기준 요구사항을 DC 기준으로 변환.

    Returns:
        (req_power_dc, req_energy_dc) in MW, MWh
    Raises:
        ValueError: system_eff 또는 battery_loss가 0 이하인 경우
        ValueError: power_poi 또는 energy_poi가 0 이하인 경우
    """

def calculate_links_and_racks(
    no_of_pcs: int,
    strings_per_pcs: int,
    racks_per_link: int,
) -> tuple[int, int]:
    """LINK 수와 Rack 수 계산.

    Returns:
        (no_of_links, no_of_racks)
        no_of_links = no_of_pcs * strings_per_pcs
        no_of_racks = no_of_links * racks_per_link
    """

def calculate_installation_energy(
    no_of_links: int,
    nameplate_energy_per_link: float,
) -> float:
    """설치 에너지 계산 (LINK 단위 Nameplate Energy 기준).

    Note:
        Rack Energy × Rack 수가 아닌, LINK Nameplate Energy × LINK 수로 계산.
    Returns:
        installation_energy_dc in MWh (예: 433.212)
    """

def calculate_cp_rate(
    power_dc: float,
    installation_energy: float,
) -> float:
    """C/P Rate 계산.

    Returns:
        cp_rate = power_dc / installation_energy (예: 0.24086)
    Raises:
        ValueError: installation_energy <= 0인 경우
    """

def calculate_dischargeable_energy(
    installation_energy: float,
    system_eff: float,
    retention_pct: float,
) -> float:
    """Year 0 기준 방전 가능 에너지 @POI 계산.

    Returns:
        dischargeable_energy_poi in MWh (예: 405.69)
    """

def size_battery(inp: BatterySizingInput) -> BatterySizingOutput:
    """배터리 사이징 전체를 한 번에 계산하는 통합 진입점."""
```

#### 에러 처리 전략

| 오류 상황 | 예외 타입 | 메시지 패턴 |
|-----------|-----------|-------------|
| 효율이 0 이하 | `ValueError` | `"system_eff must be > 0, got {value}"` |
| 설치 에너지가 0 이하 | `ValueError` | `"installation_energy must be > 0"` |
| 알 수 없는 product_type | `KeyError` | `"Product '{type}' not found in products.json"` |

---

### 1.5 retention.py

#### 함수 시그니처

```python
def lookup_retention(
    cp_rate: float,
    product_type: ProductType,
    year: int,
    rest_soc: int,
) -> float:
    """연도별 Retention % 조회.

    Note:
        - JF3 → retention_lookup_inline.json (Design tool 내장 테이블, CP=0.241 기준)
        - JF2 rSOC 40% → retention_table_rsoc40.json
        - 기타 → retention_table_rsoc30.json
        - CP rate가 테이블에 없을 경우 nearest match 또는 linear interpolation 사용
    Returns:
        retention_pct: 0.0 ~ 100.0 범위 (예: 83.2)
    Raises:
        ValueError: year가 0 미만이거나 프로젝트 수명 초과인 경우
        KeyError: product_type이 테이블에 없는 경우
    """

def calculate_retention_curve(
    cp_rate: float,
    product_type: ProductType,
    rest_soc: int,
    project_life: int,
) -> dict[int, float]:
    """전체 프로젝트 기간 Retention 곡선 계산.

    Returns:
        {year: retention_pct} 딕셔너리 (year 0 ~ project_life)
    """

def calculate_augmentation(
    retention_curve: dict[int, float],
    required_energy_poi: float,
    installation_energy_dc: float,
    system_eff: float,
    aug_schedule: list[dict],
) -> dict:
    """Augmentation 계획에 따른 연도별 에너지 계산.

    Args:
        aug_schedule: [{"year": int, "type": str, "qty": int}, ...]
    Returns:
        {
            "retention_by_year": list[RetentionYearEntry],
            "augmentation_events": list[dict],
        }
    Note:
        증설 후 해당 연도부터: 기존 배터리 열화 Retention + 신규 배터리 100% 합산
    """

def calculate_retention(inp: RetentionInput) -> RetentionOutput:
    """Retention 및 Augmentation 전체를 한 번에 계산하는 통합 진입점."""
```

#### 에러 처리 전략

| 오류 상황 | 예외 타입 | 메시지 패턴 |
|-----------|-----------|-------------|
| 지원하지 않는 product_type | `KeyError` | `"No retention table for product '{type}' with rSOC {soc}%"` |
| year 범위 초과 | `ValueError` | `"year {y} out of range [0, {life}]"` |
| aug_schedule year 중복 | `ValueError` | `"Duplicate augmentation year: {year}"` |

---

### 1.6 reactive_power.py

#### 함수 시그니처

```python
def calculate_hv_level(
    power_poi_mw: float,
    power_factor: float,
    hv_tr_impedance: float,
) -> dict:
    """HV 레벨 P/Q/S 계산.

    Returns:
        {"s_poi_kva": float, "q_grid_kvar": float, "q_hv_tr_kvar": float}
    Raises:
        ValueError: power_factor <= 0 또는 power_factor > 1인 경우
    """

def calculate_mv_level(
    hv_results: dict,
    power_aux_kw: float,
    mv_tr_impedance: float,
) -> dict:
    """MV 레벨 P/Q/S 및 역률 계산.

    Returns:
        {"p_mv_kw": float, "q_mv_kvar": float, "s_mv_kva": float, "pf_mv": float}
    """

def calculate_inverter_level(
    mv_results: dict,
    no_of_pcs: int,
    pcs_unit_kva: float,
) -> dict:
    """인버터 레벨 피상전력 및 마진 검증.

    Returns:
        {"s_inverter_kva": float, "available_s_kva": float, "margin_ok": bool}
    """

def calculate_reactive_power(inp: ReactvePowerInput) -> ReactivePowerOutput:
    """무효전력 전체를 한 번에 계산하는 통합 진입점."""
```

#### 에러 처리 전략

| 오류 상황 | 예외 타입 | 메시지 패턴 |
|-----------|-----------|-------------|
| power_factor 범위 초과 | `ValueError` | `"power_factor must be in (0, 1], got {value}"` |
| no_of_pcs <= 0 | `ValueError` | `"no_of_pcs must be > 0"` |

---

### 1.7 rte.py

#### 함수 시그니처

```python
def calculate_charge_path_efficiency(
    hv_cabling: float,
    hv_tr: float,
    mv_cabling: float,
    mv_tr: float,
    pcs: float,
    dc_cabling: float,
) -> float:
    """충전 경로(Grid → Battery) 효율 계산.

    Returns:
        charge_efficiency (같은 6단계 효율 곱)
    """

def calculate_discharge_path_efficiency(
    dc_cabling: float,
    pcs: float,
    mv_tr: float,
    mv_cabling: float,
    hv_tr: float,
    hv_cabling: float,
) -> float:
    """방전 경로(Battery → Grid) 효율 계산.

    Returns:
        discharge_efficiency (역순 6단계 효율 곱)
    """

def calculate_rte(inp: RteInput) -> RteOutput:
    """Round-Trip Efficiency 전체를 한 번에 계산하는 통합 진입점."""
```

---

### 1.8 soc.py

#### 함수 시그니처

```python
def determine_soc_range(
    cp_rate: float,
    product_type: ProductType,
    rest_soc_pct: int,
) -> SocOutput:
    """CP Rate 기반 SOC 범위 결정.

    Note:
        SOC(H), SOC(L), SOC(Rest)를 CP Rate 및 제품 타입별 규정에 따라 결정.
        applied_dod = (soc_high - soc_low) / 100
    Returns:
        SocOutput (soc_high, soc_low, soc_rest, applied_dod)
    Raises:
        ValueError: rest_soc_pct가 30 또는 40이 아닌 경우
    """
```

---

## 2. Data Flow Diagram

### 2.1 모듈 의존성 그래프

```
                     [JSON 참조 데이터]
                     products.json
                     pcs_config_map.json
                     pcs_temp_derating.json
                     pcs_alt_derating.json
                     aux_consumption.json
                     retention_*.json
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
      efficiency.py   pcs_sizing.py  soc.py
              │           │           │
              └─────┬─────┘           │
                    ▼                 │
            battery_sizing.py        │
                    │                 │
                    ├─────────────────┘ (applied_dod → efficiency.py에 피드백)
                    ▼
              retention.py
                    │
              ┌─────┴─────┐
              ▼           ▼
    reactive_power.py   rte.py
              │           │
              └─────┬─────┘
                    ▼
            [결과 조합 → routes.py → UI]
```

### 2.2 단계별 Input → Output 체인

```
[사용자 입력]
  Required Power @POI: 100 MW
  Required Energy @POI: 400 MWh
  Power Factor: 0.95
  Temperature: 45°C
  Altitude: <1000m
  Product: JF3
  PCS Config: EPC_M_JF3_5.5_x2
  Efficiency params (6단계), Aux params, Battery loss params
         │
         ▼
[Step 1] efficiency.py
  IN:  6단계 효율값, branching_point=MV, aux_tr, aux_line, dod, loss_factors, mbms
  OUT: total_bat_poi_eff=0.96639, total_battery_loss_factor=0.97716,
       total_dc_to_aux_eff=0.957634, total_efficiency=0.94432
         │
         │          ┌──────────────────────────────┐
         │          │ [Step 2] pcs_sizing.py        │
         │          │  IN:  config_name, temp=45°C, │
         │          │       altitude=<1000m          │
         │          │  OUT: pcs_unit_power=3.15756  │
         │          │       no_of_pcs=39            │
         │          └──────────────┬───────────────┘
         │                         │
         └─────────┬───────────────┘
                   ▼
[Step 3] battery_sizing.py
  IN:  req_power=100MW, req_energy=400MWh, efficiencies (Step1), pcs (Step2)
  OUT: req_power_dc=104.345 MW, req_energy_dc=433.21 MWh
       no_of_links=78, no_of_racks=468
       installation_energy=433.212 MWh, cp_rate=0.24086
       dischargeable_energy_poi=405.69 MWh
                   │
                   ▼
[Step 4] retention.py
  IN:  cp_rate=0.24086, product=JF3, rest_soc=30, project_life=20
  OUT: retention_by_year={0:100%, 5:90.2%, 10:83.2%, 15:77.4%, 20:72.6%}
       augmentation_events=[]
                   │
          ┌────────┴────────┐
          ▼                 ▼
[Step 5a] reactive_power.py  [Step 5b] rte.py
  IN:  power=100MW, pf=0.95   IN:  efficiency chain (Step1)
  OUT: S_poi=105,263 kVA      OUT: charge_eff, discharge_eff
       Q_grid=32,868 kVAR          rte=0.89xx
       PF_mv=0.9030
       S_inverter=116,669 kVA
          │                 │
          └────────┬────────┘
                   ▼
          [결과 조합 / UI 렌더링]
```

---

## 3. JSON Reference Data Schema

### 3.1 products.json

배터리 제품별 스펙을 정의한다.

```json
{
  "JF3": {
    "product_name": "JF3 0.25 DC LINK",
    "rack_energy_kwh": 793.428,
    "nameplate_energy_mwh": 5.554,
    "racks_per_link": 6,
    "link_voltage_v": 2304,
    "cell_type": "NMC"
  },
  "JF2": {
    "product_name": "JF2 DC LINK",
    "rack_energy_kwh": 744.192,
    "nameplate_energy_mwh": 5.953,
    "racks_per_link": 8,
    "link_voltage_v": 2560,
    "cell_type": "NMC"
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `product_name` | string | 제품 전체 명칭 |
| `rack_energy_kwh` | float | Rack 단위 명판 에너지 kWh |
| `nameplate_energy_mwh` | float | **LINK 단위** 명판 에너지 MWh (계산 기준값) |
| `racks_per_link` | int | LINK당 Rack 수 |
| `link_voltage_v` | float | LINK 전압 V |
| `cell_type` | string | 셀 화학 (NMC 등) |

> 주의: Installation Energy 계산 시 `nameplate_energy_mwh` (LINK 기준) 사용. `rack_energy_kwh * racks_per_link`와 소수점 차이가 있을 수 있음.

---

### 3.2 pcs_config_map.json

7개 PCS 구성 매핑을 정의한다.

```json
{
  "EPC_M_JF3_5.5_x2": {
    "display_name": "EPC Power M 6stc + JF3 5.5 x 2sets",
    "manufacturer": "EPC_Power",
    "model": "M_6stc",
    "strings_per_pcs": 2,
    "unit_kva": 3300
  },
  "EPC_M_JF2_6.0_x2": {
    "display_name": "EPC Power M 6stc + JF2 6.0 x 2sets",
    "manufacturer": "EPC_Power",
    "model": "M_6stc",
    "strings_per_pcs": 2,
    "unit_kva": 3300
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `display_name` | string | UI 표시용 전체 명칭 |
| `manufacturer` | string | 제조사 키 (temp/alt 테이블 참조용) |
| `model` | string | 모델 키 |
| `strings_per_pcs` | int | PCS당 LINK(String) 수 (PCS 수량 계산에 직접 영향) |
| `unit_kva` | float | PCS 정격 용량 kVA (25°C, 해수면 기준) |

> 참고: 총 7개 구성이 있으며, EPC Power M-series + JF3/JF2 조합 중심.

---

### 3.3 pcs_temp_derating.json

제조사·모델별 온도(25~50°C)에 따른 디레이팅된 PCS 출력(kVA)을 정의한다.

```json
{
  "EPC_Power": {
    "M_6stc": {
      "25": 3300,
      "30": 3200,
      "35": 3100,
      "40": 3050,
      "45": 3000,
      "50": 2900
    }
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| 최상위 키 | string | 제조사 키 (`pcs_config_map.manufacturer`와 일치) |
| 2단계 키 | string | 모델 키 (`pcs_config_map.model`과 일치) |
| 3단계 키 | string | 온도 °C (문자열 "25"~"50", 5°C 단위) |
| 값 | float | 해당 온도에서 디레이팅된 kVA 출력 |

> 지원 온도 범위: 25°C ~ 50°C, 5°C 단위. 6개 제조사 포함.

---

### 3.4 pcs_alt_derating.json

고도 범위별 PCS 출력 디레이팅 계수를 정의한다.

```json
{
  "EPC_Power": {
    "<1000m":    1.0,
    "1000-2000m": 0.95,
    ">2000m":    0.90
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| 최상위 키 | string | 제조사 키 |
| 고도 범위 키 | string | `AltitudeRange` Enum 값과 일치 |
| 값 | float | 고도 디레이팅 계수 (1.0 = 디레이팅 없음) |

> 3개 고도 범위. `<1000m`에서는 계수 1.0 적용.

---

### 3.5 aux_consumption.json

보조전력 소비량(Peak/Standby kW)을 제품별로 정의한다.

```json
{
  "JF3": {
    "peak_kw": 120.0,
    "standby_kw": 45.0,
    "description": "JF3 LINK 기준 보조전력"
  },
  "JF2": {
    "peak_kw": 110.0,
    "standby_kw": 40.0,
    "description": "JF2 LINK 기준 보조전력"
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `peak_kw` | float | Peak 운전 시 보조전력 kW |
| `standby_kw` | float | Standby 모드 보조전력 kW |
| `description` | string | 설명 |

---

### 3.6 retention_table_rsoc30.json

rSOC 30% 기준 Retention 룩업 테이블. 48개 CP Rate × 21 Year(Year 0~20).

```json
{
  "cp_rates": [0.10, 0.12, 0.14, ..., 0.50],
  "years": [0, 1, 2, ..., 20],
  "data": {
    "JF2": {
      "0.10": [100.0, 98.5, 97.1, ..., 82.0],
      "0.12": [100.0, 98.3, 96.8, ..., 80.5],
      ...
    }
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `cp_rates` | float[] | 지원 C/P Rate 목록 |
| `years` | int[] | Year 0~20 |
| `data[product][cp_rate][year_idx]` | float | Retention % |

> 보간법: CP rate가 테이블에 없을 경우 nearest match 우선, 필요시 linear interpolation.

---

### 3.7 retention_table_rsoc40.json

rSOC 40% 기준 Retention 룩업 테이블. 38개 CP Rate × 21 Year.

```json
{
  "cp_rates": [0.10, 0.12, ..., 0.45],
  "years": [0, 1, 2, ..., 20],
  "data": {
    "JF2": {
      "0.10": [100.0, 98.8, 97.6, ..., 84.0],
      ...
    }
  }
}
```

스키마는 `retention_table_rsoc30.json`과 동일하며, JF2 rSOC 40% 운전 조건에 해당한다.

---

### 3.8 retention_lookup_inline.json

Design Tool 내장 Retention 테이블. JF3 제품의 CP Rate ≈ 0.241 기준 값. 3개 제품 × 21 Year.

```json
{
  "description": "Design tool inline retention table for JF3 at CP~0.241",
  "cp_rate_ref": 0.241,
  "years": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
  "data": {
    "JF3": [100.0, 97.8, 95.7, 93.6, 91.9, 90.2, 88.6, 87.1, 85.6, 84.4, 83.2,
            82.1, 81.0, 79.9, 78.7, 77.4, 76.3, 75.2, 74.1, 73.3, 72.6],
    "JF2_rsoc30": [...],
    "JF2_rsoc40": [...]
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `description` | string | 테이블 설명 |
| `cp_rate_ref` | float | 이 테이블이 기반하는 CP Rate 참조값 |
| `years` | int[] | Year 0~20 |
| `data[product][year_idx]` | float | Retention % |

> JF3의 경우 이 테이블만 사용. rsoc30/rsoc40 테이블은 JF2에 적용.

---

## 4. Calculation Logic Details

### 4.1 efficiency.py 상세 로직

```python
def calculate_system_efficiency(hv_cabling, hv_tr, mv_cabling, mv_tr, pcs, dc_cabling):
    """6단계 효율 연속 곱."""
    # 검증: 모든 값이 (0, 1] 범위인지 확인
    factors = {
        "hv_cabling": hv_cabling, "hv_tr": hv_tr,
        "mv_cabling": mv_cabling, "mv_tr": mv_tr,
        "pcs": pcs, "dc_cabling": dc_cabling,
    }
    for name, val in factors.items():
        if not (0 < val <= 1.0):
            raise ValueError(f"efficiency '{name}' must be in (0, 1], got {val}")
    return hv_cabling * hv_tr * mv_cabling * mv_tr * pcs * dc_cabling
    # 예: 0.999 * 0.995 * 0.999 * 0.989 * 0.985 * 0.999 = 0.96639


def calculate_aux_efficiency(branching_point, pcs, dc_cabling, aux_tr, aux_line, system_eff):
    """분기점별 Aux 효율 계산.

    MV 분기점:
        total_aux_eff     = aux_tr * aux_line
                          = 0.985 * 0.999 = 0.984015
        total_dc_to_aux   = pcs * dc_cabling * total_aux_eff
                          = 0.985 * 0.999 * 0.984015 = 0.957634

    HV 분기점:
        total_aux_eff     = hv_tr * mv_cabling * mv_tr * pcs * dc_cabling * aux_tr * aux_line
        total_dc_to_aux   = total_aux_eff (전체 경로 포함)
    """
    if branching_point == BranchingPoint.MV:
        total_aux_eff = aux_tr * aux_line
        total_dc_to_aux = pcs * dc_cabling * total_aux_eff
    elif branching_point == BranchingPoint.HV:
        # HV 분기: system_eff 이후 aux 경로만 추가
        total_aux_eff = system_eff * aux_tr * aux_line
        total_dc_to_aux = total_aux_eff
    else:
        raise ValueError(f"Unknown branching_point: {branching_point}")
    return total_aux_eff, total_dc_to_aux


def calculate_battery_loss(applied_dod, loss_factors, mbms_consumption):
    return applied_dod * loss_factors * mbms_consumption
    # 예: 0.99 * 0.98802 * 0.999 = 0.97716


def calculate_total_efficiency(system_eff, battery_loss):
    return system_eff * battery_loss
    # 예: 0.96639 * 0.97716 = 0.94432
```

**검증 기대값 (Golden Test Case 기준)**

| 변수 | 기대값 |
|------|--------|
| `total_bat_poi_eff` | 0.9663891993882308 |
| `total_dc_to_aux_eff` | 0.957634379502525 |
| `total_battery_loss_factor` | 0.9771616602000001 |
| `total_efficiency` | 0.944318 |

---

### 4.2 pcs_sizing.py 상세 로직

```python
def get_derated_power(manufacturer, model, temperature, altitude, mv_voltage_tolerance):
    """
    1. 온도 디레이팅: pcs_temp_derating[manufacturer][model][str(temperature)]
    2. 고도 디레이팅: pcs_alt_derating[manufacturer][altitude]
    3. MV 전압 허용오차 적용:
       derated_kva = temp_kva * alt_factor * (1 - mv_voltage_tolerance)
    4. MW 단위로 변환:
       pcs_unit_power_mw = derated_kva / 1000
    """

def calculate_pcs_count(required_power_dc, pcs_unit_power_mw, strings_per_pcs):
    """
    LINK 기반 PCS 수량 계산:
    1. 최소 LINK 수 = ceil(required_power_dc / (pcs_unit_power_mw / strings_per_pcs))
       # 각 PCS는 strings_per_pcs개의 LINK를 구동
    2. PCS 수 = ceil(최소 LINK 수 / strings_per_pcs)
    3. 실제 LINK 수 = PCS 수 * strings_per_pcs

    예) required=104.345MW, unit=3.15756MW/PCS (=1.57878MW/LINK), strings_per_pcs=2
        최소 LINK = ceil(104.345 / 1.57878) = ceil(66.09) = 67 → 짝수 올림 → 68? → PCS = 34?
        ※ 실제 no_of_pcs=39인 것과 차이: 엑셀 수식 역추적 필요
    """
```

**검증 기대값**

| 변수 | 기대값 |
|------|--------|
| `pcs_unit_power_mw` | 3.15756 |
| `no_of_pcs` | 39 |

> 주의: PCS 수량 계산이 단순 나눗셈이 아닌 엑셀 수식 역추적 필요. `strings_per_pcs=2`, `no_of_pcs=39`이면 `no_of_links=78`.

---

### 4.3 battery_sizing.py 상세 로직

```python
def convert_poi_to_dc(power_poi, energy_poi, system_eff, battery_loss, retention_rate_pct=100.0):
    """
    req_power_dc = power_poi / system_eff
                 = 100 / 0.96639 = 104.345 MW

    req_energy_dc = energy_poi / (system_eff * battery_loss)
                  = 400 / (0.96639 * 0.97716) = 433.21 MWh
    ※ retention_rate_pct 적용 경로 확인 필요:
       test case의 retention_rate_pct=60이 req_energy_dc에 어떻게 반영되는지 분석
    """

def calculate_installation_energy(no_of_links, nameplate_energy_per_link):
    """
    installation_energy_dc = no_of_links * nameplate_energy_mwh
                           = 78 * 5.554 = 433.212 MWh
    ※ Rack 기반 계산 금지: rack_energy_kwh * no_of_racks ≠ 433.212 MWh (소수점 불일치)
    """
```

**검증 기대값**

| 변수 | 기대값 |
|------|--------|
| `req_power_dc` | 104.3446967674908 MW |
| `req_energy_dc` | 417.8121466160309 MWh (retention 60% 적용 전 기준 확인 필요) |
| `no_of_links` | 78 |
| `no_of_racks` | 468 |
| `installation_energy_dc` | 433.212 MWh |
| `cp_rate` | 0.240862895689618 |
| `dischargeable_energy_poi` | 405.692763695218 MWh |

---

### 4.4 retention.py 상세 로직

```python
def lookup_retention(cp_rate, product_type, year, rest_soc):
    """
    테이블 선택 기준:
    - product_type == JF3 → retention_lookup_inline.json
    - product_type == JF2 AND rest_soc == 40 → retention_table_rsoc40.json
    - product_type == JF2 AND rest_soc == 30 → retention_table_rsoc30.json

    CP Rate 보간:
    1. 테이블의 cp_rates 목록에서 입력 cp_rate에 가장 가까운 값 탐색
    2. 정확히 일치하는 값 없을 경우: nearest match 우선, 정확도 필요 시 linear interpolation
       retention = r_low + (cp_rate - cp_low) / (cp_high - cp_low) * (r_high - r_low)
    """

def calculate_augmentation(retention_curve, required_energy_poi,
                            installation_energy_dc, system_eff, aug_schedule):
    """
    증설 로직:
    1. aug_schedule의 각 year에서 신규 배터리 추가
    2. 증설 후 해당 연도의 에너지:
       total = 기존_설치_에너지 * retention(기존_배터리_경과년) + 신규_에너지 * 1.0
    3. 결과는 RetentionYearEntry 목록으로 반환
    """
```

**검증 기대값 (연도별 Retention)**

| Year | Retention % | 총 에너지 @DC (MWh) | 방전 에너지 @POI (MWh) |
|------|------------|--------------------|-----------------------|
| 0 | 100.0 | 433.212 | 405.69 |
| 5 | 90.2 | 390.7 | 365.9 |
| 10 | 83.2 | 360.4 | 337.5 |
| 15 | 77.4 | 335.3 | 314.0 |
| 20 | 72.6 | 314.5 | 294.5 |

---

### 4.5 reactive_power.py 상세 로직

```python
# HV Level
S_poi = P_poi_kw / PF                       # 100,000 / 0.95 = 105,263 kVA
Q_grid = sqrt(S_poi**2 - P_poi_kw**2)       # 32,868 kVAR
Q_hv_tr = S_poi * impedance_hv              # 105,263 * 0.14 = 14,736 kVAR

# MV Level (점진적 손실 누적)
P_mv = P_poi_kw + P_loss_hv + P_aux_kw      # 유효전력 누적
Q_mv = Q_grid + Q_hv_tr + Q_mv_tr           # 무효전력 누적
S_mv = sqrt(P_mv**2 + Q_mv**2)
PF_mv = P_mv / S_mv                         # ≈ 0.9030

# Inverter Level
S_inverter = sqrt(P_mv**2 + Q_mv**2)        # ≈ 116,669 kVA
S_available = no_of_pcs * pcs_unit_kva      # 39 * 3,222 = 125,658 kVA
margin_ok = S_available > S_inverter
```

**검증 기대값**

| 변수 | 기대값 |
|------|--------|
| `total_s_poi_kva` | 105,263.16 |
| `q_grid_kvar` | 32,868.41 |
| `pf_at_mv` | 0.9030 |
| `total_s_inverter_kva` | 116,669.30 |
| `available_s_total_kva` | 125,658 |
| `margin_ok` | True |

---

## 5. Test Specifications

### 5.1 Golden Test Case 구조

**파일**: `backend/data/test_case_jf3_100mw_400mwh.json`
**설명**: JF3 DC LINK Pairing, M12 System, 100MW/400MWh @POI, 45°C, Peak Shifting

**입력값**

| 변수 | 값 |
|------|-----|
| Required Power @POI | 100 MW |
| Required Energy @POI | 400 MWh |
| Power Factor | 0.95 |
| Temperature | 45°C |
| Altitude | <1000m |
| Product | JF3 0.25 DC LINK |
| PCS | EPC Power M 6stc + JF3 5.5 x 2sets |
| MV Voltage Tolerance | 0.0 |
| Branching Point | MV |

**기대 출력값 (±0.1% 허용)**

| 계산 결과 | 기대값 | 담당 모듈 |
|-----------|--------|----------|
| Total Bat-POI Efficiency | 0.96639 | efficiency.py |
| Total Battery Loss Factor | 0.97716 | efficiency.py |
| Total Efficiency | 0.94432 | efficiency.py |
| Required Power @DC | 104.345 MW | battery_sizing.py |
| Required Energy @DC | 433.21 MWh | battery_sizing.py |
| PCS Unit Power | 3.15756 MW | pcs_sizing.py |
| No. of PCS | 39 | pcs_sizing.py |
| No. of LINKs | 78 | battery_sizing.py |
| No. of Racks | 468 | battery_sizing.py |
| Installation Energy @DC | 433.212 MWh | battery_sizing.py |
| CP Rate | 0.24086 | retention.py |
| Dischargeable Energy @POI | 405.69 MWh | battery_sizing.py |
| Retention Y0/Y10/Y20 | 100%/83.2%/72.6% | retention.py |
| Total S @POI | 105,263 kVA | reactive_power.py |
| Total S @Inverter | 116,669 kVA | reactive_power.py |
| PF @MV | 0.9030 | reactive_power.py |

### 5.2 허용 오차 검증 함수

```python
def assert_within_tolerance(actual: float, expected: float, tolerance: float = 0.001) -> None:
    """±0.1% 허용 오차 검증.

    Args:
        actual:    실제 계산값
        expected:  엑셀 기준 기대값
        tolerance: 허용 오차 비율 (기본값 0.001 = 0.1%)
    Raises:
        AssertionError: 오차가 허용 범위 초과 시 상세 메시지 포함
    """
    if expected == 0:
        assert actual == 0, f"Expected 0 but got {actual}"
    else:
        rel_error = abs(actual - expected) / abs(expected)
        assert rel_error <= tolerance, (
            f"Relative error {rel_error:.4%} exceeds ±{tolerance:.1%}. "
            f"actual={actual}, expected={expected}"
        )
```

### 5.3 모듈별 단위 테스트 항목

#### test_efficiency.py

| 테스트 ID | 설명 | 검증 포인트 |
|-----------|------|-------------|
| `test_system_eff_golden` | Golden 입력값으로 6단계 효율 곱 | 0.96639 ±0.1% |
| `test_aux_eff_mv_branch` | MV 분기 Aux 효율 | total_dc_to_aux=0.957634 |
| `test_aux_eff_hv_branch` | HV 분기 Aux 효율 | 다른 경로 합산 |
| `test_battery_loss_golden` | Battery Loss Factor | 0.97716 ±0.1% |
| `test_total_eff_golden` | Total Efficiency | 0.94432 ±0.1% |
| `test_invalid_efficiency_range` | 효율 ≤ 0 또는 > 1 입력 | ValueError 발생 |

#### test_pcs_sizing.py

| 테스트 ID | 설명 | 검증 포인트 |
|-----------|------|-------------|
| `test_temp_derating_45c` | 45°C 온도 디레이팅 | 정확한 kVA 반환 |
| `test_alt_derating_below_1000m` | <1000m 고도 계수 | 1.0 반환 |
| `test_derated_power_golden` | Golden 조건 단위 출력 | 3.15756 MW ±0.1% |
| `test_pcs_count_golden` | Golden 조건 PCS 수 | 39 |
| `test_pcs_count_exact_divisible` | 정확히 나눠떨어지는 경우 | 올림 없이 정확한 값 |
| `test_unknown_config` | 없는 config_name | KeyError 발생 |
| `test_temperature_out_of_range` | 50°C 초과 온도 | ValueError 발생 |

#### test_battery_sizing.py

| 테스트 ID | 설명 | 검증 포인트 |
|-----------|------|-------------|
| `test_poi_to_dc_conversion` | POI → DC 변환 | 104.345 MW, 433.21 MWh ±0.1% |
| `test_links_and_racks_golden` | LINK/Rack 수량 | 78 LINKs, 468 Racks |
| `test_installation_energy_link_based` | LINK 기준 에너지 계산 | 433.212 MWh ±0.1% |
| `test_cp_rate_golden` | CP Rate | 0.24086 ±0.1% |
| `test_dischargeable_energy_golden` | 방전 가능 에너지 @POI | 405.69 MWh ±0.1% |
| `test_installation_energy_not_rack_based` | Rack 기준이면 값 불일치 확인 | 불일치 assertion |

#### test_retention.py

| 테스트 ID | 설명 | 검증 포인트 |
|-----------|------|-------------|
| `test_retention_y0_100pct` | Year 0 Retention | 100.0% |
| `test_retention_jf3_y10` | JF3 Year 10 | 83.2% ±0.1% |
| `test_retention_jf3_y20` | JF3 Year 20 | 72.6% ±0.1% |
| `test_retention_jf3_y5` | JF3 Year 5 | 90.2% ±0.1% |
| `test_cp_rate_interpolation` | CP Rate 보간 | nearest match 또는 선형 보간 |
| `test_augmentation_adds_energy` | 증설 후 에너지 증가 | 기존+신규 합산 |
| `test_augmentation_after_aug_event` | 증설 이후 연도 | 복합 Retention 계산 |

#### test_reactive_power.py

| 테스트 ID | 설명 | 검증 포인트 |
|-----------|------|-------------|
| `test_s_poi_golden` | 피상전력 @POI | 105,263 kVA ±0.1% |
| `test_q_grid_golden` | 계통 무효전력 | 32,868 kVAR ±0.1% |
| `test_pf_at_mv_golden` | MV 역률 | 0.9030 ±0.1% |
| `test_s_inverter_golden` | 인버터 피상전력 | 116,669 kVA ±0.1% |
| `test_margin_ok_true` | 마진 검증 통과 | margin_ok == True |
| `test_invalid_power_factor` | PF > 1 입력 | ValueError 발생 |

### 5.4 통합 테스트 (test_against_excel.py)

```python
def test_full_calculation_golden_case():
    """Golden Test Case 전체 입력 → 전체 출력 교차 검증."""
    with open("backend/data/test_case_jf3_100mw_400mwh.json") as f:
        test_case = json.load(f)

    inp = test_case["inputs"]
    expected = test_case["expected_results"]

    # Step 1: Efficiency
    eff_out = calculate_efficiency_chain(EfficiencyChainInput(**inp["efficiency"]))
    assert_within_tolerance(eff_out.total_bat_poi_eff, expected["total_bat_poi_eff"])

    # Step 2: PCS Sizing
    pcs_out = size_pcs(PcsSizingInput(**inp["pcs"]))
    assert_within_tolerance(pcs_out.pcs_unit_power_mw, expected["pcs_unit_power_mw"])
    assert pcs_out.no_of_pcs == expected["no_of_pcs"]

    # Step 3: Battery Sizing
    bat_out = size_battery(BatterySizingInput(efficiency=eff_out, pcs=pcs_out, **inp["battery"]))
    assert_within_tolerance(bat_out.installation_energy_dc, expected["installation_energy_dc"])
    assert bat_out.no_of_links == expected["no_of_links"]

    # Step 4: Retention
    ret_out = calculate_retention(RetentionInput(cp_rate=bat_out.cp_rate, ...))
    for year, exp_pct in [(0, 100.0), (10, 83.2), (20, 72.6)]:
        actual_pct = ret_out.retention_by_year[year].retention_pct
        assert_within_tolerance(actual_pct, exp_pct)

    # Step 5: Reactive Power
    rp_out = calculate_reactive_power(ReactvePowerInput(**inp["reactive_power"]))
    assert_within_tolerance(rp_out.total_s_poi_kva, expected["total_s_poi_kva"])
    assert rp_out.margin_ok is True
```

### 5.5 Edge Cases

| 케이스 | 대상 모듈 | 처리 방법 |
|--------|-----------|-----------|
| 효율값이 정확히 1.0 | efficiency.py | 정상 처리 (경계값 허용) |
| Temperature = 25°C (최소) | pcs_sizing.py | 테이블 최소값 반환 |
| Temperature = 50°C (최대) | pcs_sizing.py | 테이블 최대값 반환 |
| Temperature = 51°C (초과) | pcs_sizing.py | ValueError |
| Year = 0 Retention | retention.py | 항상 100% |
| CP Rate가 테이블 최솟값 미만 | retention.py | 테이블 최솟값 사용 |
| CP Rate가 테이블 최댓값 초과 | retention.py | 테이블 최댓값 사용 또는 외삽 금지 |
| PCS 수 × unit_power가 정확히 required와 일치 | pcs_sizing.py | 올림 없이 정확한 PCS 수 반환 |
| Augmentation schedule이 빈 리스트 | retention.py | 증설 없는 단순 Retention 곡선 반환 |

---

## 6. API Endpoint Specifications (Phase 3)

### 6.1 전체 사이징 계산

```
POST /api/calculate
Content-Type: application/json
```

**Request Schema**

```json
{
  "project": {
    "name": "string",
    "power_poi_mw": 100.0,
    "energy_poi_mwh": 400.0,
    "power_factor": 0.95,
    "temperature_c": 45.0,
    "altitude": "<1000m",
    "application": "Peak Shifting",
    "project_life_years": 20
  },
  "efficiency": {
    "hv_cabling": 0.999,
    "hv_tr": 0.995,
    "mv_cabling": 0.999,
    "mv_tr": 0.989,
    "pcs": 0.985,
    "dc_cabling": 0.999,
    "branching_point": "MV",
    "aux_tr": 0.985,
    "aux_line": 0.999,
    "applied_dod": 0.99,
    "loss_factors": 0.98802,
    "mbms_consumption": 0.999
  },
  "product": {
    "battery_type": "JF3",
    "pcs_config": "EPC_M_JF3_5.5_x2",
    "rest_soc_pct": 30
  },
  "augmentation": [
    {"year": 10, "type": "A", "qty": 1}
  ]
}
```

**Response Schema**

```json
{
  "status": "ok",
  "results": {
    "efficiency": {
      "total_bat_poi_eff": 0.96639,
      "total_battery_loss_factor": 0.97716,
      "total_dc_to_aux_eff": 0.957634,
      "total_efficiency": 0.94432
    },
    "pcs_sizing": {
      "pcs_unit_power_mw": 3.15756,
      "no_of_pcs": 39
    },
    "battery_sizing": {
      "req_power_dc": 104.345,
      "req_energy_dc": 433.21,
      "no_of_links": 78,
      "no_of_racks": 468,
      "installation_energy_dc": 433.212,
      "cp_rate": 0.24086,
      "dischargeable_energy_poi": 405.69
    },
    "retention": {
      "by_year": [
        {"year": 0, "retention_pct": 100.0, "total_energy_dc": 433.212, "dischargeable_energy_poi": 405.69, "augmented": false},
        {"year": 5, "retention_pct": 90.2, "total_energy_dc": 390.7, "dischargeable_energy_poi": 365.9, "augmented": false}
      ],
      "augmentation_events": []
    },
    "reactive_power": {
      "total_s_poi_kva": 105263.16,
      "q_grid_kvar": 32868.41,
      "pf_at_mv": 0.9030,
      "total_s_inverter_kva": 116669.30,
      "available_s_total_kva": 125658.0,
      "margin_ok": true
    },
    "rte": {
      "charge_efficiency": 0.9664,
      "discharge_efficiency": 0.9664,
      "rte": 0.9340
    }
  }
}
```

**Error Response**

```json
{
  "status": "error",
  "code": "VALIDATION_ERROR",
  "message": "power_factor must be in (0, 1]",
  "field": "project.power_factor"
}
```

---

### 6.2 개별 재계산 엔드포인트

```
POST /api/retention
```

Retention만 재계산 (배터리 구성 변경 없이 CP Rate, project_life만 조정 시).

**Request**: `{"cp_rate": 0.24086, "product_type": "JF3", "rest_soc_pct": 30, "project_life": 20, "augmentation": []}`
**Response**: retention 결과 블록만 반환

---

```
POST /api/reactive-power
```

무효전력만 재계산.

**Request**: ReactvePowerInput 필드 전부
**Response**: reactive_power 결과 블록만 반환

---

```
POST /api/rte
```

RTE만 재계산.

**Request**: RteInput 필드 전부
**Response**: rte 결과 블록만 반환

---

### 6.3 참조 데이터 조회

```
GET /api/products
```

**Response**: `{"products": ["JF2", "JF3"], "details": {...}}`

```
GET /api/pcs-configs
```

**Response**: `{"configs": ["EPC_M_JF3_5.5_x2", ...], "details": {...}}`

---

### 6.4 프로젝트 이력 관리

```
GET  /api/projects              # 전체 목록
POST /api/projects              # 저장
GET  /api/projects/<id>         # 단일 로드
DELETE /api/projects/<id>       # 삭제
```

**프로젝트 저장 Request**

```json
{
  "name": "Site A 100MW Project",
  "inputs": { /* 전체 입력 */ },
  "results": { /* 전체 결과 */ },
  "created_at": "2026-03-19T10:00:00"
}
```

---

### 6.5 출력

```
POST /api/export/excel          # Excel 출력 (binary .xlsx 반환)
POST /api/export/summary        # Summary PDF 출력 (binary .pdf 반환)
```

**Request**: `{"project_id": "uuid"}` 또는 `{"inputs": {...}, "results": {...}}`
**Response**: `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

---

## 7. UI Wireframe Specifications (Phase 3)

### 7.1 5-Tab 입력 폼 레이아웃

```
┌─────────────────────────────────────────────────────────────────┐
│  BESS Sizing Tool                              [저장] [불러오기] │
├─────────────────────────────────────────────────────────────────┤
│  [프로젝트 기본] [효율 설정] [제품 선택] [충방전 패턴] [Augmentation] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TAB 1 — 프로젝트 기본                                           │
│  ┌────────────────┬──────────────────────────────────────────┐  │
│  │ 프로젝트명      │ [입력 필드]                               │  │
│  │ Required Power │ [___] MW      Power Factor │ [0.95]      │  │
│  │ Required Energy│ [___] MWh     Temperature  │ [45] °C     │  │
│  │ Altitude       │ [<1000m ▼]   Application   │ [드롭다운]  │  │
│  │ Project Life   │ [20] years                              │  │
│  └────────────────┴──────────────────────────────────────────┘  │
│                                                                 │
│  TAB 2 — 효율 설정 (기본값 제공, 수정 가능)                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ HV Cabling Eff [0.999]  HV TR Eff    [0.995]          │    │
│  │ MV Cabling Eff [0.999]  MV TR Eff    [0.989]          │    │
│  │ PCS Eff        [0.985]  DC Cabling   [0.999]          │    │
│  │ Branching Point [MV ▼]  Aux TR Eff   [0.985]          │    │
│  │ Aux Line Eff   [0.999]                                │    │
│  │ Applied DoD    [0.99]   Loss Factors [0.98802]        │    │
│  │ MBMS Consump   [0.999]                                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  TAB 3 — 제품 선택                                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Battery Type [JF3 ▼]  → 스펙 자동 로드                  │    │
│  │ PCS Config   [EPC Power M 6stc + JF3 5.5 x 2sets ▼]   │    │
│  │ Rest SOC     [30% ▼]                                   │    │
│  │                                                        │    │
│  │ ┌ 제품 스펙 요약 ───────────────────────────────────┐   │    │
│  │ │ LINK Nameplate: 5.554 MWh  Racks/LINK: 6        │   │    │
│  │ └────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  TAB 4 — 충방전 패턴                                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Cycles/Day [1]    Operating Days/Year [365]           │    │
│  │ SOC High   [95%]  SOC Low [5%]   SOC Rest [30%]      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  TAB 5 — Augmentation (최대 3회)                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ [+ 증설 추가]                                          │    │
│  │ #1  Year [___]  Type [A ▼]  Qty [___]  [삭제]        │    │
│  │ #2  Year [___]  Type [A ▼]  Qty [___]  [삭제]        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│                              [계산 실행]                          │
└─────────────────────────────────────────────────────────────────┘
```

---

### 7.2 결과 Dashboard 레이아웃

```
┌─────────────────────────────────────────────────────────────────┐
│  결과 — Site A 100MW Project                [Excel] [PDF] [수정] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌── 핵심 결과 카드 ───────────────────────────────────────────┐ │
│  │  [No. of PCS]  [No. of LINKs]  [No. of Racks]            │ │
│  │       39             78              468                  │ │
│  │                                                           │ │
│  │  [Install Energy]  [Dischargeable E]  [CP Rate]           │ │
│  │    433.21 MWh        405.69 MWh        0.241              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌── Retention 그래프 ────────────────────────────────────────┐ │
│  │  100% ─┐                                                  │ │
│  │   90%  │ ╲                                                │ │
│  │   80%  │   ╲___________                                  │ │
│  │   70%  │               ╲____                             │ │
│  │        └───────────────────────── Year                   │ │
│  │          0   5   10  15  20                               │ │
│  │        [Augmentation 시점 마커 ▲]                         │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌── 효율 요약 ──────┐  ┌── Reactive Power 요약 ──────────────┐ │
│  │ Total Eff: 94.43%│  │ S @POI:     105,263 kVA           │ │
│  │ RTE:       93.40%│  │ Q Grid:      32,868 kVAR           │ │
│  │                  │  │ PF @MV:          0.903             │ │
│  │                  │  │ S @Inverter: 116,669 kVA           │ │
│  │                  │  │ Margin:       OK (125,658 kVA)     │ │
│  └──────────────────┘  └───────────────────────────────────┘ │
│                                                                 │
│  ┌── 연도별 Retention 테이블 ────────────────────────────────┐  │
│  │ Year │ Retention% │ Energy @DC │ Dischargeable @POI    │  │
│  │  0   │   100.0%   │ 433.2 MWh  │ 405.7 MWh             │  │
│  │  5   │    90.2%   │ 390.7 MWh  │ 365.9 MWh             │  │
│  │  10  │    83.2%   │ 360.4 MWh  │ 337.5 MWh             │  │
│  │  15  │    77.4%   │ 335.3 MWh  │ 314.0 MWh             │  │
│  │  20  │    72.6%   │ 314.5 MWh  │ 294.5 MWh             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Deployment Architecture

### 8.1 오프라인 우선 설계 (Offline-First)

```
본사 클라우드 PC (Windows, 인터넷 차단)
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  deploy/                                                │
│  ├── 01_BESS_SizingTool/          # 전체 소스           │
│  │   ├── backend/                                       │
│  │   │   ├── app/                 # Flask 앱            │
│  │   │   ├── calculators/         # 계산 엔진           │
│  │   │   └── data/                # JSON + SQLite       │
│  │   └── frontend/                # HTML/CSS/JS 번들    │
│  │       └── static/js/           # Chart.js 포함       │
│  ├── wheels/                      # pip wheel 패키지     │
│  │   ├── flask-3.0.x-py3-none-any.whl                  │
│  │   ├── numpy-1.26.4-cp310-win_amd64.whl              │
│  │   └── openpyxl-3.1.2-py3-none-any.whl               │
│  ├── install.bat                  # 자동 설치 스크립트   │
│  └── run.bat                      # 실행 스크립트        │
│                                                         │
│  브라우저 (Edge/Chrome) → http://localhost:5000          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 8.2 install.bat 스크립트

```bat
@echo off
echo Installing BESS Sizing Tool...
python -m pip install --no-index --find-links=./wheels -r ./01_BESS_SizingTool/requirements.txt
echo Installation complete.
pause
```

### 8.3 run.bat 스크립트

```bat
@echo off
cd /d %~dp0\01_BESS_SizingTool
python run.py
```

### 8.4 Wheel 패키징 전략 (Mac에서 Windows용 사전 다운로드)

```bash
# 개발 Mac에서 Windows용 wheel 다운로드
pip download -r requirements.txt \
  --platform win_amd64 \
  --python-version 310 \
  --only-binary=:all: \
  -d ./wheels/

# 확인: 순수 Python 패키지 (C extension 최소화)
# - flask: 순수 Python
# - numpy: C extension → win_amd64 wheel 필수
# - openpyxl: 순수 Python
# - werkzeug, jinja2: 순수 Python
```

### 8.5 외부 리소스 의존성 제거

| 리소스 | 방법 |
|--------|------|
| Chart.js | `frontend/static/js/` 에 번들 (CDN 금지) |
| Bootstrap CSS | 로컬 번들 또는 최소 CSS 직접 작성 |
| Google Fonts | 사용 금지, 시스템 폰트 사용 |
| 외부 API | 없음 (완전 오프라인) |

### 8.6 SQLite 데이터베이스 구조

```sql
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,  -- UUID
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,     -- ISO 8601
    updated_at  TEXT NOT NULL,
    inputs      TEXT NOT NULL,     -- JSON 직렬화
    results     TEXT NOT NULL      -- JSON 직렬화
);

CREATE INDEX idx_projects_created_at ON projects (created_at DESC);
```

### 8.7 성능 목표

| 항목 | 목표 |
|------|------|
| 전체 계산 응답 시간 | 3초 이내 |
| Retention 재계산 | 1초 이내 |
| Excel 출력 생성 | 5초 이내 |
| SQLite 프로젝트 저장/로드 | 1초 이내 |
| 브라우저 초기 로드 | 3초 이내 (로컬 리소스 기준) |

---

## 부록: 엑셀 시트 ↔ Python 모듈 매핑

| 엑셀 시트 | Python 모듈 | Phase |
|-----------|------------|-------|
| Input (효율 파트) | `calculators/efficiency.py` | 1 |
| Input (제품 선택) + Ref_Parameter | `calculators/pcs_sizing.py` | 1 |
| Design tool (배터리 구성) | `calculators/battery_sizing.py` | 1 |
| Design tool (Retention) + Ret Tables | `calculators/retention.py` | 1 |
| Reactive P Calc. | `calculators/reactive_power.py` | 2 |
| RTE | `calculators/rte.py` | 2 |
| SOC | `calculators/soc.py` | 2 |
| Result | `app/routes.py` (결과 조합) | 3 |
| Summary(Proposal) | `templates/summary.html` | 3 |
| Ref_Parameter, Ref_AUX | `data/*.json` (추출 완료) | Done |
