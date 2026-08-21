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

        # No insights: the multi-city response carries best_flights, other_flights
        # and airports only. Open-jaw has no sixty-day curve to rank against.
        return Observation(quotes=quotes_from(payload, route, (depart_date, return_date), observed_at))


def quotes_from(
    payload: dict,
    route: Route,
    dates: tuple[date, date],
    observed_at: datetime,
) -> list[Quote]:
    """Map one multi-city response onto Quotes, cheapest first.

    SerpApi prices the whole open-jaw as one number and describes only the
    outbound, exactly as Google prices a round trip, so stops, duration and
    carriers all describe the flight out.
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
            stops=len(itinerary["flights"]) - 1,
            duration_minutes=itinerary["total_duration"],
            carriers=_carriers(itinerary),
            observed_at=observed_at,
            return_from=route.inbound_origin,
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


def _search(key: str, route: Route, depart_date: date, return_date: date) -> dict:
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
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()
