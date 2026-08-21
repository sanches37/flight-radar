"""Mapping tests for SerpApi's multi-city response.

The sample is the real ICN-LIS / OPO-ICN payload observed on 2026-08-21, trimmed
to the fields the mapper reads. Only the mapping is tested - the search itself
belongs to SerpApi, not to us.
"""

from dataclasses import replace
from datetime import date, datetime, timezone

from flight_radar.providers.serpapi_openjaw import quotes_from

KST = timezone.utc
NOW = datetime(2026, 8, 21, 14, 0, tzinfo=KST)
DATES = (date(2026, 10, 6), date(2026, 10, 15))


def _segment(origin, destination, minutes, airline):
    return {
        "departure_airport": {"id": origin},
        "arrival_airport": {"id": destination},
        "duration": minutes,
        "airline": airline,
    }


VIA_CDG = {
    "price": 1_383_200,
    "total_duration": 1120,
    "layovers": [{"id": "CDG", "duration": 110}],
    "flights": [
        _segment("ICN", "CDG", 850, "Air France"),
        _segment("CDG", "LIS", 160, "Air France"),
    ],
}


def _open_jaw(route):
    return replace(route, id="icn-lis-opo", return_from="OPO", provider="serpapi_openjaw")


def test_the_total_price_and_the_outbound_shape_are_recorded(route):
    """SerpApi prices the whole open-jaw once and describes only the flight out."""
    quote = quotes_from({"best_flights": [VIA_CDG]}, _open_jaw(route), DATES, NOW)[0]

    assert quote.price_krw == 1_383_200
    assert quote.stops == 1
    assert quote.duration_minutes == 1120


def test_the_quote_remembers_where_the_trip_home_starts(route):
    quote = quotes_from({"best_flights": [VIA_CDG]}, _open_jaw(route), DATES, NOW)[0]

    assert (quote.origin, quote.destination, quote.return_from) == ("ICN", "LIS", "OPO")
    assert (quote.depart_date, quote.return_date) == DATES


def test_a_through_carrier_is_not_repeated(route):
    quote = quotes_from({"best_flights": [VIA_CDG]}, _open_jaw(route), DATES, NOW)[0]

    assert quote.carriers == ("Air France",)


def test_both_result_lists_are_collected_cheapest_first(route):
    cheaper = {**VIA_CDG, "price": 1_273_800}
    payload = {"best_flights": [VIA_CDG], "other_flights": [cheaper]}

    quotes = quotes_from(payload, _open_jaw(route), DATES, NOW)

    assert [quote.price_krw for quote in quotes] == [1_273_800, 1_383_200]


def test_an_itinerary_serpapi_cannot_price_is_dropped(route):
    payload = {"best_flights": [VIA_CDG, {"total_duration": 1200, "flights": []}]}

    quotes = quotes_from(payload, _open_jaw(route), DATES, NOW)

    assert [quote.price_krw for quote in quotes] == [1_383_200]


def test_an_empty_response_maps_to_nothing(route):
    assert quotes_from({}, _open_jaw(route), DATES, NOW) == []


def test_constraints_are_not_applied_at_collection_time(route):
    """route allows 1 stop; a 2-stop open-jaw must still be recorded."""
    long_way = {**VIA_CDG, "flights": [*VIA_CDG["flights"], _segment("LIS", "LIS", 60, "TAP")]}

    quotes = quotes_from({"best_flights": [long_way]}, _open_jaw(route), DATES, NOW)

    assert [quote.stops for quote in quotes] == [2]
