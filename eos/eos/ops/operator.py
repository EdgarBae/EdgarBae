"""Enterprise operators — the agents under evaluation (PRD §7, §14).

An operator only sees *symptoms* (system metrics, tickets, aging warnings),
never the ground-truth fault. It must infer a root cause (RCA) and choose a
recovery action. The simulator scores both the diagnosis and the outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import ActionKind, FaultKind, Metric, SystemState
from ..domain.organization import Enterprise
from ..domain.systems import SLA_ERROR_RATE, SLA_LATENCY_MS, System
from .helpdesk import HelpDesk


@dataclass
class Command:
    """A single operator instruction for one system this tick."""

    system_id: str
    action: ActionKind
    diagnosed_kind: FaultKind | None  # None => preventive maintenance
    rationale: str
    # Governance intent (see harness/policy.py). A policy-aware operator sets
    # request_approval on changes that need sign-off; emergency marks break-glass.
    request_approval: bool = False
    emergency: bool = False


# Ordered recovery candidates to try for each dominant symptom. The first entry
# is also the operator's initial root-cause hypothesis for that symptom.
_LATENCY_PLAYBOOK = [
    ActionKind.KILL_SLOW_QUERY,
    ActionKind.REINDEX,
    ActionKind.FAILOVER,
    ActionKind.SCALE_OUT,
    ActionKind.RESTART,
]


class RuleBasedOperator:
    """A deterministic baseline operator: diagnose-by-dominant-symptom.

    This is the reference agent every smarter (LLM-driven) operator is
    benchmarked against. It is intentionally imperfect at RCA so the
    evaluation model (PRD §14) has signal to measure.
    """

    def __init__(self, operator_id: str = "op-generalist", preventive: bool = True):
        self.id = operator_id
        self.preventive = preventive
        # Governance policy (set by the harness). When present, this operator
        # complies: it requests approval for changes, defers during freezes, and
        # refuses to touch forbidden systems — escalating instead of acting.
        self.governance_policy = None
        # system_id -> actions already attempted for the current incident
        self._attempts: dict[str, set[ActionKind]] = {}

    def notify_recovered(self, system_id: str) -> None:
        self._attempts.pop(system_id, None)

    def decide(
        self,
        enterprise: Enterprise,
        helpdesk: HelpDesk,
        aging_warnings: list[tuple[str, str]],
    ) -> list[Command]:
        commands: list[Command] = []

        # 1) Reactive: address degraded / down systems AND systems that are
        #    still "up" but tripping an alert threshold — catching e.g. a heap
        #    leak from the HighMemory signal before it becomes an outage.
        troubled = [
            s for s in enterprise.systems.values()
            if s.state() != SystemState.UP or _alerting(s)
        ]
        troubled.sort(key=lambda s: s.health())
        for system in troubled:
            commands.append(self._diagnose_and_act(system))

        # 2) Preventive: act on aging warnings for otherwise-healthy systems.
        if self.preventive:
            handled = {c.system_id for c in commands}
            for sid, reason in aging_warnings:
                if sid in handled:
                    continue
                action = _PREVENTIVE_FOR_REASON.get(reason)
                if action is None:
                    continue
                commands.append(Command(
                    system_id=sid,
                    action=action,
                    diagnosed_kind=None,
                    rationale=f"preventive: {reason}",
                ))
                handled.add(sid)

        if self.governance_policy is not None:
            commands = self._comply(commands, enterprise)
        return commands

    def _comply(self, commands: list[Command], enterprise: Enterprise) -> list[Command]:
        """Annotate/filter proposed actions to respect the governance policy.

        Forbidden systems/actions are escalated (dropped, not executed); changes
        during a freeze are deferred unless it's an outage (break-glass); every
        remaining change requests approval unless the policy is fully autonomous.
        """
        p = self.governance_policy
        clock = getattr(enterprise, "_clock", None)
        phase = clock.phase.value if clock else "business"
        month_end = clock.is_month_end if clock else False
        out: list[Command] = []
        for c in commands:
            if c.action.value in p.forbidden_actions or c.system_id in p.forbidden_systems:
                continue  # out of scope -> escalate to a human, do not act
            is_outage = enterprise.systems[c.system_id].state() == SystemState.DOWN
            if p.in_freeze(phase, month_end):
                if is_outage and p.emergency_override_allowed:
                    c.emergency = True
                    c.request_approval = True
                    out.append(c)
                continue  # otherwise defer the change out of the freeze window
            c.request_approval = (p.autonomy != "autonomous")
            out.append(c)
        return out

    def _diagnose_and_act(self, system: System) -> Command:
        guess, playbook = self._diagnose(system)
        tried = self._attempts.setdefault(system.id, set())
        action = next((a for a in playbook if a not in tried), ActionKind.RESTART)
        tried.add(action)
        return Command(
            system_id=system.id,
            action=action,
            diagnosed_kind=guess,
            rationale=f"symptom-based RCA -> {guess.value}",
        )

    def _diagnose(self, system: System) -> tuple[FaultKind, list[ActionKind]]:
        """Infer the most likely fault kind and a ranked recovery playbook."""
        m = system.metrics
        # Order matters: check the most specific signatures first.
        if m.get(Metric.MEMORY) > 80:
            if m.get(Metric.ERROR_RATE) > 0.3:
                return FaultKind.JVM_OOM, [ActionKind.RESTART, ActionKind.INCREASE_HEAP]
            return FaultKind.MEMORY_LEAK, [ActionKind.ROLLING_RESTART, ActionKind.RESTART]
        if m.get(Metric.QUEUE_DEPTH) > 80:
            return FaultKind.QUEUE_OVERFLOW, [
                ActionKind.FLUSH_QUEUE, ActionKind.RESTART_WORKER, ActionKind.SCALE_OUT,
            ]
        if m.get(Metric.DISK) > 85:
            return FaultKind.DISK_FULL, [ActionKind.CLEANUP_LOGS, ActionKind.ADD_DISK]
        if m.get(Metric.ERROR_RATE) >= 0.9 and m.get(Metric.LATENCY) < SLA_LATENCY_MS * 1.5:
            return FaultKind.SSL_EXPIRED, [ActionKind.RENEW_CERT, ActionKind.FAILOVER]
        if m.get(Metric.ERROR_RATE) > SLA_ERROR_RATE and m.get(Metric.CPU) > 45:
            return FaultKind.EC2_FAILURE, [ActionKind.FAILOVER, ActionKind.SCALE_OUT]
        if m.get(Metric.LATENCY) > SLA_LATENCY_MS:
            return FaultKind.SLOW_QUERY, list(_LATENCY_PLAYBOOK)
        # Fallback: generic restart.
        return FaultKind.API_TIMEOUT, [ActionKind.RESTART, ActionKind.SCALE_OUT]


def _alerting(system: System) -> bool:
    """A system worth attention even before it formally degrades."""
    m = system.metrics
    return (
        m.get(Metric.MEMORY) > 85
        or m.get(Metric.DISK) > 88
        or m.get(Metric.QUEUE_DEPTH) > 110
        or m.get(Metric.ERROR_RATE) > SLA_ERROR_RATE
        or m.get(Metric.LATENCY) > SLA_LATENCY_MS
    )


_PREVENTIVE_FOR_REASON: dict[str, ActionKind] = {
    "certificate_expiring": ActionKind.RENEW_CERT,
    "index_fragmentation": ActionKind.REINDEX,
    "disk_filling": ActionKind.CLEANUP_LOGS,
}
