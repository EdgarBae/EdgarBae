from eos.domain.enums import ActionKind, FaultKind, Metric, TimePhase
from eos.engines.aging_engine import (
    CERT_LIFETIME_TICKS, DISK_FULL_THRESHOLD, AgingEngine,
)
from eos.engines.chaos_engine import ChaosEngine
from eos.engines.time_engine import TICKS_PER_DAY, SimClock
from eos.enterprise_factory import build_default_enterprise


def test_clock_phases_and_load():
    clock = SimClock()
    # Tick 0 == midnight -> night, minimal load.
    assert clock.phase == TimePhase.NIGHT
    assert clock.load_factor() < 0.3
    # Advance to mid-morning business hours.
    clock.tick = 20  # 20 * 30min = 10:00
    assert clock.phase == TimePhase.BUSINESS
    assert clock.load_factor() >= 1.0


def test_month_end_amplifies_load():
    clock = SimClock()
    clock.tick = 20  # business, day 1
    normal = clock.load_factor()
    clock.tick = 29 * TICKS_PER_DAY + 20  # business, day 30 (month end)
    assert clock.is_month_end
    assert clock.load_factor() > normal


def test_chaos_is_deterministic_under_seed():
    ent1 = build_default_enterprise()
    ent2 = build_default_enterprise()
    a = ChaosEngine(seed=42, probability=1.0)
    b = ChaosEngine(seed=42, probability=1.0)
    fa = a.maybe_inject(ent1, tick=0, active_faults=[])
    fb = b.maybe_inject(ent2, tick=0, active_faults=[])
    assert [f.kind for f in fa] == [f.kind for f in fb]
    assert [f.system_id for f in fa] == [f.system_id for f in fb]


def test_chaos_skips_busy_systems():
    ent = build_default_enterprise()
    chaos = ChaosEngine(seed=1, probability=1.0)
    first = chaos.inject(next(iter(ent.systems)), FaultKind.MEMORY_LEAK, 0)
    # With every other system healthy, injection must avoid the busy one only
    # when it is the sole candidate; here just assert it never doubles up.
    injected = chaos.maybe_inject(ent, tick=1, active_faults=[first])
    assert all(f.system_id != first.system_id for f in injected)


def test_aging_spawns_disk_full_and_cert_expiry():
    ent = build_default_enterprise()
    aging = AgingEngine()
    kinds = set()
    for t in range(CERT_LIFETIME_TICKS + 60):
        for f in aging.advance(ent, t):
            kinds.add(f.kind)
    assert FaultKind.SSL_EXPIRED in kinds
    assert FaultKind.DISK_FULL in kinds


def test_preventive_action_resets_wear():
    ent = build_default_enterprise()
    aging = AgingEngine()
    sid = next(iter(ent.systems))
    for t in range(50):
        aging.advance(ent, t)
    st = aging._state(sid)
    assert st.disk_floor > 40.0
    assert aging.apply_preventive(sid, ActionKind.CLEANUP_LOGS)
    assert st.disk_floor == 40.0
    assert aging.apply_preventive(sid, ActionKind.RENEW_CERT)
    assert st.cert_ticks_left == CERT_LIFETIME_TICKS
