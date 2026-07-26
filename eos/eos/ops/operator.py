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

        # 1) Reactive: address degraded / down systems, worst first.
        troubled = [
            s for s in enterprise.systems.values()
            if s.state() != SystemState.UP
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

        return commands

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


_PREVENTIVE_FOR_REASON: dict[str, ActionKind] = {
    "certificate_expiring": ActionKind.RENEW_CERT,
    "index_fragmentation": ActionKind.REINDEX,
    "disk_filling": ActionKind.CLEANUP_LOGS,
}
