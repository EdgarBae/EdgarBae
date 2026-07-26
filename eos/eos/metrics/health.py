"""Enterprise Health Score — the operator's composite KPI (PRD §15)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Relative weights of each KPI category in the final EHS (must sum to 1.0).
EHS_WEIGHTS: dict[str, float] = {
    "availability": 0.18,
    "sla": 0.14,
    "mttr": 0.12,
    "recovery": 0.12,
    "rca": 0.12,
    "automation": 0.08,
    "user": 0.08,
    "cost": 0.06,
    "token": 0.04,
    "preventive": 0.06,
}

# Per-action operational cost (arbitrary currency units).
ACTION_COST = 5.0
# Cost accrued per system per tick while a fault is active (downtime cost).
DOWNTIME_COST_PER_TICK = 20.0
# Token cost charged per operator command (an "AI" operator spends tokens).
TOKEN_COST_PER_COMMAND = 1.0

# Target ceilings used to normalise cost-style KPIs into 0..100 (lower = better).
MTTR_TARGET_TICKS = 6.0
COST_TARGET_PER_TICK = 60.0
TOKEN_TARGET_PER_TICK = 3.0


@dataclass
class HealthLedger:
    """Accumulates raw counters across a run and derives the EHS."""

    n_systems: int
    ticks: int = 0

    system_up_ticks: int = 0
    system_sla_ok_ticks: int = 0

    resolved_faults: int = 0
    resolution_tick_sum: int = 0
    first_attempt_resolutions: int = 0

    recovery_attempts: int = 0
    recovery_successes: int = 0

    rca_attempts: int = 0
    rca_correct: int = 0

    preventive_done: int = 0
    aging_faults: int = 0

    resolved_tickets: int = 0
    ticket_resolution_tick_sum: int = 0
    open_ticket_tick_sum: int = 0  # penalty accrual for unresolved pain

    op_cost: float = 0.0
    token_cost: float = 0.0

    # ------------------------------------------------------------------ update
    def record_tick_health(self, up: int, sla_ok: int, open_tickets: int,
                           active_faults: int) -> None:
        self.ticks += 1
        self.system_up_ticks += up
        self.system_sla_ok_ticks += sla_ok
        self.open_ticket_tick_sum += open_tickets
        self.op_cost += active_faults * DOWNTIME_COST_PER_TICK

    def record_command(self, is_preventive: bool) -> None:
        self.op_cost += ACTION_COST
        self.token_cost += TOKEN_COST_PER_COMMAND
        if is_preventive:
            self.preventive_done += 1

    def record_rca(self, correct: bool) -> None:
        self.rca_attempts += 1
        if correct:
            self.rca_correct += 1

    def record_recovery(self, success: bool) -> None:
        self.recovery_attempts += 1
        if success:
            self.recovery_successes += 1

    def record_fault_resolved(self, duration_ticks: int, attempts: int) -> None:
        self.resolved_faults += 1
        self.resolution_tick_sum += duration_ticks
        if attempts <= 1:
            self.first_attempt_resolutions += 1

    def record_aging_fault(self) -> None:
        self.aging_faults += 1

    def record_ticket_resolved(self, resolution_ticks: int) -> None:
        self.resolved_tickets += 1
        self.ticket_resolution_tick_sum += resolution_ticks

    # ------------------------------------------------------------- subscores
    def subscores(self) -> dict[str, float]:
        n = max(1, self.ticks) * max(1, self.n_systems)
        availability = 100.0 * self.system_up_ticks / n
        sla = 100.0 * self.system_sla_ok_ticks / n

        mttr = (self.resolution_tick_sum / self.resolved_faults
                if self.resolved_faults else 0.0)
        mttr_score = _lower_is_better(mttr, MTTR_TARGET_TICKS)

        recovery = (100.0 * self.recovery_successes / self.recovery_attempts
                    if self.recovery_attempts else 100.0)
        rca = (100.0 * self.rca_correct / self.rca_attempts
               if self.rca_attempts else 100.0)
        automation = (100.0 * self.first_attempt_resolutions / self.resolved_faults
                      if self.resolved_faults else 100.0)

        if self.resolved_tickets:
            avg_res = self.ticket_resolution_tick_sum / self.resolved_tickets
            user = _lower_is_better(avg_res, 8.0)
        else:
            user = 100.0
        # Persistent open tickets erode satisfaction.
        user = max(0.0, user - (self.open_ticket_tick_sum / max(1, self.ticks)) * 4.0)

        cost_per_tick = self.op_cost / max(1, self.ticks)
        cost_score = _lower_is_better(cost_per_tick, COST_TARGET_PER_TICK)
        token_per_tick = self.token_cost / max(1, self.ticks)
        token_score = _lower_is_better(token_per_tick, TOKEN_TARGET_PER_TICK)

        total_aging = self.preventive_done + self.aging_faults
        preventive = (100.0 * self.preventive_done / total_aging
                      if total_aging else 100.0)

        return {
            "availability": availability,
            "sla": sla,
            "mttr": mttr_score,
            "recovery": recovery,
            "rca": rca,
            "automation": automation,
            "user": min(100.0, user),
            "cost": cost_score,
            "token": token_score,
            "preventive": preventive,
        }

    def ehs(self) -> float:
        subs = self.subscores()
        return round(sum(subs[k] * w for k, w in EHS_WEIGHTS.items()), 2)

    def report(self) -> dict[str, object]:
        subs = self.subscores()
        return {
            "ehs": self.ehs(),
            "subscores": {k: round(v, 1) for k, v in subs.items()},
            "raw": {
                "ticks": self.ticks,
                "resolved_faults": self.resolved_faults,
                "rca_attempts": self.rca_attempts,
                "rca_correct": self.rca_correct,
                "recovery_attempts": self.recovery_attempts,
                "recovery_successes": self.recovery_successes,
                "resolved_tickets": self.resolved_tickets,
                "preventive_done": self.preventive_done,
                "aging_faults": self.aging_faults,
                "op_cost": round(self.op_cost, 1),
                "token_cost": round(self.token_cost, 1),
            },
        }


def _lower_is_better(value: float, target: float) -> float:
    """Map a cost-style metric to 0..100; ``target`` scores ~63, 0 scores 100."""
    if value <= 0:
        return 100.0
    return 100.0 * math.exp(-value / target)
