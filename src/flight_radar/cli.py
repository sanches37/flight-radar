"""Entry points. `uv run track` collects; `uv run dashboard` renders.

Rendering is a separate command on purpose: the page is a pure function of what
is already stored, so it can be regenerated after a template change without
paying two minutes of scraping for it.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flight_radar.alert import record_sent
from flight_radar.config import load_routes
from flight_radar.dashboard import RouteData, render
from flight_radar.health import record_run
from flight_radar.notify import send, send_text
from flight_radar.providers import FakeProvider, GoogleFlightsProvider
from flight_radar.store import read_curves, read_latest
from flight_radar.tracker import Paths, RunResult, run

PROVIDERS = {cls.name: cls for cls in (FakeProvider, GoogleFlightsProvider)}
KST = timezone(timedelta(hours=9))


def main() -> None:
    args = _parse_args()
    paths = Paths(args.root)
    routes = load_routes(paths.routes)
    provider = PROVIDERS[args.provider]()
    now = datetime.now(KST)

    result = run(routes, provider, paths, now)
    print(f"{len(routes)} routes tracked, {result.collected} quotes, {len(result.alerts)} alerts")

    if args.dry_run:
        return

    deliver(result, paths, now.date())


def dashboard() -> None:
    parser = argparse.ArgumentParser(prog="dashboard")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    paths = Paths(args.root)
    now = datetime.now(KST)
    data = [
        RouteData(
            route=route,
            quotes=read_latest(paths.data, route.id, now.date()),
            curves=read_curves(paths.curves, route.id),
        )
        for route in load_routes(paths.routes)
    ]

    paths.docs.parent.mkdir(parents=True, exist_ok=True)
    paths.docs.write_text(render(data, now), encoding="utf-8")
    print(f"{paths.docs} written")


def deliver(result: RunResult, paths: Paths, today: date) -> None:
    """Send, then remember what was sent.

    Every piece of state here gates a future notification, so a run that does
    not deliver must not write any of it - otherwise a --dry-run silences the
    real alert for the next seven days.
    """
    send(result.alerts)
    record_sent(result.alerts, paths.state, today)

    warning = record_run(paths.health, result.collected, today)
    if warning:
        send_text(warning)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="track")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="fake")
    parser.add_argument("--dry-run", action="store_true", help="collect and store, do not notify")
    return parser.parse_args()
