"""The repo itself is the database.

GitHub Actions has no persistent disk, so everything collected is written back
into the working tree and committed. Git history then doubles as a free backup
of every price ever observed.

Two shapes live here, for two different sources:

- Quotes are append-only JSONL, one file per route per month. Each run adds
  new lines and never touches old ones.
- Google's price curves are a merged map, because Google re-serves the same
  sixty-one points on every run. Appending those would pile up duplicates.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from flight_radar.models import PriceInsight, Quote

LOOKBACK_DAYS = 30


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


def read_latest(root: Path, route_id: str, until: date) -> list[Quote]:
    """Every quote from the most recent run, within the lookback.

    One run stamps all of its quotes with the same instant, so matching on the
    newest timestamp isolates exactly one sweep. Taking the newest calendar day
    instead would blend the morning and evening runs into one picture.
    """
    recent = read_since(root, route_id, until - timedelta(days=LOOKBACK_DAYS), until)
    if not recent:
        return []

    newest = max(quote.observed_at for quote in recent)
    return [quote for quote in recent if quote.observed_at == newest]


def read_curves(root: Path, route_id: str) -> dict[str, dict[date, int]]:
    """Every price curve kept for one route, keyed by date pair then by day."""
    path = _curves_path(root, route_id)
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        pair: {date.fromisoformat(day): price for day, price in points.items()}
        for pair, points in raw.items()
    }


def write_curves(root: Path, route_id: str, insights: Sequence[PriceInsight]) -> None:
    """Merge Google's rolling window into a record that outlives it.

    Google's curve reaches sixty days back and no further, so points fall off
    the far end every day and would be lost if only the latest response were
    kept. Merging also keeps each run's diff to a line or two per date pair.

    Overwriting an older point with a newer one is safe: the same date pair
    fetched twice ten minutes apart returned all sixty-one points identical,
    so Google does not revise its own history.
    """
    if not insights:
        return

    stored = read_curves(root, route_id)
    for insight in insights:
        pair = _pair_key(insight.depart_date, insight.return_date)
        stored.setdefault(pair, {}).update(insight.curve_krw)

    serialisable = {
        pair: {day.isoformat(): price for day, price in sorted(points.items())}
        for pair, points in sorted(stored.items())
    }
    path = _curves_path(root, route_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # One point per line, so a run's diff reads as the handful of days it moved.
    path.write_text(json.dumps(serialisable, indent=1) + "\n", encoding="utf-8")


def _pair_key(depart: date, arrive: date) -> str:
    return f"{depart}..{arrive}"


def _curves_path(root: Path, route_id: str) -> Path:
    return root / f"{route_id}.json"


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
