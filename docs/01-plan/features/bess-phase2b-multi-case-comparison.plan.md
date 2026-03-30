# Multi-Case Comparison Planning Document

> **Summary**: BESS Sizing Tool에 다중 케이스 비교 기능을 추가하여, 동일 프로젝트에서 여러 설계 시나리오를 나란히 비교하고 최적안을 선정할 수 있게 한다.
>
> **Project**: BESS Sizing Tool (LG Energy Solution)
> **Version**: 2.0 (Phase 2b)
> **Author**: alex
> **Date**: 2026-03-26
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 BESS Sizing Tool은 한 번에 하나의 케이스만 계산 가능하여, 동일 프로젝트에서 배터리/PCS/효율 조합을 변경한 여러 시나리오를 비교하려면 수동으로 각각 계산 후 엑셀에 옮겨 비교해야 함. 30+ 프로젝트를 관리하는 상황에서 비효율적. |
| **Solution** | 프로젝트 내 다중 케이스(Case) 저장·관리 체계 구축 + 케이스 간 핵심 지표(설치 에너지, PCS 수, Rack 수, Retention, RTE 등) 병렬 비교 테이블/차트 UI + 케이스 복제(Clone) 기능으로 파라미터 미세 조정 지원. |
| **Function/UX Effect** | 사용자가 Case A/B/C를 생성하여 파라미터만 변경 후 한 화면에서 핵심 KPI를 나란히 비교. 최적안 선택 후 바로 Excel 리포트에 비교표 포함 출력 가능. |
| **Core Value** | 설계 의사결정 시간 단축 (수동 비교 대비 ~70% 절감 예상). 프로젝트 제안서에 비교표를 포함하여 고객 설득력 강화. 설계 이력 축적으로 향후 유사 프로젝트 참조 가능. |

---

## 1. Overview

### 1.1 Purpose

동일 프로젝트 내에서 **여러 사이징 케이스를 생성·계산·비교**할 수 있는 기능을 구현한다. BESS 프로젝트 제안 시, 발주처에게 2~4개의 설계 옵션(예: JF2 vs JF3, 100MW vs 120MW, 다른 PCS 구성 등)을 비교표로 제시하는 것이 표준 프로세스이며, 현재 이를 수동으로 수행하고 있어 자동화가 필요하다.

### 1.2 Background

- Phase 1 (완료): 단일 케이스 사이징 계산 엔진 + Flask 웹 UI + 프로젝트 저장/로드
- 현재 `projects` 테이블은 프로젝트당 1개의 input/result만 저장 (1:1 관계)
- 보고서 5.2절에 "Multi-System: Support Type A + Type B combined configurations" 및 "scenario comparison" 이 Phase 2 항목으로 명시됨
- 실무에서 프로젝트당 2~5개의 설계 대안을 비교하는 것이 일반적

### 1.3 Related Documents

- Phase 1 Report: `docs/archive/2026-03/bess-sizing-tool/bess-sizing-tool.report.md`
- Design Document: `docs/DESIGN.md`
- HANDOFF: `HANDOFF_TO_CLAUDE_CODE.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 프로젝트-케이스 1:N 관계 DB 스키마 확장 (`cases` 테이블)
- [ ] 케이스 CRUD API (생성, 조회, 수정, 삭제, 복제)
- [ ] 케이스 비교 UI (Side-by-side 테이블 + 차트)
- [ ] 케이스 복제(Clone) 기능 (기존 케이스 파라미터 복사 후 일부 변경)
- [ ] 비교 결과 Excel 출력에 비교표 시트 추가
- [ ] 기존 프로젝트 데이터 마이그레이션 (단일 → 케이스 구조)

### 2.2 Out of Scope

- Type A + Type B 혼합 구성 (하나의 케이스 내 두 가지 배터리 조합) → Phase 2c
- 파라메트릭 스윕 (자동으로 변수 범위를 돌며 최적 조합 탐색) → Phase 3
- 다중 사용자 동시 편집 → Phase 4
- PDF 비교 리포트 → Phase 2 이후

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 프로젝트 내 최대 10개 케이스 생성 가능 | High | Pending |
| FR-02 | 케이스별 독립적인 입력 파라미터 저장 (효율, 제품, PCS 등) | High | Pending |
| FR-03 | 케이스 계산 결과 독립 저장 (efficiency, pcs, battery, retention, rte) | High | Pending |
| FR-04 | 케이스 복제(Clone): 기존 케이스의 입력값을 복사하여 새 케이스 생성 | High | Pending |
| FR-05 | 2~5개 케이스를 선택하여 나란히 비교하는 비교 화면 | High | Pending |
| FR-06 | 비교 테이블: 핵심 KPI (설치 에너지, PCS 수, Rack 수, LINK 수, RTE, Retention Y10/Y20) | High | Pending |
| FR-07 | 비교 차트: Retention 커브 오버레이 (같은 그래프에 여러 케이스 표시) | Medium | Pending |
| FR-08 | 비교 결과 Excel 출력 시 "Comparison" 시트 추가 | Medium | Pending |
| FR-09 | 기존 단일 프로젝트 데이터를 "Case 1"로 자동 마이그레이션 | High | Pending |
| FR-10 | 케이스별 이름/메모 입력 (예: "JF3 Base", "JF2 Alternative") | Medium | Pending |
| FR-11 | 케이스 목록 화면에서 각 케이스 상태 표시 (계산 완료/미완료) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 5개 케이스 동시 비교 시 렌더링 < 1초 | 브라우저 개발자 도구 |
| Data Integrity | 케이스 삭제 시 프로젝트 삭제 안됨 (CASCADE 방지) | 단위 테스트 |
| Backward Compatibility | 기존 프로젝트 로드 시 자동 마이그레이션 (데이터 손실 없음) | 마이그레이션 테스트 |
| Offline | 모든 기능 오프라인 동작 (기존 제약 유지) | 네트워크 차단 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `cases` 테이블 생성 및 CRUD API 동작 확인
- [ ] 기존 프로젝트 마이그레이션 성공 (데이터 손실 없음)
- [ ] 비교 화면에서 2~5개 케이스 나란히 비교 가능
- [ ] Retention 커브 오버레이 차트 정상 표시
- [ ] Excel 출력에 Comparison 시트 포함
- [ ] 기존 15개 테스트 여전히 통과 (회귀 없음)
- [ ] 새 기능 테스트 5개+ 추가 및 통과

### 4.2 Quality Criteria

- [ ] 기존 테스트 15/15 통과 (회귀 없음)
- [ ] 새 테스트 추가 (케이스 CRUD, 비교 API, 마이그레이션)
- [ ] 케이스 비교 Excel 출력 검증

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| DB 마이그레이션 실패로 기존 데이터 손실 | High | Low | 마이그레이션 전 DB 백업 자동화. 롤백 스크립트 준비. |
| 비교 UI 복잡도 증가로 기존 단일 케이스 UX 저하 | Medium | Medium | 단일 케이스 워크플로우는 기존과 동일하게 유지. 비교는 별도 화면. |
| 5개 이상 케이스 비교 시 화면 가독성 저하 | Medium | Medium | 비교 화면 기본 2~3개, 최대 5개 제한. 스크롤 가능한 비교 테이블. |
| 기존 `/api/calculate` 엔드포인트 변경으로 프론트엔드 호환성 깨짐 | High | Low | 기존 API는 그대로 유지. 케이스 API는 별도 엔드포인트(`/api/cases/*`)로 추가. |
| 클라우드 PC에서 SQLite 마이그레이션 시 파일 잠금 | Low | Low | 마이그레이션은 앱 시작 시 1회 실행. WAL 모드 사용. |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites, portfolios | |
| **Dynamic** | Feature-based modules, BaaS integration | Web apps with backend | **X** |
| **Enterprise** | Strict layer separation, DI, microservices | High-traffic systems | |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| DB Schema | (A) cases 테이블 분리 / (B) projects에 JSON 배열 | **(A) cases 테이블** | 정규화, 인덱스 가능, 개별 케이스 CRUD 용이 |
| 비교 UI | (A) 전용 비교 페이지 / (B) result 페이지 탭 추가 | **(A) 전용 페이지** | 기존 결과 화면 UX 유지, 비교는 별도 컨텍스트 |
| 마이그레이션 | (A) 앱 시작 시 자동 / (B) CLI 명령 수동 | **(A) 자동** | 사용자 부담 최소화, 클라우드 PC에서 CLI 실행 번거로움 |
| 케이스 계산 | (A) 개별 호출 / (B) 일괄 배치 계산 | **(A) 개별** | 기존 `/api/calculate` 재사용, 복잡도 최소화 |
| 비교 차트 | Chart.js 재사용 | **Chart.js** | 이미 번들됨, 다중 데이터셋 지원 |

### 6.3 DB Schema Extension

```sql
-- 기존 projects 테이블 유지 (프로젝트 메타만)
-- ALTER: input_data/result_data 제거 → cases로 이관

-- 새 테이블: 프로젝트별 다중 케이스
CREATE TABLE cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    case_name   TEXT    NOT NULL DEFAULT 'Case 1',
    case_memo   TEXT    DEFAULT '',
    input_data  TEXT    NOT NULL,      -- JSON (기존 input_data와 동일 형식)
    result_data TEXT    DEFAULT NULL,   -- JSON (계산 결과, NULL = 미계산)
    is_baseline BOOLEAN DEFAULT 0,     -- 기준 케이스 여부
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE INDEX idx_cases_project ON cases(project_id);
```

### 6.4 API Endpoints (추가)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects/<id>/cases` | 프로젝트의 모든 케이스 목록 |
| POST | `/api/projects/<id>/cases` | 새 케이스 생성 |
| GET | `/api/cases/<case_id>` | 케이스 상세 조회 |
| PUT | `/api/cases/<case_id>` | 케이스 수정 |
| DELETE | `/api/cases/<case_id>` | 케이스 삭제 |
| POST | `/api/cases/<case_id>/clone` | 케이스 복제 |
| POST | `/api/cases/<case_id>/calculate` | 케이스 계산 실행 |
| POST | `/api/projects/<id>/compare` | 선택 케이스 비교 데이터 반환 |
| POST | `/api/projects/<id>/export/comparison` | 비교표 Excel 출력 |

### 6.5 Frontend Pages (추가/수정)

| Page | Route | Description |
|------|-------|-------------|
| **Cases List** | `/project/<id>/cases` | 프로젝트 내 케이스 목록 + 관리 |
| **Case Input** | `/project/<id>/case/<cid>` | 개별 케이스 입력 (기존 input.html 재활용) |
| **Comparison** | `/project/<id>/compare` | 케이스 비교 화면 (테이블 + 차트) |

### 6.6 Folder Structure (변경분)

```
backend/app/
├── models.py          # cases CRUD 추가, 마이그레이션 로직 추가
├── routes.py          # 기존 유지 + cases API 추가
└── export.py          # comparison 시트 추가

frontend/templates/
├── input.html         # 케이스 컨텍스트 표시 추가 (최소 변경)
├── cases.html         # [NEW] 케이스 목록/관리 화면
├── compare.html       # [NEW] 비교 화면
└── result.html        # 케이스 이름 표시 추가 (최소 변경)

frontend/static/js/
├── app.js             # 케이스 관련 API 호출 추가
└── compare.js         # [NEW] 비교 테이블/차트 로직
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` has coding conventions section
- [x] Phase 1 architecture established (Flask + SQLite + Chart.js)
- [x] Test pattern established (pytest + test_case JSON)
- [x] Naming: snake_case (Python), camelCase (JS)
- [x] API pattern: `/api/<resource>` RESTful

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **DB Migration** | Missing | 자동 마이그레이션 패턴 (앱 시작 시 버전 체크) | High |
| **Case Naming** | N/A | 기본 "Case N" 자동명명, 사용자 수정 가능 | Medium |
| **API Versioning** | None | 기존 API 유지 + 새 엔드포인트 추가 (breaking change 없음) | Medium |

---

## 8. Implementation Order

### Step 1: DB Schema Extension + Migration (1일)
1. `cases` 테이블 DDL 추가 (`models.py`)
2. 마이그레이션 로직: 기존 projects.input_data/result_data → cases 이관
3. 마이그레이션 테스트 작성

### Step 2: Cases CRUD API (1일)
1. Cases CRUD 엔드포인트 구현 (`routes.py`)
2. Clone 엔드포인트 구현
3. Case별 계산 엔드포인트 (기존 `/api/calculate` 재활용)
4. API 테스트 작성

### Step 3: Cases List UI (1일)
1. `cases.html` 템플릿 작성
2. 케이스 목록, 생성, 삭제, 복제 UI
3. 기존 `input.html`에서 케이스 컨텍스트 연결

### Step 4: Comparison UI (1.5일)
1. `compare.html` 템플릿 작성
2. 비교 테이블 (핵심 KPI 나란히)
3. Retention 커브 오버레이 차트 (Chart.js 다중 dataset)
4. `compare.js` 비교 로직

### Step 5: Excel Export + Integration (0.5일)
1. `export.py`에 Comparison 시트 추가
2. 비교 화면에서 Excel 다운로드 연결
3. 통합 테스트

**예상 총 소요: 5일**

---

## 9. Next Steps

1. [ ] Write design document (`bess-phase2b-multi-case-comparison.design.md`)
2. [ ] Review and approval
3. [ ] Start implementation (Step 1: DB Schema)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-26 | Initial draft | alex |
