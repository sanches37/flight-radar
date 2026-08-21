# flight-radar

인천 → 포르투갈 항공권 가격을 매일 수집해서 히스토리를 쌓고, 조건에 맞으면 텔레그램으로 알린다.

Google Flights 트래킹을 대체하지 않는다. **보완**한다 — Google이 안 해주는 두 가지만 담당한다:

1. **원시 가격 히스토리 소유** — Google은 "평소보다 저렴함" 판정만 주고 근거 곡선은 안 준다
2. **분리 발권 비교** — `인천→유럽 허브` + `허브→리스본`이 통합권보다 쌀 때를 잡는다

## 상태

- [x] **P-0** 파이프라인 + fake provider + 테스트
- [x] **P-1a** fast-flights 연결 (실제 Google Flights 데이터)
- [x] **P-2** GitHub Actions cron + 자동 커밋 + 텔레그램
- [ ] **P-1b** 분리 발권 조합
- [ ] **P-3** 정적 대시보드 (히트맵 + 가격 곡선) + Pages
- [ ] **P-4** percentile "지금 살까" 판정

## 쓰는 법

```bash
uv sync
uv run track --provider fake              # 네트워크 없이 한 사이클
uv run track --provider google_flights    # 실제 수집 (~2분)
uv run pytest                             # 테스트
```

수집은 GitHub Actions가 매일 07:05 / 19:05 KST에 돌리고, 결과를 이 repo에 커밋한다.
텔레그램 알림에는 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 시크릿이 필요하다.

추적 대상을 바꾸려면 `routes.yaml` 하나만 고치면 된다.

## 설계 노트

**가격 히스토리는 repo가 곧 DB다.** GitHub Actions에 영구 디스크가 없으므로
`data/quotes/{route}/{YYYY-MM}.jsonl`에 append-only로 쌓고 Action이 커밋한다.
한 줄씩만 늘어서 diff가 작고, git 히스토리가 그대로 백업이 된다.

**수집은 전부, 필터는 알림에서만.** provider는 `routes.yaml`의 constraints를 보지 않는다.
제약을 나중에 바꿔도 이미 쌓인 히스토리를 새 기준으로 다시 평가할 수 있어야 하기 때문.

**provider는 교체 전제로 분리했다.** fast-flights는 Google의 비공개 스키마에 의존하므로
언젠가 깨진다. 깨지면 `providers/` 아래 파일 하나만 갈아끼우고, 쌓인 히스토리는 남는다.

**알림은 노선당 최저가 1건만.** 매칭되는 모든 견적에 알림을 보내면 한 번의 가격 하락에
수십 개가 발사되고, 그렇게 시끄러운 알림은 결국 꺼진다.
같은 노선·출발일·5만원 가격대는 7일간 재알림하지 않는다.

**조용한 죽음이 최대 리스크다.** 스크레이핑이 깨져도 파이프라인은 성공한 것처럼 돌고
0건만 쌓인다. 3회 연속 0건이면 텔레그램으로 경고한다 (`state/health.json`).
