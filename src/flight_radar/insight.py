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

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

# Bottom of the range is a buy. Wide enough to fire a few times in sixty
# days, tight enough that firing still means something.
LOW_PERCENTILE = 15.0


@dataclass(frozen=True)
class Market:
    """Where today's cheapest trip sits in its own recent history."""

    percentile: float
    today_krw: int
    low_krw: int
    days: int

    def describe(self, price_krw: int) -> str:
        """One sentence, shared by the alert and the page so they cannot drift.

        The curve ignores the stop and duration limits, so when its price
        differs from the fare we would actually book, name which one is ranked.
        """
        line = f"최근 {self.days}일 중 하위 {self.percentile:.0f}%"
        if self.today_krw != price_krw:
            line += f" (무제약 최저 {self.today_krw:,}원 기준)"
        return line


def cheapest_by_day(curves: Iterable[Mapping[date, int]]) -> dict[date, int]:
    """The best price any watched date pair offered, day by day."""
    envelope: dict[date, int] = {}
    for curve in curves:
        for day, price in curve.items():
            envelope[day] = min(envelope.get(day, price), price)
    return envelope


def rank_today(envelope: Mapping[date, int]) -> Market | None:
    """Rank today against the days before it. 0 means never cheaper than now."""
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


def _rank(price: int, past: list[int]) -> float:
    """Ties count half, so a fare that has not moved reads as mid-range."""
    below = sum(1 for earlier in past if earlier < price)
    tied = sum(1 for earlier in past if earlier == price)
    return 100.0 * (below + 0.5 * tied) / len(past)
