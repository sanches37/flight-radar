from datetime import date, datetime, timezone

from conftest import make_quote

from flight_radar.config import load_routes
from flight_radar.providers import FakeProvider
from flight_radar.store import append, read_since
from flight_radar.tracker import Paths, collect, run

KST = timezone.utc
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=KST)


def test_date_pairs_stay_inside_the_travel_window(route):
    pairs = route.date_pairs()

    assert pairs[0] == (date(2026, 10, 5), date(2026, 10, 15))
    assert all(depart >= route.depart_from for depart, _ in pairs)
    assert all(arrive <= route.return_by for _, arrive in pairs)


def test_date_pairs_drop_combinations_that_overrun_the_window(route):
    """Oct 5 fits both 10 and 11 nights; Oct 6 fits only 10."""
    pairs = route.date_pairs()

    assert (date(2026, 10, 5), date(2026, 10, 16)) in pairs
    assert (date(2026, 10, 6), date(2026, 10, 17)) not in pairs
    assert (date(2026, 10, 6), date(2026, 10, 16)) in pairs


def test_routes_yaml_parses():
    routes = load_routes(Paths(_repo_root()).routes)

    assert {route.id for route in routes} == {"icn-lis", "icn-opo"}
    assert all(route.split_hubs for route in routes)
    assert all(route.date_pairs() for route in routes)


def test_collect_returns_through_and_split_itineraries(route):
    quotes = collect(route, FakeProvider(), NOW)

    kinds = {quote.itinerary_type for quote in quotes}
    assert kinds == {"through", "split"}
    assert len(quotes) == len(route.date_pairs()) * 2


def test_split_quote_price_equals_sum_of_legs(route):
    quotes = collect(route, FakeProvider(), NOW)

    for quote in (q for q in quotes if q.itinerary_type == "split"):
        assert quote.price_krw == sum(leg.price_krw for leg in quote.legs)


def test_store_roundtrip_preserves_quote(tmp_path):
    original = make_quote(1_234_567, date(2026, 8, 21))
    append(tmp_path, [original])

    restored = read_since(tmp_path, "icn-lis", date(2026, 8, 1), date(2026, 8, 31))

    assert restored == [original]


def test_store_appends_across_runs(tmp_path):
    append(tmp_path, [make_quote(1_000_000, date(2026, 8, 20))])
    append(tmp_path, [make_quote(1_100_000, date(2026, 8, 21))])

    restored = read_since(tmp_path, "icn-lis", date(2026, 8, 1), date(2026, 8, 31))

    assert [quote.price_krw for quote in restored] == [1_000_000, 1_100_000]


def test_read_since_spans_month_boundaries(tmp_path):
    append(tmp_path, [make_quote(1_000_000, date(2026, 7, 30))])
    append(tmp_path, [make_quote(1_100_000, date(2026, 8, 2))])

    restored = read_since(tmp_path, "icn-lis", date(2026, 7, 25), date(2026, 8, 5))

    assert len(restored) == 2


def test_run_persists_every_quote(tmp_path, route):
    paths = Paths(tmp_path)

    run([route], FakeProvider(), paths, NOW)

    stored = read_since(paths.data, route.id, date(2026, 8, 1), date(2026, 8, 31))
    assert len(stored) == len(route.date_pairs()) * 2


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent
