# Plan: BESS Phase 2a-fix — SOC & Augmentation 핵심 로직 적용

## Executive Summary

| Perspective | Description |
|-------------|-------------|
| **Problem** | Phase 2a에서 UI 골격은 구축되었으나, SOC 계산이 CP-rate/Measurement Method를 반영하지 않고, Retention 테이블이 Augmentation을 반영하지 않으며, 그래프와 UX가 실무 요구를 충족하지 못함 |
| **Solution** | Excel SI Design Tool SOC sheet (B1:C7) 역추적으로 정확한 SOC 로직 구현, Retention 테이블 Augmentation 열 확장, Dischargeable Energy 그래프 전환, Auto-Recommend UX 개선 |
| **Function UX Effect** | 엔지니어가 CP-rate/Measurement Method 조합별 정확한 SOC 범위를 확인하고, Augmentation 적용 전후 에너지 변화를 테이블·그래프에서 직관적으로 비교 가능 |
| **Core Value** | 실무 엔지니어링 정확도 확보 — Excel 도구와 동일한 계산 결과를 웹 대시보드에서 즉시 확인 |

---

## 1. 배경

Phase 2a에서 구축된 구조:
- `soc.py` — SOCInput/SOCResult/calculate_soc() (Application별 고정값, CP-rate 미반영)
- `convergence.py` — CP-rate ↔ SOC 수렴 루프 (SOC가 상수라 2회 수렴)
- `retention.py` — recommend_augmentation() (기본 동작)
- UI — SOC 바, Convergence 상태, Auto-Recommend 버튼

**문제**: 핵심 계산 로직이 Excel SI Design Tool과 불일치.

---

## 2. 수정 항목

### 2.1 SOC 계산 로직 재구현 (Critical)

**참조**: SI Design Tool.ver1.6.7 → SOC sheet → B1:C7 역추적

**현재 문제**: `soc_ranges.json`이 Application별 고정 SOC 값만 제공. CP-rate와 Measurement Method(Chg./Dchg)에 따른 분기 없음.

**수정 내용**:
1. Excel SOC sheet B1:C7의 최종 계산값 역추적 → 입력 파라미터 식별
   - CP-rate가 SOC(H)/SOC(L)에 어떻게 영향을 주는지 수식 추출
   - Measurement Method (Both CP, CPCV/CP, Both CPCV)별 분기 로직 추출
2. `soc_ranges.json` 구조 개편 — CP-rate 구간별, Measurement Method별 SOC 값 매핑
3. `soc.py` `calculate_soc()` 재구현:
   - 입력: cp_rate, application, product_type, **measurement_method**
   - CP-rate 구간 → SOC(H)/SOC(L) 조회 로직
   - Measurement Method별 보정 로직
4. Augmentation도 동일 로직 적용 (retention.py에서 SOC 조회 시)

**파일**:
- `backend/calculators/soc.py` ← [수정] calculate_soc() 로직 재구현
- `backend/data/soc_ranges.json` ← [수정] CP-rate/Measurement Method별 데이터 구조
- `backend/calculators/convergence.py` ← [수정] SOCInput에 measurement_method 전달

### 2.2 UI 입력: Measurement Method 추가 (Major)

**현재**: 입력 폼에 Measurement Method 선택 없음.

**수정 내용**:
1. `input.html`에 드롭다운 추가: `Both CP` / `CPCV/CP` / `Both CPCV`
2. `app.js` collectFormData()에 `measurement_method` 필드 추가
3. API `/api/calculate` 요청에 measurement_method 포함
4. `routes.py`에서 convergence/SOC 호출 시 measurement_method 전달

**파일**:
- `frontend/templates/input.html` ← [수정] 드롭다운 추가
- `frontend/static/js/app.js` ← [수정] collectFormData, displayResults
- `backend/app/routes.py` ← [수정] measurement_method 파라미터 처리

### 2.3 Retention & Energy Data Table 개선 (Critical + Minor)

#### 2.3.1 스타일 개선 (Minor)
- 제목행 배경색: 검정 → 브랜드 컬러(--color-primary, 진한 빨강) 또는 진한 회색
- 열 구분선: `border-right: 1px solid #e0e0e0` 추가

**파일**: `frontend/static/css/style.css` ← [수정]

#### 2.3.2 Augmentation 열 확장 (Critical)

**참조**: Excel Result sheet C22:U44

**현재 문제**: Augmentation 추가 시 테이블에 반영 없음.

**수정 내용**:
1. Excel Result sheet C22:U44의 column 구조 파악:
   - 기본 열: Year, Retention%, Total Energy, Dischargeable @DC, @DC-Aux, @MV, @POI
   - Augmentation 추가 시: Aug 에너지, 누적 에너지, Aug 후 Dischargeable 등 열 확장
2. `retention.py` — augmentation 적용 후 연도별 상세 데이터 반환 구조 확장
3. `app.js` — Augmentation 존재 시 추가 열 동적 생성
4. 이 range의 모든 column 유지 (제거 금지)

**파일**:
- `backend/calculators/retention.py` ← [수정] 반환 데이터 구조 확장
- `frontend/static/js/app.js` ← [수정] 테이블 동적 열 생성
- `frontend/templates/input.html` ← [수정 가능] 테이블 구조

### 2.4 Capacity Retention Curve → Dischargeable Energy 그래프 (Major)

**현재**: Capacity Retention Curve (%) 차트.

**수정 내용**:
1. Y축을 Retention % → Dischargeable Energy @POI (MWh)로 변경
2. Augmentation 적용 시 에너지 증가를 시각적으로 표현
   - 기본 라인: Augmentation 없는 감쇠 곡선
   - Augmentation 후 라인: 증설 시점에서 에너지 점프
   - Required Energy 수평선: 목표 에너지 레벨
3. 차트 범례: "Base Decay", "With Augmentation", "Required Energy @POI"

**파일**:
- `frontend/static/js/charts.js` ← [수정] 차트 데이터/옵션 변경
- `frontend/static/js/app.js` ← [수정] 차트 데이터 전달 로직

### 2.5 Auto-Recommend Augmentation UX 개선 (Major)

**현재**: 결과 화면에서만 버튼 활성화, 추천 결과 수정 불가.

**수정 내용**:
1. **입력 단계 상시 활성화**: Calculate 전에도 Auto-Recommend 실행 가능
   - 필수 입력값(에너지, 제품, 수명)만 있으면 활성화
2. **추천 결과 수동 조정**:
   - 각 Wave의 LINK 수를 +/- 버튼으로 조정 가능
   - 예: 1차 Wave 20 LINKs → 사용자가 22로 올림
3. **재계산 연동**:
   - 조정된 Augmentation을 augmentation waves 입력에 자동 반영
   - "Calculate" 버튼으로 조정된 값 기반 전체 재계산
4. **시나리오**: 1차 augmentation 20개 추천 → 적용 → 2차 year까지 에너지 부족 → 사용자가 수동으로 LINK 추가 → 재계산

**파일**:
- `frontend/templates/input.html` ← [수정] Auto-Recommend 위치/UI 변경
- `frontend/static/js/app.js` ← [수정] 추천→조정→재계산 워크플로우
- `frontend/static/css/style.css` ← [수정] 조정 UI 스타일

---

## 3. 구현 순서

| 순서 | 항목 | 의존성 | 난이도 |
|------|------|--------|--------|
| 1 | Excel SOC sheet 역추적 & 로직 문서화 | 없음 | 높음 (Excel 분석) |
| 2 | SOC 계산 로직 재구현 (2.1) | #1 | 높음 |
| 3 | Measurement Method UI 추가 (2.2) | #2 | 낮음 |
| 4 | Retention 테이블 스타일 (2.3.1) | 없음 | 낮음 |
| 5 | Excel Result sheet C22:U44 분석 | 없음 | 중간 |
| 6 | Retention 테이블 Augmentation 열 (2.3.2) | #5 | 높음 |
| 7 | Dischargeable Energy 그래프 (2.4) | #6 | 중간 |
| 8 | Auto-Recommend UX 개선 (2.5) | #2, #6 | 중간 |

---

## 4. 테스트 계획

| 테스트 | 검증 대상 |
|--------|-----------|
| `test_soc.py` 확장 | CP-rate 구간별 SOC 값, Measurement Method별 분기 |
| `test_convergence.py` 확장 | SOC가 CP-rate에 따라 변할 때 실제 수렴 동작 |
| `test_retention_table.py` (신규) | Augmentation 적용 시 테이블 열 확장 데이터 정합성 |
| Excel 대조 검증 | SI Design Tool 결과값과 웹 도구 결과값 1:1 비교 |
| cmux 브라우저 검증 | UI 전체 워크플로우 시각적 검증 |

---

## 5. 필수 참조 자료

| 자료 | 용도 |
|------|------|
| SI Design Tool.ver1.6.7 SOC sheet (B1:C7) | SOC 계산 로직 역추적 |
| SI Design Tool.ver1.6.7 Result sheet (C22:U44) | Retention 테이블 열 구조 |
| 기존 `soc.py`, `convergence.py` | 구조 유지, 로직만 교체 |

---

## 6. 범위 외 (이번 Plan에서 제외)

- 새로운 Product Type 추가
- Multi-case comparison (Phase 2b)
- 프로젝트 저장/불러오기 개선
