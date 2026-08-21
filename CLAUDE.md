# flight-radar

인천 → 포르투갈(리스본/포르투) 항공권 가격을 매일 수집해 히스토리를 쌓고,
조건 충족 시 텔레그램으로 알린다. 개인용 도구. 앱 아님.

**실제 여행이 걸려 있다**: 2026-10-05 이후 출발, 2026-10-16 이전 귀국.
그 이후로도 계속 쓸 도구.

## 이 도구의 존재 이유

Google Flights 트래킹을 **대체하지 않는다. 보완한다.** Google이 안 해주는 둘만 담당:

1. **원시 가격 히스토리 소유** — Google은 "평소보다 저렴함" 판정만 주고 근거 곡선은 안 준다
2. **분리 발권 비교** — `인천→유럽 허브` + `허브→리스본`이 통합권보다 쌀 때를 잡는다.
   한국→포르투갈은 직항이 없어 실제로 돈이 나오는 지점이 여기다.

Google Flights 트래킹도 **같이 켜두는 것이 전제**다. 이 도구가 Google 스키마 변경으로
조용히 죽어도 Google 알림은 계속 온다.

## 명령

```bash
uv sync
uv run pytest                 # 테스트
uv run track --provider google_flights            # 실제 수집 한 사이클 (~2분)
uv run track --provider google_flights --dry-run  # 수집·저장만, 알림 없음
uv run track --provider fake                      # 네트워크 없이 파이프라인만
```

추적 대상 변경은 `routes.yaml` 하나만 고치면 된다.

## 확정된 설계 (재논의 대상 아님)

**repo가 곧 DB.** GitHub Actions에 영구 디스크가 없으므로
`data/quotes/{route}/{YYYY-MM}.jsonl`에 append-only로 쌓고 Action이 커밋한다.
diff가 한 줄씩만 늘고, git 히스토리가 그대로 백업.

**수집은 전부, 필터는 알림에서만.** provider는 `routes.yaml`의 constraints를 보지 않는다.
제약을 나중에 바꿔도 이미 쌓인 히스토리를 새 기준으로 재평가할 수 있어야 하므로.

**provider는 교체 전제.** fast-flights는 Google의 비공개 스키마 의존이라 언젠가 깨진다.
깨지면 `providers/` 파일 하나만 갈아끼우고 히스토리는 남는다.

**알림은 노선당 최저가 1건.** 견적마다 보내면 한 번의 하락에 수십 건이 발사되고,
그렇게 시끄러운 알림은 결국 꺼진다. 같은 노선·출발일·5만원대는 7일간 재알림 금지.

**왕복 가격은 가는 편에 붙는다.** Google은 왕복 총액을 아웃바운드 여정에 매기고
귀국 여정은 응답에 없다. 그래서 `stops`/`duration_minutes`/`carriers`는 **가는 편 기준**이고
`max_stops` 제약도 가는 편에만 걸린다. Google 자체 동작이라 우회 불가.

**baseline에서 제약 위반 견적 제외.** 싼 3-경유 운임이 기준선이 되면
정작 탈 만한 운임이 영원히 "비싸다"로 판정된다. 테스트로 고정돼 있다.

## 금지 패턴

- 모듈 내부에서 `datetime.now()` 직접 호출 금지. `observed_at`을 주입한다.
  진입점(`cli.py`) 1곳만 예외.
- fake 데이터를 `data/quotes/`에 커밋 금지. 실제 baseline이 오염된다.
- provider가 constraints를 보고 필터링하지 말 것 (위 "수집은 전부" 참조).
  `fast_flights.FlightQuery`에 `max_stops`/`max_duration_minutes`가 있지만 쓰지 않는다.

## 구조

```
routes.yaml              추적 대상 (사용자가 고치는 유일한 파일)
src/flight_radar/
  config.py              routes.yaml 로드·검증, date_pairs() 전개
  models.py              Quote / Leg
  providers/base.py      Provider 프로토콜
  providers/fake.py      결정론적 fake (네트워크 없이 테스트)
  providers/google_flights.py  fast-flights 스크레이핑 (통합권)
  store.py               append-only JSONL 읽기/쓰기
  alert.py               목표가·급락 판정 + 중복 차단
  notify.py              텔레그램 (자격증명 없으면 stdout)
  tracker.py             한 사이클 조립
  cli.py                 진입점
tests/                   30 passed
```

## 코드 스타일

- 함수 20~30줄, 파라미터 3개 이하, early return
- 영리한 한 줄보다 평범한 루프 (`seen.add()` 반환값 활용 같은 트릭 금지)
- 주석은 "왜"만. "무엇"은 코드가 말하게 한다
- 사용자 대면 문자열은 한국어, 코드·주석은 영어

## 진행 상황

- [x] **P-0** 파이프라인 + fake provider + 테스트 20개 — 커밋 `268c8cb`까지
- [x] **P-1a** fast-flights 통합권 연결 — 실제 KRW 가격 수집 중
- [ ] **P-2** GitHub Actions cron + 자동 커밋 + 텔레그램  ← **다음**
- [ ] **P-1b** 분리 발권 조합 (P-2 이후. 수집 시작이 더 급함)
- [ ] **P-3** 정적 대시보드 (히트맵 + 가격 곡선) + Pages
- [ ] **P-4** percentile "지금 살까" 판정

상세 계획은 `.claude/plans/flight-radar.md`.

## 작업 규칙

Step 하나 = 세션 하나. Step 시작 전 `.claude/plans/flight-radar.md`를 읽고
진입 전 객관 리뷰 5항목을 수행한다. 사용자의 전역 룰
(`~/.claude/rules/sdd_workflow.md`, `cost_efficiency.md`)이 우선한다.
