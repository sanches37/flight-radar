"""Mapping tests for SerpApi's two-stage multi-city response.

The samples are the real ICN-LIS / MAD-ICN payloads observed on 2026-09-08,
trimmed to the fields the mapper reads. The first call describes only the way
out and hands back a token; the second lists the ways home, each priced for the
whole trip. Only the mapping is tested - the search itself belongs to SerpApi.
"""

from dataclasses import replace
from datetime import date, datetime, timezone

from flight_radar.providers.serpapi_openjaw import quotes_from

KST = timezone.utc
NOW = datetime(2026, 9, 8, 14, 0, tzinfo=KST)
DATES = (date(2026, 10, 5), date(2026, 10, 15))


def _segment(origin, destination, minutes, airline):
    return {
        "departure_airport": {"id": origin},
        "arrival_airport": {"id": destination},
        "duration": minutes,
        "airline": airline,
    }


# 1단계: 가는 편. ICN → AUH → LIS, 20h55.
OUTBOUND = {
    "price": 1_365_400,
    "total_duration": 1255,
    "departure_token": "tok",
    "flights": [
        _segment("ICN", "AUH", 585, "Etihad"),
        _segment("AUH", "LIS", 495, "Etihad"),
    ],
}

# 2단계: 오는 편. 값은 여정 전체 가격이다.
HOME_LONG = {          # 28h30 — 아부다비에서 12h55 대기
    "price": 1_365_400,
    "total_duration": 1710,
    "flights": [_segment("MAD", "AUH", 435, "Etihad"), _segment("AUH", "ICN", 500, "Etihad")],
}
HOME_SHORT = {         # 17h25
    "price": 1_554_300,
    "total_duration": 1045,
    "flights": [_segment("MAD", "AUH", 420, "Etihad"), _segment("AUH", "ICN", 515, "Etihad")],
}


def _open_jaw(route):
    return replace(route, id="icn-lis-mad", return_from="MAD", provider="serpapi_openjaw")


def test_the_price_comes_from_the_way_home_and_the_shape_from_the_way_out(route):
    """2단계 가격이 여정 전체 값이다. stops·duration·carriers 는 가는 편 기준."""
    quote = quotes_from({"best_flights": [HOME_LONG]}, _open_jaw(route), DATES, NOW, OUTBOUND)[0]

    assert quote.price_krw == 1_365_400
    assert quote.stops == 1
    assert quote.duration_minutes == 1255
    assert quote.carriers == ("Etihad",)


def test_the_way_home_is_recorded_separately(route):
    """2026-09-08: 가는 편 20h55 뒤에 28h30 짜리 귀국편이 숨어 있었다."""
    quotes = quotes_from(
        {"best_flights": [HOME_LONG, HOME_SHORT]}, _open_jaw(route), DATES, NOW, OUTBOUND
    )

    assert [quote.return_duration_minutes for quote in quotes] == [1710, 1045]
    assert all(quote.duration_minutes == 1255 for quote in quotes)


def test_the_quote_remembers_where_the_trip_home_starts(route):
    quote = quotes_from({"best_flights": [HOME_LONG]}, _open_jaw(route), DATES, NOW, OUTBOUND)[0]

    assert (quote.origin, quote.destination, quote.return_from) == ("ICN", "LIS", "MAD")
    assert (quote.depart_date, quote.return_date) == DATES


def test_both_result_lists_are_collected_cheapest_first(route):
    payload = {"best_flights": [HOME_SHORT], "other_flights": [HOME_LONG]}

    quotes = quotes_from(payload, _open_jaw(route), DATES, NOW, OUTBOUND)

    assert [quote.price_krw for quote in quotes] == [1_365_400, 1_554_300]


def test_an_itinerary_serpapi_cannot_price_is_dropped(route):
    payload = {"best_flights": [HOME_LONG, {"total_duration": 1200, "flights": []}]}

    quotes = quotes_from(payload, _open_jaw(route), DATES, NOW, OUTBOUND)

    assert [quote.price_krw for quote in quotes] == [1_365_400]


def test_an_empty_response_maps_to_nothing(route):
    assert quotes_from({}, _open_jaw(route), DATES, NOW, OUTBOUND) == []


def test_constraints_are_not_applied_at_collection_time(route):
    """route allows 23h; the 28h30 way home must still be recorded."""
    quote = quotes_from({"best_flights": [HOME_LONG]}, _open_jaw(route), DATES, NOW, OUTBOUND)[0]

    assert quote.return_duration_minutes == 1710
    assert not _open_jaw(route).constraints.allows(
        quote.stops, quote.duration_minutes, quote.carriers, quote.return_duration_minutes
    )
