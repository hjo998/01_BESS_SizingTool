# BESS Sizing Tool — Claude Code 핸드오프 문서

> Cowork에서 엑셀 분석 → 설계 완료. 이 문서를 읽고 Phase 1부터 코딩 시작할 것.
> 작성일: 2026-03-19

---

## 0. 읽어야 할 파일 목록

| 파일 | 내용 | 중요도 |
|------|------|--------|
| `../CLAUDE.md` | 전체 개발 환경 제약조건 (타겟: 본사 클라우드PC, 오프라인, Windows) | ★★★ |
| `docs/DESIGN.md` | 엑셀 분석 결과 + 전체 설계서 (입력 변수, 계산 로직, 모듈 구조, API) | ★★★ |
| `backend/data/*.json` | 엑셀에서 추출한 참조 데이터 (바로 사용 가능) | ★★★ |
| `backend/data/test_case_jf3_100mw_400mwh.json` | 교차 검증용 테스트 케이스 (입력→기대 출력) | ★★★ |

---

## 1. 프로젝트 목표

사내 엑셀 사이징 툴(SI Design Tool ver1.6.7)의 **계산 로직을 Python으로 이식**하고, **Flask 웹 UI**로 제공한다.

**타겟 환경**: 본사 클라우드 PC (Windows, 오프라인, 브라우저 접근 가능, Python 설치 가능)

---

## 2. 이미 준비된 것

### 2.1 엑셀 참조 데이터 (JSON, backend/data/ 폴더)
```
products.json                    - 배터리 제품 스펙 (JF2/JF3, Rack Energy, Nameplate 등)
pcs_temp_derating.json           - PCS 온도별 디레이팅 (25~50°C, 제조사별)
pcs_alt_derating.json            - PCS 고도별 디레이팅 (<1000m ~ 2000m+)
pcs_config_map.json              - PCS 구성 매핑 (config_name → manufacturer, model, strings)
aux_consumption.json             - 보조전력 소비 (제품별 Peak/Standby kW)
retention_table_rsoc30.json      - Retention 룩업 rSOC 30% (48 cases × 21 years)
retention_table_rsoc40.json      - Retention 룩업 rSOC 40% (38 CP-rates × 21 years)
retention_lookup_inline.json     - Design tool 내장 Retention (CP=0.241, 3 products × 21 years)
test_case_jf3_100mw_400mwh.json  - 교차 검증용 (입력값 + 엑셀 기대 출력값)
```

### 2.2 폴더 구조 (이미 생성됨)
```
├── backend/
│   ├── app/            → Flask 앱 (routes, models)
│   ├── calculators/    → 계산 모듈 (여기에 코딩)
│   └── data/           → JSON 참조 데이터 (준비 완료)
├── frontend/
│   ├── static/css,js/
│   └── templates/
├── tests/
├── docs/DESIGN.md
├── requirements.txt
└── run.py
```

---

## 3. 개발 순서 (Phase 1 → 4)

### Phase 1: 계산 엔진 코어 ← **여기서 시작**

**목표**: 엑셀과 동일한 계산 결과를 Python으로 재현

#### Step 1-1: efficiency.py (효율 체인)
```python
# 입력: 각 단계 효율값 (HV Cabling, HV TR, MV Cabling, MV TR, PCS, DC Cabling)
# 출력: Total Bat-POI Efficiency, Total Aux Efficiency, Total Battery Loss Factor

# 계산 공식:
total_bat_poi_eff = hv_cabling * hv_tr * mv_cabling * mv_tr * pcs * dc_cabling
# 예시: 0.999 * 0.995 * 0.999 * 0.989 * 0.985 * 0.999 = 0.96639

# Aux 효율은 Branching Point (HV or MV)에 따라 경로가 다름
# MV 분기 시: aux_tr_lv * aux_line_lv = 0.985 * 0.999 = 0.984015
# Total DC to Aux = total_bat_poi_eff * ... (경로에 따라 다름)

# Battery Loss Factor:
total_bat_loss = applied_dod * loss_factors * mbms_consumption
# 예시: 0.99 * 0.98802 * 0.999 = 0.97716

# Total Efficiency (including battery):
total_eff = total_bat_poi_eff * total_bat_loss
# 예시: 0.96639 * 0.97716 = 0.94432
```

**검증**: test_case에서 `total_bat_poi=0.9664`, `total_battery_loss_factor=0.9772`, `total_eff=0.9443`

#### Step 1-2: pcs_sizing.py (PCS 사이징)
```python
# 입력: PCS model, temperature, altitude, MV voltage tolerance
# 출력: Derated PCS power, No. of PCS

# 1. 온도 디레이팅: pcs_temp_derating.json에서 조회
#    M-series @45°C = 537 kVA (실제로는 디레이팅 됨, 데이터 확인)
# 2. 고도 디레이팅: pcs_alt_derating.json에서 계수 조회
# 3. MV 전압 허용오차 반영: (1 - voltage_tolerance)
#    Derated Power = base_kva * temp_factor * alt_factor * (1 - 0.02) / 1000 [MW]
# 4. PCS 수량: ceil(Required Power @DC / PCS Unit Power)

# 현재 예시에서:
# PCS Unit Power = 3.15756 MW (Design tool!E15)
# No. of PCS = 39 (Design tool!E16)
# → 확인: 104.345 / 3.15756 ≈ 33.04...
# ※ 주의: PCS 수는 단순 나누기가 아닐 수 있음.
#   Config에서 strings_per_pcs와 LINK 구성이 영향을 줌
```

#### Step 1-3: battery_sizing.py (배터리 구성)
```python
# 입력: Required Power/Energy @POI, efficiencies, product specs
# 출력: No. of LINKs, No. of Racks, Installation Energy

# 1. POI → DC 변환:
req_power_dc = req_power_poi / total_bat_poi_eff
req_energy_dc = req_energy_poi / (total_bat_poi_eff * total_bat_loss)
# 예시: 100/0.9664 = 104.345 MW, 400/(0.9664*0.9772) ≈ 433.21 MWh

# 2. Rack 수량:
# Racks per LINK = E22 (Design tool) = 6
# Total Racks = No. of PCS * Racks per LINK...
#   ※ 이 부분 LINK 구성 방식이 중요 - 확인 필요
# 78 LINKs × 6 Racks/LINK = 468 Racks ✓

# 3. Installation Energy:
inst_energy = total_racks * rack_energy_kwh / 1000
# 468 * 793.428 / 1000 ≠ 433.21...
# ※ 이건 LINK 단위의 Nameplate Energy로 계산하는 듯
# 78 * 5.554 = 433.212 ✓ (Nameplate Energy per LINK)

# 4. Dischargeable Energy @POI:
disc_energy_poi = inst_energy * total_bat_poi_eff * retention_factor
```

**⚠️ 핵심 검증 포인트**:
| 변수 | 엑셀 기대값 | 검증 |
|------|------------|------|
| Required Power @DC | 104.345 MW | |
| Required Energy @DC | 433.21 MWh | |
| No. of PCS | 39 | |
| No. of LINKs | 78 (= 39 PCS × 2 LINKs/PCS) | |
| No. of Racks | 468 (= 78 × 6) | |
| Installation Energy @DC | 433.212 MWh | |
| CP Rate | 0.2409 | |
| Dischargeable Energy @POI | 405.69 MWh | |
| Retention Y0/Y10/Y20 | 100% / 83.2% / 72.6% | |

#### Step 1-4: retention.py (연도별 열화)
```python
# 입력: CP rate, product type, rest SOC
# 출력: 연도별 Capacity Retention %

# 1. CP rate 계산:
cp_rate = req_power_dc / inst_energy_dc
# 104.345 / 433.212 = 0.24086

# 2. Retention Table 조회:
# CP rate를 retention_table에서 가장 가까운 열로 매칭
# → 연도별 Retention % 반환

# 3. Augmentation:
# N년차까지 (요구 에너지 / 설치 에너지) * 100 > Retention[N] 이면 증설 불필요
# Retention이 이 수준 아래로 떨어지면 → 추가 LINK 설치

# 4. 복합 Retention (Augmentation 후):
# 기존 배터리 에너지 × 기존 Retention + 신규 배터리 에너지 × 신규 Retention
```

### Phase 2: Reactive Power + RTE

#### reactive_power.py
```python
# HV Level:
S_poi = P_poi / PF  # 100/0.95 = 105,263 kVA
Q_grid = sqrt(S_poi**2 - P_poi**2)  # 32,868 kVAR
Q_hv_tr = S_poi * impedance_hv  # 105,263 * 0.14 = 14,736 kVAR
P_loss_hv = S_poi * (1 - eff_hv_tr)  # 105,263 * 0.005 = 526 kW

# MV Level:
P_mv = P_poi + P_loss_hv + P_aux  # 점진적 누적
Q_mv = Q_grid + Q_hv_tr + Q_mv_tr
S_mv = sqrt(P_mv**2 + Q_mv**2)
PF_mv = P_mv / S_mv  # ~0.903

# Inverter Level:
S_inverter = 116,669 kVA  # 최종
S_available = No_PCS * PCS_unit_kVA  # 이것보다 커야 OK
```

#### rte.py
```python
# 충전 경로: Grid → HV → MV → PCS → DC → Battery
# 방전 경로: Battery → DC → PCS → MV → HV → Grid
# RTE = 방전 에너지 / 충전 에너지
# 각 단계 효율을 양방향으로 적용
```

### Phase 3: Flask 웹 UI
- 입력 화면: 탭 구조 (프로젝트 기본 / 효율 / 제품 / 패턴 / Augmentation)
- 결과 화면: 수치 카드 + Retention 그래프 + Reactive Power + RTE
- 프로젝트 저장/로드 (SQLite)

### Phase 4: 출력 + 배포
- Excel/PDF 출력
- 오프라인 wheel 패키징
- Windows 배포 스크립트

---

## 4. 기술 스택

```
Python 3.10+
Flask 3.0
NumPy (계산)
SQLite (이력 관리)
openpyxl (Excel 출력)
Chart.js 또는 Plotly.js (프론트 차트)
```

requirements.txt 이미 작성됨.

---

## 5. 주의사항

### 5.1 오프라인 우선
- 외부 CDN 의존 금지 (Chart.js 등은 static 폴더에 번들)
- pip wheel 오프라인 설치 지원 필요

### 5.2 엑셀과 교차 검증 필수
- `backend/data/test_case_jf3_100mw_400mwh.json`에 입력값 + 기대 출력값 있음
- 각 계산 모듈 작성 후 반드시 이 테스트 케이스로 검증
- 허용 오차: ±0.1% 이내

### 5.3 Type A / Type B 혼합 구성
- 한 프로젝트에서 두 가지 배터리/PCS 조합 사용 가능
- 각각 독립 계산 후 시스템 레벨에서 합산
- Phase 1에서는 Type A (단일 구성)만 먼저 구현해도 OK

### 5.4 Augmentation 로직
- 초기 설치 년수(변수) 동안 증설 없이 요구 P/E 충족해야 함
- 예: "Initial 10년" = 10년차까지 Retention 기반 에너지가 요구 에너지 이상
- 증설 시점/수량은 사용자가 직접 지정 (자동 추천은 Phase 4)

### 5.5 LINK vs Rack 관계
- 1 LINK = N Racks (제품에 따라 다름, JF3: 6 Racks/LINK)
- Nameplate Energy는 LINK 단위 (JF3: 5.554 MWh/LINK)
- PCS 1대당 LINK 수는 config에 따라 다름 (현재 예: 2 LINKs/PCS)
- 전체: 39 PCS × 2 LINKs/PCS = 78 LINKs × 6 Racks/LINK = 468 Racks

### 5.6 Retention Table 구조
- rSOC 30%: 48 cases (다양한 조건 조합별 결과). 각 case에 CP-rate가 있고, 연도별 Retention % 제공.
- rSOC 40%: JF2 0.25 DC LINK 전용, 38개 CP-rate 구간별 Retention.
- 현재 JF3 기준 조회는 Design tool 내장 테이블 사용 (retention_lookup_inline.json).
- 실제 조회 로직: CP-rate에 가장 가까운 열을 보간(interpolation) 또는 nearest match.

---

## 6. 원본 엑셀 시트 ↔ Python 모듈 매핑

| 엑셀 시트 | Python 모듈 | 상태 |
|-----------|------------|------|
| Input (효율 파트) | `calculators/efficiency.py` | Phase 1 |
| Input (제품 선택) + Ref_Parameter | `calculators/pcs_sizing.py` | Phase 1 |
| Design tool (배터리 구성) | `calculators/battery_sizing.py` | Phase 1 |
| Design tool (Retention) + Ret Tables | `calculators/retention.py` | Phase 1 |
| Reactive P Calc. | `calculators/reactive_power.py` | Phase 2 |
| RTE | `calculators/rte.py` | Phase 2 |
| SOC | `calculators/soc.py` | Phase 2 |
| Result | `app/routes.py` (결과 조합) | Phase 3 |
| Summary(Proposal) | `templates/summary.html` | Phase 3 |
| Ref_Parameter, Ref_AUX | `data/*.json` (추출 완료) | ✅ Done |

---

## 7. 첫 번째 할 일

```bash
# 1. efficiency.py 작성
# 2. test_efficiency.py로 엑셀 값과 검증
# 3. 통과하면 battery_sizing.py → pcs_sizing.py → retention.py 순으로 진행
```

각 모듈은 **독립적으로 테스트 가능**하게 만들 것. 함수 단위로 입력/출력을 명확히 하고, 테스트 케이스 JSON의 해당 값과 비교.
