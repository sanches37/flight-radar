"""The page has to say the same thing the phone says, and say when it is blind."""

from datetime import date, datetime, timezone

from conftest import make_insight, make_quote

from flight_radar.dashboard import RouteData, _history_curve, observed_lows, render

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


def test_observed_lows_keeps_one_price_per_collection_day(route):
    """오픈조는 Google 곡선이 없어 우리가 쌓은 관측이 유일한 히스토리다."""
    quotes = [
        make_quote(1_500_000, date(2026, 8, 21)),
        make_quote(1_300_000, date(2026, 8, 21)),   # 같은 날 더 싼 견적
        make_quote(1_400_000, date(2026, 8, 25)),
    ]

    assert observed_lows(route, quotes) == {
        date(2026, 8, 21): 1_300_000,
        date(2026, 8, 25): 1_400_000,
    }


def test_observed_lows_ignores_fares_the_trip_cannot_use(route):
    """제약 위반 운임이 곡선을 끌어내리면 '싸다'는 판단이 통째로 틀어진다."""
    quotes = [
        make_quote(900_000, date(2026, 8, 21), stops=3),
        make_quote(1_300_000, date(2026, 8, 21)),
    ]

    assert observed_lows(route, quotes) == {date(2026, 8, 21): 1_300_000}


def test_a_single_observation_draws_no_curve():
    """점 하나로 선을 그리면 추세가 있는 것처럼 보인다."""
    assert _history_curve({date(2026, 8, 21): 1_300_000}) == ""


def test_the_history_curve_is_labelled_with_real_dates():
    """수집이 매일은 아니므로 'N일 전'으로 눈금을 매기면 과장이 된다."""
    svg = _history_curve({date(2026, 8, 21): 1_300_000, date(2026, 8, 25): 1_400_000})

    assert "08-21" in svg and "08-25" in svg
    assert "일 전" not in svg
    assert "수집 2회" in svg
