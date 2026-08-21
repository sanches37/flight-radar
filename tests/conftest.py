from datetime import date, datetime, timezone

import pytest

from flight_radar.config import Constraints, Route
from flight_radar.models import Quote

KST = timezone.utc


@pytest.fixture
def route() -> Route:
    return Route(
        id="icn-lis",
        origin="ICN",
        destination="LIS",
        depart_from=date(2026, 10, 12),
        depart_to=date(2026, 10, 14),
        trip_nights=(10,),
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
        depart_date=date(2026, 10, 12),
        return_date=date(2026, 10, 22),
        price_krw=price,
        stops=1,
        duration_minutes=1100,
        carriers=("QR",),
        observed_at=datetime.combine(observed, datetime.min.time(), tzinfo=KST),
    )
    return Quote(**{**defaults, **overrides})
