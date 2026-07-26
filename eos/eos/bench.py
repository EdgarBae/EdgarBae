"""Benchmark operators: continuous EHS + ITBench-style scenario solve rate.

    python -m eos.bench

Prints a leaderboard comparing the rule-based baseline against a naive agent,
on two axes:
  * EHS      — the long-horizon continuous run (availability, prevention, cost)
  * Solve %  — discrete scenario suite, ITBench-style pass/fail
"""
from __future__ import annotations

from .harness.agent import AgentOperator
from .harness.evaluator import baseline_factory, run_scenario
from .harness.scenario import SCENARIOS, leaderboard


def naive_agent_policy(obs: dict) -> list[dict]:
    """A deliberately shallow agent: restart anything alerting, renew on cert.

    Reads the tool-shaped observation (alerts + runbooks) exactly as a real
    SRE agent would — but with a thin policy, so it scores well below the
    tuned baseline. That gap is the point of the harness.
    """
    actions, seen = [], set()
    for a in obs.get("alerts", []):
        sid = a["system"]
        if sid in seen:
            continue
        seen.add(sid)
        action = "renew_certificate" if a["alertname"] == "HighErrorRate" else "restart"
        actions.append({"system": sid, "action": action,
                        "diagnosis": "ssl_expired" if action == "renew_certificate" else "memory_leak",
                        "rationale": f"agent: {a['alertname']}"})
    return actions


def _bar(pct: float, width: int = 24) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    operators = {
        "baseline (preventive)": baseline_factory(True),
        "baseline (no preventive)": baseline_factory(False),
        "naive agent": lambda: AgentOperator(naive_agent_policy, "op-naive"),
    }

    # Continuous EHS (long-horizon run).
    ehs = {}
    noprev = run_scenario(baseline_factory(False), with_transcript=False).ehs
    for name, factory in operators.items():
        ehs[name] = run_scenario(factory, with_transcript=False).ehs

    # Discrete scenario solve rate (ITBench-style).
    board = leaderboard(operators)

    print("\nEOS operator leaderboard  (seed 7)\n" + "=" * 58)
    print(f"{'operator':<26}{'EHS':>7}   {'solve %':>7}   scenarios")
    print("-" * 58)
    for row in board:
        name = row["operator"]
        print(f"{name:<26}{ehs[name]:>7.1f}   {row['solve_rate']:>6.1f}%   "
              f"{row['passed']}/{row['total']}")
    print("-" * 58)
    print(f"scenario suite: {', '.join(s.id for s in SCENARIOS)}")
    print("\nper-scenario (best operator):")
    best = board[0]
    for sid, ok in best["per_scenario"].items():
        print(f"  {'PASS' if ok else 'FAIL':<5} {sid}")
    print(f"\nreference — IBM ITBench: SOTA agents solve ~11% of SRE scenarios.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
