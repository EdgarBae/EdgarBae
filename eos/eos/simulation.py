"""The EOS simulation loop — wires every engine together (PRD §14, §15)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .domain.enums import ActionKind, Metric, SystemState, TicketType, TimePhase
from .domain.organization import Enterprise
from .domain.systems import Metrics, System
from .engines.aging_engine import AgingEngine
from .engines.chaos_engine import ChaosEngine
from .engines.time_engine import SimClock
from .metrics.health import HealthLedger
from .ops.helpdesk import HelpDesk, Ticket
from .ops.incidents import Fault
from .ops.operator import Command, RuleBasedOperator

# Routine (non-incident) help-desk workload — codes rendered per-language by UIs.
_SR_CODES = ["access_request", "report_request", "password_reset",
             "data_extract", "account_unlock"]
_CR_CODES = ["schedule_change", "config_change", "new_user", "capacity_upgrade"]
_DESK_HANDLING = {TicketType.SERVICE_REQUEST: 2, TicketType.CHANGE_REQUEST: 4}
_DESK_ACTIVE_PHASES = (TimePhase.MORNING, TimePhase.BUSINESS, TimePhase.EVENING)


@dataclass
class TickLog:
    tick: int
    phase: str
    load: float
    up: int
    degraded: int
    down: int
    active_faults: int
    open_tickets: int
    commands: int


class Simulator:
    """Drives an :class:`Enterprise` through time under an operator's control."""

    def __init__(
        self,
        enterprise: Enterprise,
        operator: RuleBasedOperator | None = None,
        chaos: ChaosEngine | None = None,
        aging: AgingEngine | None = None,
        seed: int = 0,
        scripted_faults: dict[int, list[tuple[str, "FaultKind"]]] | None = None,
    ):
        self.enterprise = enterprise
        self.operator = operator or RuleBasedOperator()
        self.chaos = chaos or ChaosEngine(seed=seed)
        self.aging = aging or AgingEngine()
        # tick -> [(system_id, FaultKind)] injected deterministically (scenarios).
        self.scripted_faults = scripted_faults or {}
        self.clock = SimClock()
        self.helpdesk = HelpDesk()
        self.ledger = HealthLedger(n_systems=len(enterprise.systems))
        self.faults: list[Fault] = []
        self.history: list[TickLog] = []
        self._sys_attempts: dict[str, int] = {}
        self.desk_rng = random.Random(seed + 991)
        # Harness instrumentation (append-only logs the transcript is built from).
        self.metric_log: list[list] = []   # per tick: [[state_code, cpu, mem, disk, lat, err, q], ...]
        self.event_log: list[dict] = []     # per operator command, with outcome
        self.ehs_log: list[float] = []       # running EHS after each tick

    # ------------------------------------------------------------------- run
    def run(self, ticks: int) -> HealthLedger:
        for _ in range(ticks):
            self.step()
        return self.ledger

    def step(self) -> TickLog:
        tick = self.clock.tick
        # Expose the clock so an AgentOperator's Observation is time-accurate.
        self.enterprise._clock = self.clock

        # 1) Aging wear + spawned faults.
        for fault in self.aging.advance(self.enterprise, tick):
            self.faults.append(fault)
            self.ledger.record_aging_fault()

        # 2) Random chaos.
        for fault in self.chaos.maybe_inject(self.enterprise, tick, self._active()):
            self.faults.append(fault)

        # 2b) Scripted faults for controlled scenarios (deterministic).
        for system_id, kind in self.scripted_faults.get(tick, []):
            self.faults.append(self.chaos.inject(system_id, kind, tick, origin="scenario"))

        # 3) Materialise metrics from load + active faults.
        self._recompute_metrics(age_faults=True)

        # 4) Users raise tickets.
        self.helpdesk.intake(self.enterprise, tick)

        # 5) Operator observes and acts.
        warnings = self.aging.warnings(self.enterprise)
        commands = self.operator.decide(self.enterprise, self.helpdesk, warnings)
        for cmd in commands:
            self._execute(cmd, tick)

        # 6) Recompute post-action; resolve tickets for recovered systems.
        self._recompute_metrics(age_faults=False)
        self._settle_recoveries(tick)

        # 6b) Routine help-desk workload (service & change requests, PRD §6).
        self._service_desk(tick)

        # 7) Bookkeeping for the health score.
        log = self._record_tick(tick, len(commands))
        self.clock.advance()
        return log

    def _service_desk(self, tick: int) -> None:
        """Generate and clear routine service/change requests from users."""
        if (self.clock.phase in _DESK_ACTIVE_PHASES
                and self.enterprise.users and self.desk_rng.random() < 0.11):
            is_change = self.desk_rng.random() < 0.22
            ttype = TicketType.CHANGE_REQUEST if is_change else TicketType.SERVICE_REQUEST
            code = self.desk_rng.choice(_CR_CODES if is_change else _SR_CODES)
            user = self.desk_rng.choice(self.enterprise.users)
            self.helpdesk.file_request(Ticket(
                system_id=user.system_id, type=ttype,
                priority=3 if is_change else self.desk_rng.choice([3, 4]),
                summary=code, opened_tick=tick, reporter_id=user.id, request_code=code,
            ))
        for t in self.helpdesk.service_requests(self.operator.id, tick, _DESK_HANDLING):
            res = t.resolution_ticks()
            if res is not None:
                self.ledger.record_ticket_resolved(res)

    # -------------------------------------------------------------- internals
    def _active(self) -> list[Fault]:
        return [f for f in self.faults if not f.resolved]

    def _active_on(self, system_id: str) -> list[Fault]:
        return [f for f in self._active() if f.system_id == system_id]

    def _recompute_metrics(self, age_faults: bool) -> None:
        load = self.clock.load_factor()
        for system in self.enterprise.systems.values():
            base = system.baseline
            cap = (2.0 / max(1, system.config.instances)) ** 0.5
            load_hi = 0.6 + 0.8 * load
            m = Metrics(
                cpu_pct=base.cpu_pct * (0.5 + 0.7 * load) * cap,
                mem_pct=base.mem_pct * (0.7 + 0.3 * load),
                disk_pct=base.disk_pct,
                latency_ms=base.latency_ms * load_hi * cap,
                error_rate=base.error_rate,
                queue_depth=base.queue_depth + 20.0 * max(0.0, load - 1.0),
            )
            for fault in self._active_on(system.id):
                if age_faults:
                    fault.age += 1
                for metric, delta in fault.current_effects().items():
                    m.add(metric, delta)
            m.clamp()
            system.metrics = m

    def _execute(self, cmd: Command, tick: int) -> None:
        system = self.enterprise.systems[cmd.system_id]
        is_preventive = cmd.diagnosed_kind is None
        self.ledger.record_command(is_preventive=is_preventive)

        event = {
            "t": tick, "sys": system.id, "action": cmd.action.value,
            "diag": cmd.diagnosed_kind.value if cmd.diagnosed_kind else None,
            "preventive": is_preventive, "rationale": cmd.rationale,
            "rca_correct": None, "recovery": None, "resolved": False,
        }
        self.event_log.append(event)

        if is_preventive:
            self.aging.apply_preventive(system.id, cmd.action)
            return

        active = self._active_on(system.id)
        self._sys_attempts[system.id] = self._sys_attempts.get(system.id, 0) + 1
        # Route the affected system's open tickets to this operator (PRD §6).
        for t in self.helpdesk.open_for(system.id):
            self.helpdesk.assign(t, self.operator.id)
        if not active:
            # System strained by load, not a fault: a capacity action still helps.
            self._apply_capacity_action(system, cmd.action)
            return

        primary = max(
            active, key=lambda f: system.metrics.get(f.profile.signature_metric)
        )
        rca_correct = cmd.diagnosed_kind == primary.kind
        self.ledger.record_rca(rca_correct)
        event["rca_correct"] = rca_correct
        event["actual"] = primary.kind.value  # ground truth for the transcript

        target = next(
            (f for f in active if cmd.action in f.profile.recoveries), None
        )
        self.ledger.record_recovery(success=target is not None)
        event["recovery"] = target is not None
        if target is not None:
            target.resolved_tick = tick
            event["resolved"] = True
            self.ledger.record_fault_resolved(
                duration_ticks=tick - target.started_tick,
                attempts=self._sys_attempts.get(system.id, 1),
            )
            self.aging.apply_preventive(system.id, cmd.action)
            self._apply_capacity_action(system, cmd.action)

    def _apply_capacity_action(self, system: System, action: ActionKind) -> None:
        if action == ActionKind.SCALE_OUT:
            system.config.instances += 1
        elif action == ActionKind.INCREASE_HEAP:
            system.config.heap_mb = int(system.config.heap_mb * 1.5)
            system.baseline.mem_pct = max(15.0, system.baseline.mem_pct - 5.0)
        elif action == ActionKind.INCREASE_POOL:
            system.config.connection_pool += 10

    def _settle_recoveries(self, tick: int) -> None:
        for system in self.enterprise.systems.values():
            if self._active_on(system.id):
                continue
            if system.state() != SystemState.UP:
                continue
            closed = self.helpdesk.resolve_for_system(system.id, tick)
            for t in closed:
                res = t.resolution_ticks()
                if res is not None:
                    self.ledger.record_ticket_resolved(res)
            if closed or self._sys_attempts.get(system.id):
                self.operator.notify_recovered(system.id)
                self._sys_attempts.pop(system.id, None)

    _STATE_CODE = {SystemState.UP: 0, SystemState.DEGRADED: 1, SystemState.DOWN: 2}

    def _record_tick(self, tick: int, n_commands: int) -> TickLog:
        up = deg = down = 0
        sla_ok = 0
        snapshot: list[list] = []
        for system in self.enterprise.systems.values():
            st = system.state()
            if st == SystemState.UP:
                up += 1
            elif st == SystemState.DEGRADED:
                deg += 1
            else:
                down += 1
            if not system.violates_sla():
                sla_ok += 1
            m = system.metrics
            snapshot.append([
                self._STATE_CODE[st], round(m.cpu_pct), round(m.mem_pct),
                round(m.disk_pct), round(m.latency_ms), round(m.error_rate, 3),
                round(m.queue_depth),
            ])
        self.metric_log.append(snapshot)
        open_tickets = len(self.helpdesk.open_tickets)
        active = len(self._active())
        self.ledger.record_tick_health(up, sla_ok, open_tickets, active)
        self.ehs_log.append(self.ledger.ehs())
        log = TickLog(
            tick=tick,
            phase=self.clock.phase.value,
            load=round(self.clock.load_factor(), 2),
            up=up,
            degraded=deg,
            down=down,
            active_faults=active,
            open_tickets=open_tickets,
            commands=n_commands,
        )
        self.history.append(log)
        return log
