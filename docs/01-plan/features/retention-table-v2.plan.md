# Retention Table V2 Planning Document

> **Summary**: Retention & Energy Data Table을 개선하여 Augmentation wave별 상세 에너지 분해를 제공하고, Dischargeable Energy를 핵심 값으로 강조하며, 모든 수치를 소수점 3자리까지 표시한다.
>
> **Project**: BESS Sizing Tool (LG Energy Solution)
> **Feature**: retention-table-v2
> **Author**: alex
> **Date**: 2026-03-30
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 Augmentation 테이블이 모든 wave를 합산하여 표시하므로 1차/2차/3차 augmentation의 개별 기여도를 파악할 수 없음. Total Energy와 Cumulative Total Energy 구분이 모호하고, 소수점 1자리로 정밀도 부족. 가장 중요한 Dischargeable Energy @POI가 시각적으로 강조되지 않음. |
| **Solution** | 백엔드에서 per-wave 연도별 에너지 분해 데이터를 반환하고, 프론트엔드에서 각 wave를 개별 컬럼으로 표시. 토글 체크박스로 wave별 표시/숨기기 지원. 갈색 테이블 헤더를 Cumulative로 명확히 변경. 소수점 3자리 통일. |
| **Function/UX Effect** | Wave 1/2/3 개별 토글로 상세 확인 가능. Cumul. Disch. @POI가 시각적으로 강조되어 한눈에 핵심 값 파악. 가로 스크롤 활용하여 정보 손실 없이 상세 데이터 제공. |
| **Core Value** | Augmentation 설계 의사결정 정밀도 향상. 각 wave의 기여도를 정량적으로 파악하여 최적 augmentation 전략 수립 가능. 소수점 3자리로 엔지니어링 정밀도 확보. |

---

## 1. Overview

### 1.1 Purpose

Retention & Energy Data Table의 Augmentation 섹션을 개선하여:
1. 각 Augmentation wave의 개별 에너지 기여도를 연도별로 확인 가능하게 함
2. Dischargeable Energy @POI를 핵심 값으로 시각적 강조
3. 모든 수치를 소수점 3자리로 통일하여 엔지니어링 정밀도 확보
4. Cumulative Total Energy / Cumulative Dischargeable Energy 헤더 명확화

### 1.2 Background

- Phase 1 (완료): 기본 Retention 테이블 + Augmentation 합산 표시
- 현재 갈색 Aug 컬럼 3개: Aug. Energy, Total Energy, Cumu. Disch. Energy
- 백엔드 `calculate_with_augmentation()`은 합산만 반환, per-wave 분해 없음
- JS에서 `augmentation_detail`을 참조하나 백엔드에서 미반환

### 1.3 Related Files

| File | Role |
|------|------|
| `backend/calculators/retention.py` | Retention 계산 엔진 (calculate_with_augmentation) |
| `frontend/templates/input.html` | Retention 테이블 HTML (lines 894-931) |
| `frontend/static/js/app.js` | 테이블 렌더링 JS (lines 1946-2016) |
| `frontend/static/css/style.css` | 갈색 Aug 컬럼 스타일 (lines 1886-1903) |
| `frontend/templates/result.html` | 읽기 전용 결과 뷰 (lines 56-84) |

---

## 2. Scope

### 2.1 In Scope

- [ ] 백엔드: per-wave 연도별 에너지 분해 데이터 반환 (`wave_details` 필드)
- [ ] 백엔드: 소수점 3자리 통일 (`retention_pct`, `total_energy_mwh`, `dischargeable_*`)
- [ ] 프론트엔드: Wave별 개별 컬럼 추가 (Wave 1/2/3 Energy, Wave 1/2/3 Disch.)
- [ ] 프론트엔드: Wave별 토글 체크박스 (기존 @DC/@DC-Aux/@MV 패턴 활용)
- [ ] 프론트엔드: 갈색 헤더 "Total Energy" → "Cumul. Total Energy" 변경
- [ ] 프론트엔드: Cumul. Disch. @POI 시각적 강조 스타일
- [ ] 프론트엔드: `.toFixed(3)` 전체 적용
- [ ] result.html 읽기 전용 뷰 동기화
- [ ] 컬럼 과다 시 UX 개선 (요약 뷰 + 상세 팝업 대안 검토)

### 2.2 Out of Scope

- Augmentation 추천 알고리즘 변경
- 차트(retentionChart) 변경
- Excel export 형식 변경
- 새로운 효율 계산 추가

---

## 3. Technical Design

### 3.1 Backend Changes (retention.py)

#### 3.1.1 Per-Wave Breakdown 반환

`calculate_with_augmentation()` 함수에서 각 wave의 연도별 에너지를 별도로 추적:

```python
# 반환할 wave_details 구조
wave_details = {
    0: {  # wave index (0=initial, 1=aug1, 2=aug2, 3=aug3)
        "start_year": 0,
        "installed_energy_mwh": 500.0,
        "links": 90,
        "by_year": {
            0: {"retention_pct": 100.0, "energy_mwh": 500.0, "disch_poi_mwh": 420.5},
            1: {"retention_pct": 98.1, "energy_mwh": 490.5, "disch_poi_mwh": 412.5},
            ...
        }
    },
    1: {  # aug wave 1
        "start_year": 8,
        "installed_energy_mwh": 50.0,
        "links": 9,
        "by_year": {
            8: {"retention_pct": 100.0, "energy_mwh": 50.0, "disch_poi_mwh": 42.0},
            ...
        }
    }
}
```

#### 3.1.2 소수점 3자리 통일

`RetentionYear` 생성 시 모든 필드를 `round(x, 3)`으로 통일:
- `retention_pct`: 현재 `round(x, 1)` → `round(x, 3)`
- `total_energy_mwh`: 현재 `round(x, 1)` → `round(x, 3)`
- `dischargeable_energy_poi_mwh`: 현재 `round(x, 1)` → `round(x, 3)`
- 나머지 (`dc`, `dc_aux`, `mv`): 이미 `round(x, 3)` — 유지

#### 3.1.3 RetentionResult 확장

```python
@dataclass
class RetentionResult:
    cp_rate: float
    lookup_source: str
    retention_by_year: dict
    curve: list
    wave_details: dict = None  # NEW: per-wave breakdown
```

### 3.2 Frontend Changes

#### 3.2.1 테이블 컬럼 구조 (Augmentation 활성 시)

| 기본 | 토글 가능 | Aug 기본 | Aug Wave 토글 |
|------|-----------|----------|---------------|
| Year | @DC | Cumul. Total Energy | Wave 1 Energy |
| Retention % | @DC-Aux | **Cumul. Disch. @POI** | Wave 1 Disch. |
| Total Energy | @MV | | Wave 2 Energy |
| Disch. @POI | | | Wave 2 Disch. |
| | | | Wave 3 Energy |
| | | | Wave 3 Disch. |

#### 3.2.2 토글 체크박스 추가 (input.html)

기존 `ret-col-toggles` div에 Wave 토글 추가:
```html
<label><input type="checkbox" id="togWave1" onchange="toggleRetCol('colWave1', this.checked)" checked> Wave 1</label>
<label><input type="checkbox" id="togWave2" onchange="toggleRetCol('colWave2', this.checked)" checked> Wave 2</label>
<label><input type="checkbox" id="togWave3" onchange="toggleRetCol('colWave3', this.checked)" checked> Wave 3</label>
```

- Wave 토글은 Augmentation이 있을 때만 표시
- 기본: checked (모두 표시)

#### 3.2.3 소수점 표시 (app.js)

모든 `.toFixed(1)` → `.toFixed(3)` 변경:
- retention_pct: `.toFixed(3)` + `%`
- total_energy_mwh: `.toFixed(3)`
- dischargeable_*: `.toFixed(3)`

#### 3.2.4 Cumul. Disch. @POI 강조 스타일

```css
.retention-table .col-aug-highlight {
    font-weight: 700;
    color: #B35600;
    background: rgba(230,92,0,0.08);
    border-left: 3px solid #C76100;
}
```

### 3.3 UX 대안: 컬럼 과다 시

Wave 3개 × Energy+Disch 2개 = 6개 추가 컬럼. 기존 기본 4 + Aug 2 + Wave 6 = 12컬럼.

**대안 A (선택)**: 가로 스크롤 활용 (이미 `.retention-table__wrap`에 `overflow-x: auto` 있음)
- Wave 토글로 필요한 것만 표시
- 가장 단순하고 일관된 UX

**대안 B (필요 시)**: 요약 뷰 기본 + "상세 보기" 버튼 → 모달/팝업
- 기본: Year, Retention%, Total Energy, Disch. @POI, Cumul. Total, Cumul. Disch. @POI
- 모달: 전체 wave별 상세

→ **대안 A를 기본으로 구현**, 디자이너 리뷰 후 대안 B 검토

---

## 4. Implementation Order

| Step | File | Description | Est. |
|------|------|-------------|------|
| 1 | `retention.py` | per-wave breakdown + 소수점 3자리 통일 | Backend |
| 2 | `input.html` | 갈색 헤더 수정 + Wave 토글 체크박스 + Wave 컬럼 th 추가 | Frontend |
| 3 | `app.js` | wave_details 렌더링 + .toFixed(3) + 토글 로직 | Frontend |
| 4 | `style.css` | Cumul. Disch. @POI 강조 + Wave 컬럼 스타일 | Frontend |
| 5 | `result.html` | 읽기 전용 뷰 동기화 (소수점 + Aug 컬럼) | Frontend |
| 6 | 디자이너 리뷰 | 전체 UX 검토 + 대안 B 필요 여부 판단 | QA |

---

## 5. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| 컬럼 과다로 가독성 저하 | Medium | Wave 토글 기본 off + 필요 시만 on |
| 소수점 3자리로 컬럼 폭 증가 | Low | font-size 조정 또는 컬럼 min-width |
| wave_details 데이터 크기 증가 | Low | 20년 × 4wave = 80행, 무시 가능 |
| result.html과 input.html 불일치 | Medium | Step 5에서 동기화 |

---

## 6. Acceptance Criteria

- [ ] Augmentation 활성 시 각 wave의 연도별 Energy, Disch. @POI가 개별 컬럼으로 표시됨
- [ ] Wave 1/2/3 토글 체크박스로 개별 표시/숨기기 가능
- [ ] 갈색 헤더가 "Cumul. Total Energy", "Cumul. Disch. @POI"로 표시됨
- [ ] Cumul. Disch. @POI가 시각적으로 강조됨 (bold, border 등)
- [ ] 모든 숫자가 소수점 3자리까지 표시됨
- [ ] Augmentation 없을 때 기존과 동일하게 동작 (회귀 없음)
- [ ] result.html도 소수점 3자리 + Aug 컬럼 반영
