"""One tracking run: fetch every watched date pair, persist, decide alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from flight_radar.alert import HISTORY_DAYS, Alert, find_alerts, suppress_repeats
from flight_radar.config import Route
from flight_radar.models import Observation, Quote
from flight_radar.providers import Provider
from flight_radar.store import append, read_since, write_curves


class Paths:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.routes = root / "routes.yaml"
        self.data = root / "data" / "quotes"
        self.curves = root / "data" / "curves"
        self.docs = root / "docs" / "index.html"
        self.state = root / "state" / "alerts.json"
        self.health = root / "state" / "health.json"


@dataclass(frozen=True)
class RunResult:
    alerts: list[Alert]
    collected: int


def run(
    routes: list[Route],
    provider: Provider,
    paths: Paths,
    observed_at: datetime,
) -> RunResult:
    alerts: list[Alert] = []
    collected = 0

    for route in routes:
        observed = collect(route, provider, observed_at)
        append(paths.data, observed.quotes)
        write_curves(paths.curves, route.id, observed.insights)
        collected += len(observed.quotes)

        history = _history_before(paths.data, route, observed_at)
        alerts.extend(
            find_alerts(
                route, observed.quotes, history, observed_at.date(), observed.insights
            )
        )

    return RunResult(suppress_repeats(alerts, paths.state, observed_at.date()), collected)


def collect(route: Route, provider: Provider, observed_at: datetime) -> Observation:
    observed = Observation()
    for depart_date, return_date in route.date_pairs():
        seen = provider.fetch(route, depart_date, return_date, observed_at)
        observed.quotes.extend(seen.quotes)
        observed.insights.extend(seen.insights)
    return observed


def _history_before(data_root: Path, route: Route, observed_at: datetime) -> list[Quote]:
    """History excludes today so a drop is measured against earlier runs only."""
    today = observed_at.date()
    return read_since(data_root, route.id, today - timedelta(days=HISTORY_DAYS), today - timedelta(days=1))
