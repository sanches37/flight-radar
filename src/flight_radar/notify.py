"""Telegram delivery. Falls back to stdout when no token is configured."""

from __future__ import annotations

import os

import httpx

from flight_radar.alert import Alert

_API = "https://api.telegram.org/bot{token}/sendMessage"


def send(alerts: list[Alert]) -> None:
    if not alerts:
        return

    text = "\n\n".join(format_alert(alert) for alert in alerts)
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
    headline = f"{quote.origin}->{quote.destination} {quote.price_krw:,}원"
    dates = f"{quote.depart_date} ~ {quote.return_date}"
    routing = f"{'/'.join(quote.carriers)} · 경유 {quote.stops}회 · {quote.duration_minutes // 60}시간"

    lines = [headline, dates, routing, _why(alert)]
    if quote.itinerary_type == "split":
        lines.append("분리 발권 " + " + ".join(f"{leg.price_krw:,}" for leg in quote.legs))
    return "\n".join(lines)


def _why(alert: Alert) -> str:
    if alert.reason == "target":
        return "목표가 도달"
    if alert.baseline_krw is None:
        return "가격 하락"
    saved = alert.baseline_krw - alert.quote.price_krw
    return f"30일 최저({alert.baseline_krw:,}) 대비 {saved:,}원 하락"
