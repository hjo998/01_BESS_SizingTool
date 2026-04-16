# BESS Sizing Tool - 향후 개선 사항

> ECAP 서버 migration 완료 후 진행할 개선 항목 목록.
> 현재 migration 단계에서는 기능 변경 없이 서버 배포만 우선 진행한다.

---

## 1. 프론트엔드 기술 스택 전환 (React + MUI)

### 1-1. 현재 상태
- Jinja2 SSR + Vanilla JS (ES5 IIFE 패턴)
- `app.js` 단일 파일 ~2600줄 (모놀리식)
- DOM 직접 조작 (~80개 getElementById + textContent)
- 인라인 onclick 핸들러
- 전역 변수 기반 상태 관리 (`lastResult`, `_caseId`, `augChipId` 등)

### 1-2. 전환 방향
- React 18+ (TypeScript)
- MUI (Material-UI) 컴포넌트 라이브러리 -> ECAP 공통 테마 적용
- Zustand 또는 Jotai 상태 관리
- react-hook-form + Zod 폼 검증
- TanStack Query (react-query) API 레이어
- Recharts 차트 라이브러리 (현재 Canvas 직접 렌더링 + Chart.js 혼재)

### 1-3. 컴포넌트 구조 (권장)
```
src/
  components/
    layout/         AppLayout, AppHeader, AppFooter
    sizing/
      tabs/         ProjectBasicTab, EfficiencyTab, ProductSelectionTab, AuxiliaryLoadTab, ReactivePowerTab
      results/      KpiCards, BatteryResultTable, PcsResultTable, RetentionTable, RetentionChart, SocVisualization
      diagrams/     EfficiencyChainDiagram, AuxChainDiagram, TopologyDiagram, LossWaterfallBar
      forms/        AugmentationWavesTable, UsagePatternCard
    projects/       ProjectsGrid, ProjectCard, CreateProjectModal
    cases/          CasesGrid, CaseCard, CreateCaseModal
    compare/        ComparisonTable, RetentionOverlayChart
    shared/         SharedDesignsList, SharedDetailPage, UnlockModal
  hooks/
    useCalculation.ts
    useProducts.ts
    useCaseContext.ts
  stores/
    sizingStore.ts
    authStore.ts
  api/
    sizingApi.ts
    projectApi.ts
    sharedApi.ts
  utils/
    efficiencyCalc.ts   (프론트엔드 실시간 효율 미리보기용 순수 함수)
```

### 1-4. 마이그레이션 복잡도

| 컴포넌트 | 복잡도 | 이유 |
|----------|--------|------|
| Projects/Cases 페이지 | 낮음 | 단순 CRUD + 카드 그리드 |
| Shared DB 페이지 | 낮음 | 목록 + 상세 패턴 |
| 비교 페이지 | 중간 | 동적 테이블 + 차트 |
| Efficiency Tab | 높음 | 실시간 계산 + 복수 연동 다이어그램 |
| Product Selection Tab | 높음 | 복잡한 SVG 토폴로지 다이어그램 3종 |
| Retention Table | 높음 | 동적 열 구조 (4개 토글 x 4개 파동) |
| 결과 섹션 전체 | 높음 | 80+ 개별 필드 표시 |

### 1-5. 재사용 가능한 로직
- 효율 계산 수식 (`updateEfficiencyPreview` 내 수식 부분) -> 순수 함수 추출
- Waterfall 세그먼트 계산 -> 순수 함수화
- 캐스케이딩 드롭다운 필터 로직 -> 순수 함수
- Canvas 차트 렌더링 로직 -> useRef+useEffect 래핑 또는 Recharts 교체

---

## 2. 백엔드 개선

### 2-1. ORM 도입
- 현재: raw sqlite3, 매 함수마다 커넥션 열고 닫음, 커넥션 풀링 없음
- 개선: SQLAlchemy Core 또는 ORM 도입
- models.py(280줄)와 shared_models.py(490줄)의 모든 raw SQL을 ORM으로 전환
- Alembic을 활용한 체계적 DB 마이그레이션 관리

### 2-2. API 스키마 관리
- 현재: 계산 request/response 계약이 코드 내부에 암묵적 존재
- 개선: Pydantic v2 모델로 명시적 스키마 정의
- OpenAPI/Swagger 자동 생성 (Flask-RESTX 또는 FastAPI 전환 검토)

### 2-3. FastAPI 전환 검토
- Flask -> FastAPI 전환 시:
  - Pydantic 네이티브 지원
  - async 지원 (향후 비동기 계산 필요 시)
  - 자동 OpenAPI 문서 생성
  - 타입 안전성 향상
- 현재 Flask 의존성이 주로 라우팅+세션에만 있으므로 전환 비용 낮음

### 2-4. 계산 오케스트레이터 리팩토링
- `_run_calculation()` (~470줄 단일 함수): SRP 위반
- 효율/PCS/배터리/리텐션/RTE 각 단계를 Pipeline 패턴으로 분리
- 각 단계의 input/output 계약을 Pydantic 모델로 명시

### 2-5. export 모듈 개선
- 현재: `_get_nested()`가 deep nested path를 문자열로 처리 (타입 안전성 없음)
- 개선: 타입 안전한 결과 접근 (Pydantic 모델 또는 TypedDict)
- PDF export 포맷 추가 검토
- LG 브랜드 색상 하드코딩(`LG_RED = "A50034"`) -> 설정 외부화

---

## 3. 계산 엔진 개선

### 3-1. 데이터 정합성 문제 해결
| # | 파일 | 내용 | 우선순위 |
|---|------|------|----------|
| 1 | `products.json` | `rack_energy_kwh x racks_per_link != nameplate_energy_mwh` 불일치 (JF3: 6x793.428=4760.6 kWh vs 5554 kWh) | High |
| 2 | `pcs_temp_derating.json` | 45C FLEX(Chg) 비단조 데이터 (44C:2898.4 -> 45C:2972 -> 46C:2953.6) | High |
| 3 | `pcs_alt_derating.json` | 다수 모델(FP4200, FP4390_JF1, FLEX, LSE)의 고도 derating 데이터 누락 | Medium |
| 4 | `retention_table_rsoc30.json` | 12개 엔트리의 cp_rate: null | High |
| 5 | `soc.py` 라인 125-141 | measurement method 조정값이 플레이스홀더 (Excel B1:C7 기준 교체 필요) | High |
| 6 | `soc.py` 라인 146-147 | effective_dod = applied_dod x 1.0 (product correction 항상 1.0) | Low |

### 3-2. 하드코딩 제거
| # | 파일 | 위치 | 내용 |
|---|------|------|------|
| 1 | `battery_sizing.py` | 라인 196 | `no_of_mvt = no_of_pcs / 2` (구성별 MVT 비율 고정) |
| 2 | `battery_sizing.py` | 라인 83-107 | `known_racks` 하드코딩 dict (products.json 사용으로 대체 가능) |
| 3 | `retention.py` | 라인 77-83 | JF3 retention 하드코딩 골든 데이터 (특정 CP rate 전용) |
| 4 | `reactive_power.py` | 라인 23-24 | `impedance_hv=0.14`, `impedance_mv=0.08` 기본값 |
| 5 | `convergence.py` | 초기 CP-rate | 0.25 고정 (제품/구성 무관) |

### 3-3. 멀티스레드 안전성
- `convergence.py` 라인 413: `inp.link_override` 직접 변조 (try/finally 보호됨, 멀티스레드 비안전)
- dataclass의 shallow copy 또는 `dataclasses.replace()` 사용으로 교체

### 3-4. 테스트 커버리지 확대
- 현재 JSON expected_result 중간값이 실제 코드 출력과 불일치하는 항목들:
  - `req_power_dc`: JSON 104.345 vs 코드 ~104.424
  - `req_energy_dc`: JSON 417.812 vs 코드 ~423.56
  - `cp_rate_dc`: JSON 0.240863 vs 코드 ~0.24097
- 핵심 결과(no_of_links, installation_energy 등)에는 영향 없지만, 테스트 golden data 정비 필요

---

## 4. 운영 품질 개선

### 4-1. 비동기 계산 지원
- 현재: sync 요청-응답 모델 (단건 계산)
- 개선 조건: 계산 시간이 HTTP timeout을 넘기거나, batch/multi-case 실행 필요 시
- 방향: Celery + Redis 또는 AWS SQS 기반 async job queue

### 4-2. Revision Workflow 서비스 경계 분리
- 현재: submit, unlock, relock, new revision 로직이 shared_routes.py + shared_models.py에 산재
- 개선: RevisionService 클래스로 통합, 상태 전이 규칙 명시화
- ECAP 권한 모델과 연동 가능한 서비스 경계 확보

### 4-3. 보안 강화
- `/api/calculate` 엔드포인트에 현재 인증 없음 (누구나 호출 가능)
- `main.py`의 하드코딩 SECRET_KEY(`'bess-sizing-tool-dev'`) -> 환경변수 필수화
- 비밀번호 최소 길이 4자 (auth.py 86행) -> ECAP 플랫폼 인증으로 대체

### 4-4. 모니터링 및 가시성
- 구조화 로깅에 trace ID, 계산 소요 시간 등 운영 메트릭 추가
- 계산 결과의 audit trail (누가, 언제, 어떤 입력으로 계산했는지)
- 에러 추적 (Sentry 등) 연동

### 4-5. Export 확장
- 현재: Excel 단일 포맷
- 추가 검토: PDF export, API 응답으로 직접 다운로드 대신 S3 pre-signed URL

---

## 5. 미구현/보류 기능 정리 (README 기준)

| 항목 | 현재 상태 | 우선순위 |
|------|-----------|----------|
| Phase 2a: SOC & Augmentation 고도화 | Plan만 작성 | Medium |
| Shared DB Edit UI | API만 동작, 프론트엔드 편집 화면 미구현 | High |
| Shared Design 간 비교 | 미구현 (Case 비교는 있음) | Medium |
| Shared Design Export | 미구현 (Excel/PDF) | Medium |
| `result.html` 정리 | Dead code (route 없음, input.html에서 인라인 처리) | Low (삭제) |
| 로그인 리다이렉트 미복귀 | `/shared/` 비로그인 시 원래 페이지 미복귀 | Low (ECAP 인증 시 해결) |

---

## 6. 구현 권장 순서

1. **서버 migration 완료 후** -> 이 문서의 개선 착수
2. 3-1 데이터 정합성 문제 (계산 정확도 직결)
3. 2-2 API 스키마 관리 (프론트엔드 전환 전제 조건)
4. 1번 전체 (React 프론트엔드 전환)
5. 2-3 FastAPI 전환 (선택)
6. 4-1 비동기 계산 (수요 발생 시)
7. 4-2 Revision Workflow 서비스 분리

---

*문서 작성일: 2026-04-16*
*문서 작성 기준: 코드 분석 + SI_SIZING_migration 문서 + 수동 계산 검증 결과*
