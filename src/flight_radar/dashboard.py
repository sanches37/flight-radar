"""A static page answering the three questions this tool exists to answer.

Which date combination is cheap, how the price has moved, and whether today is
a good day to buy. No server, no JavaScript, no CDN: the page is a pure
function of what is already in the repo, so there is nothing here that can go
down, drift out of sync, or need a key.

A fourth panel reports collection health. Losing only the price curve leaves
quotes flowing, which health.py cannot see, so the coverage count is printed
where a human will notice it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape

from flight_radar.config import Route
from flight_radar.insight import LOW_PERCENTILE, Market, cheapest_by_day, rank_today
from flight_radar.models import Quote, trip_shape

WIDTH = 720
HEIGHT = 200
PAD = 30


@dataclass(frozen=True)
class RouteData:
    """One route's newest quotes and every price curve kept for it."""

    route: Route
    quotes: list[Quote]
    curves: Mapping[str, Mapping[date, int]]
    history: Mapping[date, int] = field(default_factory=dict)
    """Cheapest eligible price we ourselves recorded, per collection day.

    Open-jaw has no Google curve to draw - the multi-city response carries no
    price_insights - so the only history that exists for it is the one this
    tool accumulated. Kept separate from `curves` because the two are not the
    same measure: Google's is daily and dense, ours is one point per sweep.
    """


def render(data: Sequence[RouteData], generated_at: datetime) -> str:
    sections = "\n".join(_section(entry) for entry in data)
    return _PAGE.format(
        generated=generated_at.strftime("%Y-%m-%d %H:%M"),
        sections=sections,
    )


def _section(data: RouteData) -> str:
    route = data.route
    grid = cheapest_by_pair(route, data.quotes)
    envelope = cheapest_by_day(data.curves.values())
    market = rank_today(envelope)
    cheapest = min(grid.values(), default=None)

    parts = [
        f"<h2>{_heading(route)}</h2>",
        _verdict(route, cheapest, market),
        _curve(envelope) if envelope else _history_curve(data.history),
        _heatmap(route, grid) if grid else "<p class='empty'>아직 수집된 견적이 없습니다.</p>",
        _health(data),
    ]
    return "<section>" + "".join(part for part in parts if part) + "</section>"


def _heading(route: Route) -> str:
    legs = trip_shape(route.origin, route.destination, route.inbound_origin)
    return " / ".join(f"{escape(start)} → {escape(end)}" for start, end in legs)


def cheapest_by_pair(route: Route, quotes: Sequence[Quote]) -> dict[tuple[date, date], int]:
    """The lowest price per date pair among itineraries we would actually book.

    Constraint-violating fares are excluded here for the same reason they are
    excluded from the alert baseline: a cheap three-stop routing nobody would
    take makes every reasonable fare look expensive.
    """
    grid: dict[tuple[date, date], int] = {}
    for quote in quotes:
        if quote.return_date is None:
            continue
        if not route.constraints.allows(quote.stops, quote.duration_minutes, quote.carriers):
            continue
        pair = (quote.depart_date, quote.return_date)
        grid[pair] = min(grid.get(pair, quote.price_krw), quote.price_krw)
    return grid


def _verdict(route: Route, cheapest: int | None, market: Market | None) -> str:
    """The buy call, ordered exactly as the alert orders its reasons.

    Page and notification have to agree; a dashboard that says wait while the
    phone says buy is worse than having neither.
    """
    if cheapest is None:
        return "<p class='empty'>판정할 견적이 없습니다.</p>"

    if cheapest <= route.target_price_krw:
        tone, call = "buy", "목표가 도달"
    elif market is not None and market.percentile <= LOW_PERCENTILE:
        tone, call = "buy", "저점 구간"
    else:
        tone, call = "hold", "기다릴 것"

    rank = market.describe(cheapest) if market else "가격 곡선 없음"
    floor = f"{market.days}일 최저 {market.low_krw:,}원 · " if market else ""

    return (
        f"<div class='verdict {tone}'>"
        f"<div class='call'>{call}</div>"
        f"<div class='price'>{cheapest:,}원</div>"
        f"<div class='rank'>{rank}</div>"
        f"<div class='note'>{floor}목표 {route.target_price_krw:,}원</div>"
        "</div>"
    )


def _curve(envelope: Mapping[date, int]) -> str:
    """The cheapest price available on each day, across every watched pair."""
    days = sorted(envelope)
    prices = [envelope[day] for day in days]
    low, high = min(prices), max(prices)
    span = high - low or 1
    step = (WIDTH - 2 * PAD) / max(len(days) - 1, 1)

    # Labelled by age rather than by date: the day keys only exist to line the
    # date pairs up with each other, and Google stamps its points at midnight
    # in a zone we deliberately do not try to identify.
    def point(index: int, price: int) -> tuple[float, float]:
        y = HEIGHT - PAD - (price - low) / span * (HEIGHT - 2 * PAD)
        return PAD + index * step, y

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(point, range(len(prices)), prices))
    last_x, last_y = point(len(prices) - 1, prices[-1])

    return (
        f"<svg class='curve' viewBox='0 0 {WIDTH} {HEIGHT}' role='img' "
        f"aria-label='최근 {len(days)}일 최저가 추이'>"
        f"<polyline points='{line}'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='4'/>"
        f"<text class='y' x='4' y='{PAD}'>{high:,}</text>"
        f"<text class='y' x='4' y='{HEIGHT - PAD + 4}'>{low:,}</text>"
        f"<text class='x' x='{PAD}' y='{HEIGHT - 6}'>{len(days) - 1}일 전</text>"
        f"<text class='x end' x='{WIDTH - PAD}' y='{HEIGHT - 6}'>오늘</text>"
        "</svg>"
    )


def observed_lows(route: Route, quotes: Sequence[Quote]) -> dict[date, int]:
    """Our own record: the cheapest eligible price seen on each collection day.

    Constraint-violating fares are excluded for the same reason alerting
    excludes them - a cheap three-stop fare is not a fare this trip can use.
    """
    lows: dict[date, int] = {}
    for quote in quotes:
        if not route.constraints.allows(quote.stops, quote.duration_minutes, quote.carriers):
            continue
        day = quote.observed_at.date()
        lows[day] = min(lows.get(day, quote.price_krw), quote.price_krw)
    return lows


def _history_curve(history: Mapping[date, int]) -> str:
    """The same shape as the Google curve, but plotted from our own sweeps.

    Labelled with real dates, not "N일 전": sweeps are not daily, so evenly
    spacing them and calling the gaps days would overstate what we measured.
    """
    if len(history) < 2:
        return ""

    days = sorted(history)
    prices = [history[day] for day in days]
    low, high = min(prices), max(prices)
    span = high - low or 1
    step = (WIDTH - 2 * PAD) / max(len(days) - 1, 1)

    def point(index: int, price: int) -> tuple[float, float]:
        y = HEIGHT - PAD - (price - low) / span * (HEIGHT - 2 * PAD)
        return PAD + index * step, y

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(point, range(len(prices)), prices))
    last_x, last_y = point(len(prices) - 1, prices[-1])
    dots = "".join(
        f"<circle class='obs' cx='{x:.1f}' cy='{y:.1f}' r='2.5'/>"
        for x, y in map(point, range(len(prices)), prices)
    )

    return (
        f"<svg class='curve' viewBox='0 0 {WIDTH} {HEIGHT}' role='img' "
        f"aria-label='직접 수집한 {len(days)}회의 최저가 추이'>"
        f"<polyline points='{line}'/>{dots}"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='4'/>"
        f"<text class='y' x='4' y='{PAD}'>{high:,}</text>"
        f"<text class='y' x='4' y='{HEIGHT - PAD + 4}'>{low:,}</text>"
        f"<text class='x' x='{PAD}' y='{HEIGHT - 6}'>{days[0].strftime('%m-%d')}</text>"
        f"<text class='x end' x='{WIDTH - PAD}' y='{HEIGHT - 6}'>{days[-1].strftime('%m-%d')}</text>"
        "</svg>"
        f"<p class='note'>수집 {len(days)}회 · 제약 통과 최저가</p>"
    )


def _heatmap(route: Route, grid: Mapping[tuple[date, date], int]) -> str:
    """Every watched combination, laid out as departure rows by return columns.

    The grid is a rectangle but the travel window is not, so combinations
    outside it are left blank. Drawing them the same as a watched pair that
    found nothing would read as missing data on ten of twenty-five cells.
    """
    pairs = route.date_pairs()
    departs = sorted({depart for depart, _ in pairs})
    returns = sorted({arrive for _, arrive in pairs})
    cells = {pair: grid.get(pair) for pair in pairs}
    low, high = min(grid.values()), max(grid.values())

    header = "".join(f"<th>{arrive:%m/%d}</th>" for arrive in returns)
    rows = "".join(
        f"<tr><th>{depart:%m/%d}</th>"
        + "".join(_cell(cells, (depart, arrive), low, high) for arrive in returns)
        + "</tr>"
        for depart in departs
    )

    return (
        "<table class='heatmap'><caption>출발일 × 귀국일 · 만원 · 제약 만족 최저가"
        " · 빈칸은 여행 창 밖 조합</caption>"
        f"<tr><th></th>{header}</tr>{rows}</table>"
    )


def _cell(
    cells: Mapping[tuple[date, date], int | None],
    pair: tuple[date, date],
    low: int,
    high: int,
) -> str:
    if pair not in cells:
        return "<td class='off'></td>"

    price = cells[pair]
    if price is None:
        return "<td class='none'>—</td>"

    best = " class='best'" if price == low else ""
    return f"<td{best} style='background:{_tint(price, low, high)}'>{price / 10_000:.0f}</td>"


def _tint(price: int, low: int, high: int) -> str:
    """Green for the cheapest cell in the grid, red for the dearest."""
    ratio = 0.0 if high == low else (price - low) / (high - low)
    return f"hsl({120 - 120 * ratio:.0f} 62% {90 - 9 * ratio:.0f}%)"


def _health(data: RouteData) -> str:
    """Collected counts, printed because a partial failure looks like success."""
    pairs = len(data.route.date_pairs())
    curves = len(data.curves)
    observed = max((quote.observed_at for quote in data.quotes), default=None)
    stamp = observed.strftime("%Y-%m-%d %H:%M") if observed else "없음"
    tone = "" if curves == pairs else " warn"

    return (
        f"<p class='health{tone}'>견적 {len(data.quotes)}건 · "
        f"곡선 {curves}/{pairs}쌍 · 마지막 수집 {stamp}</p>"
    )


_PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>flight-radar</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font: 15px/1.5 -apple-system, "Helvetica Neue", sans-serif; margin: 0 auto;
       max-width: 780px; padding: 24px 16px 64px; }}
h1 {{ font-size: 20px; margin: 0; }}
h2 {{ font-size: 17px; margin: 32px 0 12px; }}
.stamp {{ color: #777; font-size: 13px; margin: 4px 0 0; }}
section {{ border-top: 1px solid #ddd; }}
.verdict {{ border-radius: 10px; padding: 14px 16px; margin: 12px 0; }}
.verdict.buy {{ background: hsl(120 62% 92%); }}
.verdict.hold {{ background: hsl(35 70% 93%); }}
.call {{ font-weight: 700; }}
.price {{ font-size: 26px; font-weight: 700; margin: 2px 0; }}
.rank {{ font-size: 14px; }}
.note, .health {{ color: #666; font-size: 13px; }}
.health.warn {{ color: #b00; font-weight: 600; }}
.empty {{ color: #777; }}
.curve {{ width: 100%; height: auto; display: block; margin: 8px 0 4px; }}
.curve polyline {{ fill: none; stroke: #2b6cb0; stroke-width: 2; }}
.curve circle {{ fill: #2b6cb0; }}
.curve circle.obs {{ fill: #90b8dd; }}
.curve text {{ fill: #888; font-size: 11px; }}
.curve text.end {{ text-anchor: end; }}
.heatmap {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 8px 0; }}
.heatmap caption {{ caption-side: top; color: #666; font-size: 12px;
                   text-align: left; padding-bottom: 6px; }}
.heatmap th {{ color: #666; font-weight: 500; padding: 4px; }}
.heatmap td {{ color: #111; padding: 6px 4px; text-align: center;
              border: 1px solid rgba(0,0,0,.06); }}
.heatmap td.none {{ background: transparent; color: #bbb; }}
.heatmap td.off {{ background: transparent; border-color: transparent; }}
.heatmap td.best {{ outline: 2px solid #1a7f37; font-weight: 700; }}
</style>
</head>
<body>
<h1>flight-radar</h1>
<p class="stamp">{generated} KST 기준</p>
{sections}
</body>
</html>
"""
