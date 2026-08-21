"""Provider contract. Swapping the data source must not touch anything else."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from flight_radar.config import Route
from flight_radar.models import Observation


class Provider(Protocol):
    name: str

    def fetch(
        self, route: Route, depart_date: date, return_date: date, observed_at: datetime
    ) -> Observation:
        """Return every itinerary found for one date pair, cheapest first.

        Implementations must not filter on route.constraints - the tracker
        records everything and filtering happens at alert time, so that a
        constraint change can be re-evaluated against existing history.

        A price curve for the date pair comes back in the same Observation
        when the source carries one; it is optional, and alerting degrades to
        target and drop reasons without it.
        """
        ...
