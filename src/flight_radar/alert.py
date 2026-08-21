"""Decide which quotes are worth interrupting the user for."""

from __future__ import annotations

import json
from dataclasses import dataclass
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from flight_radar.config import Route
from flight_radar.insight import Market, read_market
from flight_radar.models import PriceInsight, Quote

HISTORY_DAYS = 30
DROP_RATIO = 0.90
LOW_PERCENTILE = 15.0
RENOTIFY_AFTER_DAYS = 7


@dataclass(frozen=True)
class Alert:
    quote: Quote
    reason: str
    baseline_krw: int | None
    market: Market | None = None


def find_alerts(
    route: Route,
    fresh: list[Quote],
    history: list[Quote],
    today: date,
    insights: Sequence[PriceInsight] = (),
) -> list[Alert]:
    """Alert on the single best eligible quote per route, not on every match.

    Alerting per quote would fire dozens of times for one price drop, and an
    alert stream that noisy just gets muted.
    """
    eligible = [quote for quote in fresh if _satisfies(route, quote)]
    if not eligible:
        return []

    best = min(eligible, key=lambda quote: quote.price_krw)
    baseline = _recent_low(route, history, today)
    market = read_market(insights)

    if best.price_krw <= route.target_price_krw:
        return [Alert(best, "target", baseline, market)]
    if market is not None and market.percentile <= LOW_PERCENTILE:
        return [Alert(best, "percentile", baseline, market)]
    if baseline is not None and best.price_krw <= baseline * DROP_RATIO:
        return [Alert(best, "drop", baseline, market)]
    return []


def _satisfies(route: Route, quote: Quote) -> bool:
    return route.constraints.allows(quote.stops, quote.duration_minutes, quote.carriers)


def _recent_low(route: Route, history: list[Quote], today: date) -> int | None:
    cutoff = today - timedelta(days=HISTORY_DAYS)
    prices = [
        quote.price_krw
        for quote in history
        if quote.observed_at.date() >= cutoff and _satisfies(route, quote)
    ]
    return min(prices) if prices else None


def suppress_repeats(alerts: list[Alert], state_path: Path, today: date) -> list[Alert]:
    """Drop alerts already sent for the same route and price band this week.

    This only filters. `record_sent` writes the state, and the caller runs it
    after delivery - marking an alert as sent before it goes out would let a
    dry run, or a failed post, mute the real thing for seven days.
    """
    state = _load_state(state_path)
    cutoff = today - timedelta(days=RENOTIFY_AFTER_DAYS)
    return [alert for alert in alerts if not _sent_since(state, alert, cutoff)]


def record_sent(alerts: list[Alert], state_path: Path, today: date) -> None:
    """Remember delivered alerts so the same news stays quiet for a week."""
    if not alerts:
        return

    state = _load_state(state_path)
    for alert in alerts:
        state[_dedupe_key(alert)] = today.isoformat()

    _save_state(state_path, state, today - timedelta(days=RENOTIFY_AFTER_DAYS))


def _sent_since(state: dict[str, str], alert: Alert, cutoff: date) -> bool:
    last_sent = state.get(_dedupe_key(alert))
    return last_sent is not None and date.fromisoformat(last_sent) > cutoff


def _dedupe_key(alert: Alert) -> str:
    """Price banded to 50k KRW - a 3,000 KRW wobble is not news."""
    band = alert.quote.price_krw // 50_000
    return f"{alert.quote.route_id}|{alert.quote.depart_date}|{alert.reason}|{band}"


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, str], cutoff: date) -> None:
    kept = {key: sent for key, sent in state.items() if date.fromisoformat(sent) > cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kept, indent=2, sort_keys=True), encoding="utf-8")
