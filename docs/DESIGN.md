# BESS Sizing Tool — 설계 문서

> 원본: SI Design Tool ver1.6.7 (JF3_only) 엑셀 분석 결과
> 작성일: 2026-03-19

---

## 1. 엑셀 원본 구조 요약

### 1.1 시트 역할 분류

| 구분 | 시트명 | 역할 |
|------|--------|------|
| **입력** | Input | 프로젝트 요구조건, 효율 체인, 제품 선택, 사용 패턴 |
| **핵심 계산** | Design tool | 배터리 구성 산출, 연도별 Retention 계산 |
| **핵심 계산** | Reactive P Calc. | 무효전력 계산 (HV→MV→Inverter 각 레벨) |
| **핵심 계산** | RTE | Round-Trip Efficiency 계산 |
| **핵심 계산** | SOC | SOC 범위 결정 (CP rate 기반) |
| **참조 데이터** | Ref_Parameter | 제품 스펙 DB (배터리, PCS 모델별 사양) |
| **참조 데이터** | Ref_AUX | 보조전력 소비량 테이블 |
| **참조 데이터** | Ret Table (2개) | 용량 유지율 룩업 테이블 (rSOC 30%, 40%) |
| **출력** | Result | 연도별 성능 추이, 누적 구성 |
| **출력** | Summary(Proposal) | 고객 제안용 1페이지 요약 |
| **출력** | Requirement Form | SE팀 요청 양식 |
| **부가** | Appx. Detail_Energy | 에너지 상세 계산 |
| **부가** | History, Approval Process 등 | 이력관리, 기타 |

### 1.2 계산 흐름도

```
[Input 시트]
  │
  ├── 프로젝트 요구조건 (Power, Energy, PF, 수명, Application)
  ├── 설계 조건 (온도, 고도, POI 레벨)
  ├── 효율 체인 (HV→MV→PCS→DC 각 단계 효율)
  ├── Aux 효율 체인
  ├── 배터리 Loss Factor (DoD, Additional Loss, MBMS)
  ├── 제품 선택 (Battery Type, PCS Type) → Ref_Parameter VLOOKUP
  └── 충방전 패턴 (Cycle/day, SOC 범위, 운전일수)
       │
       ▼
[Design tool 시트] ← Ret Table 참조
  │
  ├── POI→DC 변환: Required Power/Energy @DC 산출
  ├── 배터리 수량 결정: PCS 수 × Rack/PCS 구성
  ├── 연도별 Capacity Retention 계산
  └── Augmentation 시점/수량 반영
       │
       ├──→ [Reactive P Calc.] 무효전력 P/Q/S 계산
       ├──→ [RTE] 충방전 효율 계산
       ├──→ [SOC] CP rate 기반 SOC 범위 결정
       │
       ▼
[Result 시트]
  │
  ├── 연도별: Retention%, Total Energy, Dischargeable Energy @POI
  ├── 장비 수량: LINK 수, PCS 수, MVT 수, Rack 수
  └── Augmentation 누적 구성
       │
       ▼
[Summary(Proposal)] ── 고객 제안서 요약
[Requirement Form]  ── SE팀 요청 양식
```

---

## 2. 핵심 입력 변수 목록

### 2.1 프로젝트 기본 정보
| 변수 | 엑셀 위치 | 예시값 | 설명 |
|------|-----------|--------|------|
| Project Title | Input!E3 | JF3 DC LINK Pairing | 프로젝트명 |
| Customer | Input!E4 | Internal | 고객사 |
| Project Life [yr] | Input!E8 | 20 | 프로젝트 수명 |
| POI | Input!E9 | HV | Point of Interconnection 레벨 |
| Required Power [MW] | Input!E10 | 100 | 요구 출력 @POI |
| Required Energy [MWh] | Input!E11 | 400 | 요구 에너지 @POI |
| Power Factor | Input!E12 | 0.95 | 역률 |
| Aux Power Source | Input!E13 | Battery | 보조전력 공급원 |
| Scope of Supply | Input!E14 | BAT+PCS+MVT+EMS | 공급 범위 |
| Application | Input!E15 | Peak Shifting (PS) | 용도 |
| POI Voltage | Input!E16 | 230 kV | POI 전압 |
| Altitude | Input!E18 | <1000m | 고도 |
| Ambient Temperature | Input!E19 | 45°C | 설계 온도 |
| Measurement Method | Input!E20 | CPCV/CP | 충방전 측정방식 |

### 2.2 효율 체인 (System)
| 단계 | 엑셀 위치 | 기본값 | 설명 |
|------|-----------|--------|------|
| HV AC Cabling | Input!E24 | 0.999 | |
| HV Transformer | Input!E25 | 0.995 | |
| MV AC Cabling | Input!E26 | 0.999 | |
| MV Transformer & LV AC Cabling | Input!E27 | 0.989 | |
| PCS Efficiency | Input!E28 | 0.985 | |
| DC Cabling | Input!E29 | 0.999 | |
| **Total Bat-POI Efficiency** | Input!E30 | **~0.9664** | 위 6개의 곱 |

### 2.3 Aux 효율 체인
| 단계 | 엑셀 위치 | 설명 |
|------|-----------|------|
| Branching Point | Input!E32 | MV or HV |
| Aux TR @HV/MV/LV | Input!E33~E37 | 분기점에 따라 적용 |
| Aux line @HV/MV/LV | Input!E34~E38 | |
| Total Aux Efficiency | Input!E39 | 분기점 기준 종합 |
| Total DC to Aux Efficiency | Input!E40 | DC 기준 종합 |

### 2.4 배터리 손실 계수
| 변수 | 엑셀 위치 | 예시값 |
|------|-----------|--------|
| Applied DoD | Input!E42 | 0.99 |
| Loss Factors | Input!E43 | 0.98802 |
| MBMS Consumption | Input!E44 | 0.999 |
| **Total Battery Loss Factor** | Input!E45 | **0.9772** |

### 2.5 제품 선택 (Ref_Parameter 연동)
| 변수 | 엑셀 위치 | 설명 |
|------|-----------|------|
| Product Type (Type A) | Input!E65 | JF3 0.25 DC LINK 등 |
| Product Type (Type B) | Input!F65 | 혼합 구성 시 |
| PCS Type | Input!E66 | EPC Power M 6stc + JF3 5.5 x 2sets 등 |
| → Rack Energy [kWh] | Input!E70 | VLOOKUP from Ref_Parameter |
| → Nameplate Energy [MWh] | Input!E73 | VLOOKUP from Ref_Parameter |
| → PCS Power [kVA] | Input!E79~E80 | 온도/고도별 디레이팅 적용 |

### 2.6 충방전 패턴
| 변수 | 엑셀 위치 | 설명 |
|------|-----------|------|
| Rest SOC | Input!E51 | Mid |
| Rest Time [hr] | Input!E52 | 2 |
| Cycle/day | Input!E53 | 1 |
| Operation days/year | Input!E54 | 365 |
| SOC(H) | Input!E55 | SOC 시트 참조 |
| SOC(L) | Input!E56 | SOC 시트 참조 |
| SOC(Rest) | Input!E57 | 0.4 |

### 2.7 Augmentation 설정
| 변수 | 엑셀 위치 | 설명 |
|------|-----------|------|
| System Design (Initial) | Input!K9~K14 | 초기 설치 Type/수량 |
| 1st Aug Year | Input!L7 | 1차 증설 년도 |
| 2nd Aug Year | Input!M7 | 2차 증설 년도 |
| 3rd Aug Year | Input!N7 | 3차 증설 년도 |
| Aug Type/Qty | Input!L9~N14 | 각 증설의 제품/수량 |

---

## 3. 핵심 계산 로직

### 3.1 POI → DC 변환
```
Required Power @DC = Required Power @POI / Total Bat-POI Efficiency
Required Energy @DC = Required Energy @POI / (Total Bat-POI Efficiency × Total Battery Loss Factor)
```
예시: 100MW / 0.9664 ≈ 104.35 MW @DC

### 3.2 배터리 수량 결정
```
PCS Unit Power = Derated PCS Power @온도 × 고도계수 × (1-MV Voltage Tolerance)
No. of PCS = ceil(Required Power @DC / PCS Unit Power)
No. of Racks = No. of PCS × Racks per PCS (LINK 구성에 따라)
Installation Energy @DC = No. of Racks × Rack Energy / 1000
```

### 3.3 연도별 Capacity Retention
- CP rate 계산: Required Power @DC / (Installation Energy @DC)
- CP rate + 제품 타입으로 Ret Table 에서 연도별 Retention % 조회
- 열화 곡선: Year 0 = 100% → Year 20 ≈ 72.6% (예시)

### 3.4 Augmentation 로직
- 초기 설치의 Retention이 일정 수준 이하로 떨어지는 시점에 증설
- "N년차까지 증설 없이 요구 Power/Energy 준수" 조건으로 초기 수량 결정
- 증설 시: 새 배터리의 Retention은 Year 0부터 시작, 기존 배터리와 합산

### 3.5 Reactive Power 계산 (Reactive P Calc.)
```
HV Level:
  Total Apparent Power @POI = Power / PF
  Grid kVAR = sqrt(S² - P²)
  HV TR kVAR = S × Impedance
  Power Loss = S × (1 - Efficiency)

MV Level:
  MV Requirements = HV 통과 후 + MV TR 손실 + Aux
  PF @MV = P_mv / S_mv

Inverter Level:
  Total S @Inverter = MV 통과 후 + 모든 손실
  → 이 값이 PCS 총 용량보다 작아야 OK
```

### 3.6 RTE (Round-Trip Efficiency)
- 충전/방전 경로의 각 단계 효율을 양방향으로 적용
- Battery DC RTE + System 손실 = 전체 RTE
- 연도별 RTE 변화 추적 (Retention 감소에 따른 영향)

---

## 4. 참조 데이터 구조 (DB화 대상)

### 4.1 배터리 제품 스펙 (Ref_Parameter!B2:M5)
```json
{
  "JF2 0.25 DC LINK": {
    "module_type": "EP096636PFB1",
    "rack_type": "NR27N414L_P15190NB3",
    "rack_energy_kwh": 852.096,
    "gen": "Gen3",
    "nameplate_energy_mwh": 1.704
  },
  "JF3 0.25 DC LINK": {
    "rack_energy_kwh": 793.428,
    "gen": "Gen3",
    "nameplate_energy_mwh": 5.554
  }
}
```

### 4.2 PCS 온도별 디레이팅 (Ref_Parameter!B17:K44)
- 25~40°C: 정격 유지 (M-series: 537kVA)
- 40°C 초과: 1°C당 약 2% 감소
- 제조사별 디레이팅 커브 상이 (EPC Power, PE, SMA, LSE)

### 4.3 PCS 고도별 디레이팅 (Ref_Parameter!B46:K55)
- <1000m: 100%
- 1000~1500m: ~96.7%
- 1500~2000m: ~93.4%

### 4.4 Retention Table (Ret Table 시트)
- X축: 년도 (0~25)
- Y축: CP rate별 제품 타입
- 값: Capacity Retention %
- rSOC 30%와 rSOC 40% 두 가지 테이블

### 4.5 보조전력 소비량 (Ref_AUX)
| 제품 | Peak [kW] | Standby [kW] |
|------|-----------|--------------|
| JF2 0.25 DC LINK | 15.36 | 8.37 |
| JF2 0.25 AC LINK | 25.89 | 13.44 |
| JF3 0.25 DC LINK | 10.63 | 6.30 |

---

## 5. 웹 툴 아키텍처

### 5.1 모듈 구조
```
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # Flask 앱 진입점
│   │   ├── routes.py            # API 엔드포인트
│   │   └── models.py            # SQLite ORM (프로젝트, 사이징 이력)
│   ├── calculators/
│   │   ├── __init__.py
│   │   ├── efficiency.py        # 효율 체인 계산 (System + Aux + Battery)
│   │   ├── battery_sizing.py    # 배터리 수량/구성 산출
│   │   ├── pcs_sizing.py        # PCS 디레이팅, 수량 결정
│   │   ├── retention.py         # 연도별 Retention 계산 + Augmentation
│   │   ├── reactive_power.py    # 무효전력 계산 (HV/MV/Inverter)
│   │   ├── rte.py               # Round-Trip Efficiency
│   │   └── soc.py               # SOC 범위 결정
│   └── data/
│       ├── products.json        # 배터리/PCS 제품 스펙 DB
│       ├── retention_tables.json # Retention 룩업 테이블
│       ├── aux_consumption.json # 보조전력 소비 데이터
│       └── db/
│           └── sizing.db        # SQLite (프로젝트별 사이징 이력)
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       ├── app.js           # 메인 앱 로직
│   │       ├── input_form.js    # 입력 폼 동적 제어
│   │       ├── charts.js        # Retention/RTE 그래프
│   │       └── export.js        # 결과 Export (Excel/PDF)
│   └── templates/
│       ├── base.html
│       ├── input.html           # 입력 화면 (탭 구조)
│       ├── result.html          # 결과 화면
│       └── summary.html         # 제안서 요약 화면
├── tests/
│   ├── test_efficiency.py
│   ├── test_battery_sizing.py
│   ├── test_reactive_power.py
│   └── test_against_excel.py    # 엑셀 결과와 교차 검증
├── requirements.txt
├── run.py
└── docs/
    └── DESIGN.md                # 이 문서
```

### 5.2 UI 화면 구성

**입력 화면 (탭 구조)**
```
[프로젝트 기본] [효율 설정] [제품 선택] [충방전 패턴] [Augmentation]
```
- 탭 1: 프로젝트명, Power, Energy, PF, 온도, 고도, Application
- 탭 2: 효율 체인 (기본값 제공, 수정 가능)
- 탭 3: Battery Type (드롭다운), PCS Type (드롭다운) → 자동 스펙 로드
- 탭 4: Cycle/day, SOC 범위, 운전 일수, 패턴
- 탭 5: 증설 년도, 타입, 수량

**결과 화면**
- 상단: 핵심 수치 카드 (총 LINK 수, PCS 수, MVT 수, 설치 에너지)
- 중단: 연도별 Retention 그래프 + Augmentation 반영
- 하단: Reactive Power 요약, RTE 추이, Summary 테이블

### 5.3 API 설계
```
POST /api/calculate        # 전체 사이징 계산
POST /api/retention        # Retention만 재계산
POST /api/reactive-power   # 무효전력만 재계산
POST /api/rte              # RTE만 재계산
GET  /api/products         # 제품 스펙 목록
GET  /api/projects         # 저장된 프로젝트 목록
POST /api/projects         # 프로젝트 저장
GET  /api/projects/<id>    # 프로젝트 로드
POST /api/export/excel     # 결과 Excel 다운로드
POST /api/export/summary   # Summary 출력
```

---

## 6. 개발 단계 (Phase)

### Phase 1: 계산 엔진 (Python)
1. 효율 체인 계산 모듈 (efficiency.py)
2. 배터리 사이징 모듈 (battery_sizing.py + pcs_sizing.py)
3. Retention 계산 모듈 (retention.py)
4. **엑셀 결과와 교차 검증** (test_against_excel.py)

### Phase 2: 무효전력 + RTE
5. Reactive Power 계산 (reactive_power.py)
6. RTE 계산 (rte.py)
7. SOC 범위 결정 (soc.py)
8. 교차 검증 2차

### Phase 3: 웹 UI
9. Flask 앱 + API 구현
10. 입력 화면 (탭 구조)
11. 결과 화면 + 차트
12. 프로젝트 저장/로드

### Phase 4: 출력 + 고도화
13. Excel/Summary 출력
14. Augmentation 자동 최적화 (optional)
15. 다중 제품 지원 검증 (JF1, JF2)
16. 오프라인 배포 패키징

---

## 7. Type A / Type B 혼합 구성

하나의 프로젝트에서 서로 다른 배터리/PCS 조합을 혼합 사용하는 경우:
- Type A: 주력 제품 (예: JF3 0.25 DC LINK + EPC Power M-series)
- Type B: 보조 제품 (예: 같은 배터리 + 다른 PCS, 또는 다른 배터리)
- 각각 독립적으로 수량 계산 후, 전체 시스템 레벨에서 합산
- Reactive Power는 Type A + Type B 합산으로 검증

---

## 8. 엑셀 → 웹 전환 시 개선점

1. **입력 검증**: 엑셀은 잘못된 값 입력 시 #REF! 등 에러. 웹에서는 실시간 범위 검증.
2. **자동 제품 필터링**: 선택한 Application/Duration에 맞는 제품만 드롭다운에 표시
3. **시각화**: Retention 그래프에 Augmentation 시점 표시, 요구 에너지 라인과 비교
4. **이력 관리**: 프로젝트별 사이징 버전 관리 (엑셀은 파일 복사로 관리)
5. **다중 케이스 비교**: 같은 프로젝트에서 다른 구성(제품, 증설 전략) 비교
