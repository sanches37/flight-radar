"""One tracking run: fetch every watched date pair, persist, decide alerts."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from flight_radar.alert import HISTORY_DAYS, Alert, find_alerts, suppress_repeats
from flight_radar.config import Route
from flight_radar.models import Quote
from flight_radar.providers import Provider
from flight_radar.store import append, read_since


class Paths:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.routes = root / "routes.yaml"
        self.data = root / "data" / "quotes"
        self.state = root / "state" / "alerts.json"


def run(
    routes: list[Route],
    provider: Provider,
    paths: Paths,
    observed_at: datetime,
) -> list[Alert]:
    alerts: list[Alert] = []

    for route in routes:
        fresh = collect(route, provider, observed_at)
        append(paths.data, fresh)

        history = _history_before(paths.data, route, observed_at)
        alerts.extend(find_alerts(route, fresh, history, observed_at.date()))

    return suppress_repeats(alerts, paths.state, observed_at.date())


def collect(route: Route, provider: Provider, observed_at: datetime) -> list[Quote]:
    quotes: list[Quote] = []
    for depart_date, return_date in route.date_pairs():
        quotes.extend(provider.fetch(route, depart_date, return_date, observed_at))
    return quotes


def _history_before(data_root: Path, route: Route, observed_at: datetime) -> list[Quote]:
    """History excludes today so a drop is measured against earlier runs only."""
    today = observed_at.date()
    return read_since(data_root, route.id, today - timedelta(days=HISTORY_DAYS), today - timedelta(days=1))
