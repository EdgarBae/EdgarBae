"""Builds a compact, replayable transcript of a harness run.

The transcript is the bridge between the Python harness (the single source of
truth) and any inspector — the browser console replays it rather than
re-implementing the simulation. It carries *codes*, not prose, so the inspector
can render every label in either language.
"""
from __future__ import annotations

from ..simulation import Simulator

# Worst-metric -> symptom code (what the *user* experiences, not the hidden cause).
_SYMPTOM_ORDER = [
    ("error_rate", 0.5, "cannot_connect"),
    ("queue", 120, "backlog"),
    ("disk", 88, "save_fails"),
    ("mem", 82, "crashes"),
    ("latency", 700, "slow"),
]


def _symptom_at(snapshot_row: list) -> str:
    # snapshot_row = [state, cpu, mem, disk, lat, err, q]
    _, cpu, mem, disk, lat, err, q = snapshot_row
    vals = {"error_rate": err, "queue": q, "disk": disk, "mem": mem, "latency": lat}
    for key, thresh, code in _SYMPTOM_ORDER:
        if vals[key] >= thresh:
            return code
    return "slow"


def build_transcript(sim: Simulator, ehs_noprev: float | None = None) -> dict:
    ent = sim.enterprise
    sys_ids = list(ent.systems.keys())
    idx = {sid: i for i, sid in enumerate(sys_ids)}

    systems = [
        {"id": s.id, "name": s.name, "layer": s.layer.value,
         "org": s.org.value, "stack": s.stack}
        for s in ent.systems.values()
    ]

    # Tickets: attach the user-visible symptom at the moment they were opened.
    tickets = []
    for t in sim.helpdesk.tickets:
        i = idx[t.system_id]
        ot = min(t.opened_tick, len(sim.metric_log) - 1)
        u = next((u for u in ent.users if u.id == t.reporter_id), None)
        is_incident = t.type.value == "incident"
        tickets.append({
            "id": t.id, "sys": t.system_id, "type": t.type.value, "prio": t.priority,
            # incidents carry the user-visible symptom; SR/CR carry a request code
            "symptom": _symptom_at(sim.metric_log[ot][i]) if is_incident else None,
            "request": t.request_code,
            "role": u.role if u else "User",
            "open": t.opened_tick, "resolved": t.resolved_tick, "assignee": t.assignee,
        })

    # Incidents: ground-truth faults (shown in the operator view as "actual cause").
    incidents = [
        {"sys": f.system_id, "kind": f.kind.value, "sev": f.severity.value,
         "origin": f.origin, "start": f.started_tick,
         "end": f.resolved_tick if f.resolved_tick is not None else len(sim.metric_log)}
        for f in sim.faults
    ]

    report = sim.ledger.report()
    return {
        "meta": {
            "seed": 7, "ticks": len(sim.metric_log), "ehs": report["ehs"],
            "ehs_noprev": ehs_noprev, "operator": sim.operator.id,
            "n_users": len(ent.users),
        },
        "systems": systems,
        "metrics": sim.metric_log,     # metrics[tick][sys_index] = [state,cpu,mem,disk,lat,err,q]
        "ehs": [round(x, 1) for x in sim.ehs_log],
        "ops": sim.event_log,           # operator commands with outcomes
        "tickets": tickets,
        "incidents": incidents,
        "subscores": report["subscores"],
        "raw": report["raw"],
    }
