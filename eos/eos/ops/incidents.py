"""Faults: the concrete failure instances injected into systems.

Each :class:`FaultKind` has a static *profile* describing how it manifests
(which metrics it degrades and how fast), what its true root cause label is,
and which operator actions legitimately recover it. The Chaos engine, Aging
engine, and Operators all read from this single registry so that symptoms,
diagnosis, and remediation stay consistent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import ActionKind, FaultKind, Metric, Severity


@dataclass(frozen=True)
class FaultProfile:
    kind: FaultKind
    rca_label: str
    # metric -> (initial magnitude, per-tick growth) applied while active
    effects: dict[Metric, tuple[float, float]]
    recoveries: frozenset[ActionKind]
    # The metric an operator should key on when diagnosing (dominant symptom).
    signature_metric: Metric
    base_severity: Severity = Severity.MEDIUM


FAULT_PROFILES: dict[FaultKind, FaultProfile] = {
    FaultKind.MEMORY_LEAK: FaultProfile(
        FaultKind.MEMORY_LEAK, "JVM heap slowly exhausted by a leak",
        {Metric.MEMORY: (12.0, 3.0), Metric.LATENCY: (40.0, 8.0)},
        frozenset({ActionKind.RESTART, ActionKind.ROLLING_RESTART}),
        Metric.MEMORY, Severity.HIGH,
    ),
    FaultKind.JVM_OOM: FaultProfile(
        FaultKind.JVM_OOM, "OutOfMemoryError crashed the application process",
        {Metric.MEMORY: (55.0, 2.0), Metric.ERROR_RATE: (0.6, 0.05)},
        frozenset({ActionKind.RESTART, ActionKind.INCREASE_HEAP}),
        Metric.MEMORY, Severity.CRITICAL,
    ),
    FaultKind.QUEUE_OVERFLOW: FaultProfile(
        FaultKind.QUEUE_OVERFLOW, "Consumer lag; message queue backing up",
        {Metric.QUEUE_DEPTH: (140.0, 45.0), Metric.LATENCY: (120.0, 20.0)},
        frozenset({ActionKind.FLUSH_QUEUE, ActionKind.SCALE_OUT}),
        Metric.QUEUE_DEPTH, Severity.HIGH,
    ),
    FaultKind.SSL_EXPIRED: FaultProfile(
        FaultKind.SSL_EXPIRED, "TLS certificate expired; handshakes rejected",
        {Metric.ERROR_RATE: (0.95, 0.0)},
        frozenset({ActionKind.RENEW_CERT}),
        Metric.ERROR_RATE, Severity.CRITICAL,
    ),
    FaultKind.WORKER_DOWN: FaultProfile(
        FaultKind.WORKER_DOWN, "Background worker process died",
        {Metric.QUEUE_DEPTH: (90.0, 25.0), Metric.ERROR_RATE: (0.15, 0.02)},
        frozenset({ActionKind.RESTART_WORKER, ActionKind.RESTART}),
        Metric.QUEUE_DEPTH, Severity.MEDIUM,
    ),
    FaultKind.SLOW_QUERY: FaultProfile(
        FaultKind.SLOW_QUERY, "Un-indexed query causing table scans",
        {Metric.LATENCY: (350.0, 60.0), Metric.CPU: (20.0, 5.0)},
        frozenset({ActionKind.KILL_SLOW_QUERY, ActionKind.REINDEX}),
        Metric.LATENCY, Severity.MEDIUM,
    ),
    FaultKind.NETWORK_DELAY: FaultProfile(
        FaultKind.NETWORK_DELAY, "Inter-AZ network latency spike",
        {Metric.LATENCY: (280.0, 15.0)},
        frozenset({ActionKind.FAILOVER}),
        Metric.LATENCY, Severity.MEDIUM,
    ),
    FaultKind.EC2_FAILURE: FaultProfile(
        FaultKind.EC2_FAILURE, "Compute instance failed / unreachable",
        {Metric.ERROR_RATE: (0.5, 0.08), Metric.CPU: (30.0, 5.0)},
        frozenset({ActionKind.FAILOVER, ActionKind.SCALE_OUT}),
        Metric.ERROR_RATE, Severity.CRITICAL,
    ),
    FaultKind.DISK_FULL: FaultProfile(
        FaultKind.DISK_FULL, "Disk exhausted by log/table growth",
        {Metric.DISK: (55.0, 4.0), Metric.ERROR_RATE: (0.2, 0.03)},
        frozenset({ActionKind.CLEANUP_LOGS, ActionKind.ADD_DISK}),
        Metric.DISK, Severity.HIGH,
    ),
    FaultKind.API_TIMEOUT: FaultProfile(
        FaultKind.API_TIMEOUT, "Downstream API timing out",
        {Metric.LATENCY: (400.0, 40.0), Metric.ERROR_RATE: (0.2, 0.03)},
        frozenset({ActionKind.SCALE_OUT, ActionKind.RESTART}),
        Metric.LATENCY, Severity.HIGH,
    ),
    FaultKind.DB_LOCK: FaultProfile(
        FaultKind.DB_LOCK, "Long-held transaction lock blocking writers",
        {Metric.LATENCY: (300.0, 50.0), Metric.ERROR_RATE: (0.1, 0.02)},
        frozenset({ActionKind.KILL_SLOW_QUERY, ActionKind.RESTART}),
        Metric.LATENCY, Severity.HIGH,
    ),
    FaultKind.INDEX_FRAGMENTATION: FaultProfile(
        FaultKind.INDEX_FRAGMENTATION, "Fragmented indexes degrading reads",
        {Metric.LATENCY: (180.0, 25.0)},
        frozenset({ActionKind.REINDEX}),
        Metric.LATENCY, Severity.LOW,
    ),
}


_seq = 0


def _next_id() -> str:
    global _seq
    _seq += 1
    return f"F{_seq:04d}"


@dataclass
class Fault:
    """A live fault instance attached to a system."""

    kind: FaultKind
    system_id: str
    started_tick: int
    severity: Severity
    origin: str = "chaos"  # "chaos" | "aging" | "manual"
    id: str = field(default_factory=_next_id)
    resolved_tick: int | None = None
    age: int = 0  # ticks since injection

    @property
    def profile(self) -> FaultProfile:
        return FAULT_PROFILES[self.kind]

    @property
    def resolved(self) -> bool:
        return self.resolved_tick is not None

    def current_effects(self) -> dict[Metric, float]:
        """Metric deltas at the fault's current age (leaks worsen over time)."""
        out: dict[Metric, float] = {}
        for metric, (base, growth) in self.profile.effects.items():
            out[metric] = base + growth * self.age
        return out
