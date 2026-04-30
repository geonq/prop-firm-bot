"""Replayable trade-day inputs for historical strategy validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReplayDay:
    """One session day of realized strategy outcomes.

    `r_multiples` are normalized trade results for the session. Empty tuples are
    intentional: they represent no-trade days and must stay in the replay so
    finite-horizon timeout math is not overstated.
    """

    session_date: date
    r_multiples: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a datetime.date")

    @classmethod
    def from_values(cls, session_date: date, *r_multiples: float) -> "ReplayDay":
        return cls(session_date=session_date, r_multiples=tuple(float(value) for value in r_multiples))
