"""Entry point. `uv run track` performs one tracking run."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flight_radar.config import load_routes
from flight_radar.notify import send
from flight_radar.providers import FakeProvider
from flight_radar.tracker import Paths, run

PROVIDERS = {"fake": FakeProvider}
KST = timezone(timedelta(hours=9))


def main() -> None:
    args = _parse_args()
    paths = Paths(args.root)
    routes = load_routes(paths.routes)
    provider = PROVIDERS[args.provider]()

    alerts = run(routes, provider, paths, datetime.now(KST))
    print(f"{len(routes)} routes tracked, {len(alerts)} alerts")

    if not args.dry_run:
        send(alerts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="track")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="fake")
    parser.add_argument("--dry-run", action="store_true", help="collect and store, do not notify")
    return parser.parse_args()
