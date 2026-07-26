from eos.domain.enums import Metric, OrgUnit, SystemLayer, SystemState
from eos.domain.systems import Metrics, System, SystemConfig
from eos.domain.users import VirtualUser


def _system(**metrics) -> System:
    return System(
        id="s1", name="S1", layer=SystemLayer.APPLICATION, org=OrgUnit.IT,
        baseline=Metrics(), metrics=Metrics(**metrics),
    )


def test_healthy_system_is_up():
    s = _system(cpu_pct=25, mem_pct=30, latency_ms=150, error_rate=0.0)
    assert s.state() == SystemState.UP
    assert s.health() > 90


def test_high_latency_violates_sla_and_degrades():
    s = _system(latency_ms=1500)
    assert s.violates_sla()
    assert s.state() == SystemState.DEGRADED


def test_total_failure_is_down():
    s = _system(error_rate=0.95)
    assert s.state() == SystemState.DOWN
    assert s.health() < 15


def test_metrics_clamp_bounds():
    m = Metrics(cpu_pct=250, error_rate=5, disk_pct=-10)
    m.clamp()
    assert m.cpu_pct == 100
    assert m.error_rate == 1.0
    assert m.disk_pct == 0
    assert m.get(Metric.CPU) == 100


def test_impatient_user_complains_earlier():
    impatient = VirtualUser("u1", "a", "eng", "s1", OrgUnit.IT, patience=0.0)
    patient = VirtualUser("u2", "b", "eng", "s1", OrgUnit.IT, patience=1.0)
    assert impatient.complaint_threshold < patient.complaint_threshold


def test_config_clone_is_independent():
    c = SystemConfig()
    d = c.clone()
    d.instances += 5
    assert c.instances != d.instances
