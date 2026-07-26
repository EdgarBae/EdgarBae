"""The Observation — everything an operator agent is allowed to perceive.

This is the harness's *observation surface*. An operator (rule-based, or an
LLM/MCP agent) sees exactly this serialisable snapshot each tick — system
screens, help-desk tickets, and aging warnings — and **never** the ground-truth
fault kind. Inferring the cause from these symptoms is the operator's job, and
the scoring (RCA accuracy, recovery rate) depends on that information barrier.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..domain.enums import SystemState
from ..domain.organization import Enterprise
from ..engines.aging_engine import AgingEngine
from ..engines.time_engine import SimClock
from ..ops.helpdesk import HelpDesk


@dataclass
class SystemView:
    """How one system appears on the operator's screen right now."""

    id: str
    name: str
    layer: str
    stack: str
    state: str          # up | degraded | down
    sla_ok: bool
    metrics: dict[str, float]
    config: dict[str, int]


@dataclass
class TicketView:
    id: str
    system: str
    type: str
    priority: int
    summary: str
    reporter_role: str
    state: str
    assignee: str | None
    age: int


@dataclass
class Observation:
    """The complete, serialisable perception handed to an operator each tick."""

    tick: int
    phase: str
    load: float
    month_end: bool
    ehs: float
    systems: list[SystemView] = field(default_factory=list)
    tickets: list[TicketView] = field(default_factory=list)
    aging_warnings: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    # ---------------------------------------------------------------- capture
    @classmethod
    def capture(
        cls,
        enterprise: Enterprise,
        helpdesk: HelpDesk,
        aging: AgingEngine,
        clock: SimClock,
        ehs: float,
    ) -> "Observation":
        systems = []
        for s in enterprise.systems.values():
            m = s.metrics
            systems.append(SystemView(
                id=s.id, name=s.name, layer=s.layer.value, stack=s.stack,
                state=s.state().value, sla_ok=not s.violates_sla(),
                metrics={
                    "cpu": round(m.cpu_pct, 1), "mem": round(m.mem_pct, 1),
                    "disk": round(m.disk_pct, 1), "latency_ms": round(m.latency_ms),
                    "error_rate": round(m.error_rate, 3), "queue": round(m.queue_depth),
                },
                config={
                    "instances": s.config.instances, "heap_mb": s.config.heap_mb,
                    "connection_pool": s.config.connection_pool, "workers": s.config.workers,
                },
            ))
        tickets = []
        for t in helpdesk.open_tickets:
            u = next((u for u in enterprise.users if u.id == t.reporter_id), None)
            tickets.append(TicketView(
                id=t.id, system=t.system_id, type=t.type.value, priority=t.priority,
                summary=t.summary, reporter_role=u.role if u else "user",
                state=t.state.value, assignee=t.assignee, age=clock.tick - t.opened_tick,
            ))
        warnings = [{"system": sid, "reason": r} for sid, r in aging.warnings(enterprise)]
        return cls(
            tick=clock.tick, phase=clock.phase.value,
            load=round(clock.load_factor(), 2), month_end=clock.is_month_end,
            ehs=ehs, systems=systems, tickets=tickets, aging_warnings=warnings,
        )
