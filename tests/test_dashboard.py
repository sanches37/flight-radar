"""The page has to say the same thing the phone says, and say when it is blind."""

from datetime import date, datetime, timezone

from conftest import make_insight, make_quote

from flight_radar.dashboard import RouteData, render

NOW = datetime(2026, 8, 21, 13, 0, tzinfo=timezone.utc)
CHEAP_TODAY = make_insight((1_800_000,) * 20 + (1_100_000,)).curve_krw
DEAR_TODAY = make_insight((900_000,) * 20 + (1_800_000,)).curve_krw


def _page(route, quotes, curves=None) -> str:
    return render([RouteData(route, quotes, curves or {})], NOW)


def test_the_heatmap_shows_the_cheapest_fare_we_would_actually_book(route):
    """A cheap three-stop routing must not become the cell everyone reads."""
    quotes = [
        make_quote(1_500_000, date(2026, 8, 21)),
        make_quote(900_000, date(2026, 8, 21), stops=3, duration_minutes=2000),
    ]

    page = _page(route, quotes)

    assert ">150<" in page
    assert ">90<" not in page


def test_a_combination_outside_the_window_is_not_drawn_as_missing_data(route):
    """Three watched pairs in a two-by-two grid; the fourth cell is not data."""
    quotes = [make_quote(1_500_000, date(2026, 8, 21))]

    page = _page(route, quotes)

    assert page.count("—") == len(route.date_pairs()) - 1
    assert page.count("td class='off'") == 1


def test_reaching_target_reads_as_a_buy_even_when_the_market_is_high(route):
    """Verdict order matches the alert; a page that disagrees is worse than none."""
    quotes = [make_quote(1_350_000, date(2026, 8, 21))]

    page = _page(route, quotes, {"2026-10-05..2026-10-15": DEAR_TODAY})

    assert "목표가 도달" in page
    assert "verdict buy" in page


def test_the_bottom_of_the_range_reads_as_a_buy(route):
    quotes = [make_quote(1_500_000, date(2026, 8, 21))]

    page = _page(route, quotes, {"2026-10-05..2026-10-15": CHEAP_TODAY})

    assert "저점 구간" in page
    assert "최근 20일 중 하위 0%" in page


def test_an_ordinary_price_reads_as_wait(route):
    quotes = [make_quote(1_500_000, date(2026, 8, 21))]

    page = _page(route, quotes, {"2026-10-05..2026-10-15": DEAR_TODAY})

    assert "기다릴 것" in page
    assert "verdict hold" in page


def test_missing_curves_are_flagged_where_a_human_will_see_them(route):
    """Losing only the curve leaves quotes flowing, so health.py cannot see it."""
    quotes = [make_quote(1_500_000, date(2026, 8, 21))]

    page = _page(route, quotes, {"2026-10-05..2026-10-15": CHEAP_TODAY})

    assert f"곡선 1/{len(route.date_pairs())}쌍" in page
    assert "health warn" in page


def test_a_full_sweep_is_not_flagged(route):
    quotes = [make_quote(1_500_000, date(2026, 8, 21))]
    curves = {f"{depart}..{arrive}": CHEAP_TODAY for depart, arrive in route.date_pairs()}

    page = _page(route, quotes, curves)

    assert "health warn" not in page


def test_the_page_survives_a_route_with_nothing_collected_yet(route):
    page = _page(route, [])

    assert "판정할 견적이 없습니다" in page
    assert "견적 0건" in page


def test_the_page_names_the_price_the_ranking_describes(route):
    """Same caveat the alert carries: the curve ignores our constraints."""
    quotes = [make_quote(1_500_000, date(2026, 8, 21))]

    page = _page(route, quotes, {"2026-10-05..2026-10-15": DEAR_TODAY})

    assert "무제약 최저 1,800,000원 기준" in page


def test_the_curve_axis_is_labelled_by_age_not_by_date(route):
    """The day keys are UTC alignment keys; Google stamps midnight elsewhere."""
    quotes = [make_quote(1_500_000, date(2026, 8, 21))]

    page = _page(route, quotes, {"2026-10-05..2026-10-15": CHEAP_TODAY})

    assert "20일 전" in page and "오늘" in page


def test_an_open_jaw_section_names_both_ends(route):
    from dataclasses import replace

    open_jaw = replace(route, return_from="OPO")
    page = _page(open_jaw, [make_quote(1_383_200, date(2026, 8, 21), return_from="OPO")])

    assert "ICN → LIS / OPO → ICN" in page


def test_a_round_trip_section_is_unchanged(route):
    page = _page(route, [make_quote(1_350_000, date(2026, 8, 21))])

    assert "<h2>ICN → LIS</h2>" in page
