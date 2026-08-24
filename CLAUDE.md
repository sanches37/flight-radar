# flight-radar

인천 → 포르투갈(리스본/포르투) 항공권 가격을 매일 수집해 히스토리를 쌓고,
조건 충족 시 텔레그램으로 알린다. 개인용 도구. 앱 아님.

**실제 여행이 걸려 있다**: 2026-10-05 이후 출발, 2026-10-16 이전 귀국.
그 이후로도 계속 쓸 도구.

## 이 도구의 존재 이유

Google Flights 트래킹을 **대체하지 않는다. 보완한다.** Google이 안 해주는 것:

1. **제약을 건 다중 날짜 비교** — Google은 한 번에 한 날짜쌍만 판정한다.
   이 도구는 15개 날짜쌍 × 모든 여정을 매일 훑고 경유 1회·23시간 제약을 건
   최저가만 남긴다. "어느 날짜 조합이 싼가"는 이렇게만 보인다
2. **해상도 높은 원시 히스토리** — 실행마다·날짜쌍마다·여정마다 쌓는다
3. **오픈조 비교** — 리스본 in / 마드리드 out처럼 나가는 공항과 들어오는 공항이
   다른 조합. Google 트래킹으로는 비교가 안 된다

**원래 명분 둘은 2026-08-21 실측으로 정정됐다. 되풀이하지 말 것:**

- ~~"Google은 근거 곡선을 안 준다"~~ → **준다.** 62일 일별 곡선이 우리가 이미
  받는 페이로드 `payload[5][10][0]`에 있다. 다만 하루 1점·날짜쌍 하나·제약
  필터 없음이라 위 2번과 해상도가 다르다. 대체재가 아니라 보완재
- ~~"분리 발권이 돈 나오는 지점"~~ → **이 노선에서는 성립하지 않았다.**
  `ICN↔CDG 왕복`이 `ICN↔LIS 왕복 통합권`보다 비싸다. 허브가 목적지보다 비싸면
  분리 발권은 원리상 못 이긴다. 리스본이 TAP의 본거지 허브라 그렇다

Google Flights 트래킹도 **같이 켜두는 것이 전제**다. 이 도구가 Google 스키마 변경으로
조용히 죽어도 Google 알림은 계속 온다.

## 명령

```bash
uv sync
uv run pytest                 # 테스트
uv run track --provider google_flights            # 왕복 수집 한 사이클 (~2분)
uv run track --provider google_flights --dry-run  # 수집·저장만, 알림 없음
uv run track --provider serpapi_openjaw           # 오픈조 수집 (SerpApi 14회 소모)
uv run track --provider fake                      # 네트워크 없이 파이프라인만
uv run dashboard              # 저장된 데이터로 docs/index.html 재생성 (수집 없음)
```

추적 대상 변경은 `routes.yaml` 하나만 고치면 된다.

## 확정된 설계 (재논의 대상 아님)

**repo가 곧 DB.** GitHub Actions에 영구 디스크가 없으므로
`data/quotes/{route}/{YYYY-MM}.jsonl`에 append-only로 쌓고 Action이 커밋한다.
diff가 한 줄씩만 늘고, git 히스토리가 그대로 백업.

**Google 곡선만 예외적으로 병합 갱신이다** (`data/curves/{route}.json`).
매 실행 같은 61점을 다시 주므로 append하면 중복만 쌓인다. 맵으로 합치면 diff가
쌍당 1~2줄이고, Google의 60일 창이 롤오프해도 예전 점이 파일에 남는다.
과거 점이 사후 수정되지 않음은 실측으로 확인(같은 쌍 두 번 fetch → 61/61 동일).

**수집은 전부, 필터는 알림에서만.** provider는 `routes.yaml`의 constraints를 보지 않는다.
제약을 나중에 바꿔도 이미 쌓인 히스토리를 새 기준으로 재평가할 수 있어야 하므로.

**`--provider`는 구현 선택이자 노선 필터다.** 노선이 `routes.yaml`에서 자기 출처를
선언하고, 워크플로는 출처 이름만 넘긴다 — 일일 cron은 `google_flights` 노선만,
주 2회 cron은 `serpapi_openjaw` 노선만 돈다. 노선 이름을 워크플로에 박지 않으므로
"추적 대상 변경은 routes.yaml 하나"가 유지된다. `fake`는 모든 노선의 대역.

**오픈조는 SerpApi로만 된다.** Google이 다구간 결과를 서버 렌더링하지 않는다
(왕복 페이로드 66,067자 vs 다구간 5,579자). 무료 한도가 월 250회뿐이라
**주 2회 × 2조합 × 7쌍 = 월 122회**에 맞췄고, `window.depart_until`로 출발일을
좁혀 쌍 수를 줄인다. 한도를 넘기는 설정 변경은 테스트가 먼저 실패한다
(`test_the_metered_routes_stay_inside_the_free_search_quota`).

**오픈조에는 60일 곡선이 없다.** 다구간 응답에 `price_insights`가 없어
percentile 판정을 못 한다. 오픈조는 **목표가 도달로만** 알린다.

**provider는 교체 전제.** fast-flights는 Google의 비공개 스키마 의존이라 언젠가 깨진다.
깨지면 `providers/` 파일 하나만 갈아끼우고 히스토리는 남는다.

**알림 상태는 발송 뒤에 쓴다.** `suppress_repeats`는 거르기만 하고
`record_sent`가 기록한다. 순서가 반대면 `--dry-run` 한 번이 진짜 알림을 7일간 막는다.
`state/health.json`도 같은 이유로 발송 경로에서만 갱신된다.

**알림은 노선당 최저가 1건.** 견적마다 보내면 한 번의 하락에 수십 건이 발사되고,
그렇게 시끄러운 알림은 결국 꺼진다. 같은 노선·출발일·5만원대는 7일간 재알림 금지.

**왕복 가격은 가는 편에 붙는다.** Google은 왕복 총액을 아웃바운드 여정에 매기고
귀국 여정은 응답에 없다. 그래서 `stops`/`duration_minutes`/`carriers`는 **가는 편 기준**이고
`max_stops` 제약도 가는 편에만 걸린다. Google 자체 동작이라 우회 불가.

**Google은 결과를 두 목록으로 준다.** `payload[2][0]`이 "Best departing flights",
`payload[3][0]`이 "Other departing flights"다. **싼 게 앞쪽에 있다.** fast-flights는
뒤쪽만 읽어서 최저가를 23만원 놓치고 있었다. `_itineraries()`가 둘을 합친다.
증상이 "조용히 일부가 빔"이라 `health.py`(0건 감시)로는 안 잡힌다.

**"지금 살까"는 날짜쌍 하나가 아니라 15쌍 최저 계열로 판정한다.** Google이 날짜쌍마다
주는 60일 곡선(`payload[5][10][0]`)을 그대로 쓰면 안 된다. 여행은 날짜쌍 하나에 묶여
있지 않고 창 안의 아무 조합이나 되므로, 판정 대상은 **날마다 15쌍 중 최저가**다.
2026-08-21 실측: 한 쌍이 자기 기준 최저(percentile 0%)였는데 15쌍 최저 계열로는
하위 87%였다. 쌍 하나만 보면 **틀린 매수 신호**가 나간다.

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
  providers/google_flights.py  fast-flights 스크레이핑 (왕복 통합권)
  providers/serpapi_openjaw.py SerpApi 다구간 (오픈조, 유료 한도 소모)
  store.py               견적은 append-only JSONL, 곡선은 병합 갱신 맵
  alert.py               목표가·급락 판정 + 중복 차단
  notify.py              텔레그램 (자격증명 없으면 stdout)
  health.py              연속 0건 수집 감시 (조용한 죽음 탐지)
  tracker.py             한 사이클 조립
  cli.py                 진입점
docs/index.html          정적 대시보드 (GitHub Pages)
.github/workflows/track.yml    하루 2회 cron (왕복) + data/state/docs 자동 커밋
.github/workflows/openjaw.yml  주 2회 cron (오픈조) — 월/목 06:05 KST
tests/                   90 passed
```

## 코드 스타일

- 함수 20~30줄, 파라미터 3개 이하, early return
- 영리한 한 줄보다 평범한 루프 (`seen.add()` 반환값 활용 같은 트릭 금지)
- 주석은 "왜"만. "무엇"은 코드가 말하게 한다
- 사용자 대면 문자열은 한국어, 코드·주석은 영어

## 진행 상황

- [x] **P-0** 파이프라인 + fake provider + 테스트 20개 — 커밋 `268c8cb`까지
- [x] **P-1a** fast-flights 통합권 연결 — 실제 KRW 가격 수집 중
- [x] **P-2** GitHub Actions cron + 자동 커밋 + 텔레그램 — 07:05 / 19:05 KST
- [x] **P-1c** Best flights 섹션 수집 누락 수정 — 최저가 23만원 되찾음
- [x] **P-4** percentile "지금 살까" 판정 — Google 60일 곡선으로 오늘부터 가능
- [x] **P-3** 정적 대시보드 — `docs/index.html`. **Pages 활성화는 사용자 몫**
      (repo Settings → Pages → `main` / `/docs`)
- [x] **P-5** 오픈조 (리스본 in / 포르투·마드리드 out) — SerpApi, 주 2회.
      **Actions Secrets에 `SERPAPI_KEY` 필요**
- [ ] **P-1b** 분리 발권 조합 — **전제 확인 먼저.** 위 "존재 이유" 정정 참조

상세 계획은 `.claude/plans/flight-radar.md`.

## 작업 규칙

Step 하나 = 세션 하나. Step 시작 전 `.claude/plans/flight-radar.md`를 읽고
진입 전 객관 리뷰 5항목을 수행한다. 사용자의 전역 룰
(`~/.claude/rules/sdd_workflow.md`, `cost_efficiency.md`)이 우선한다.
