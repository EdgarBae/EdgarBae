from eos.domain.enums import ActionKind, FaultKind, Metric, SystemState, TicketType
from eos.domain.systems import Metrics
from eos.engines.aging_engine import AgingEngine
from eos.enterprise_factory import build_default_enterprise
from eos.ops.helpdesk import HelpDesk
from eos.ops.incidents import FAULT_PROFILES, Fault
from eos.ops.operator import RuleBasedOperator


def test_every_fault_kind_has_a_recovery():
    for kind, profile in FAULT_PROFILES.items():
        assert profile.recoveries, f"{kind} has no recovery action"
        assert profile.signature_metric in Metric
        # A fault's effects must touch its signature metric.
        assert profile.signature_metric in profile.effects


def test_helpdesk_opens_incident_for_down_system():
    ent = build_default_enterprise()
    hd = HelpDesk()
    sid = "sap-pm"
    ent.systems[sid].metrics = Metrics(error_rate=0.95)  # DOWN
    new = hd.intake(ent, tick=5)
    assert any(t.system_id == sid and t.type == TicketType.INCIDENT for t in new)
    # No duplicate incident while one is still open.
    assert hd.intake(ent, tick=6) == []


def test_helpdesk_escalates_priority_for_outage():
    ent = build_default_enterprise()
    hd = HelpDesk()
    ent.systems["sap-pm"].metrics = Metrics(error_rate=0.95)
    ticket = hd.intake(ent, tick=0)[0]
    # Supervisor priority is 1; an outage should keep it at the top.
    assert ticket.priority == 1


def test_operator_diagnoses_memory_leak():
    op = RuleBasedOperator()
    ent = build_default_enterprise()
    system = ent.systems["sap-pm"]
    system.metrics = Metrics(mem_pct=92, latency_ms=400)
    guess, playbook = op._diagnose(system)
    assert guess == FaultKind.MEMORY_LEAK
    assert ActionKind.ROLLING_RESTART in playbook


def test_operator_acts_on_preventive_warnings():
    op = RuleBasedOperator()
    ent = build_default_enterprise()
    warnings = [("pg-core", "certificate_expiring")]
    cmds = op.decide(ent, HelpDesk(), warnings)
    assert any(
        c.action == ActionKind.RENEW_CERT and c.diagnosed_kind is None
        for c in cmds
    )
