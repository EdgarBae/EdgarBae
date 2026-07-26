"""Help Desk — turns user pain into classified, prioritised tickets (PRD §6)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import Severity, TicketState, TicketType
from ..domain.organization import Enterprise
from ..domain.systems import SystemState

_seq = 0


def _next_id() -> str:
    global _seq
    _seq += 1
    return f"T{_seq:05d}"


@dataclass
class Ticket:
    system_id: str
    type: TicketType
    priority: int  # 1 (highest) .. 5
    summary: str
    opened_tick: int
    reporter_id: str
    id: str = field(default_factory=_next_id)
    state: TicketState = TicketState.OPEN
    assignee: str | None = None
    resolved_tick: int | None = None
    request_code: str | None = None  # for service/change requests (non-incidents)

    def resolution_ticks(self) -> int | None:
        if self.resolved_tick is None:
            return None
        return self.resolved_tick - self.opened_tick


class HelpDesk:
    """Generates tickets from user dissatisfaction and routes them."""

    def __init__(self) -> None:
        self.tickets: list[Ticket] = []

    @property
    def open_tickets(self) -> list[Ticket]:
        return [t for t in self.tickets if t.state != TicketState.RESOLVED]

    def open_for(self, system_id: str) -> list[Ticket]:
        return [t for t in self.open_tickets if t.system_id == system_id]

    def open_incident_for(self, system_id: str) -> list[Ticket]:
        return [t for t in self.open_for(system_id) if t.type == TicketType.INCIDENT]

    def intake(self, enterprise: Enterprise, tick: int) -> list[Ticket]:
        """Create incident tickets for systems whose users are unhappy.

        At most one open incident per system at a time (deduplicated).
        """
        new: list[Ticket] = []
        for sid, system in enterprise.systems.items():
            if self.open_incident_for(sid):
                continue
            health = system.health()
            state = system.state()
            if state == SystemState.UP:
                continue
            complainers = [
                u for u in enterprise.users_of(sid)
                if health < u.complaint_threshold
            ]
            if not complainers:
                continue
            reporter = min(complainers, key=lambda u: u.priority)
            new.append(self._make_incident(system, reporter, state, tick))
        self.tickets.extend(new)
        return new

    def _make_incident(self, system, reporter, state, tick) -> Ticket:
        priority = reporter.priority
        if state == SystemState.DOWN:
            priority = max(1, priority - 2)  # outages escalate
        summary = (
            f"{system.name} is {'unavailable' if state == SystemState.DOWN else 'slow'} "
            f"(reported by {reporter.role})"
        )
        return Ticket(
            system_id=system.id,
            type=TicketType.INCIDENT,
            priority=priority,
            summary=summary,
            opened_tick=tick,
            reporter_id=reporter.id,
        )

    def assign(self, ticket: Ticket, operator_id: str) -> None:
        ticket.assignee = operator_id
        ticket.state = TicketState.ASSIGNED

    def resolve_for_system(self, system_id: str, tick: int) -> list[Ticket]:
        """Close open *incident* tickets for a system that has recovered.

        Service/change requests are unrelated to system health and are cleared
        separately by :meth:`service_requests`.
        """
        closed: list[Ticket] = []
        for t in self.open_incident_for(system_id):
            t.state = TicketState.RESOLVED
            t.resolved_tick = tick
            closed.append(t)
        return closed

    def file_request(self, ticket: Ticket) -> Ticket:
        self.tickets.append(ticket)
        return ticket

    def service_requests(self, operator_id: str, tick: int,
                         handling: dict[TicketType, int]) -> list[Ticket]:
        """Assign and time-resolve open service/change requests (the desk's
        routine workload, distinct from incident recovery). Returns the tickets
        resolved this tick.
        """
        resolved: list[Ticket] = []
        for t in self.open_tickets:
            if t.type == TicketType.INCIDENT:
                continue
            if t.assignee is None:
                self.assign(t, operator_id)
            elif tick - t.opened_tick >= handling.get(t.type, 3):
                t.state = TicketState.RESOLVED
                t.resolved_tick = tick
                resolved.append(t)
        return resolved
