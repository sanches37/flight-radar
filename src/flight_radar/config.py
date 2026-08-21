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
    return_by: date
    trip_nights: tuple[int, ...]
    target_price_krw: int
    constraints: Constraints
    split_hubs: tuple[str, ...] = ()
    provider: str = "google_flights"
    return_from: str | None = None
    depart_until: date | None = None

    @property
    def inbound_origin(self) -> str:
        """Where the trip home starts. Same as the destination unless open-jaw."""
        return self.return_from or self.destination

    def date_pairs(self) -> list[tuple[date, date]]:
        """Every (depart, return) pair that fits inside the travel window.

        depart_until caps the departure side independently of return_by. Open-jaw
        costs a metered API call per pair, so its window is narrowed to the days
        that actually carry the cheap fares rather than the whole grid.
        """
        pairs: list[tuple[date, date]] = []
        departure = self.depart_from
        last_departure = self.depart_until or self.return_by

        while departure + timedelta(days=min(self.trip_nights)) <= self.return_by:
            if departure > last_departure:
                break
            for nights in sorted(self.trip_nights):
                arrival = departure + timedelta(days=nights)
                if arrival <= self.return_by:
                    pairs.append((departure, arrival))
            departure += timedelta(days=1)

        return pairs


def load_routes(path: Path) -> list[Route]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    routes = [_parse_route(entry) for entry in raw["routes"]]

    duplicates = _find_duplicate_ids(routes)
    if duplicates:
        raise ValueError(f"routes.yaml has duplicate ids: {sorted(duplicates)}")

    return routes


def _parse_route(entry: dict) -> Route:
    window = entry["window"]
    trip_nights = tuple(entry["trip_nights"])
    if not trip_nights:
        raise ValueError(f"route {entry['id']}: trip_nights must not be empty")

    depart_from = _as_date(window["depart_from"])
    return_by = _as_date(window["return_by"])
    if depart_from + timedelta(days=min(trip_nights)) > return_by:
        raise ValueError(
            f"route {entry['id']}: window is too short for the shortest trip"
        )

    depart_until = window.get("depart_until")

    return Route(
        id=entry["id"],
        origin=entry["origin"],
        destination=entry["destination"],
        depart_from=depart_from,
        return_by=return_by,
        trip_nights=trip_nights,
        target_price_krw=entry["target_price_krw"],
        constraints=_parse_constraints(entry.get("constraints", {})),
        split_hubs=tuple(entry.get("split_hubs", [])),
        provider=entry.get("provider", "google_flights"),
        return_from=entry.get("return_from"),
        depart_until=_as_date(depart_until) if depart_until else None,
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
