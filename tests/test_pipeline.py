import shutil
import sys
from datetime import date, datetime, timezone

from conftest import make_quote

from dataclasses import replace

from flight_radar.cli import PROVIDERS, main, routes_for
from flight_radar.config import load_routes
from flight_radar.models import PriceInsight
from flight_radar.providers import FakeProvider
from flight_radar.store import append, read_curves, read_latest, read_since, write_curves
from flight_radar.tracker import Paths, collect, run

KST = timezone.utc
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=KST)
DEPART, RETURN = date(2026, 10, 5), date(2026, 10, 15)
WEEKS_PER_MONTH = 4.35


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

    assert {route.id for route in routes} == {"icn-lis", "icn-opo", "icn-lis-opo", "icn-lis-mad"}
    assert all(route.date_pairs() for route in routes)
    assert all(route.provider in PROVIDERS for route in routes)


def test_the_metered_routes_stay_inside_the_free_search_quota():
    """SerpApi gives 250 searches a month; widening a window must fail here first.

    One search per date pair, two sweeps a week. Quota exhaustion would show up
    as silently missing open-jaw prices, which nothing else in the pipeline
    would notice.
    """
    routes = load_routes(Paths(_repo_root()).routes)
    metered = [route for route in routes if route.provider == "serpapi_openjaw"]
    per_sweep = sum(len(route.date_pairs()) for route in metered)

    assert per_sweep * 2 * WEEKS_PER_MONTH <= 250


def test_each_source_only_runs_the_routes_that_declare_it():
    """Schedules stay out of routes.yaml: the workflow asks for a source."""
    routes = load_routes(Paths(_repo_root()).routes)

    assert {r.id for r in routes_for(routes, "google_flights")} == {"icn-lis", "icn-opo"}
    assert {r.id for r in routes_for(routes, "serpapi_openjaw")} == {"icn-lis-opo", "icn-lis-mad"}
    assert routes_for(routes, "fake") == routes


def test_an_open_jaw_window_can_cap_the_departure_side(route):
    """Every metered call costs quota, so the grid is narrowed on purpose."""
    narrowed = replace(route, depart_until=date(2026, 10, 5))

    assert {depart for depart, _ in narrowed.date_pairs()} == {date(2026, 10, 5)}
    assert len(narrowed.date_pairs()) < len(route.date_pairs())


def test_collect_returns_through_and_split_itineraries(route):
    quotes = collect(route, FakeProvider(), NOW).quotes

    kinds = {quote.itinerary_type for quote in quotes}
    assert kinds == {"through", "split"}
    assert len(quotes) == len(route.date_pairs()) * 2


def test_split_quote_price_equals_sum_of_legs(route):
    quotes = collect(route, FakeProvider(), NOW).quotes

    for quote in (q for q in quotes if q.itinerary_type == "split"):
        assert quote.price_krw == sum(leg.price_krw for leg in quote.legs)


def test_collect_gathers_one_price_curve_per_date_pair(route):
    """The curve rides on the same response, so every pair should bring one."""
    insights = collect(route, FakeProvider(), NOW).insights

    assert len(insights) == len(route.date_pairs())
    assert {(i.depart_date, i.return_date) for i in insights} == set(route.date_pairs())


def test_store_roundtrip_preserves_quote(tmp_path):
    original = make_quote(1_234_567, date(2026, 8, 21))
    append(tmp_path, [original])

    restored = read_since(tmp_path, "icn-lis", date(2026, 8, 1), date(2026, 8, 31))

    assert restored == [original]


def test_store_roundtrip_preserves_an_open_jaw_quote(tmp_path):
    original = make_quote(1_383_200, date(2026, 8, 21), return_from="OPO")
    append(tmp_path, [original])

    restored = read_since(tmp_path, "icn-lis", date(2026, 8, 1), date(2026, 8, 31))

    assert restored == [original]


def test_quotes_written_before_open_jaw_existed_still_load(tmp_path):
    """Stored history predates the field; reading it must not need a migration."""
    import json

    legacy = make_quote(1_156_200, date(2026, 8, 21)).to_json()
    del legacy["return_from"]
    path = tmp_path / "icn-lis" / "2026-08.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    restored = read_since(tmp_path, "icn-lis", date(2026, 8, 1), date(2026, 8, 31))

    assert restored[0].return_from is None


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


def test_read_latest_isolates_the_most_recent_sweep(tmp_path):
    """Two runs a day must not be blended into one picture."""
    morning = datetime(2026, 8, 21, 7, 5, tzinfo=KST)
    evening = datetime(2026, 8, 21, 19, 5, tzinfo=KST)
    append(tmp_path, [make_quote(1_000_000, date(2026, 8, 20)),
                      make_quote(1_100_000, date(2026, 8, 21), observed_at=morning),
                      make_quote(1_200_000, date(2026, 8, 21), observed_at=evening)])

    latest = read_latest(tmp_path, "icn-lis", date(2026, 8, 21))

    assert [quote.price_krw for quote in latest] == [1_200_000]


def test_curves_keep_points_that_fell_off_googles_window(tmp_path):
    """Google reaches sixty days back and no further; the record has to outlive that."""
    june = PriceInsight(DEPART, RETURN, {date(2026, 6, 22): 1_700_000, date(2026, 8, 21): 1_120_100})
    august = PriceInsight(DEPART, RETURN, {date(2026, 8, 21): 1_120_100, date(2026, 8, 22): 1_050_000})

    write_curves(tmp_path, "icn-lis", [june])
    write_curves(tmp_path, "icn-lis", [august])

    stored = read_curves(tmp_path, "icn-lis")["2026-10-05..2026-10-15"]
    assert stored == {
        date(2026, 6, 22): 1_700_000,
        date(2026, 8, 21): 1_120_100,
        date(2026, 8, 22): 1_050_000,
    }


def test_reading_curves_before_any_run_is_empty_not_an_error(tmp_path):
    assert read_curves(tmp_path, "icn-lis") == {}


def test_run_persists_a_curve_for_every_date_pair(tmp_path, route):
    paths = Paths(tmp_path)

    run([route], FakeProvider(), paths, NOW)

    assert len(read_curves(paths.curves, route.id)) == len(route.date_pairs())


def test_run_persists_every_quote(tmp_path, route):
    paths = Paths(tmp_path)

    result = run([route], FakeProvider(), paths, NOW)

    stored = read_since(paths.data, route.id, date(2026, 8, 1), date(2026, 8, 31))
    assert len(stored) == len(route.date_pairs()) * 2
    assert result.collected == len(stored)


def test_dry_run_writes_no_notification_state(tmp_path, monkeypatch):
    """A dry run that marked alerts as sent would mute the real one for a week."""
    paths = _cli_run(tmp_path, monkeypatch, "--dry-run")

    assert not paths.state.exists()
    assert not paths.health.exists()


def test_a_real_run_records_what_it_delivered(tmp_path, monkeypatch):
    paths = _cli_run(tmp_path, monkeypatch)

    assert paths.health.exists()


def _cli_run(tmp_path, monkeypatch, *flags) -> Paths:
    paths = Paths(tmp_path)
    shutil.copy(_repo_root() / "routes.yaml", paths.routes)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["track", "--root", str(tmp_path), *flags])

    main()

    return paths


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent
