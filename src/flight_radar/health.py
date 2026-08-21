"""Watch for the silent death: the job still runs but collects nothing.

A scraper that returns zero quotes is indistinguishable from a market with no
flights. Google changing its payload, or Actions' IP getting blocked, would
otherwise just stop the history from growing with nobody noticing.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

EMPTY_RUNS_BEFORE_ALERT = 3


def record_run(path: Path, collected: int, today: date) -> str | None:
    """Store this run's outcome and return a warning when collection looks dead.

    The warning repeats on every run past the threshold rather than firing
    once on the crossing: a single message lost to a failed delivery is
    exactly the silence this exists to break.
    """
    state = _load(path)

    if collected > 0:
        _save(path, {"empty_streak": 0, "last_collected_on": today.isoformat()})
        return None

    streak = int(state.get("empty_streak", 0)) + 1
    last_collected = state.get("last_collected_on")
    _save(path, {"empty_streak": streak, "last_collected_on": last_collected})

    if streak < EMPTY_RUNS_BEFORE_ALERT:
        return None
    return _warning(streak, last_collected)


def _warning(streak: int, last_collected: str | None) -> str:
    seen = f"마지막 수집 성공: {last_collected}" if last_collected else "수집에 성공한 적 없음"
    return (
        f"⚠️ flight-radar가 {streak}회 연속 0건을 수집했습니다.\n"
        f"{seen}\n"
        "Google 응답 형식이 바뀌었거나 Actions IP가 차단됐을 수 있습니다."
    )


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
