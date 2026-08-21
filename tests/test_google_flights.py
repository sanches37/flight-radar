"""Mapping tests for the Google response.

The sample below is the real ICN-LIS payload observed on 2026-08-21, trimmed
to the fields the mapper reads. Only the mapping is tested - the network call
itself belongs to Google, not to us.
"""

import json
from datetime import date, datetime, timezone

from fast_flights import ResultList
from fast_flights.model import Airline, Airport, Flights, JsMetadata, SimpleDatetime, SingleFlight

from flight_radar.providers.google_flights import _parse, quotes_from

KST = timezone.utc
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=KST)
DATES = (date(2026, 10, 5), date(2026, 10, 13))


def _leg(origin, destination, depart, arrive, duration):
    return SingleFlight(
        from_airport=Airport(code=origin, name=origin),
        to_airport=Airport(code=destination, name=destination),
        departure=SimpleDatetime(date=(2026, 10, 5), time=depart),
        arrival=SimpleDatetime(date=(2026, 10, 5), time=arrive),
        duration=duration,
        plane_type="Airbus A350",
    )


def _results(*flights) -> ResultList:
    results = ResultList(flights)
    results.metadata = JsMetadata(
        alliances=[],
        airlines=[
            Airline(code="ET", name="Ethiopian"),
            Airline(code="TP", name="Tap Air Portugal"),
            Airline(code="LO", name="LOT"),
        ],
    )
    return results


VIA_ADD_LHR = Flights(
    type="multi",
    price=1_660_300,
    airlines=["Ethiopian", "Tap Air Portugal"],
    flights=[
        _leg("ICN", "ADD", (0, 20), (5, 50), 690),
        _leg("ADD", "LHR", (11, 25), (17, 20), 475),
        _leg("LHR", "LIS", (18, 45), (21, 35), 170),
    ],
    carbon=None,
)


def test_quote_carries_the_krw_price_and_outbound_stop_count(route):
    quote = quotes_from(_results(VIA_ADD_LHR), route, DATES, NOW)[0]

    assert quote.price_krw == 1_660_300
    assert quote.stops == 2
    assert quote.itinerary_type == "through"
    assert quote.legs == ()


def test_quote_takes_its_dates_from_the_query_not_the_response(route):
    quote = quotes_from(_results(VIA_ADD_LHR), route, DATES, NOW)[0]

    assert (quote.depart_date, quote.return_date) == DATES
    assert quote.observed_at == NOW


def test_duration_counts_layovers_and_survives_the_timezone_shift(route):
    """ICN departs 00:20 KST, LIS arrives 21:35 WEST - eight hours apart.

    Subtracting the local clocks would report 21h15m for a 29h15m trip.
    """
    quote = quotes_from(_results(VIA_ADD_LHR), route, DATES, NOW)[0]

    assert quote.duration_minutes == 690 + 475 + 170 + 335 + 85
    assert quote.duration_minutes == 29 * 60 + 15


def test_airline_names_become_iata_codes(route):
    quote = quotes_from(_results(VIA_ADD_LHR), route, DATES, NOW)[0]

    assert quote.carriers == ("ET", "TP")


def test_unknown_airline_keeps_its_name_rather_than_vanishing(route):
    unlisted = Flights(
        type="XX",
        price=2_000_000,
        airlines=["Air Nowhere"],
        flights=[_leg("ICN", "LIS", (10, 0), (20, 0), 900)],
        carbon=None,
    )

    quote = quotes_from(_results(unlisted), route, DATES, NOW)[0]

    assert quote.carriers == ("Air Nowhere",)


def test_quotes_come_back_cheapest_first(route):
    direct = Flights(
        type="LO",
        price=1_400_000,
        airlines=["LOT"],
        flights=[_leg("ICN", "LIS", (11, 15), (23, 0), 700)],
        carbon=None,
    )

    quotes = quotes_from(_results(VIA_ADD_LHR, direct), route, DATES, NOW)

    assert [quote.price_krw for quote in quotes] == [1_400_000, 1_660_300]


def test_an_empty_response_has_no_metadata_and_still_maps(route):
    """fast_flights leaves .metadata unset when Google returns nothing."""
    assert quotes_from(ResultList(), route, DATES, NOW) == []


def test_constraints_are_not_applied_at_collection_time(route):
    """route allows 1 stop; the 2-stop itinerary must still be recorded."""
    quotes = quotes_from(_results(VIA_ADD_LHR), route, DATES, NOW)

    assert route.constraints.max_stops == 1
    assert [quote.stops for quote in quotes] == [2]


def _payload_leg() -> list:
    """One leg, at the indices Google puts each field on."""
    leg = [None] * 22
    leg[3], leg[4] = "ICN", "Incheon International Airport"
    leg[5], leg[6] = "Humberto Delgado Airport", "LIS"
    leg[8], leg[20] = [11, 15], [2026, 10, 5]
    leg[10], leg[21] = [23, 0], [2026, 10, 5]
    leg[11] = 700
    leg[17] = "Boeing 787"
    return leg


def _payload_itinerary(price: int | None) -> list:
    flight = [None] * 23
    flight[0], flight[1], flight[2] = "LO", ["LOT"], [_payload_leg()]
    flight[22] = [None] * 9
    flight[22][7], flight[22][8] = 982_000, 682_000
    # Google leaves the price slot empty when it cannot quote the itinerary.
    price_slot = [[None, price]] if price else [[]]
    return [flight, [*price_slot, "token"]]


def _script(*itineraries: list, best: tuple = ()) -> str:
    """Google's payload: best departing flights at [2], the rest at [3]."""
    payload = [None] * 8
    payload[2] = [list(best)] if best else None
    payload[3] = [list(itineraries)]
    payload[7] = [None, [[], [["LO", "LOT"]]]]
    return "AF_initDataCallback({key: 'ds:1', data:" + json.dumps(payload) + ",});"


def test_one_unpriced_itinerary_does_not_take_the_whole_page_down():
    """fast-flights 3.1.0 raises IndexError on these and loses every result."""
    script = _script(_payload_itinerary(1_400_000), _payload_itinerary(None))

    results = _parse(f"<script class='ds:1'>{script}</script>")

    assert [result.price for result in results] == [1_400_000]


def test_a_response_with_no_itineraries_at_all_parses_to_nothing():
    payload = json.loads(_script().split("data:", 1)[1].rsplit(",", 1)[0])
    payload[3] = [None]
    script = "AF_initDataCallback({data:" + json.dumps(payload) + ",});"

    assert _parse(f"<script class='ds:1'>{script}</script>") == []


def test_the_best_departing_flights_list_is_collected_too():
    """The cheap fares live in Google's first list, which fast-flights skips."""
    script = _script(_payload_itinerary(1_388_300), best=(_payload_itinerary(1_156_200),))

    results = _parse(f"<script class='ds:1'>{script}</script>")

    assert sorted(result.price for result in results) == [1_156_200, 1_388_300]


def test_an_unpriced_entry_in_the_best_list_is_dropped_like_any_other():
    script = _script(_payload_itinerary(1_388_300), best=(_payload_itinerary(None),))

    results = _parse(f"<script class='ds:1'>{script}</script>")

    assert [result.price for result in results] == [1_388_300]
