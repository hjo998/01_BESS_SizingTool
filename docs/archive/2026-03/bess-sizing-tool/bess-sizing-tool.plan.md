# BESS Sizing Tool — 강화 계획서

> 원본: `/Users/alex/Projects/LG_ImprovWrkEff/01_BESS_SizingTool/HANDOFF_TO_CLAUDE_CODE.md`
> 작성일: 2026-03-19
> PDCA Phase: Plan

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | BESS Sizing Tool (Excel → Python/Flask 웹 전환) |
| 시작일 | 2026-03-19 |
| 예상 기간 | Phase 1: 3~4일, Phase 2: 2일, Phase 3: 3일, Phase 4: 2일 (총 ~12일) |

### Value Delivered (4 관점)

| 관점 | 설명 |
|------|------|
| **Problem** | 사내 BESS 사이징 엑셀(SI Design Tool v1.6.7)이 복잡한 수식 체인, 버전 관리 어려움, 동시 사용 불가 등의 한계. 30개+ 프로젝트에서 수작업으로 반복 사용 중 |
| **Solution** | Python 계산 엔진 + Flask 웹 UI로 전환. 오프라인 우선 설계로 본사 클라우드 PC(Windows, 인터넷 차단)에서 완결적 동작 |
| **Function UX Effect** | 브라우저 기반 탭 입력 → 실시간 계산 → Retention 그래프 시각화 → Excel/PDF 출력. 프로젝트 이력 SQLite 저장/로드 |
| **Core Value** | 엑셀 대비 입력 검증 자동화, 프로젝트 이력 관리, 다중 케이스 비교, 시각적 Augmentation 분석으로 BESS 설계 생산성 향상 |

---

## 1. 프로젝트 개요

### 1.1 목표
LG Energy Solution 사내 BESS 사이징 엑셀 도구(SI Design Tool ver1.6.7)의 **계산 로직을 Python으로 정확히 이식**하고, **Flask 웹 UI**를 통해 제공한다.

### 1.2 핵심 제약조건

| 제약 | 상세 |
|------|------|
| **타겟 환경** | 본사 클라우드 PC (Windows, 오프라인, 브라우저 사용 가능) |
| **네트워크** | 인터넷 차단 — 외부 CDN 의존 금지, 모든 리소스 번들 |
| **배포 방식** | pip wheel 오프라인 설치 (Teams 경유 폴더 전달) |
| **DB** | SQLite (설치 불필요, 단일 파일) |
| **정확도** | 엑셀 결과 대비 ±0.1% 이내 (교차 검증 필수) |

### 1.3 기존 준비 상태

| 항목 | 상태 |
|------|------|
| 프로젝트 폴더 구조 | ✅ 생성 완료 |
| JSON 참조 데이터 8개 | ✅ 엑셀에서 추출 완료 |
| 테스트 케이스 (Golden Test) | ✅ `test_case_jf3_100mw_400mwh.json` |
| requirements.txt | ✅ Flask 3.0, NumPy 1.26.4, openpyxl 3.1.2 |
| 설계 문서 | ✅ `docs/DESIGN.md` 완성 |
| Python 코드 | ❌ 없음 — 모든 코드 신규 작성 필요 |

---

## 2. 아키텍처 설계

### 2.1 전체 모듈 구조

```
01_BESS_SizingTool/
├── backend/
│   ├── app/
│   │   ├── __init__.py          # Flask 앱 팩토리
│   │   ├── main.py              # 진입점 (create_app)
│   │   ├── routes.py            # REST API 엔드포인트
│   │   └── models.py            # SQLite ORM (프로젝트 이력)
│   ├── calculators/
│   │   ├── __init__.py          # 계산 모듈 통합 인터페이스
│   │   ├── efficiency.py        # 효율 체인 (System + Aux + Battery Loss)
│   │   ├── pcs_sizing.py        # PCS 디레이팅 + 수량 결정
│   │   ├── battery_sizing.py    # 배터리 구성 (LINK/Rack/Energy)
│   │   ├── retention.py         # 연도별 Retention + Augmentation
│   │   ├── reactive_power.py    # 무효전력 (HV/MV/Inverter)
│   │   ├── rte.py               # Round-Trip Efficiency
│   │   └── soc.py               # SOC 범위 결정
│   └── data/                    # ✅ JSON 참조 데이터 (준비 완료)
├── frontend/
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/
│   │       ├── app.js           # 메인 로직
│   │       ├── input_form.js    # 탭 폼 제어
│   │       ├── charts.js        # Retention/RTE 차트
│   │       └── export.js        # Excel/PDF 출력
│   └── templates/
│       ├── base.html            # 레이아웃
│       ├── input.html           # 입력 (5 탭)
│       ├── result.html          # 결과 + 차트
│       └── summary.html         # 제안서 요약
├── tests/
│   ├── test_efficiency.py
│   ├── test_pcs_sizing.py
│   ├── test_battery_sizing.py
│   ├── test_retention.py
│   ├── test_reactive_power.py
│   └── test_against_excel.py    # 통합 교차 검증
├── run.py
└── requirements.txt
```

### 2.2 계산 흐름 (Data Flow)

```
[사용자 입력]
    │
    ▼
┌─────────────────────┐
│  efficiency.py       │ → Total Bat-POI Eff, Aux Eff, Battery Loss Factor
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  pcs_sizing.py       │ → Derated PCS Power, No. of PCS
│  (temp/alt derating) │
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  battery_sizing.py   │ → Req P/E @DC, No. of LINKs, Racks, Install Energy
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  retention.py        │ → CP Rate, 연도별 Retention%, Augmentation
└────────┬────────────┘
         ▼
┌────────┴────────────────────────────┐
│                                      │
▼                                      ▼
┌──────────────────┐    ┌──────────────────┐
│ reactive_power.py │    │     rte.py        │
│ (HV/MV/Inverter) │    │ (Round-Trip Eff)  │
└──────────────────┘    └──────────────────┘
         │                        │
         └────────┬───────────────┘
                  ▼
          [Result 조합 → UI 렌더링]
```

### 2.3 API 설계

```
POST /api/calculate           # 전체 사이징 계산 (Phase 1+2 통합)
POST /api/retention           # Retention만 재계산
POST /api/reactive-power      # 무효전력만 재계산
POST /api/rte                 # RTE만 재계산
GET  /api/products            # 제품 스펙 목록
GET  /api/pcs-configs         # PCS 구성 목록
GET  /api/projects            # 저장된 프로젝트 목록
POST /api/projects            # 프로젝트 저장
GET  /api/projects/<id>       # 프로젝트 로드
POST /api/export/excel        # Excel 출력
POST /api/export/summary      # Summary PDF 출력
```

---

## 3. 개발 Phase 상세 (강화)

### Phase 1: 계산 엔진 코어 (최우선)

**목표**: 엑셀과 ±0.1% 이내 동일한 계산 결과를 Python으로 재현

#### Step 1-1: `efficiency.py` — 효율 체인

| 항목 | 내용 |
|------|------|
| **입력** | 6단계 효율값 (HV Cabling ~ DC Cabling), Aux 분기점, Battery Loss 3요소 |
| **출력** | `total_bat_poi_eff`, `total_aux_eff`, `total_dc_to_aux_eff`, `total_battery_loss_factor`, `total_efficiency` |
| **핵심 로직** | |

```python
# System Efficiency Chain
total_bat_poi_eff = hv_cabling * hv_tr * mv_cabling * mv_tr * pcs * dc_cabling
# 0.999 * 0.995 * 0.999 * 0.989 * 0.985 * 0.999 = 0.96639

# Aux Efficiency (MV branching point 기준)
total_aux_eff_mv = aux_tr_lv * aux_line_lv  # 0.985 * 0.999 = 0.984015
total_dc_to_aux = pcs * dc_cabling * total_aux_eff  # 경로별 계산

# Battery Loss Factor
total_bat_loss = applied_dod * loss_factors * mbms_consumption
# 0.99 * 0.98802 * 0.999 = 0.97716

# Total Efficiency
total_eff = total_bat_poi_eff * total_bat_loss  # 0.96639 * 0.97716 = 0.94432
```

| 검증 기대값 | |
|-------------|---|
| `total_bat_poi` | 0.9663891993882308 |
| `total_battery_loss_factor` | 0.9771616602000001 |
| `total_efficiency_up_to_poi` | 0.944318 |

**주의사항**:
- Aux 효율은 Branching Point(HV/MV)에 따라 경로가 다름
- MV 분기 시와 HV 분기 시 적용되는 단계가 다름
- `total_dc_to_aux_eff = 0.957634379502525` (MV 분기 기준)

#### Step 1-2: `pcs_sizing.py` — PCS 사이징

| 항목 | 내용 |
|------|------|
| **입력** | PCS config name, temperature, altitude, MV voltage tolerance |
| **출력** | `derated_pcs_power_mw`, `no_of_pcs` |
| **참조 데이터** | `pcs_config_map.json`, `pcs_temp_derating.json`, `pcs_alt_derating.json` |

```python
# 1. PCS config에서 제조사/모델 식별
config = pcs_config_map[pcs_type]  # manufacturer, model, strings_per_pcs

# 2. 온도 디레이팅 조회
temp_power_kva = pcs_temp_derating[manufacturer][temperature]  # @45°C

# 3. 고도 디레이팅
alt_factor = pcs_alt_derating[manufacturer][altitude]  # <1000m → 1.0

# 4. MV 전압 허용오차
derated_power_mw = temp_power_kva * alt_factor * (1 - mv_voltage_tolerance) / 1000

# 5. PCS 수량 (strings_per_pcs 고려)
# ※ 주의: 단순 ceil(req_power / unit_power)가 아닐 수 있음
# config의 strings_per_pcs와 LINK 구성이 영향
```

| 검증 기대값 | |
|-------------|---|
| `pcs_unit_power_mw` | 3.15756 |
| `no_of_pcs` | 39 |

**주의사항**:
- PCS 수량 결정은 단순 나눗셈이 아님. `strings_per_pcs` (= LINKs per PCS)가 영향
- 현재 예시: 2 LINKs/PCS → PCS 수 × 2 = LINK 수
- `pcs_config_map.json`의 `strings_per_pcs` 필드 확인 필수

#### Step 1-3: `battery_sizing.py` — 배터리 구성

| 항목 | 내용 |
|------|------|
| **입력** | req_power/energy @POI, efficiencies, product specs, no_of_pcs |
| **출력** | `req_power_dc`, `req_energy_dc`, `no_of_links`, `no_of_racks`, `installation_energy_dc`, `dischargeable_energy_poi` |
| **참조 데이터** | `products.json` |

```python
# 1. POI → DC 변환
req_power_dc = req_power_poi / total_bat_poi_eff
req_energy_dc = req_energy_poi / (total_bat_poi_eff * total_bat_loss)
# 100/0.9664 = 104.345 MW, 400/(0.9664*0.9772) = 433.21 MWh

# 2. LINK/Rack 수량
no_of_links = no_of_pcs * links_per_pcs  # 39 * 2 = 78
racks_per_link = product["racks_per_link"]  # JF3: 6
no_of_racks = no_of_links * racks_per_link  # 78 * 6 = 468

# 3. Installation Energy (LINK 단위 Nameplate Energy 기준!)
installation_energy_dc = no_of_links * product["nameplate_energy_mwh"]
# 78 * 5.554 = 433.212 MWh  ← Rack Energy가 아닌 LINK Nameplate!

# 4. Dischargeable Energy @POI
dischargeable_energy_poi = installation_energy_dc * total_bat_poi_eff * retention_y0
```

| 검증 기대값 | |
|-------------|---|
| `req_power_dc` | 104.3446967674908 MW |
| `req_energy_dc` | 417.8121466160309 MWh (※ `retention_rate` 60% 적용 시 다를 수 있음) |
| `no_of_links` | 78 |
| `qty_of_racks` | 468 |
| `installation_energy_dc` | 433.212 MWh |
| `cp_rate_dc` | 0.240862895689618 |
| `dischargeable_energy_poi` | 405.692763695218 MWh |

**핵심 주의사항**:
- Installation Energy는 **LINK 단위 Nameplate Energy** (5.554 MWh)로 계산, Rack Energy (793.428 kWh) × Rack 수가 아님
- `req_energy_dc`에 `retention_rate_pct: 60`이 적용되는 경로 확인 필요
- CP Rate = `req_power_dc / installation_energy_dc`

#### Step 1-4: `retention.py` — 연도별 열화

| 항목 | 내용 |
|------|------|
| **입력** | CP rate, product type, rest SOC, project_life |
| **출력** | `retention_by_year` (Year 0~20+), Augmentation 시점/수량 |
| **참조 데이터** | `retention_table_rsoc30.json`, `retention_table_rsoc40.json`, `retention_lookup_inline.json` |

```python
# 1. CP Rate 계산
cp_rate = req_power_dc / installation_energy_dc  # 0.24086

# 2. Retention Table 조회 (CP rate 기준 nearest match 또는 interpolation)
# JF3 → retention_lookup_inline.json (Design tool 내장 테이블)
# JF2 rSOC 40% → retention_table_rsoc40.json
# 기타 → retention_table_rsoc30.json

# 3. 연도별 Dischargeable Energy 계산
for year in range(0, project_life + 1):
    retention_pct = lookup_retention(cp_rate, product, year)
    total_energy = installation_energy * retention_pct / 100
    disc_energy_poi = total_energy * total_bat_poi_eff

# 4. Augmentation 로직
# 특정 년도에 Retention이 요구 에너지 비율 이하로 하락 시 증설
# 증설 후: 기존 배터리(열화된 Retention) + 신규 배터리(100%) 합산
```

| 검증 기대값 (연도별) | |
|---------------------|---|
| Year 0 | 100%, 433.2 MWh, 405.6 MWh @POI |
| Year 5 | 90.2%, 390.7 MWh, 365.9 MWh @POI |
| Year 10 | 83.2%, 360.4 MWh, 337.5 MWh @POI |
| Year 15 | 77.4%, 335.3 MWh, 314.0 MWh @POI |
| Year 20 | 72.6%, 314.5 MWh, 294.5 MWh @POI |

### Phase 2: Reactive Power + RTE

#### Step 2-1: `reactive_power.py`

```python
# HV Level
S_poi = P_poi / PF  # 100MW / 0.95 = 105,263 kVA
Q_grid = sqrt(S_poi**2 - P_poi**2)  # 32,868 kVAR
Q_hv_tr = S_poi * impedance_hv  # 105,263 * 0.14 = 14,736 kVAR

# MV Level (점진적 손실 누적)
P_mv = P_poi + P_loss_hv + P_aux
Q_mv = Q_grid + Q_hv_tr + Q_mv_tr
S_mv = sqrt(P_mv**2 + Q_mv**2)
PF_mv = P_mv / S_mv  # ~0.903

# Inverter Level
S_inverter = 116,669 kVA  # 최종 Apparent Power
S_available = no_of_pcs * pcs_unit_kva  # 이것보다 커야 OK
```

| 검증 기대값 | |
|-------------|---|
| `total_apparent_power_poi_kva` | 105,263.16 |
| `grid_kvar` | 32,868.41 |
| `pf_at_mv` | 0.9030 |
| `total_s_inverter_kva` | 116,669.30 |
| `available_s_total_kva` | 125,658 |

#### Step 2-2: `rte.py`

- 충전 경로: Grid → HV → MV → PCS → DC → Battery
- 방전 경로: Battery → DC → PCS → MV → HV → Grid
- RTE = 방전 에너지 / 충전 에너지 (양방향 효율 적용)

#### Step 2-3: `soc.py`

- CP Rate 기반 SOC 범위 결정
- SOC(H), SOC(L), SOC(Rest) 계산

### Phase 3: Flask 웹 UI

#### Step 3-1: Flask 앱 구조

```python
# app/__init__.py — Factory Pattern
def create_app():
    app = Flask(__name__,
                template_folder='../../frontend/templates',
                static_folder='../../frontend/static')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data/db/sizing.db'
    return app
```

#### Step 3-2: 입력 화면 (5 탭)

| 탭 | 내용 |
|----|------|
| 프로젝트 기본 | 프로젝트명, Power, Energy, PF, 온도, 고도, Application |
| 효율 설정 | 6단계 효율 체인 (기본값 제공, 수정 가능) |
| 제품 선택 | Battery Type (드롭다운), PCS Type (드롭다운) → 자동 스펙 로드 |
| 충방전 패턴 | Cycle/day, SOC 범위, 운전일수 |
| Augmentation | 증설 년도, 타입, 수량 (최대 3회) |

#### Step 3-3: 결과 화면

- 상단: 핵심 수치 카드 (LINK 수, PCS 수, 설치 에너지 등)
- 중단: Retention 그래프 (Chart.js, 번들) + Augmentation 시점 표시
- 하단: Reactive Power 요약, RTE 추이

#### Step 3-4: 프로젝트 저장/로드 (SQLite)

### Phase 4: 출력 + 배포

#### Step 4-1: Excel 출력 (openpyxl)
- 기존 엑셀 Result/Summary 시트 형식 재현

#### Step 4-2: 오프라인 배포 패키징

```bash
# 개발 Mac에서 Windows용 wheel 다운로드
pip download -r requirements.txt --platform win_amd64 --only-binary=:all: -d ./wheels/

# 배포 폴더 구성
deploy/
├── 01_BESS_SizingTool/     # 전체 소스
├── wheels/                  # 오프라인 패키지
├── install.bat              # 자동 설치 스크립트
└── run.bat                  # 실행 스크립트
```

---

## 4. Golden Test Case (교차 검증 기준)

**파일**: `backend/data/test_case_jf3_100mw_400mwh.json`
**설명**: JF3 DC LINK Pairing, M12 System, 100MW/400MWh @POI, 45°C, Peak Shifting

### 4.1 입력값

| 변수 | 값 |
|------|-----|
| Required Power @POI | 100 MW |
| Required Energy @POI | 400 MWh |
| Power Factor | 0.95 |
| Temperature | 45°C |
| Altitude | <1000m |
| Product | JF3 0.25 DC LINK |
| PCS | EPC Power M 6stc + JF3 5.5 x 2sets |

### 4.2 기대 출력값 (허용 오차: ±0.1%)

| 계산 결과 | 기대값 | 모듈 |
|-----------|--------|------|
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

---

## 5. 리스크 및 완화 전략

### 5.1 기술 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| PCS 수량 산출 로직 불명확 | 계산 오차 | 엑셀 수식 역추적 + `strings_per_pcs` 필드 활용. 단순 `ceil(power/unit)` 아닌 LINK 구성 기반 계산 |
| `req_energy_dc` 계산에 `retention_rate_pct: 60` 적용 방식 | 에너지 산출 오차 | test_case JSON의 `expected_design_tool.retention_rate_pct`와 `expected_result.req_energy_dc` 관계 분석 |
| Retention Table 보간법 미지정 | Retention 오차 | nearest match 우선, 필요시 linear interpolation 적용. 두 방식 모두 구현 후 정확도 비교 |
| Aux 효율 경로 분기 복잡 | HV/MV 분기 오류 | 경로별 단위 테스트 작성, HV 분기 + MV 분기 각각 검증 |

### 5.2 환경 리스크

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 클라우드 PC localhost 접근 불가 | Flask 웹 UI 사용 불가 | 대안: Streamlit / Tkinter 데스크톱 UI. localhost 확인 후 결정 |
| Windows wheel 호환성 | 패키지 설치 실패 | NumPy, Flask 등 순수 Python 패키지 위주. C extension 최소화 |
| Python 버전 차이 | 문법/라이브러리 호환 오류 | Python 3.10+ 기준 개발, type hint 사용하되 3.8 호환 유지 |

---

## 6. 구현 순서 및 의존성

```
[Step 1-1] efficiency.py ─────────────┐
                                       │
[Step 1-2] pcs_sizing.py ─────────────┤ 병렬 가능
                                       │
                                       ▼
[Step 1-3] battery_sizing.py ─────────── (1-1, 1-2에 의존)
                                       │
                                       ▼
[Step 1-4] retention.py ──────────────── (1-3에 의존: CP Rate 필요)
                                       │
                                       ▼
[Step 2-1] reactive_power.py ─────────┐
[Step 2-2] rte.py ────────────────────┤ 병렬 가능 (Phase 1 완료 후)
[Step 2-3] soc.py ────────────────────┘
                                       │
                                       ▼
[Step 3-*] Flask UI ──────────────────── (Phase 1+2 계산 엔진 완료 후)
                                       │
                                       ▼
[Step 4-*] Export + Deploy ───────────── (Phase 3 완료 후)
```

### 병렬화 기회
- **Step 1-1과 1-2**: 독립적 — 동시 개발 가능
- **Step 2-1, 2-2, 2-3**: 독립적 — 동시 개발 가능
- **Step 3-2와 3-3**: 입력 화면과 결과 화면 독립 개발 가능

---

## 7. 테스트 전략

### 7.1 단위 테스트 (모듈별)

| 테스트 파일 | 검증 항목 |
|-------------|-----------|
| `test_efficiency.py` | 6단계 효율 곱, Aux 경로별(HV/MV), Battery Loss Factor |
| `test_pcs_sizing.py` | 온도 디레이팅, 고도 디레이팅, PCS 수량, edge case (정확히 나눠떨어지는 경우) |
| `test_battery_sizing.py` | POI→DC 변환, LINK/Rack 수량, Installation Energy, CP Rate |
| `test_retention.py` | CP Rate 기반 테이블 조회, 보간, 연도별 Retention, Augmentation 합산 |
| `test_reactive_power.py` | HV/MV/Inverter 각 레벨 P/Q/S, PF 검증 |

### 7.2 통합 테스트

| 테스트 | 방식 |
|--------|------|
| `test_against_excel.py` | Golden Test Case JSON 전체 입력 → 전체 출력 비교, ±0.1% 허용 |

### 7.3 검증 기준

```python
# 허용 오차 검증 함수
def assert_within_tolerance(actual, expected, tolerance=0.001):
    """±0.1% 허용 오차 검증"""
    if expected == 0:
        assert actual == 0
    else:
        assert abs(actual - expected) / abs(expected) <= tolerance
```

---

## 8. Type A / Type B 혼합 구성 (확장)

Phase 1에서는 **Type A (단일 구성)만 구현**. 이후 확장:

- Type A: 주력 제품 (JF3 0.25 DC LINK + EPC Power M-series)
- Type B: 보조 제품 (다른 Battery/PCS 조합)
- 각각 독립 계산 → 시스템 레벨 합산
- Reactive Power는 A+B 합산으로 재검증

**설계 고려**: 계산 모듈을 `TypeConfig` 객체에 바인딩하여, 동일 코드로 A/B 각각 실행 가능하도록 설계

---

## 9. JSON 참조 데이터 요약

| 파일 | 용도 | 크기 |
|------|------|------|
| `products.json` | 배터리 스펙 (JF2, JF3) — rack_energy, nameplate_energy | 2 products |
| `pcs_config_map.json` | PCS 구성 매핑 — manufacturer, model, strings_per_pcs | 7 configs |
| `pcs_temp_derating.json` | 온도별 PCS 출력 (25~50°C, 제조사별) | 6 manufacturers |
| `pcs_alt_derating.json` | 고도별 디레이팅 계수 | 3 altitude ranges |
| `aux_consumption.json` | 보조전력 Peak/Standby kW | 3 products |
| `retention_table_rsoc30.json` | Retention 룩업 rSOC 30% | 48 cases × 21 years |
| `retention_table_rsoc40.json` | Retention 룩업 rSOC 40% | 38 CP-rates × 21 years |
| `retention_lookup_inline.json` | Design tool 내장 Retention (CP=0.241) | 3 products × 21 years |

---

## 10. 성공 기준

| 기준 | 목표 |
|------|------|
| **계산 정확도** | Golden Test Case 대비 ±0.1% 이내 (모든 출력값) |
| **모듈 독립성** | 각 calculator 모듈이 독립적으로 테스트 가능 |
| **오프라인 동작** | 외부 네트워크 의존 없이 완전 동작 |
| **배포 용이성** | 단일 폴더 전달 → install.bat → run.bat 으로 실행 |
| **UI 응답성** | 전체 계산 결과 3초 이내 반환 |
| **프로젝트 이력** | SQLite에 프로젝트 저장/로드/비교 가능 |

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
| Ref_Parameter, Ref_AUX | `data/*.json` (추출 완료) | ✅ Done |
