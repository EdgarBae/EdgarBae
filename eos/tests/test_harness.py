from eos.domain.enums import TicketType
from eos.harness.agent import AgentOperator, HumanOperator, Operator
from eos.harness.evaluator import baseline_factory, benchmark, run_scenario
from eos.harness.observation import Observation
from eos.ops.operator import RuleBasedOperator


def test_rule_based_operator_satisfies_protocol():
    assert isinstance(RuleBasedOperator(), Operator)
    assert isinstance(AgentOperator(lambda o: []), Operator)


def test_run_scenario_produces_score_and_transcript():
    res = run_scenario(baseline_factory(True), seed=7, ticks=120)
    assert 0 <= res.ehs <= 100
    t = res.transcript
    assert len(t["metrics"]) == 120
    assert len(t["systems"]) == 13
    assert len(t["ehs"]) == 120
    assert t["meta"]["operator"] == "op-generalist"


def test_transcript_has_service_and_incident_tickets():
    t = run_scenario(baseline_factory(True), seed=7, ticks=240).transcript
    types = {tk["type"] for tk in t["tickets"]}
    assert "incident" in types
    assert "service_request" in types
    # incidents carry a symptom; requests carry a request code
    for tk in t["tickets"]:
        if tk["type"] == "incident":
            assert tk["symptom"] and tk["request"] is None
        else:
            assert tk["request"] and tk["symptom"] is None


def test_agent_operator_runs_and_is_scored():
    def policy(obs):
        return [
            {"system": s["id"], "action": "restart", "diagnosis": "memory_leak"}
            for s in obs["systems"] if s["state"] != "up"
        ]
    res = run_scenario(lambda: AgentOperator(policy, "op-x"), ticks=120)
    assert res.operator_id == "op-x"
    assert 0 <= res.ehs <= 100


def test_benchmark_ranks_preventive_above_neglect():
    table = benchmark({
        "prev": baseline_factory(True),
        "noprev": baseline_factory(False),
    }, ticks=240)
    names = [n for n, _ in table]
    assert names[0] == "prev"  # best first
    assert dict(table)["prev"] > dict(table)["noprev"]


def test_observation_hides_ground_truth_fault():
    # An Observation must expose symptoms but never the fault kind.
    res = run_scenario(baseline_factory(True), ticks=60)
    # Capture is exercised via AgentOperator; ensure the schema has no 'fault'.
    from eos.enterprise_factory import build_default_enterprise
    from eos.engines.aging_engine import AgingEngine
    from eos.engines.time_engine import SimClock
    from eos.ops.helpdesk import HelpDesk
    obs = Observation.capture(build_default_enterprise(), HelpDesk(),
                              AgingEngine(), SimClock(), 0.0).to_dict()
    assert "systems" in obs and "tickets" in obs
    for s in obs["systems"]:
        assert "fault" not in s and "kind" not in s
        assert set(s["metrics"]) == {"cpu", "mem", "disk", "latency_ms", "error_rate", "queue"}


def test_human_operator_drains_pending_actions():
    op = HumanOperator()
    op.pending.append({"system": "sap-pm", "action": "restart", "diagnosis": "memory_leak"})
    assert op._drain({}) and op.pending == []
