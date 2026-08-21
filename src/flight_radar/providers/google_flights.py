"""Google Flights, scraped through fast-flights.

This reads Google's private search payload, so it will break the day Google
changes it. That is expected: the Provider seam means only this file changes
and every price already collected stays.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone

from fast_flights import FlightQuery, Passengers, ResultList, create_query, fetch_flights_html
from fast_flights.model import SimpleDatetime, SingleFlight
from fast_flights.parser import parse_js
from selectolax.lexbor import LexborHTMLParser

from flight_radar.config import Route
from flight_radar.models import Observation, PriceInsight, Quote

PAUSE_SECONDS = 3.0


class GoogleFlightsProvider:
    name = "google_flights"

    def fetch(
        self, route: Route, depart_date: date, return_date: date, observed_at: datetime
    ) -> Observation:
        # Back-to-back scrapes get blocked, so every request waits its turn.
        time.sleep(PAUSE_SECONDS)

        try:
            html = fetch_flights_html(_query(route, depart_date, return_date))
            payload = _payload(html)
            results = _parse(payload)
        except Exception as error:
            # Never fail silently. A provider that quietly returns nothing
            # looks exactly like a market with no flights, and P-2 has to be
            # able to tell those apart from the log.
            print(
                f"{self.name}: {route.id} {depart_date}..{return_date} failed: {error!r}",
                file=sys.stderr,
            )
            return Observation()

        insight = _insight(payload, depart_date, return_date)
        if insight is None:
            # Losing only the curve leaves quotes flowing, so health.py never
            # sees it. Say so here or the percentile alert dies in silence.
            print(
                f"{self.name}: {route.id} {depart_date}..{return_date} carried no price curve",
                file=sys.stderr,
            )

        return Observation(
            quotes=quotes_from(results, route, (depart_date, return_date), observed_at),
            insights=[insight] if insight else [],
        )


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


def _payload(html: str) -> list:
    """Google's search payload, lifted out of the inline script that carries it."""
    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        raise ValueError("response carried no flight payload")

    return json.loads(script.text().split("data:", 1)[1].rsplit(",", 1)[0])


def _parse(payload: list) -> ResultList:
    """Parse both result lists, minus the itineraries Google prices as unavailable.

    Two fast-flights 3.1.0 problems are worked around here.

    It reads only Google's second list. Google splits results into "Best
    departing flights" and "Other departing flights", and the cheap fares sit
    in the first one: on a measured ICN-LIS query the best list opened at
    1,156,200 KRW while the other list's cheapest was 1,388,300.

    It also reads every itinerary's price unconditionally (parser.py:77), so
    one price-less entry raises IndexError and takes the whole page down with
    it. Those are useless to a price tracker anyway, so they go before parsing.
    """
    payload[3][0] = [entry for entry in _itineraries(payload) if entry[1][0]]

    return parse_js("data:" + json.dumps(payload) + ",")


def _itineraries(payload: list) -> list:
    """Google's two result lists as one, best first then the rest."""
    entries = []
    for section in (payload[2], payload[3]):
        if section:
            entries.extend(section[0] or ())
    return entries


def _insight(payload: list, depart_date: date, return_date: date) -> PriceInsight | None:
    """Google's daily lowest-price curve for this date pair, if it is there.

    Sixty-one daily points ending today, measured identical to our own
    cheapest unfiltered quote on every watched date pair. Positional indices
    into a private payload are exactly as fragile as they look, so anything
    unexpected returns None and the caller warns rather than losing the run.
    """
    try:
        block = payload[5]
        curve = block[10][0]
        return PriceInsight(
            depart_date=depart_date,
            return_date=return_date,
            curve_krw={_day(point[0]): int(point[1]) for point in curve},
        )
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def _day(unix_ms: int) -> date:
    """A stable label for one curve point.

    Only used to line the watched date pairs up with each other, never shown,
    so UTC is chosen to avoid guessing which zone Google stamped them in.
    """
    return datetime.fromtimestamp(unix_ms / 1000, timezone.utc).date()


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
