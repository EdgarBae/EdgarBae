from eos.domain.enums import OrgUnit, SystemLayer
from eos.domain.systems import Metrics, System
from eos.harness import observability as obs


def _sys(**metrics) -> System:
    return System(id="s1", name="S1", layer=SystemLayer.APPLICATION,
                  org=OrgUnit.IT, metrics=Metrics(**metrics))


def test_prometheus_has_canonical_names_and_ratios():
    samples = obs.prometheus(_sys(cpu_pct=50, mem_pct=80))
    names = {s.name for s in samples}
    assert "node_cpu_utilization_ratio" in names
    assert "jvm_heap_used_ratio" in names
    cpu = next(s for s in samples if s.name == "node_cpu_utilization_ratio")
    assert cpu.value == 0.5  # percent -> ratio


def test_alerts_fire_on_threshold_only():
    assert obs.alerts(_sys(cpu_pct=20, mem_pct=30, latency_ms=100)) == []
    firing = obs.alerts(_sys(mem_pct=92, latency_ms=1500, error_rate=0.6))
    names = {a.alertname for a in firing}
    assert {"HighMemory", "HighLatency", "HighErrorRate"} <= names
    assert any(a.severity == "critical" for a in firing)


def test_logs_are_symptom_based_not_cause_labelled():
    lines = obs.logs(_sys(mem_pct=92), tick=5)
    assert lines and all(l.system == "s1" for l in lines)
    # Must not leak the ground-truth fault kind name.
    text = " ".join(l.message.lower() for l in lines)
    for kind in ("memory_leak", "jvm_oom", "ssl_expired"):
        assert kind not in text


def test_runbooks_actions_are_valid_action_kinds():
    from eos.domain.enums import ActionKind
    valid = {a.value for a in ActionKind}
    for rb in obs.RUNBOOKS.values():
        assert rb["actions"] and all(a in valid for a in rb["actions"])
    assert len(obs.runbook_index()) == len(obs.RUNBOOKS)


def test_observation_exposes_tool_shaped_surface():
    from eos.enterprise_factory import build_default_enterprise
    from eos.engines.aging_engine import AgingEngine
    from eos.engines.time_engine import SimClock
    from eos.harness.observation import Observation
    from eos.ops.helpdesk import HelpDesk
    ent = build_default_enterprise()
    ent.systems["sap-pm"].metrics = Metrics(mem_pct=93, latency_ms=1600)
    o = Observation.capture(ent, HelpDesk(), AgingEngine(), SimClock(), 0.0).to_dict()
    assert o["prometheus"] and o["alerts"] and o["runbooks"]
    assert any(a["system"] == "sap-pm" for a in o["alerts"])
