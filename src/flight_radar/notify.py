"""Telegram delivery. Falls back to stdout when no token is configured."""

from __future__ import annotations

import os

import httpx

from flight_radar.alert import Alert
from flight_radar.models import Quote, trip_shape

_API = "https://api.telegram.org/bot{token}/sendMessage"


def send(alerts: list[Alert]) -> None:
    if not alerts:
        return
    send_text("\n\n".join(format_alert(alert) for alert in alerts))


def send_text(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(f"[no telegram credentials, printing instead]\n{text}")
        return

    response = httpx.post(
        _API.format(token=token),
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=15.0,
    )
    response.raise_for_status()


def format_alert(alert: Alert) -> str:
    quote = alert.quote
    headline = f"{_shape(quote)} {quote.price_krw:,}원"
    dates = f"{quote.depart_date} ~ {quote.return_date}"
    routing = f"{'/'.join(quote.carriers)} · 경유 {quote.stops}회 · {quote.duration_minutes // 60}시간"

    lines = [headline, dates, routing, _why(alert)]
    lines.extend(_market_lines(alert))
    if quote.itinerary_type == "split":
        lines.append("분리 발권 " + " + ".join(f"{leg.price_krw:,}" for leg in quote.legs))
    return "\n".join(lines)


def _shape(quote: Quote) -> str:
    legs = trip_shape(quote.origin, quote.destination, quote.return_from)
    return " / ".join(f"{start}->{end}" for start, end in legs)


def _market_lines(alert: Alert) -> list[str]:
    """How today compares with the last sixty days of the same measure."""
    market = alert.market
    if market is None:
        return []

    return [market.describe(alert.quote.price_krw), f"그동안 최저 {market.low_krw:,}원"]


def _why(alert: Alert) -> str:
    if alert.reason == "target":
        return "목표가 도달"
    if alert.reason == "percentile":
        return "저점 구간 — 매수 신호"
    if alert.baseline_krw is None:
        return "가격 하락"
    saved = alert.baseline_krw - alert.quote.price_krw
    return f"30일 최저({alert.baseline_krw:,}) 대비 {saved:,}원 하락"
