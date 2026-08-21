"""The alert text a phone actually shows."""

from datetime import date

from conftest import make_insight, make_quote

from flight_radar.alert import Alert
from flight_radar.insight import read_market
from flight_radar.notify import format_alert

TODAY = date(2026, 8, 21)
AT_ITS_LOW = read_market([make_insight((1_800_000,) * 20 + (1_100_000,))])


def test_the_message_says_where_today_sits_and_how_low_it_has_been():
    alert = Alert(make_quote(1_100_000, TODAY), "percentile", None, AT_ITS_LOW)

    message = format_alert(alert)

    assert "저점 구간 — 매수 신호" in message
    assert "최근 20일 중 하위 0%" in message
    assert "그동안 최저 1,100,000원" in message


def test_the_message_names_the_price_the_ranking_describes():
    """The curve ignores our stop and duration limits; the headline does not."""
    alert = Alert(make_quote(1_156_200, TODAY), "target", None, AT_ITS_LOW)

    assert "무제약 최저 1,100,000원 기준" in format_alert(alert)


def test_no_curve_means_no_history_lines():
    alert = Alert(make_quote(1_350_000, TODAY), "target", None)

    assert format_alert(alert).splitlines() == [
        "ICN->LIS 1,350,000원",
        "2026-10-05 ~ 2026-10-15",
        "QR · 경유 1회 · 18시간",
        "목표가 도달",
    ]
