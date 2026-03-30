# BESS Sizing Tool Phase 2a — SOC & Augmentation Enhancement Plan

> **Feature**: bess-phase2a-soc-augmentation
> **작성일**: 2026-03-26
> **PDCA Phase**: Plan
> **선행 완료**: Phase 1 (BESS Sizing Tool Core) — 2026-03-26 완료, 15/15 테스트 통과

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | SOC 범위 계산 모듈 신규 구현 + Augmentation 자동 최적화 강화 |
| 시작일 | 2026-03-26 |
| 예상 기간 | 4~5일 (SOC+수렴 2~3일 + Augmentation 강화 1일 + UI/통합 1일) |

### Value Delivered (4 관점)

| 관점 | 설명 |
|------|------|
| **Problem** | Phase 1에서 SOC 모듈이 미구현(applied_dod 수동 입력으로 우회). Augmentation은 수동으로 년도/수량을 입력해야 하며, 최적 증설 시점을 사용자가 직접 계산해야 함. 엑셀 Design Tool에는 SOC 시트와 자동 Augmentation 로직이 모두 존재하나 Python 미이식 상태 |
| **Solution** | 1) `soc.py` 모듈 구현: CP Rate + 충방전 패턴으로 SOC(H)/SOC(L)/SOC(Rest) 자동 계산. 2) `retention.py` Augmentation 로직 강화: Required Energy 임계치 기반 자동 증설 시점 산출 + 최적 수량 제안 |
| **Function UX Effect** | SOC 범위가 자동 표시되어 배터리 운전 범위를 즉시 확인 가능. Augmentation 탭에서 "자동 추천" 버튼으로 최적 증설 전략을 한 번에 산출. 결과 화면에 SOC 바 차트 + Augmentation 시점이 Retention 그래프에 시각적 표시 |
| **Core Value** | 엑셀 Design Tool의 SOC/Augmentation 기능을 완전 이식하여 웹 툴의 기능 완결성 달성. 수동 계산 대비 증설 최적화 시간 대폭 단축 (시행착오 3~5회 → 자동 1회) |

---

## 1. 프로젝트 개요

### 1.1 배경

Phase 1 완료 보고서(2026-03-26)에서 다음 2개 항목이 미구현/기본 수준으로 남아 있음:

| 항목 | Phase 1 상태 | Phase 2a 목표 |
|------|-------------|---------------|
| `soc.py` (SOC 범위 모듈) | 미구현. `applied_dod` 입력으로 기능적 우회 | CP Rate 기반 SOC(H)/SOC(L)/SOC(Rest) 자동 계산 구현 |
| Augmentation 자동 최적화 | `retention.py`에 수동 wave 입력만 지원 | Required Energy 임계치 기반 자동 증설 시점/수량 산출 |

### 1.2 범위 (Scope)

**In Scope:**
- `soc.py` 신규 모듈 생성
- SOC 계산 API 엔드포인트 (`POST /api/soc`)
- Augmentation 자동 추천 로직 (`retention.py` 확장)
- Augmentation 자동 추천 API 엔드포인트 (`POST /api/augmentation/recommend`)
- 기존 `/api/calculate` 응답에 SOC 결과 포함
- UI: SOC 바 차트, Augmentation 자동 추천 버튼
- 단위 테스트: `test_soc.py`, `test_augmentation_auto.py`

**Out of Scope:**
- PDF export (Phase 2b로 유지)
- Multi-System Type A + Type B 혼합 (Phase 2c로 유지)
- 기존 계산 모듈 변경 (efficiency, pcs_sizing, battery_sizing, reactive_power, rte는 건드리지 않음)

### 1.3 성공 기준

| 기준 | 목표 |
|------|------|
| SOC 계산 정확도 | 엑셀 SOC 시트 결과 대비 ±0.1% 이내 |
| Augmentation 자동 추천 | 엑셀 Design Tool의 수동 최적화 결과와 동일한 증설 시점 산출 |
| 기존 테스트 유지 | Phase 1의 15/15 테스트 전부 통과 유지 |
| 신규 테스트 | SOC 4건 + 수렴 4건 + Augmentation 자동 추천 3건 (~11건) |
| UI 통합 | SOC 결과가 결과 화면에 표시, Augmentation 추천이 입력 탭에 반영 |

---

## 2. 기술 분석

### 2.1 SOC 모듈 (`soc.py`)

#### 엑셀 SOC 시트 분석

엑셀 SOC 시트는 CP Rate를 기반으로 배터리 운전 SOC 범위를 결정한다:

```
SOC(H) = Upper SOC limit (충전 상한)
SOC(L) = Lower SOC limit (방전 하한)
SOC(Rest) = Rest state SOC (대기 상태)
Applied DoD = SOC(H) - SOC(L)  → 현재 Phase 1에서 수동 입력(0.99)으로 우회 중
```

#### ⚠️ CP-rate ↔ SOC 순환 의존성 및 수렴 반복 (핵심 설계)

SOC 계산에는 CP-rate가 필요하고, CP-rate는 배터리 사이징(=초기 설계)의 결과이다.
그런데 SOC가 바뀌면 Applied DoD가 바뀌고, 이는 Battery Loss Factor에 영향을 주어
배터리 사이징 결과(Installation Energy)가 달라지고, 결과적으로 CP-rate도 변한다.

**즉, CP-rate → SOC → Applied DoD → Battery Sizing → CP-rate 의 순환 루프가 존재한다.**

이 루프는 **고정점 반복(fixed-point iteration)**으로 수렴시킨다:

```python
def iterative_sizing_with_soc(inputs) -> ConvergedResult:
    """
    CP-rate ↔ SOC 순환 의존성을 반복 수렴으로 해소.

    알고리즘:
    1. 초기 추정: CP-rate = 0.25 (제품의 최대 CP-rate)
    2. CP-rate → SOC(H)/SOC(L) 계산 → Applied DoD 산출
    3. Applied DoD → Battery Loss Factor 재계산
    4. Battery Sizing 재실행 → 새 CP-rate 산출
    5. |CP-rate(n) - CP-rate(n-1)| < ε 이면 수렴 완료
    6. 수렴 안 되면 Step 2로 (최대 N회)
    """
    MAX_ITERATIONS = 20
    CONVERGENCE_THRESHOLD = 1e-6  # CP-rate 변화량 기준
    DAMPING_FACTOR = 0.7          # 발산 방지 감쇠 계수

    cp_rate = 0.25  # 초기값: 제품 최대 CP-rate

    for iteration in range(MAX_ITERATIONS):
        # Step 2: SOC 계산
        soc = calculate_soc(cp_rate, application, product_type)
        applied_dod = soc.soc_high - soc.soc_low

        # Step 3: Battery Loss 재계산 (applied_dod 반영)
        bat_loss = calculate_battery_loss(applied_dod, loss_factors, mbms)

        # Step 4: Battery Sizing 재실행
        bat_result = calculate_battery_sizing(...)
        new_cp_rate = bat_result.cp_rate

        # 발산 방지: 감쇠 적용 (급격한 변동 억제)
        damped_cp_rate = cp_rate + DAMPING_FACTOR * (new_cp_rate - cp_rate)

        # Step 5: 수렴 판정
        delta = abs(damped_cp_rate - cp_rate)
        cp_rate = damped_cp_rate

        if delta < CONVERGENCE_THRESHOLD:
            return ConvergedResult(cp_rate, soc, bat_result, iteration + 1)

    # 수렴 실패 시: 마지막 값 반환 + 경고 플래그
    return ConvergedResult(cp_rate, soc, bat_result, MAX_ITERATIONS,
                           converged=False, warning="Max iterations reached")
```

**수렴 보장 메커니즘:**

| 메커니즘 | 설명 |
|----------|------|
| **감쇠 계수 (Damping)** | `cp_rate(n+1) = cp_rate(n) + 0.7 × (raw_new - cp_rate(n))`. 급격한 진동 억제 |
| **최대 반복 횟수** | 20회 제한. 실제로는 3~5회 내 수렴 예상 (CP-rate 변화가 SOC에 미치는 영향은 단조적) |
| **발산 감지** | 연속 3회 이상 delta가 증가하면 감쇠 계수를 0.5로 강화 |
| **수렴 실패 처리** | `converged=False` 플래그 + UI 경고 표시. 마지막 계산 결과는 그대로 사용 가능 |

**수렴 특성 분석:**
- CP-rate ↑ → SOC(H) 감소 또는 SOC(L) 증가 → Applied DoD ↓ → Battery Loss Factor ↑ → Installation Energy ↓ → CP-rate ↑ (동일 방향)
- 그러나 Installation Energy 감소 → LINK 수 감소 → 이산적 계단 변화
- 이산적 계단(LINK 수 = 정수) 때문에 수렴이 2개 값 사이에서 진동할 수 있음 → **감쇠 계수**로 해결
- 일반적으로 3~5회 반복 내에 수렴. 발산은 물리적으로 발생하지 않음 (음의 피드백 루프)

**핵심 계산 로직 (엑셀 역추적):**

```python
# CP Rate에 따른 SOC 범위 결정
# CP Rate = Required Power @DC / Installation Energy @DC

# 일반적 매핑 (Application별 차이)
# Peak Shifting (PS): SOC(H)=0.95, SOC(L)=0.05, Rest=0.30~0.40
# Frequency Regulation (FR): SOC(H)=0.90, SOC(L)=0.10, Rest=0.50
# Solar Shifting (SS): SOC(H)=0.95, SOC(L)=0.05, Rest=0.30

# Applied DoD = SOC(H) - SOC(L)
# → 이 값이 efficiency.py의 BatteryLossInput.applied_dod에 연결
```

**입력:**
- CP Rate (from `battery_sizing.py` — 반복 수렴 시 매 iteration 갱신)
- Application type (Peak Shifting, Frequency Regulation 등)
- Cycle/day, Rest Time
- Product type (제품별 SOC 제한 범위 상이)

**출력:**
- `soc_high`: SOC 상한 (e.g., 0.95)
- `soc_low`: SOC 하한 (e.g., 0.05)
- `soc_rest`: 대기 SOC (e.g., 0.30 or 0.40)
- `applied_dod`: SOC(H) - SOC(L) (e.g., 0.90)
- `effective_dod`: Applied DoD × 제품 보정 계수

#### 데이터 의존성

| 참조 데이터 | 현재 상태 | 필요 작업 |
|-------------|-----------|-----------|
| SOC 범위 테이블 (Application별) | 미추출 | 엑셀 SOC 시트에서 JSON 추출 필요 |
| 제품별 SOC 제한 | `products.json`에 미포함 | 필드 추가 필요 (soc_max, soc_min) |

### 2.2 Augmentation 자동 최적화

#### 현재 구현 (`retention.py`)

```python
# 현재: 사용자가 수동으로 AugmentationWave 배열을 전달
augmentation_waves = [
    AugmentationWave(year=8, additional_links=10, additional_energy_mwh=55.54, product_type="JF3 0.25 DC LINK"),
]
result = calculate_with_augmentation(inp, augmentation_waves)
```

#### 목표: 자동 추천 로직

```python
# 목표: Required Energy @POI 기준으로 자동 증설 시점/수량 산출
def recommend_augmentation(
    retention_result: RetentionResult,
    required_energy_poi_mwh: float,     # 400 MWh
    total_bat_poi_eff: float,
    total_battery_loss_factor: float,
    product_type: str,
    max_augmentations: int = 3,         # 최대 3회 증설
    nameplate_energy_per_link_mwh: float = 5.554,
) -> list[AugmentationWave]:
    """
    알고리즘:
    1. 연도별 Dischargeable Energy @POI를 순회
    2. Required Energy @POI 미달 시점 탐지
    3. 미달 시점에서 부족 에너지량 계산
    4. 필요 LINK 수 = ceil(부족 에너지 / (nameplate × efficiency))
    5. AugmentationWave 생성
    6. 증설 후 Retention 재계산 → 다음 미달 시점 탐색
    7. max_augmentations 도달 또는 프로젝트 수명 끝까지 반복
    """
```

#### Augmentation 추천 UI 흐름

```
[Augmentation 탭]
  ├── [수동 입력] (기존 유지)
  │     ├── 1차 증설: 년도, LINK 수, 에너지
  │     ├── 2차 증설: 년도, LINK 수, 에너지
  │     └── 3차 증설: 년도, LINK 수, 에너지
  │
  └── [자동 추천] 버튼 (신규)
        ├── Required Energy @POI 기준 자동 산출
        ├── 결과를 수동 입력 필드에 자동 채움
        └── 사용자가 수정 가능 (추천값 기반 조정)
```

---

## 3. 아키텍처

### 3.1 모듈 구조 (Phase 2a 추가분)

```
backend/calculators/
├── soc.py                    ← [신규] SOC 범위 계산 (CP-rate → SOC(H)/SOC(L)/DoD)
├── convergence.py            ← [신규] CP-rate ↔ SOC 수렴 반복 오케스트레이터
├── retention.py              ← [수정] recommend_augmentation() 추가
└── (efficiency, pcs_sizing, battery_sizing 코드 변경 없음.
      단, convergence.py가 이들을 내부적으로 재호출함)

backend/data/
├── soc_ranges.json           ← [신규] Application별 SOC 범위 테이블
└── products.json             ← [수정] soc_max, soc_min 필드 추가

backend/app/
└── routes.py                 ← [수정] /api/soc, /api/augmentation/recommend 추가
                                       /api/calculate → convergence.py 호출로 전환
                                       응답에 soc + convergence_info 포함

frontend/
├── templates/result.html     ← [수정] SOC 바 차트 + 수렴 정보 표시
├── static/js/app.js          ← [수정] SOC 표시 + 자동 추천 버튼 로직
└── static/css/style.css      ← [수정] SOC 바 스타일

tests/
├── test_soc.py               ← [신규] SOC 단위 테스트
├── test_convergence.py       ← [신규] 수렴 반복 테스트 (수렴 확인, 발산 방지)
└── test_augmentation_auto.py ← [신규] Augmentation 자동 추천 테스트
```

### 3.2 데이터 흐름 (수렴 반복 포함)

```
[사용자 입력]
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  convergence.py — 수렴 루프 (max 20회, 보통 3~5회)       │
│                                                         │
│   초기값: CP-rate = 0.25 (제품 최대)                      │
│         │                                               │
│         ▼                                               │
│   ┌─ soc.py ──────────┐                                 │
│   │ CP-rate → SOC(H/L) │                                │
│   │ → Applied DoD      │                                │
│   └────────┬───────────┘                                │
│            ▼                                            │
│   ┌─ efficiency.py ───┐  (Applied DoD 반영)              │
│   │ Battery Loss 재계산 │                                │
│   └────────┬───────────┘                                │
│            ▼                                            │
│   ┌─ battery_sizing.py ┐                                │
│   │ 새 CP-rate 산출     │                                │
│   └────────┬───────────┘                                │
│            ▼                                            │
│   수렴 판정: |ΔCP-rate| < 1e-6?                          │
│     Yes → 루프 종료                                      │
│     No  → 감쇠 적용 후 soc.py로 되돌아감                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
      │
      ├── 수렴된 결과 (CP-rate, SOC, Battery Sizing)
      │
      ▼
┌─ retention.py ─────────────┐
│ Retention 곡선 계산          │
│ + recommend_augmentation() │
└────────────┬───────────────┘
             ▼
      [결과 통합 API 응답]
      { efficiency, pcs, battery, soc, retention,
        convergence_info: { iterations, converged, delta } }
```

### 3.3 API 설계 (추가분)

```
POST /api/soc                          # SOC 범위 단독 계산 (디버그/확인용)
  Input:  { cp_rate, application, product_type, cycle_per_day, rest_time_hr }
  Output: { soc_high, soc_low, soc_rest, applied_dod, effective_dod }

POST /api/augmentation/recommend       # Augmentation 자동 추천
  Input:  { cp_rate, product_type, project_life_yr, rest_soc,
            installation_energy_dc_mwh, required_energy_poi_mwh,
            total_bat_poi_eff, total_battery_loss_factor, total_dc_to_aux_eff,
            max_augmentations }
  Output: { waves: [{ year, additional_links, additional_energy_mwh }],
            total_additional_links, total_additional_energy_mwh }

POST /api/calculate                    # 기존 (convergence.py 통합)
  변경: 내부적으로 convergence.py의 수렴 루프를 호출
  Output: { ...,
            soc: { soc_high, soc_low, soc_rest, applied_dod },
            convergence_info: { iterations, converged, final_delta } }
```

**`/api/calculate` 변경 상세:**
- 기존: efficiency → pcs → battery → retention 순차 1회 실행
- 변경: `convergence.iterative_sizing_with_soc()` 호출로 전환
  - 초기 CP-rate=0.25 → SOC → Battery Loss 재계산 → Battery Sizing → 새 CP-rate → 수렴까지 반복
  - 수렴 후 retention, reactive_power, rte는 기존과 동일하게 1회 실행
- **하위 호환**: `application` 미전달 시 SOC 수렴 루프를 건너뛰고 기존 로직으로 fallback (Phase 1 동작 유지)

---

## 4. 구현 순서 및 의존성

```
[Step 1] soc.py 모듈 구현 + soc_ranges.json 생성 ────────┐
    │                                                      │ 병렬 가능
    ├── products.json에 soc_max/soc_min 추가               │
    │                                                      │
[Step 2] test_soc.py 작성 + 검증                           │
    │                                                      │
    ▼                                                      │
[Step 3] convergence.py 수렴 오케스트레이터 구현             │
    │   (soc.py + efficiency + battery_sizing 재호출 루프)   │
    │   + 감쇠 계수, 발산 방지, 수렴 판정                     │
    │                                                      │
    ▼                                                      │
[Step 4] test_convergence.py 작성 + 검증                   │
    │   - 수렴 확인 (3~5회 내 수렴)                          │
    │   - 발산 방지 테스트 (극단적 입력)                       │
    │   - fallback 테스트 (application 미전달 시 기존 동작)    │
    │                                                      │
    ▼                                                      ▼
[Step 5] retention.py에 recommend_augmentation() 추가 ←──── (독립)
    │
    ▼
[Step 6] test_augmentation_auto.py 작성 + 검증
    │
    ▼
[Step 7] routes.py 확장
    │   - /api/soc, /api/augmentation/recommend 추가
    │   - /api/calculate → convergence.py 호출로 전환
    │   - 하위 호환: application 미전달 시 기존 로직 유지
    │
    ▼
[Step 8] UI 통합
    │   - SOC 바 차트 (결과 화면)
    │   - 수렴 정보 표시 (iterations, converged)
    │   - Augmentation 자동 추천 버튼
    │
    ▼
[Step 9] 통합 테스트 (기존 15/15 + 신규 ~10건)
```

### 병렬화 기회
- **Step 1~4과 Step 5~6**: SOC/수렴과 Augmentation 추천은 독립적 — 동시 개발 가능
- **Step 8**: UI 작업은 API 완성(Step 7) 후

---

## 5. 리스크 및 완화

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 엑셀 SOC 시트의 정확한 계산 로직 불명 | SOC 값 오차 | 엑셀 파일에서 수식 역추적. 불가 시 업계 표준 SOC 범위 테이블 사용 |
| SOC 범위 데이터(soc_ranges.json) 미추출 | 모듈 구현 지연 | DESIGN.md Section 2.6의 기존 분석값 활용 + 합리적 기본값 설정 |
| **CP-rate ↔ SOC 수렴 루프가 진동/발산** | 계산 결과 불안정 | 감쇠 계수(0.7) 적용 + 연속 3회 delta 증가 시 감쇠 강화(0.5). 물리적으로 음의 피드백 루프이므로 발산 가능성 매우 낮음 |
| **LINK 수 이산 계단으로 인한 2값 진동** | 수렴 판정 실패 | LINK 수가 동일한 2회 연속 iteration이면 수렴으로 판정 (CP-rate 미세 차이 무시) |
| Augmentation 자동 추천의 최적성 검증 어려움 | 부정확한 추천 | 엑셀에서 수동 최적화한 결과와 비교 검증. 최소 2개 프로젝트 케이스로 교차 검증 |
| 기존 retention.py 수정 시 Phase 1 테스트 깨짐 | 회귀 오류 | recommend_augmentation()을 별도 함수로 추가, 기존 함수 변경 없음 |
| `/api/calculate` 변경으로 기존 프론트엔드 깨짐 | UI 호환성 | application 미전달 시 기존 로직 fallback. 응답에 soc, convergence_info 필드 추가만 (기존 필드 변경 없음) |
| UI SOC 바 차트 구현 복잡도 | 일정 지연 | 단순 수평 바 차트로 시작, Chart.js 불필요 (CSS + HTML로 충분) |

---

## 6. 테스트 전략

### 6.1 신규 단위 테스트

| 테스트 파일 | 검증 항목 | 예상 건수 |
|-------------|-----------|-----------|
| `test_soc.py` | SOC(H)/SOC(L)/SOC(Rest) 계산, Application별 차이, 제품별 SOC 제한 | 4건 |
| `test_convergence.py` | 수렴 확인(3~5회 내), 발산 방지(극단 입력), fallback(application 미전달), LINK 이산 진동 처리 | 4건 |
| `test_augmentation_auto.py` | 자동 추천 시점/수량, 다회 증설, 증설 불필요 케이스 | 3건 |

### 6.2 회귀 테스트

| 테스트 | 기대 결과 |
|--------|-----------|
| Phase 1 기존 15/15 | 전부 PASS 유지 |
| `test_against_excel.py` | Golden Test Case 변동 없음 |

### 6.3 검증 기준

```python
# SOC 허용 오차
def assert_soc_within_tolerance(actual, expected, tolerance=0.001):
    """±0.1% 허용 오차 검증"""
    assert abs(actual - expected) <= tolerance

# Augmentation 추천 검증
def assert_augmentation_year(recommended_year, expected_year, tolerance=1):
    """추천 년도 ±1년 허용"""
    assert abs(recommended_year - expected_year) <= tolerance
```

---

## 7. 확인 필요 사항 (개발 전)

- [ ] 엑셀 SOC 시트 수식 역추적 → `soc_ranges.json` 데이터 추출
- [ ] 제품별 SOC 운전 제한 범위 확인 (JF2 vs JF3 차이 유무)
- [ ] Golden Test Case에 SOC 기대값 추가 가능 여부
- [ ] Augmentation 수동 최적화 결과 비교 대상 케이스 확보

---

## 부록: 엑셀 시트 ↔ Python 모듈 매핑 (Phase 2a)

| 엑셀 시트 | Python 모듈 | Phase | 상태 |
|-----------|------------|-------|------|
| SOC | `calculators/soc.py` | 2a | **신규 구현** |
| Design tool (Augmentation 자동화) | `calculators/retention.py` 확장 | 2a | **기능 추가** |
| Input (충방전 패턴) → SOC 연동 | `app/routes.py` | 2a | **API 확장** |
