"""Run and score operators — the top of the harness.

``run_scenario`` executes one operator against a seeded enterprise and returns
its Enterprise Health Score plus a replayable transcript. ``benchmark`` runs
several operators on the *same* seed so a new agent can be compared head-to-head
with the rule-based baseline — the core loop of "can this AI replace the human
operator?".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..enterprise_factory import build_default_enterprise
from ..engines.chaos_engine import ChaosEngine
from ..ops.operator import RuleBasedOperator
from ..simulation import Simulator
from .agent import Operator
from .transcript import build_transcript

OperatorFactory = Callable[[], Operator]


@dataclass
class RunResult:
    operator_id: str
    ehs: float
    subscores: dict[str, float]
    raw: dict
    transcript: dict = field(repr=False, default_factory=dict)


def run_scenario(
    operator_factory: OperatorFactory,
    seed: int = 7,
    ticks: int = 240,
    chaos_p: float = 0.08,
    with_transcript: bool = True,
    ehs_noprev: float | None = None,
    policy=None,
) -> RunResult:
    enterprise = build_default_enterprise()
    operator = operator_factory()
    chaos = ChaosEngine(seed=seed, probability=chaos_p)
    sim = Simulator(enterprise, operator=operator, chaos=chaos, seed=seed, policy=policy)
    sim.run(ticks)
    report = sim.ledger.report()
    return RunResult(
        operator_id=getattr(operator, "id", "operator"),
        ehs=report["ehs"],
        subscores=report["subscores"],
        raw=report["raw"],
        transcript=build_transcript(sim, ehs_noprev) if with_transcript else {},
    )


def benchmark(
    operators: dict[str, OperatorFactory],
    seed: int = 7,
    ticks: int = 240,
    chaos_p: float = 0.08,
) -> list[tuple[str, float]]:
    """Score each named operator on the same scenario; sorted best-first."""
    rows = []
    for name, factory in operators.items():
        res = run_scenario(factory, seed, ticks, chaos_p, with_transcript=False)
        rows.append((name, res.ehs))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def baseline_factory(preventive: bool = True) -> OperatorFactory:
    return lambda: RuleBasedOperator(preventive=preventive)
