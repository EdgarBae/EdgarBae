from eos.engines.chaos_engine import ChaosEngine
from eos.enterprise_factory import build_default_enterprise
from eos.metrics.health import EHS_WEIGHTS
from eos.ops.operator import RuleBasedOperator
from eos.simulation import Simulator


def _run(seed=7, ticks=240, preventive=True, chaos_p=0.08):
    ent = build_default_enterprise()
    op = RuleBasedOperator(preventive=preventive)
    chaos = ChaosEngine(seed=seed, probability=chaos_p)
    sim = Simulator(ent, operator=op, chaos=chaos, seed=seed)
    sim.run(ticks)
    return sim


def test_weights_sum_to_one():
    assert abs(sum(EHS_WEIGHTS.values()) - 1.0) < 1e-9


def test_simulation_runs_and_scores_in_range():
    sim = _run()
    report = sim.ledger.report()
    assert 0.0 <= report["ehs"] <= 100.0
    for name, value in report["subscores"].items():
        assert 0.0 <= value <= 100.0, f"{name}={value} out of range"
    assert sim.ledger.ticks == 240
    assert len(sim.history) == 240


def test_simulation_is_reproducible():
    a = _run(seed=11).ledger.report()
    b = _run(seed=11).ledger.report()
    assert a == b


def test_preventive_maintenance_improves_health():
    with_prev = _run(preventive=True, ticks=300).ledger.ehs()
    without = _run(preventive=False, ticks=300).ledger.ehs()
    assert with_prev > without


def test_quiet_enterprise_stays_healthy():
    # No chaos, preventive on -> availability should be near perfect.
    sim = _run(chaos_p=0.0, ticks=200)
    subs = sim.ledger.subscores()
    assert subs["availability"] > 95.0
    assert subs["preventive"] == 100.0


def test_recovery_attempts_are_scored():
    sim = _run(seed=7, chaos_p=0.15, ticks=240)
    raw = sim.ledger.report()["raw"]
    assert raw["recovery_attempts"] > 0
    assert raw["rca_attempts"] > 0
