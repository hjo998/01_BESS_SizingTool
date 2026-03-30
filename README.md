# BESS Sizing Tool

BESS(Battery Energy Storage System) 종합 사이징 계산 웹 툴

## 목적
사내 엑셀 사이징 툴의 계산 로직을 웹 기반으로 전환하여, 입력-계산-결과 프로세스를 자동화하고 이력 관리를 가능하게 한다.

## 주요 기능
- **배터리 사이징**: Cell → Module → Rack → Container 구성 계산
- **PCS 사이징**: Power Conversion System 용량 및 수량 산정
- **변압기 사이징**: 변압기 용량 및 사양 결정
- **BOP 설계**: Balance of Plant 부대설비 산정
- **결과 리포트**: 사이징 결과를 PDF/Excel로 출력
- **이력 관리**: 프로젝트별 사이징 이력 저장 및 비교

## 기술 스택
| 구성 | 기술 | 비고 |
|------|------|------|
| Backend | Python (Flask) | 클라우드 PC 설치 가능 |
| Frontend | HTML/JS/CSS | 브라우저 기반 |
| DB | SQLite | 설치 불필요, 단일 파일 |
| 계산 엔진 | Python (NumPy 등) | 엑셀 로직 이식 |

## 폴더 구조
```
01_BESS_SizingTool/
├── backend/
│   ├── app/            # Flask 앱 (라우팅, API)
│   ├── calculators/    # 사이징 계산 모듈 (배터리, PCS, 변압기, BOP)
│   └── data/           # 제품 스펙 DB, 기본값 데이터
├── frontend/
│   ├── static/         # CSS, JS, 이미지
│   └── templates/      # HTML 템플릿 (Jinja2)
├── tests/              # 단위 테스트 (계산 검증)
├── docs/               # 설계 문서, 엑셀 분석 결과
├── requirements.txt
├── run.py              # 실행 진입점
└── README.md
```

## 개발 상태
- [ ] 사내 엑셀 사이징 툴 분석
- [ ] 계산 로직 Python 이식
- [ ] 웹 UI 구현
- [ ] 결과 리포트 출력
- [ ] 테스트 및 검증
