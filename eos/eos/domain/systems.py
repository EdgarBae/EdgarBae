"""Virtual enterprise systems and their live metrics."""
from __future__ import annotations

from dataclasses import dataclass, field

from .enums import Metric, OrgUnit, SystemLayer, SystemState


# SLA thresholds — a system violates its SLA when either bound is exceeded.
SLA_LATENCY_MS = 800.0
SLA_ERROR_RATE = 0.05


@dataclass
class SystemConfig:
    """Operator-tunable configuration knobs (PRD §8)."""

    heap_mb: int = 1024
    connection_pool: int = 20
    cache_mb: int = 256
    workers: int = 4
    instances: int = 2

    def clone(self) -> "SystemConfig":
        return SystemConfig(**self.__dict__)


@dataclass
class Metrics:
    """Live observable signals for a system. All percentages are 0..100."""

    cpu_pct: float = 20.0
    mem_pct: float = 30.0
    disk_pct: float = 40.0
    latency_ms: float = 120.0
    error_rate: float = 0.0
    queue_depth: float = 0.0

    def get(self, metric: Metric) -> float:
        return getattr(self, metric.value)

    def add(self, metric: Metric, delta: float) -> None:
        setattr(self, metric.value, getattr(self, metric.value) + delta)

    def clamp(self) -> None:
        self.cpu_pct = _clamp(self.cpu_pct, 0, 100)
        self.mem_pct = _clamp(self.mem_pct, 0, 100)
        self.disk_pct = _clamp(self.disk_pct, 0, 100)
        self.latency_ms = max(0.0, self.latency_ms)
        self.error_rate = _clamp(self.error_rate, 0.0, 1.0)
        self.queue_depth = max(0.0, self.queue_depth)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass
class System:
    """A single operable enterprise system (an ERP module, portal, DB, ...)."""

    id: str
    name: str
    layer: SystemLayer
    org: OrgUnit
    stack: str = ""
    depends_on: list[str] = field(default_factory=list)
    config: SystemConfig = field(default_factory=SystemConfig)

    # Baseline (idle) metrics; the effective metrics are recomputed each tick.
    baseline: Metrics = field(default_factory=Metrics)
    metrics: Metrics = field(default_factory=Metrics)

    def health(self) -> float:
        """Composite 0..100 health score, higher is better."""
        m = self.metrics
        penalties = (
            max(0.0, m.cpu_pct - 70) * 0.6
            + max(0.0, m.mem_pct - 75) * 0.7
            + max(0.0, m.disk_pct - 80) * 0.9
            + max(0.0, m.latency_ms - SLA_LATENCY_MS) / 40.0
            + m.error_rate * 100.0
            + max(0.0, m.queue_depth - 100) * 0.15
        )
        return _clamp(100.0 - penalties, 0.0, 100.0)

    def state(self) -> SystemState:
        h = self.health()
        if self.metrics.error_rate >= 0.9 or h <= 10:
            return SystemState.DOWN
        if h < 65 or self.violates_sla():
            return SystemState.DEGRADED
        return SystemState.UP

    def violates_sla(self) -> bool:
        return (
            self.metrics.latency_ms > SLA_LATENCY_MS
            or self.metrics.error_rate > SLA_ERROR_RATE
        )
