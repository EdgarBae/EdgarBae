"""Virtual users that exercise the enterprise systems (PRD §5)."""
from __future__ import annotations

from dataclasses import dataclass

from .enums import OrgUnit


@dataclass(frozen=True)
class VirtualUser:
    """An AI-driven user of a system.

    Personality drives how readily the user raises a ticket when a system
    misbehaves; ``patience`` (0..1) scales the degradation they will tolerate
    before complaining. Higher priority users' complaints weigh more.
    """

    id: str
    name: str
    role: str
    system_id: str
    org: OrgUnit
    personality: str = "neutral"
    priority: int = 3  # 1 (highest) .. 5 (lowest)
    patience: float = 0.5  # 0 = complains instantly, 1 = very tolerant

    @property
    def complaint_threshold(self) -> float:
        """Health level below which this user files a ticket."""
        # Impatient users complain earlier (higher threshold).
        return 40.0 + self.patience * 35.0
