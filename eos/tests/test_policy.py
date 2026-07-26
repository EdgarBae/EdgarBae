import json
import os

from eos.domain.enums import ActionKind
from eos.harness.agent import AgentOperator
from eos.harness.evaluator import baseline_factory, run_scenario
from eos.harness.policy import (
    Autonomy, Decision, EnterprisePolicy, PolicyGate, load_policy,
)


def test_example_policy_loads_and_is_generic():
    p = load_policy()  # the generic EXAMPLE
    assert p.autonomy == Autonomy.PROPOSE_APPROVE
    assert p.forbidden_systems == frozenset()  # no real org rules baked in
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "enterprise_policy.example.json")) as f:
        assert "_comment" in json.load(f)  # clearly a fill-in template


def test_gate_forbids_freezes_and_requires_approval():
    p = EnterprisePolicy(
        autonomy=Autonomy.PROPOSE_APPROVE,
        forbidden_systems=frozenset({"pg-core"}),
        freeze_when_month_end=True,
    )
    gate = PolicyGate(p)
    assert gate.classify(ActionKind.RESTART, "pg-core", "business", False) == Decision.FORBIDDEN
    assert gate.classify(ActionKind.RESTART, "sap-pm", "business", True) == Decision.FREEZE_BLOCKED
    assert gate.classify(ActionKind.RESTART, "sap-pm", "business", False) == Decision.NEEDS_APPROVAL


def test_autonomous_policy_auto_allows():
    gate = PolicyGate(EnterprisePolicy(autonomy=Autonomy.AUTONOMOUS))
    assert gate.classify(ActionKind.RESTART, "sap-pm", "business", False) == Decision.AUTO_ALLOW


def test_compliant_operator_keeps_trust_and_naive_agent_loses_it():
    policy = load_policy()
    # Rule-based operator is policy-aware -> requests approval -> no violations.
    good = run_scenario(baseline_factory(True), ticks=120, with_transcript=False, policy=policy)
    assert good.subscores["governance"] == 100.0
    assert good.raw["governance_violations"] == 0

    # A naive agent that just acts on alerts never asks -> unauthorized changes.
    def naive(obs):
        return [{"system": a["system"], "action": "restart", "diagnosis": "memory_leak"}
                for a in obs.get("alerts", [])]
    bad = run_scenario(lambda: AgentOperator(naive, "op-naive"), ticks=120,
                       with_transcript=False, policy=policy)
    assert bad.raw["governance_violations"] > 0
    assert bad.subscores["governance"] < good.subscores["governance"]


def test_governance_absent_without_policy():
    # No policy -> governance dimension is a perfect 100 (backward compatible).
    res = run_scenario(baseline_factory(True), ticks=60, with_transcript=False)
    assert res.subscores["governance"] == 100.0
    assert res.raw["governance_violations"] == 0
