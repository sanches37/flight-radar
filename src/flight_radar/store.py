"""Append-only JSONL price history, one file per route per month.

GitHub Actions has no persistent disk, so the repo itself is the database.
Append-only keeps each run's diff to a few lines and makes git history a
free backup of every price ever observed.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from flight_radar.models import Quote


def append(root: Path, quotes: list[Quote]) -> None:
    by_file: dict[Path, list[Quote]] = {}
    for quote in quotes:
        by_file.setdefault(_path_for(root, quote.route_id, quote.observed_at.date()), []).append(quote)

    for path, batch in by_file.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(quote.to_json(), ensure_ascii=False) for quote in batch]
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def read_since(root: Path, route_id: str, since: date, until: date) -> list[Quote]:
    """Every quote observed in [since, until] for one route."""
    quotes: list[Quote] = []
    for path in _paths_covering(root, route_id, since, until):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            quote = Quote.from_json(json.loads(line))
            if since <= quote.observed_at.date() <= until:
                quotes.append(quote)
    return quotes


def _path_for(root: Path, route_id: str, observed: date) -> Path:
    return root / route_id / f"{observed:%Y-%m}.jsonl"


def _paths_covering(root: Path, route_id: str, since: date, until: date) -> list[Path]:
    months: list[str] = []
    cursor = since.replace(day=1)
    while cursor <= until:
        months.append(f"{cursor:%Y-%m}")
        cursor = (cursor + timedelta(days=32)).replace(day=1)

    candidates = [root / route_id / f"{month}.jsonl" for month in months]
    return [path for path in candidates if path.exists()]
