# SI Sizing Tool Ver.2.0

> BESS(Battery Energy Storage System) 종합 사이징 계산 웹 툴 — LG Energy Solution 내부용

---

## 1. 개요

사내 엑셀 사이징 툴(SI Design Tool)의 계산 로직을 웹 기반으로 전환하여, 입력→계산→결과→공유 프로세스를 자동화하고 팀 단위 설계 이력 관리를 가능하게 한다.

## 2. 기술 스택

| 구성 | 기술 | 비고 |
|------|------|------|
| Backend | Python 3.9+ / Flask | gunicorn 프로덕션 서빙 |
| Frontend | Jinja2 + Vanilla JS | 빌드 도구 없음, 오프라인 호환 |
| DB | SQLite (WAL mode) | 단일 파일 `sizing.db` |
| 배포 | Docker → 사내 AWS | IT팀 자동 배포 파이프라인 |
| 개발 서버 | `python run.py --port 5001` | localhost:5001 |

## 3. 폴더 구조

```
├── backend/
│   ├── app/
│   │   ├── main.py            # Flask app factory
│   │   ├── routes.py          # 메인 사이징 API (Blueprint: main)
│   │   ├── models.py          # 프로젝트/케이스 CRUD (raw SQL)
│   │   ├── auth.py            # 인증 Blueprint (/auth)
│   │   ├── decorators.py      # login_required, admin_required
│   │   ├── shared_routes.py   # Shared DB API (Blueprint: shared)
│   │   ├── shared_models.py   # 공유 설계 DB 모델
│   │   └── export.py          # Excel 내보내기
│   ├── calculators/           # 계산 엔진 모듈
│   │   ├── battery_sizing.py  # 배터리 구성 (Cell→Rack→Container)
│   │   ├── pcs_sizing.py      # PCS 용량/수량
│   │   ├── efficiency.py      # 시스템 효율 체인
│   │   ├── retention.py       # 용량 유지율 + Augmentation
│   │   ├── reactive_power.py  # 무효전력 (S,P,Q)
│   │   ├── rte.py             # Round-Trip Efficiency
│   │   ├── soc.py             # State of Charge
│   │   └── convergence.py     # 수렴 계산
│   ├── data/
│   │   ├── db/sizing.db       # SQLite DB (git-ignored)
│   │   └── products/          # 제품 스펙 JSON
│   └── tests/                 # 계산기 단위 테스트
├── frontend/
│   ├── static/
│   │   ├── css/style.css      # 전체 스타일
│   │   └── js/
│   │       ├── app.js         # 메인 앱 로직 (IIFE 모듈 패턴, ~2600줄)
│   │       └── charts.js      # Canvas 차트 (순수 JS, 외부 의존 없음)
│   └── templates/             # Jinja2 템플릿
│       ├── base.html          # 공통 레이아웃 (헤더/네비게이션)
│       ├── input.html         # 메인 입력 + 인라인 결과 표시
│       ├── projects.html      # 프로젝트 목록
│       ├── cases.html         # 케이스 관리
│       ├── compare.html       # 다중 케이스 비교
│       ├── summary.html       # 인쇄용 요약
│       ├── rte.html           # 독립 RTE 계산기
│       ├── login.html         # 로그인
│       ├── register.html      # 회원가입
│       ├── shared_list.html   # 공유 설계 목록
│       ├── shared_detail.html # 공유 설계 상세 (탭: Summary/Input/Result/Audit)
│       └── admin_audit.html   # 관리자 감사 로그
├── tests/                     # API 통합 테스트
├── docs/                      # PDCA 문서 (plan/design/analysis/report)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── gunicorn.conf.py
├── run.py                     # 개발 서버 진입점
├── run.bat                    # Windows 실행 스크립트
└── install.bat                # Windows 설치 스크립트
```

## 4. 완료된 기능

### Core Sizing (Phase 1) — 완료
- 배터리 사이징: Cell → Module → Rack → Link → Container 구성 자동 계산
- PCS 사이징: 모델 선택, 용량/수량 산정, 구성 (centralized/distributed)
- 시스템 효율 체인: HV→MV→LV→PCS→DC 7단 효율 계산
- 용량 유지율: 연도별 Retention curve + Augmentation wave 지원
- 무효전력: S, P, Q 분석 + SLD 다이어그램
- RTE: Round-Trip Efficiency 독립 계산기 페이지
- SOC: Rest SOC, Usage Pattern, Average SOC
- 수렴 계산: Convergence solver

### Engineering Features (F1~F7) — 완료
- F1: M10 주문 수량, 변압기 블록, 파워블록 라벨
- F2+F5: Reactive Power 탭 (S,P,Q + SLD)
- F3: 독립 RTE 계산기 페이지
- F4: Definition 툴팁 (기술 용어 호버 설명)
- F6: Usage Pattern / Average SOC
- F7: Annual Energy Throughput 컬럼

### Multi-Case Comparison (Phase 2b) — 완료
- 프로젝트 내 다중 케이스 생성/복제/삭제
- 나란히 비교 테이블 (KPI 하이라이트)
- URL 파라미터 기반 케이스 컨텍스트 (`?case_id=X&project_id=Y`)

### Shared DB & 버전관리 — 완료
- 회원가입/로그인 (세션 기반, werkzeug 비밀번호 해싱)
- 역할 기반 접근 제어 (engineer / admin)
- 사이징 결과 → Shared DB 업로드 (input.html 결과 섹션에서 직접)
- 설계 목록: 필터(프로젝트/상태/작성자/날짜), 정렬, 페이지네이션
- 설계 상세: Summary/Input/Result/Audit 4탭 뷰
- 상태 관리: Draft → Submit(잠금) → Unlock(사유 필수) → Relock
- 버전 관리: 프로젝트별 자동 revision 번호, New Revision 생성
- 감사 로그: 모든 동작 기록 (생성/수정/제출/잠금해제 등)
- Admin 감사 페이지: 전체 로그 조회

### 기타
- Excel 내보내기 (`/api/export`)
- 인쇄용 Summary 페이지
- Docker 배포 설정 (Dockerfile + docker-compose.yml + gunicorn)
- Windows 오프라인 설치 스크립트 (install.bat + run.bat)

## 5. 미구현 / 보류

| 항목 | 상태 | 비고 |
|------|------|------|
| Phase 2a: SOC & Augmentation 고도화 | Plan만 작성 | 구현 미착수 |
| Shared DB Edit UI | API만 동작 | 프론트엔드 편집 화면 미구현 (Phase C) |
| Shared Design 간 비교 | 미구현 | Case 비교는 있음 |
| Shared Design Export | 미구현 | Excel/PDF 다운로드 없음 |
| `result.html` 정리 | Dead code | 렌더링 route 없음, input.html에서 인라인 처리 |

## 6. 알려진 이슈

1. **로그인 리다이렉트 미복귀**: `/shared/` 비로그인 시 로그인 페이지로 이동 후, 원래 가려던 페이지로 돌아가지 않음
2. **result.html dead code**: Flask route가 없어 사용되지 않는 템플릿. input.html이 실제 결과 표시 담당
3. **Shared DB Edit 버튼**: 클릭 시 alert("Phase C 예정")만 표시

## 7. DB 스키마 요약

```
sizing.db (SQLite, WAL mode)
├── projects          # 프로젝트 마스터
├── cases             # 프로젝트별 케이스 (input_data, result_data JSON)
├── users             # 사용자 (username, email, password_hash, role)
├── designs           # 공유 설계 (project_name, revision, status, input/result JSON)
├── unlock_log        # 잠금 해제 이력 (사유, 해제자, 시간)
└── design_audit_log  # 감사 로그 (action, actor, detail, timestamp)
```

## 8. 실행 방법

### 개발 (Mac)
```bash
pip install -r requirements.txt
python run.py --port 5001
# → http://localhost:5001
```

### 프로덕션 (Docker)
```bash
docker-compose up -d
# → http://localhost:5000
```

### Windows 오프라인 배포
```
1. install.bat 실행 (venv 생성 + 의존성 설치)
2. run.bat 실행 (서버 시작)
```

## 9. 배포 경로

```
[개발 Mac] → git push → [GitHub] → IT팀 pull → [사내 AWS Docker 배포]
```

## 10. Hand-off 참고사항

- **아키텍처 패턴**: Flask Blueprint (main_bp, auth_bp, shared_bp), raw SQL (ORM 없음), Jinja2 + vanilla JS (빌드 도구 없음)
- **핵심 파일**: `app.js` (~2600줄 IIFE), `routes.py` (~1100줄), `input.html` (~1080줄)
- **계산 로직**: `backend/calculators/` 각 모듈이 독립적. dataclass 기반 Input/Output
- **DB**: 단일 `sizing.db` 파일. 마이그레이션 도구 없음 — `init_db()` / `init_shared_db()`가 CREATE IF NOT EXISTS로 처리
- **테스트**: `tests/` 디렉토리에 계산 검증 + API 통합 테스트. `pytest` 실행
