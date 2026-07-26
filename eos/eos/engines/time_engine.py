"""Simulated enterprise time and the load it induces (PRD §11)."""
from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import TimePhase

MINUTES_PER_TICK = 30
TICKS_PER_DAY = 24 * 60 // MINUTES_PER_TICK  # 48


@dataclass
class SimClock:
    """Tracks simulated time and derives the current business phase and load.

    One tick advances the clock by ``MINUTES_PER_TICK`` simulated minutes.
    """

    tick: int = 0

    @property
    def day(self) -> int:
        return self.tick // TICKS_PER_DAY

    @property
    def minute_of_day(self) -> int:
        return (self.tick % TICKS_PER_DAY) * MINUTES_PER_TICK

    @property
    def hour(self) -> int:
        return self.minute_of_day // 60

    @property
    def day_of_month(self) -> int:
        return (self.day % 30) + 1

    @property
    def phase(self) -> TimePhase:
        h = self.hour
        if h < 7 or h >= 20:
            return TimePhase.NIGHT
        if 7 <= h < 9:
            return TimePhase.MORNING
        if 12 <= h < 13:
            return TimePhase.LUNCH
        if 17 <= h < 20:
            return TimePhase.EVENING
        return TimePhase.BUSINESS

    @property
    def is_month_end(self) -> bool:
        return self.day_of_month >= 28

    def load_factor(self) -> float:
        """Multiplier applied to baseline load for the current moment."""
        base = {
            TimePhase.NIGHT: 0.15,
            TimePhase.MORNING: 0.8,
            TimePhase.BUSINESS: 1.0,
            TimePhase.LUNCH: 0.5,
            TimePhase.EVENING: 0.7,
        }[self.phase]
        if self.is_month_end and self.phase not in (TimePhase.NIGHT, TimePhase.LUNCH):
            base *= 1.6  # month-end / quarter-close batch surge
        return base

    def advance(self) -> None:
        self.tick += 1
