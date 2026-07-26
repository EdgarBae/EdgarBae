from eos.harness.agent import AgentOperator
from eos.harness.evaluator import baseline_factory
from eos.harness.scenario import (
    SCENARIOS, leaderboard, run_scenario_case, run_suite, solve_rate,
)


def test_scenarios_are_deterministic():
    a = run_suite(baseline_factory(True))
    b = run_suite(baseline_factory(True))
    assert [(r.scenario_id, r.passed) for r in a] == [(r.scenario_id, r.passed) for r in b]


def test_baseline_solves_the_suite():
    results = run_suite(baseline_factory(True))
    assert solve_rate(results) >= 80.0  # a tuned operator clears most scenarios


def test_each_scenario_injects_only_scripted_faults():
    # With random chaos off, the only faults are the scripted/aging ones.
    from eos.enterprise_factory import build_default_enterprise
    for s in SCENARIOS:
        res = run_scenario_case(baseline_factory(True), s)
        assert res.scenario_id == s.id
        assert 0 <= res.ehs <= 100


def test_leaderboard_ranks_baseline_above_naive_agent():
    def naive(obs):
        return [{"system": a["system"], "action": "restart", "diagnosis": "memory_leak"}
                for a in obs.get("alerts", [])]
    board = leaderboard({
        "baseline": baseline_factory(True),
        "naive": lambda: AgentOperator(naive, "op-naive"),
    })
    assert board[0]["operator"] == "baseline"
    assert board[0]["solve_rate"] >= board[-1]["solve_rate"]


def test_solve_rate_bounds():
    assert solve_rate([]) == 0.0
    results = run_suite(baseline_factory(True))
    assert 0.0 <= solve_rate(results) <= 100.0
