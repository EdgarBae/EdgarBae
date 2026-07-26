"""Chaos engine — random and manual fault injection (PRD §9)."""
from __future__ import annotations

import random
from collections.abc import Iterable

from ..domain.enums import FaultKind, Severity
from ..domain.organization import Enterprise
from ..ops.incidents import FAULT_PROFILES, Fault

# Faults the automatic engine may inject at random (aging owns DISK_FULL etc.).
_RANDOM_KINDS = [
    FaultKind.MEMORY_LEAK,
    FaultKind.JVM_OOM,
    FaultKind.QUEUE_OVERFLOW,
    FaultKind.WORKER_DOWN,
    FaultKind.SLOW_QUERY,
    FaultKind.NETWORK_DELAY,
    FaultKind.EC2_FAILURE,
    FaultKind.API_TIMEOUT,
    FaultKind.DB_LOCK,
]


class ChaosEngine:
    """Randomly injects faults, and lets an operator inject them manually."""

    def __init__(self, seed: int = 0, probability: float = 0.08):
        self.rng = random.Random(seed)
        self.probability = probability

    def maybe_inject(
        self,
        enterprise: Enterprise,
        tick: int,
        active_faults: Iterable[Fault],
    ) -> list[Fault]:
        """Possibly inject one random fault into a currently-healthy system."""
        if self.rng.random() >= self.probability:
            return []
        busy = {f.system_id for f in active_faults if not f.resolved}
        healthy = [s for s in enterprise.systems.values() if s.id not in busy]
        if not healthy:
            return []
        system = self.rng.choice(healthy)
        kind = self.rng.choice(_RANDOM_KINDS)
        return [self.inject(system.id, kind, tick, origin="chaos")]

    def inject(
        self,
        system_id: str,
        kind: FaultKind,
        tick: int,
        origin: str = "manual",
        severity: Severity | None = None,
    ) -> Fault:
        """Create a fault instance (used by both random and manual paths)."""
        profile = FAULT_PROFILES[kind]
        return Fault(
            kind=kind,
            system_id=system_id,
            started_tick=tick,
            severity=severity or profile.base_severity,
            origin=origin,
        )
