"""Aging engine — slow, deterministic degradation over time (PRD §10).

Unlike the Chaos engine's sudden faults, aging accumulates: disks fill with
logs, certificates march toward expiry, indexes fragment. Left unattended,
these cross thresholds and *spawn* faults. Preventive maintenance resets the
underlying counters before that happens.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import ActionKind, FaultKind, Severity
from ..domain.organization import Enterprise
from ..ops.incidents import Fault

# How many ticks a fresh certificate lasts before it expires.
CERT_LIFETIME_TICKS = 240
DISK_GROWTH_PER_TICK = 0.35
DISK_FULL_THRESHOLD = 90.0
FRAG_GROWTH_PER_TICK = 0.5
FRAG_THRESHOLD = 60.0


@dataclass
class AgingState:
    cert_ticks_left: int = CERT_LIFETIME_TICKS
    fragmentation: float = 0.0
    disk_floor: float = 40.0  # baseline disk grows from here
    cert_alerted: bool = False
    frag_alerted: bool = False


class AgingEngine:
    """Advances per-system wear and spawns faults when thresholds are crossed."""

    def __init__(self) -> None:
        self.state: dict[str, AgingState] = {}

    def _state(self, system_id: str) -> AgingState:
        return self.state.setdefault(system_id, AgingState())

    def warnings(self, enterprise: Enterprise) -> list[tuple[str, str]]:
        """(system_id, reason) pairs an operator could act on preventively."""
        out: list[tuple[str, str]] = []
        for sid in enterprise.systems:
            st = self._state(sid)
            if 0 < st.cert_ticks_left <= 40:
                out.append((sid, "certificate_expiring"))
            if st.fragmentation >= FRAG_THRESHOLD * 0.75:
                out.append((sid, "index_fragmentation"))
            if st.disk_floor >= DISK_FULL_THRESHOLD * 0.85:
                out.append((sid, "disk_filling"))
        return out

    def advance(self, enterprise: Enterprise, tick: int) -> list[Fault]:
        """Advance wear one tick; return any faults that just spawned."""
        spawned: list[Fault] = []
        for sid, system in enterprise.systems.items():
            st = self._state(sid)
            st.cert_ticks_left -= 1
            st.fragmentation += FRAG_GROWTH_PER_TICK
            st.disk_floor += DISK_GROWTH_PER_TICK
            system.baseline.disk_pct = min(99.0, st.disk_floor)

            if st.cert_ticks_left <= 0 and not st.cert_alerted:
                st.cert_alerted = True
                spawned.append(Fault(
                    FaultKind.SSL_EXPIRED, sid, tick, Severity.CRITICAL, origin="aging",
                ))
            if st.disk_floor >= DISK_FULL_THRESHOLD:
                st.disk_floor = DISK_FULL_THRESHOLD  # pin until remediated
                spawned.append(Fault(
                    FaultKind.DISK_FULL, sid, tick, Severity.HIGH, origin="aging",
                ))
            if st.fragmentation >= FRAG_THRESHOLD and not st.frag_alerted:
                st.frag_alerted = True
                spawned.append(Fault(
                    FaultKind.INDEX_FRAGMENTATION, sid, tick, Severity.LOW, origin="aging",
                ))
        return spawned

    def apply_preventive(self, system_id: str, action: ActionKind) -> bool:
        """Reset the wear counter a preventive action addresses.

        Returns True if the action was a recognised preventive measure.
        """
        st = self._state(system_id)
        if action in (ActionKind.CLEANUP_LOGS, ActionKind.ADD_DISK):
            st.disk_floor = 40.0
            return True
        if action == ActionKind.RENEW_CERT:
            st.cert_ticks_left = CERT_LIFETIME_TICKS
            st.cert_alerted = False
            return True
        if action == ActionKind.REINDEX:
            st.fragmentation = 0.0
            st.frag_alerted = False
            return True
        if action == ActionKind.PATCH:
            return True
        return False
