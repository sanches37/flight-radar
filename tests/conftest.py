from datetime import date, datetime, timedelta, timezone

import pytest

from flight_radar.config import Constraints, Route
from flight_radar.models import PriceInsight, Quote

KST = timezone.utc


@pytest.fixture
def route() -> Route:
    return Route(
        id="icn-lis",
        origin="ICN",
        destination="LIS",
        depart_from=date(2026, 10, 5),
        return_by=date(2026, 10, 16),
        trip_nights=(10, 11),
        target_price_krw=1_400_000,
        constraints=Constraints(max_stops=1, max_duration_minutes=1200),
        split_hubs=("CDG",),
    )


def make_quote(price: int, observed: date, **overrides) -> Quote:
    defaults = dict(
        route_id="icn-lis",
        provider="fake",
        itinerary_type="through",
        origin="ICN",
        destination="LIS",
        depart_date=date(2026, 10, 5),
        return_date=date(2026, 10, 15),
        price_krw=price,
        stops=1,
        duration_minutes=1100,
        carriers=("QR",),
        observed_at=datetime.combine(observed, datetime.min.time(), tzinfo=KST),
    )
    return Quote(**{**defaults, **overrides})


def make_insight(curve: tuple[int, ...], **overrides) -> PriceInsight:
    """A curve given oldest first, ending on the day the tests call today."""
    last = date(2026, 8, 21)
    defaults = dict(
        depart_date=date(2026, 10, 5),
        return_date=date(2026, 10, 15),
        curve_krw={
            last - timedelta(days=len(curve) - 1 - age): price
            for age, price in enumerate(curve)
        },
    )
    return PriceInsight(**{**defaults, **overrides})
