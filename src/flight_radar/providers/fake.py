"""Deterministic stand-in for a real provider.

Prices are derived from a hash of (route, dates, day) so that the same day
always yields the same numbers - the pipeline and its tests stay reproducible
without touching the network.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from flight_radar.config import Route
from flight_radar.models import Leg, Quote

_BASE_PRICE_KRW = 1_500_000
_SWING_KRW = 700_000
_HUB_CARRIERS = {"CDG": "AF", "AMS": "KL", "IST": "TK", "DOH": "QR", "DXB": "EK", "HEL": "AY"}


class FakeProvider:
    name = "fake"

    def fetch(
        self, route: Route, depart_date: date, return_date: date, observed_at: datetime
    ) -> list[Quote]:
        through = self._through_quote(route, depart_date, return_date, observed_at)
        splits = [
            self._split_quote(route, hub, depart_date, return_date, observed_at)
            for hub in route.split_hubs
        ]
        return sorted([through, *splits], key=lambda quote: quote.price_krw)

    def _through_quote(
        self, route: Route, depart_date: date, return_date: date, observed_at: datetime
    ) -> Quote:
        seed = _seed(route.id, depart_date, return_date, observed_at.date(), "through")
        return Quote(
            route_id=route.id,
            provider=self.name,
            itinerary_type="through",
            origin=route.origin,
            destination=route.destination,
            depart_date=depart_date,
            return_date=return_date,
            price_krw=_BASE_PRICE_KRW + seed % _SWING_KRW,
            stops=1 + seed % 2,
            duration_minutes=17 * 60 + seed % (9 * 60),
            carriers=("KE", "AF") if seed % 2 else ("QR",),
            observed_at=observed_at,
        )

    def _split_quote(
        self,
        route: Route,
        hub: str,
        depart_date: date,
        return_date: date,
        observed_at: datetime,
    ) -> Quote:
        seed = _seed(route.id, depart_date, return_date, observed_at.date(), hub)
        long_haul = _BASE_PRICE_KRW - 250_000 + seed % _SWING_KRW
        short_hop = 40_000 + seed % 60_000
        hub_carrier = _HUB_CARRIERS.get(hub, "XX")
        legs = (
            Leg(route.origin, hub, depart_date, long_haul, hub_carrier),
            Leg(hub, route.destination, depart_date + timedelta(days=1), short_hop, "FR"),
        )
        return Quote(
            route_id=route.id,
            provider=self.name,
            itinerary_type="split",
            origin=route.origin,
            destination=route.destination,
            depart_date=depart_date,
            return_date=return_date,
            price_krw=long_haul + short_hop,
            stops=2 + seed % 2,
            duration_minutes=22 * 60 + seed % (12 * 60),
            carriers=(hub_carrier, "FR"),
            observed_at=observed_at,
            legs=legs,
        )


def _seed(route_id: str, depart: date, ret: date, observed: date, tag: str) -> int:
    key = f"{route_id}|{depart}|{ret}|{observed}|{tag}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big")
