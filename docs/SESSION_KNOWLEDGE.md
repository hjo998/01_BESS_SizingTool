# Session Knowledge — BESS Sizing Tool

> 세션별 축적 노하우. 새 세션에서 이 파일을 읽으면 맥락을 빠르게 파악 가능.
> 최종 업데이트: 2026-04-14

---

## 1. 아키텍처 변경 이력 (이번 세션)

### 1.1 Power Flow 모듈 (`power_flow.py`) — 신규
- **기존** `reactive_power.py`: 효율 기반 (`P_loss = S × (1-η)`), Q는 부하 무관
- **신규** `power_flow.py`: 임피던스 기반 (`P_loss = 3×I²×R`, `Q_loss = Z%×S_rated×(S/S_rated)²`)
- 8단계: PCS → LV → MVT → MV_BUS → AUX → MV_LINE → MPT → POI
- Per-powerblock 계산 (LV, MVT) → MV Bus에서 집합
- **Top-down** (POI→PCS): 반복 수렴으로 필요 PCS 출력 산정
- **Bottom-up** (PCS→POI): 기존 방식, PCS 출력에서 POI 도달량 계산
- `reactive_power.py`는 하위 호환용으로 유지

### 1.2 RTE v2 (`rte.py`) — 재작성
- 4개 Reference Point: DC, PCS, MV, POI
- `dc_rte_by_year` 배열 (연차별 퇴화)
- Aux 에너지 밸런스: `RTE = E_out / (E_charge + E_rest_aux)`
- `total_battery_loss_factor` 제거 — `battery_dc_rte`가 DC 터미널 기준으로 포함

### 1.3 LINK 사이징 로직 — 수정
- **기존**: BOL 기준 `req_energy_dc / nameplate` → LINK 개수
- **신규**: Oversizing year의 retention rate 반영
  ```
  req_bol = req_poi / retention(oversizing_yr)
  req_dc = req_bol / total_efficiency
  links = ceil(req_dc / nameplate) → links_per_pcs 배수 올림
  → CP-rate → retention 갱신 → 수렴까지 반복
  ```
- 진동 시 큰 값 선택

### 1.4 PF → Q 변환
- `Q = P × tan(acos(PF))` — routes.py에서 `power_factor` 입력으로 자동 계산

---

## 2. 기술적 교훈 (버그 & 패턴)

### 2.1 Python 스코핑 — 조건부 import 금지
```python
# BAD: 함수 내 조건부 import → Python이 지역 변수로 취급
def func(body):
    if isinstance(x, list):
        import math          # ← 이 줄이 있으면
        y = math.prod(x)
    z = math.tan(...)        # ← UnboundLocalError (math가 지역 취급됨)

# GOOD: 모듈 최상단 import
import math
```

### 2.2 Top-down 수렴 — Q는 가산 보정
- P: 비율 스케일링 (`pcs_p *= target_p / result_p`) — P 손실이 작아서 안정
- Q: **가산 보정** (`pcs_q += damping × error_q / num_pcs`) — Q는 `Q_poi = Q_pcs - Q_consumed` 관계라 비율 스케일링 실패
- 초기 Q 추정: 변압기 Z% 파라미터로 Q 소모량 사전 추정

### 2.3 SVG 반응형 — viewBox 트릭
- `viewBox` 작게 → 요소가 크게 보임 (확대 효과)
- `width="100%"` + `preserveAspectRatio="xMidYMid meet"` → 컨테이너에 맞춰 스케일링
- 고정 viewBox (600×200) + 큰 요소가 동적 viewBox보다 예측 가능

### 2.4 UI/UX 피드백 패턴
- 사용자는 **큰 카드보다 깔끔한 테이블** 선호 (정보 밀도 > 시각적 화려함)
- SLD는 **전체 너비**로 크게, 테이블은 **컴팩트하게**
- Summary는 **3×2 그리드 + Waterfall** 나란히 배치 (3:7)
- React 코드의 장점: 계산 모델 (임피던스 기반), 단점: 직접 포팅 시 과잉 장식

---

## 3. 파일 구조 (현재)

```
backend/calculators/
  power_flow.py      ← NEW: 임피던스 기반 8단계 Power Flow
  rte.py             ← REWRITTEN: 4 ref point × 연차별 × aux
  reactive_power.py  ← LEGACY: 효율 기반 (하위 호환)
  battery_sizing.py  ← MODIFIED: oversizing_retention_rate
  convergence.py     ← MODIFIED: retention 포함 수렴 루프
  efficiency.py      ← 변경 없음
  retention.py       ← 변경 없음 (lookup_retention_curve 사용)

backend/app/
  routes.py          ← MODIFIED: /api/power-flow, /api/rte v2, PF→Q

frontend/templates/
  input.html         ← MODIFIED: Tab 5 리뉴얼 (SLD + 테이블 + Summary)
  rte.html           ← REWRITTEN: 4 ref point + 연차별 테이블

frontend/static/js/
  app.js             ← MODIFIED: drawSLD(), drawLossWaterfall(), 
                       updateReactivePowerTab(), collectFormData (PF fields),
                       sessionStorage 연동

tests/
  test_power_flow.py ← NEW: 16 tests
  test_rte_v2.py     ← NEW: 12 tests (기존 28 + 신규 28 = 66 total)
```

---

## 4. API 엔드포인트 (현재)

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/api/calculate` | POST | 메인 계산 (convergence + power_flow + rte v2) |
| `/api/power-flow` | POST | 독립 Power Flow (bottom_up / top_down) |
| `/api/rte` | POST | RTE v2 (chain_eff 입력) 또는 Legacy (total_bat_poi_eff) |
| `/api/reactive-power` | POST | Legacy RP (하위 호환) |

---

## 5. 다음 세션 작업 목록 (23개 항목)

### 우선순위 HIGH (핵심 기능)
1. **Usage Pattern SOC 그래프** (Tab 1) — 0~24h 시간축, 0~100% SOC, charge/rest/discharge 패턴
2. **Augmentation auto-recommend 수정** — 연도 직접 입력 존중, 빈 경우만 제안
3. **Efficiency Default 편집 UI** (Tab 2)
4. **Efficiency Tab SLD** = RP Tab SLD 재사용 + aux 상세
9. **DC→Aux aux_line 누락 확인** — efficiency.py 수식 검증

### 우선순위 MEDIUM (표시 개선)
5. Loss Breakdown 5:5 화면 분할 (Tab 2)
6. Result: Power@DC 수식 tooltip
7. Result: M10 Order Qty → Required EPC M10 Qty
8. Result: Derated Power 수식 tooltip
10. Chain Efficiency 설명 추가 (definitions.json)
11. RP: Total S@POI + Required S@POI 동시 표시
12. RP: PF at PCS 표시, @MV 제거
14. Retention 테이블 열 그룹 시각화 (Base vs Aug 구분)
15. Discharge Energy@POI 그래프 제목 개선
16. Required Energy 가로선 + on/off 범례

### 우선순위 LOW (부가 기능)
13. PCS P-Q circle PNG 입력 기능
17. Product: Module Type 제거, 랙개수+단수 추가
18. PCS: 25도 S, 온도/고도 derating 표시
19. Configuration: 최소 증가 단위 설명
20. 토폴로지 비율 3:7
21. Aux SLD + 사이징/RTE aux 차이 설명 + 온도별 PNG
22. RTE: Battery RTE Import 기능
23. RTE: Aux@MV 프로젝트 DB에서, Aux@POI 제거
