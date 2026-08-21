"""Google Flights, scraped through fast-flights.

This reads Google's private search payload, so it will break the day Google
changes it. That is expected: the Provider seam means only this file changes
and every price already collected stays.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime

from fast_flights import FlightQuery, Passengers, ResultList, create_query, fetch_flights_html
from fast_flights.model import SimpleDatetime, SingleFlight
from fast_flights.parser import parse_js
from selectolax.lexbor import LexborHTMLParser

from flight_radar.config import Route
from flight_radar.models import Quote

PAUSE_SECONDS = 3.0


class GoogleFlightsProvider:
    name = "google_flights"

    def fetch(
        self, route: Route, depart_date: date, return_date: date, observed_at: datetime
    ) -> list[Quote]:
        # Back-to-back scrapes get blocked, so every request waits its turn.
        time.sleep(PAUSE_SECONDS)

        try:
            html = fetch_flights_html(_query(route, depart_date, return_date))
            results = _parse(html)
        except Exception as error:
            # Never fail silently. A provider that quietly returns nothing
            # looks exactly like a market with no flights, and P-2 has to be
            # able to tell those apart from the log.
            print(
                f"{self.name}: {route.id} {depart_date}..{return_date} failed: {error!r}",
                file=sys.stderr,
            )
            return []

        return quotes_from(results, route, (depart_date, return_date), observed_at)


def quotes_from(
    results: ResultList,
    route: Route,
    dates: tuple[date, date],
    observed_at: datetime,
) -> list[Quote]:
    """Map one Google response onto Quotes, cheapest first.

    Google prices a round trip as a single number attached to the outbound
    itinerary, so stops, duration and carriers all describe the outbound only.
    """
    depart_date, return_date = dates
    code_by_name = _code_by_name(results)
    quotes = [
        Quote(
            route_id=route.id,
            provider=GoogleFlightsProvider.name,
            itinerary_type="through",
            origin=route.origin,
            destination=route.destination,
            depart_date=depart_date,
            return_date=return_date,
            price_krw=result.price,
            stops=len(result.flights) - 1,
            duration_minutes=_elapsed_minutes(result.flights),
            carriers=tuple(code_by_name.get(name, name) for name in result.airlines),
            observed_at=observed_at,
        )
        for result in results
    ]
    return sorted(quotes, key=lambda quote: quote.price_krw)


def _parse(html: str) -> ResultList:
    """Parse the response, minus the itineraries Google prices as unavailable.

    fast-flights 3.1.0 reads every itinerary's price unconditionally
    (parser.py:77), so one price-less entry raises IndexError and takes the
    whole page down with it - eight good itineraries lost to one bad one.
    They are useless to a price tracker anyway, so they go before parsing.
    """
    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        raise ValueError("response carried no flight payload")

    payload = json.loads(script.text().split("data:", 1)[1].rsplit(",", 1)[0])
    itineraries = payload[3][0]
    if itineraries is not None:
        payload[3][0] = [entry for entry in itineraries if entry[1][0]]

    return parse_js("data:" + json.dumps(payload) + ",")


def _query(route: Route, depart_date: date, return_date: date):
    """Deliberately carries no constraint filters.

    Handing route.constraints to Google would bake today's rules into the
    stored history and make a later constraint change unanswerable.
    """
    return create_query(
        flights=[
            FlightQuery(
                date=depart_date.isoformat(),
                from_airport=route.origin,
                to_airport=route.destination,
            ),
            FlightQuery(
                date=return_date.isoformat(),
                from_airport=route.destination,
                to_airport=route.origin,
            ),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1),
        language="en-US",
        currency="KRW",
    )


def _code_by_name(results: ResultList) -> dict[str, str]:
    """Airlines arrive as display names; the payload's own table has the codes."""
    metadata = getattr(results, "metadata", None)
    if metadata is None:
        return {}
    return {airline.name: airline.code for airline in metadata.airlines}


def _elapsed_minutes(legs: list[SingleFlight]) -> int:
    """Time in the air plus time waiting between planes.

    Departure and arrival clocks are local to their own airport, so
    subtracting the final arrival from the first departure would silently
    drop the timezone shift - eight hours of it on ICN to Lisbon. Per-leg
    durations are already true elapsed time, and a layover is safe to
    subtract because both sides are the same airport, hence the same zone.
    """
    flying = sum(leg.duration for leg in legs)
    layovers = 0
    for before, after in zip(legs, legs[1:]):
        waiting = _as_datetime(after.departure) - _as_datetime(before.arrival)
        layovers += int(waiting.total_seconds() // 60)

    return flying + layovers


def _as_datetime(value: SimpleDatetime) -> datetime:
    year, month, day = value.date
    hour, minute = value.time
    return datetime(year, month, day, hour, minute)
