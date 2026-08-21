"""Core value types shared by providers, store, and alerting."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from collections.abc import Mapping
from datetime import date, datetime
from typing import Literal

ItineraryType = Literal["through", "split"]


@dataclass(frozen=True)
class Leg:
    """One separately-ticketed hop. Only present on split itineraries."""

    origin: str
    destination: str
    depart_date: date
    price_krw: int
    carrier: str


@dataclass(frozen=True)
class Quote:
    """One observed price for one route on one date pair."""

    route_id: str
    provider: str
    itinerary_type: ItineraryType
    origin: str
    destination: str
    depart_date: date
    return_date: date | None
    price_krw: int
    stops: int
    duration_minutes: int
    carriers: tuple[str, ...]
    observed_at: datetime
    legs: tuple[Leg, ...] = field(default=())

    def to_json(self) -> dict:
        raw = asdict(self)
        raw["depart_date"] = self.depart_date.isoformat()
        raw["return_date"] = self.return_date.isoformat() if self.return_date else None
        raw["observed_at"] = self.observed_at.isoformat()
        raw["carriers"] = list(self.carriers)
        raw["legs"] = [_leg_to_json(leg) for leg in self.legs]
        return raw

    @classmethod
    def from_json(cls, raw: dict) -> Quote:
        return cls(
            route_id=raw["route_id"],
            provider=raw["provider"],
            itinerary_type=raw["itinerary_type"],
            origin=raw["origin"],
            destination=raw["destination"],
            depart_date=date.fromisoformat(raw["depart_date"]),
            return_date=date.fromisoformat(raw["return_date"]) if raw["return_date"] else None,
            price_krw=raw["price_krw"],
            stops=raw["stops"],
            duration_minutes=raw["duration_minutes"],
            carriers=tuple(raw["carriers"]),
            observed_at=datetime.fromisoformat(raw["observed_at"]),
            legs=tuple(_leg_from_json(leg) for leg in raw.get("legs", [])),
        )


@dataclass(frozen=True)
class PriceInsight:
    """Google's cheapest fare per day for one date pair, sixty days back.

    The curve rides along with every search response, so it costs no extra
    request. Its newest point was measured equal to our own parser's cheapest
    unfiltered price on all 15 watched date pairs, which makes the whole curve
    the same quantity we measure - already observed, once a day, 60 days back.

    Keyed by day rather than ordered, because the useful reading combines the
    curves of every watched date pair and they have to line up by date.
    """

    depart_date: date
    return_date: date
    curve_krw: Mapping[date, int]


@dataclass
class Observation:
    """What one fetch saw: itineraries plus the date pair's price history.

    Both arrive in the same response, so a provider cannot hand them back
    separately without paying for a second request.
    """

    quotes: list[Quote] = field(default_factory=list)
    insights: list[PriceInsight] = field(default_factory=list)


def _leg_to_json(leg: Leg) -> dict:
    raw = asdict(leg)
    raw["depart_date"] = leg.depart_date.isoformat()
    return raw


def _leg_from_json(raw: dict) -> Leg:
    return Leg(
        origin=raw["origin"],
        destination=raw["destination"],
        depart_date=date.fromisoformat(raw["depart_date"]),
        price_krw=raw["price_krw"],
        carrier=raw["carrier"],
    )
