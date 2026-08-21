"""Is today a good day to buy?

The answer is read off the cheapest price available on each day across every
watched date pair, not off any single pair - the trip is not tied to one.
"""

from datetime import date

from conftest import make_insight

from flight_radar.insight import read_market


def test_a_record_low_reads_as_zero():
    market = read_market([make_insight((1_500_000, 1_400_000, 1_300_000, 1_100_000))])

    assert market.percentile == 0.0
    assert market.today_krw == 1_100_000
    assert market.low_krw == 1_100_000
    assert market.days == 3


def test_a_record_high_reads_as_a_hundred():
    market = read_market([make_insight((1_100_000, 1_300_000, 1_400_000, 1_500_000))])

    assert market.percentile == 100.0
    assert market.low_krw == 1_100_000


def test_a_price_that_has_not_moved_in_two_months_is_not_a_buy_signal():
    """Ties count half, so a flat curve lands mid-range instead of at zero."""
    market = read_market([make_insight((1_200_000,) * 61)])

    assert market.percentile == 50.0


def test_the_ranking_counts_only_the_days_before_today():
    market = read_market([make_insight((1_000_000, 2_000_000, 3_000_000, 1_500_000))])

    assert market.percentile == 100.0 * 1 / 3


def test_the_cheapest_date_pair_of_each_day_sets_the_series():
    """A pair at its own record low can still be a bad day to buy.

    Measured 2026-08-21: one ICN-LIS pair read as a record low while the
    cheapest-across-pairs price had been beaten on 87% of the last sixty days.
    """
    at_its_own_low = make_insight((900_000, 900_000, 800_000))
    cheaper_until_today = make_insight(
        (700_000, 700_000, 900_000), return_date=date(2026, 10, 16)
    )

    market = read_market([at_its_own_low, cheaper_until_today])

    assert market.today_krw == 800_000
    assert market.percentile == 100.0
    assert market.low_krw == 700_000


def test_a_curve_with_no_history_yields_no_reading():
    assert read_market([make_insight((1_200_000,))]) is None


def test_no_curves_at_all_yields_no_reading():
    assert read_market([]) is None
