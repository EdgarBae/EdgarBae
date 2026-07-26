"""ITBench-style scenarios and a solve-rate leaderboard.

Where :mod:`evaluator` scores an operator over a long, random-chaos run (the
*continuous* story — availability, prevention, cost over time), scenarios are
the *discrete* story: a controlled fault, a goal, and a pass/fail check, exactly
like IBM's ITBench. Running the same scenario suite across operators yields a
comparable **solve rate** — the headline number ITBench reports (SOTA agents
solve only ~11% of SRE scenarios today).

Scenarios keep random chaos OFF and inject faults deterministically, so a
pass/fail is attributable to the operator, not luck.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..domain.enums import FaultKind
from ..enterprise_factory import build_default_enterprise
from ..engines.aging_engine import AgingEngine, AgingState
from ..engines.chaos_engine import ChaosEngine
from ..ops.incidents import Fault
from ..simulation import Simulator
from .agent import Operator

OperatorFactory = Callable[[], Operator]
Injection = tuple[str, FaultKind]


@dataclass
class Scenario:
    id: str
    title: str
    goal: str
    ticks: int
    scripted_faults: dict[int, list[Injection]] = field(default_factory=dict)
    setup: Callable[[Simulator], None] | None = None
    check: Callable[[Simulator], tuple[bool, dict]] = lambda sim: (False, {})


@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    ehs: float
    detail: dict


def run_scenario_case(operator_factory: OperatorFactory, scenario: Scenario,
                      seed: int = 7) -> ScenarioResult:
    enterprise = build_default_enterprise()
    chaos = ChaosEngine(seed=seed, probability=0.0)  # controlled: no random chaos
    sim = Simulator(enterprise, operator=operator_factory(), chaos=chaos,
                    aging=AgingEngine(), seed=seed,
                    scripted_faults=scenario.scripted_faults)
    if scenario.setup:
        scenario.setup(sim)
    sim.run(scenario.ticks)
    passed, detail = scenario.check(sim)
    return ScenarioResult(scenario.id, passed, sim.ledger.ehs(), detail)


def run_suite(operator_factory: OperatorFactory,
              scenarios: list[Scenario] | None = None,
              seed: int = 7) -> list[ScenarioResult]:
    return [run_scenario_case(operator_factory, s, seed)
            for s in (scenarios or SCENARIOS)]


def solve_rate(results: list[ScenarioResult]) -> float:
    if not results:
        return 0.0
    return round(100.0 * sum(r.passed for r in results) / len(results), 1)


def leaderboard(operators: dict[str, OperatorFactory],
                scenarios: list[Scenario] | None = None,
                seed: int = 7) -> list[dict]:
    """Solve rate per operator over the scenario suite, best-first."""
    scenarios = scenarios or SCENARIOS
    rows = []
    for name, factory in operators.items():
        results = run_suite(factory, scenarios, seed)
        rows.append({
            "operator": name,
            "solve_rate": solve_rate(results),
            "passed": sum(r.passed for r in results),
            "total": len(results),
            "per_scenario": {r.scenario_id: r.passed for r in results},
        })
    rows.sort(key=lambda r: r["solve_rate"], reverse=True)
    return rows


# --------------------------------------------------------------------- checks
def _scenario_faults(sim: Simulator) -> list[Fault]:
    return [f for f in sim.faults if f.origin == "scenario"]


def _resolved_within(sim: Simulator, kinds: set[FaultKind], within: int
                     ) -> tuple[bool, dict]:
    faults = [f for f in sim.faults if f.kind in kinds and f.origin != "aging"]
    if not faults:
        return False, {"reason": "target fault never occurred"}
    ok = all(f.resolved_tick is not None and (f.resolved_tick - f.started_tick) <= within
             for f in faults)
    detail = {f.id: (None if f.resolved_tick is None else f.resolved_tick - f.started_tick)
              for f in faults}
    return ok, {"mttr_ticks": detail, "budget": within}


def _no_prolonged_outage(sim: Simulator, kinds: set[FaultKind], within: int
                        ) -> tuple[bool, dict]:
    """Pass if the fault was prevented entirely, or recovered within budget."""
    faults = [f for f in sim.faults if f.kind in kinds]
    if not faults:
        return True, {"reason": "prevented — fault never occurred"}
    ok = all(f.resolved_tick is not None and (f.resolved_tick - f.started_tick) <= within
             for f in faults)
    return ok, {"occurred": len(faults), "budget": within}


def _preset_cert(sim: Simulator, system_id: str, ticks_left: int) -> None:
    sim.aging.state[system_id] = AgingState(cert_ticks_left=ticks_left)


# ---------------------------------------------------------------- the suite
# Inject during business hours (tick 20 = 10:00) so faults manifest under load.
_INJ = 20

SCENARIOS: list[Scenario] = [
    Scenario(
        id="sre-memory-leak", title="Memory leak on SAP PM",
        goal="Detect the heap leak and recover the service within 8 ticks.",
        ticks=60, scripted_faults={_INJ: [("sap-pm", FaultKind.MEMORY_LEAK)]},
        check=lambda sim: _resolved_within(sim, {FaultKind.MEMORY_LEAK}, 8),
    ),
    Scenario(
        id="sre-queue-overflow", title="Queue overflow on the EAI bus",
        goal="Clear the consumer backlog within 8 ticks.",
        ticks=60, scripted_faults={_INJ: [("eai", FaultKind.QUEUE_OVERFLOW)]},
        check=lambda sim: _resolved_within(sim, {FaultKind.QUEUE_OVERFLOW}, 8),
    ),
    Scenario(
        id="sre-db-lock", title="Lock contention on PostgreSQL",
        goal="Identify the blocking transaction and restore latency within 8 ticks.",
        ticks=60, scripted_faults={_INJ: [("pg-core", FaultKind.DB_LOCK)]},
        check=lambda sim: _resolved_within(sim, {FaultKind.DB_LOCK}, 8),
    ),
    Scenario(
        id="sre-cascade", title="Cascading latency (slow query + API timeout)",
        goal="Recover both affected systems within 10 ticks.",
        ticks=64, scripted_faults={_INJ: [("pg-core", FaultKind.SLOW_QUERY),
                                          ("portal-ai", FaultKind.API_TIMEOUT)]},
        check=lambda sim: _resolved_within(
            sim, {FaultKind.SLOW_QUERY, FaultKind.API_TIMEOUT}, 10),
    ),
    Scenario(
        id="sre-cert-expiry", title="Certificate about to expire on IAM",
        goal="Prevent the outage (renew in time) or recover within 4 ticks.",
        ticks=60, setup=lambda sim: _preset_cert(sim, "iam", 15),
        check=lambda sim: _no_prolonged_outage(sim, {FaultKind.SSL_EXPIRED}, 4),
    ),
]
