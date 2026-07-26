"""The EOS simulation loop — wires every engine together (PRD §14, §15)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .domain.enums import ActionKind, Metric, SystemState
from .domain.organization import Enterprise
from .domain.systems import Metrics, System
from .engines.aging_engine import AgingEngine
from .engines.chaos_engine import ChaosEngine
from .engines.time_engine import SimClock
from .metrics.health import HealthLedger
from .ops.helpdesk import HelpDesk
from .ops.incidents import Fault
from .ops.operator import Command, RuleBasedOperator


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
    ):
        self.enterprise = enterprise
        self.operator = operator or RuleBasedOperator()
        self.chaos = chaos or ChaosEngine(seed=seed)
        self.aging = aging or AgingEngine()
        self.clock = SimClock()
        self.helpdesk = HelpDesk()
        self.ledger = HealthLedger(n_systems=len(enterprise.systems))
        self.faults: list[Fault] = []
        self.history: list[TickLog] = []
        self._sys_attempts: dict[str, int] = {}

    # ------------------------------------------------------------------- run
    def run(self, ticks: int) -> HealthLedger:
        for _ in range(ticks):
            self.step()
        return self.ledger

    def step(self) -> TickLog:
        tick = self.clock.tick

        # 1) Aging wear + spawned faults.
        for fault in self.aging.advance(self.enterprise, tick):
            self.faults.append(fault)
            self.ledger.record_aging_fault()

        # 2) Random chaos.
        for fault in self.chaos.maybe_inject(self.enterprise, tick, self._active()):
            self.faults.append(fault)

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

        # 7) Bookkeeping for the health score.
        log = self._record_tick(tick, len(commands))
        self.clock.advance()
        return log

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

        if is_preventive:
            self.aging.apply_preventive(system.id, cmd.action)
            return

        active = self._active_on(system.id)
        self._sys_attempts[system.id] = self._sys_attempts.get(system.id, 0) + 1
        if not active:
            # System strained by load, not a fault: a capacity action still helps.
            self._apply_capacity_action(system, cmd.action)
            return

        primary = max(
            active, key=lambda f: system.metrics.get(f.profile.signature_metric)
        )
        self.ledger.record_rca(cmd.diagnosed_kind == primary.kind)

        target = next(
            (f for f in active if cmd.action in f.profile.recoveries), None
        )
        self.ledger.record_recovery(success=target is not None)
        if target is not None:
            target.resolved_tick = tick
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

    def _record_tick(self, tick: int, n_commands: int) -> TickLog:
        up = deg = down = 0
        sla_ok = 0
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
        open_tickets = len(self.helpdesk.open_tickets)
        active = len(self._active())
        self.ledger.record_tick_health(up, sla_ok, open_tickets, active)
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
