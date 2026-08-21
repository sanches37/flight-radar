"""routes.yaml loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Constraints:
    max_stops: int | None = None
    max_duration_minutes: int | None = None
    exclude_carriers: tuple[str, ...] = ()

    def allows(self, stops: int, duration_minutes: int, carriers: tuple[str, ...]) -> bool:
        if self.max_stops is not None and stops > self.max_stops:
            return False
        if self.max_duration_minutes is not None and duration_minutes > self.max_duration_minutes:
            return False
        return not any(carrier in self.exclude_carriers for carrier in carriers)


@dataclass(frozen=True)
class Route:
    id: str
    origin: str
    destination: str
    depart_from: date
    depart_to: date
    trip_nights: tuple[int, ...]
    target_price_krw: int
    constraints: Constraints
    split_hubs: tuple[str, ...] = ()

    def date_pairs(self) -> list[tuple[date, date]]:
        """Every (depart, return) combination this route watches."""
        span = (self.depart_to - self.depart_from).days
        departures = [self.depart_from + timedelta(days=offset) for offset in range(span + 1)]
        return [
            (departure, departure + timedelta(days=nights))
            for departure in departures
            for nights in self.trip_nights
        ]


def load_routes(path: Path) -> list[Route]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    routes = [_parse_route(entry) for entry in raw["routes"]]

    duplicates = _find_duplicate_ids(routes)
    if duplicates:
        raise ValueError(f"routes.yaml has duplicate ids: {sorted(duplicates)}")

    return routes


def _parse_route(entry: dict) -> Route:
    window = entry["depart_window"]
    trip_nights = tuple(entry["trip_nights"])
    if not trip_nights:
        raise ValueError(f"route {entry['id']}: trip_nights must not be empty")

    return Route(
        id=entry["id"],
        origin=entry["origin"],
        destination=entry["destination"],
        depart_from=_as_date(window["from"]),
        depart_to=_as_date(window["to"]),
        trip_nights=trip_nights,
        target_price_krw=entry["target_price_krw"],
        constraints=_parse_constraints(entry.get("constraints", {})),
        split_hubs=tuple(entry.get("split_hubs", [])),
    )


def _parse_constraints(entry: dict) -> Constraints:
    return Constraints(
        max_stops=entry.get("max_stops"),
        max_duration_minutes=entry.get("max_duration_minutes"),
        exclude_carriers=tuple(entry.get("exclude_carriers", [])),
    )


def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _find_duplicate_ids(routes: list[Route]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for route in routes:
        if route.id in seen:
            duplicates.add(route.id)
        seen.add(route.id)
    return duplicates
