"""Is today a good day to buy, judged against sixty days of the same measure.

Google attaches a daily price curve to every search response. One curve covers
one date pair, but the trip is not tied to a date pair - any combination inside
the travel window will do - so the series worth judging is the cheapest price
available on each day across every watched pair.

That distinction is not academic. Measured on 2026-08-21, one ICN-LIS date pair
read as a record low while the cheapest-across-pairs price had been beaten on
87% of the previous sixty days. Judging that pair alone would have called a buy
on a day when the trip had been cheaper almost every day of the last two months.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from flight_radar.models import PriceInsight


@dataclass(frozen=True)
class Market:
    """Where today's cheapest trip sits in its own recent history."""

    percentile: float
    today_krw: int
    low_krw: int
    days: int


def read_market(insights: Sequence[PriceInsight]) -> Market | None:
    """Rank today against the days before it. 0 means never cheaper than now."""
    envelope = _cheapest_by_day(insights)
    if len(envelope) < 2:
        return None

    days = sorted(envelope)
    today_krw = envelope[days[-1]]
    past = [envelope[day] for day in days[:-1]]

    return Market(
        percentile=_rank(today_krw, past),
        today_krw=today_krw,
        low_krw=min(envelope.values()),
        days=len(past),
    )


def _cheapest_by_day(insights: Sequence[PriceInsight]) -> dict[date, int]:
    """The best price any watched date pair offered, day by day."""
    envelope: dict[date, int] = {}
    for insight in insights:
        for day, price in insight.curve_krw.items():
            envelope[day] = min(envelope.get(day, price), price)
    return envelope


def _rank(price: int, past: list[int]) -> float:
    """Ties count half, so a fare that has not moved reads as mid-range."""
    below = sum(1 for earlier in past if earlier < price)
    tied = sum(1 for earlier in past if earlier == price)
    return 100.0 * (below + 0.5 * tied) / len(past)
