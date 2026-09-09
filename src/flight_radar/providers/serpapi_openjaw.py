"""Open-jaw fares through SerpApi's multi-city search.

Google renders multi-city results in the browser rather than in the HTML, so the
scraping path this project uses everywhere else cannot reach them (measured: a
round-trip payload carries 66,067 characters of itineraries, the same query as
multi-city carries 5,579 characters of airport names). SerpApi runs the search
and returns JSON, which is why this one route type is metered.

Every call costs quota, so the caller decides how often. The provider itself
just answers one date pair.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime

import httpx

from flight_radar.config import Route
from flight_radar.models import Observation, Quote

ENDPOINT = "https://serpapi.com/search"
NAME = "serpapi_openjaw"
# 몇 번째로 싼 가는 편까지 오는 편을 확인할지. 조회 비용이 여기에 비례한다.
OUTBOUND_FOLLOWED = 3
TIMEOUT_SECONDS = 60.0


class SerpApiOpenJawProvider:
    name = NAME

    def fetch(
        self, route: Route, depart_date: date, return_date: date, observed_at: datetime
    ) -> Observation:
        key = os.environ.get("SERPAPI_KEY")
        if not key:
            print(f"{self.name}: SERPAPI_KEY is not set", file=sys.stderr)
            return Observation()

        try:
            payload = _search(key, route, depart_date, return_date)
        except Exception as error:
            # Same rule as the scraping provider: an empty answer must never be
            # indistinguishable from a market with no flights.
            print(
                f"{self.name}: {route.id} {depart_date}..{return_date} failed: {error!r}",
                file=sys.stderr,
            )
            return Observation()

        if "error" in payload:
            print(
                f"{self.name}: {route.id} {depart_date}..{return_date}: {payload['error']}",
                file=sys.stderr,
            )
            return Observation()

        outbound = _itineraries(payload)
        if not outbound:
            return Observation()

        # The first response describes only the flight out; the way home costs
        # another call per outbound. Several are followed, not just the cheapest:
        # on 2026-09-09 the cheapest outbound (1,507,400) led only to 4.5M and
        # 7.0M ways home, while the second cheapest (1,532,400) reached a
        # 1,532,400 trip. Following one outbound reported the 4.5M as the day's
        # price - a threefold error, not a market move.
        quotes = []
        for candidate in sorted(outbound, key=lambda entry: entry["price"])[:OUTBOUND_FOLLOWED]:
            try:
                homeward = _search(
                    key, route, depart_date, return_date,
                    departure_token=candidate["departure_token"],
                )
            except Exception as error:
                print(
                    f"{self.name}: {route.id} {depart_date}..{return_date} "
                    f"return leg failed: {error!r}",
                    file=sys.stderr,
                )
                continue
            quotes += quotes_from(homeward, route, (depart_date, return_date), observed_at, candidate)

        # No insights: the multi-city response carries best_flights, other_flights
        # and airports only. Open-jaw has no sixty-day curve to rank against.
        return Observation(quotes=sorted(quotes, key=lambda quote: quote.price_krw))


def quotes_from(
    payload: dict,
    route: Route,
    dates: tuple[date, date],
    observed_at: datetime,
    outbound: dict,
) -> list[Quote]:
    """Map the second-stage response onto Quotes, cheapest first.

    `payload` lists the ways home for one chosen outbound, and each carries the
    price of the whole trip. `stops`, `duration_minutes` and `carriers` still
    describe the flight out - that is what `outbound` is for - while
    `return_duration_minutes` describes the flight home.
    """
    depart_date, return_date = dates
    quotes = [
        Quote(
            route_id=route.id,
            provider=NAME,
            itinerary_type="through",
            origin=route.origin,
            destination=route.destination,
            depart_date=depart_date,
            return_date=return_date,
            price_krw=itinerary["price"],
            stops=len(outbound["flights"]) - 1,
            duration_minutes=outbound["total_duration"],
            carriers=_carriers(outbound),
            observed_at=observed_at,
            return_from=route.inbound_origin,
            return_duration_minutes=itinerary["total_duration"],
        )
        for itinerary in _itineraries(payload)
    ]
    return sorted(quotes, key=lambda quote: quote.price_krw)


def _itineraries(payload: dict) -> list[dict]:
    """Both result lists as one, minus the ones SerpApi cannot price."""
    entries = (payload.get("best_flights") or []) + (payload.get("other_flights") or [])
    return [entry for entry in entries if entry.get("price") and entry.get("flights")]


def _carriers(itinerary: dict) -> tuple[str, ...]:
    """Airline names in the order flown, without repeating a through carrier."""
    names: list[str] = []
    for segment in itinerary["flights"]:
        airline = segment.get("airline")
        if airline and airline not in names:
            names.append(airline)
    return tuple(names)


def _search(
    key: str,
    route: Route,
    depart_date: date,
    return_date: date,
    departure_token: str | None = None,
) -> dict:
    """Deliberately carries no constraint filters, like every other provider."""
    legs = [
        {
            "departure_id": route.origin,
            "arrival_id": route.destination,
            "date": depart_date.isoformat(),
        },
        {
            "departure_id": route.inbound_origin,
            "arrival_id": route.origin,
            "date": return_date.isoformat(),
        },
    ]
    response = httpx.get(
        ENDPOINT,
        params={
            "engine": "google_flights",
            "type": "3",  # multi-city
            "multi_city_json": json.dumps(legs),
            "currency": "KRW",
            "hl": "en",
            "adults": "1",
            "travel_class": "1",
            "api_key": key,
            **({"departure_token": departure_token} if departure_token else {}),
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()
