"""Tool-shaped observability surface (Prometheus / logs / alerts / runbooks).

Real SRE agents (OpenSRE, Aurora, ...) read Prometheus metrics, log lines, and
Alertmanager alerts, and consult runbooks. To let such an agent run against EOS
with minimal glue — and to make skills learned here transfer to real infra —
the harness projects each system's state into those exact shapes.

Everything here is *symptom-level*: it is derived from the observable metrics an
operator can see, never from the ground-truth fault kind. RCA stays the agent's
job.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..domain.systems import SLA_ERROR_RATE, SLA_LATENCY_MS, System

# Prometheus-style metric names (mirror common exporters).
PROM_NAMES = {
    "cpu": "node_cpu_utilization_ratio",
    "mem": "jvm_heap_used_ratio",
    "disk": "node_filesystem_used_ratio",
    "latency": "http_request_duration_seconds:p95",
    "error": "http_requests_errors_ratio",
    "queue": "messaging_queue_depth",
}


@dataclass
class PromSample:
    name: str
    system: str
    layer: str
    value: float


@dataclass
class LogLine:
    tick: int
    system: str
    level: str
    message: str


@dataclass
class Alert:
    alertname: str
    severity: str      # warning | critical
    system: str
    summary: str
    metric: str


def prometheus(system: System) -> list[PromSample]:
    m = system.metrics
    vals = {
        "cpu": round(m.cpu_pct / 100, 3),
        "mem": round(m.mem_pct / 100, 3),
        "disk": round(m.disk_pct / 100, 3),
        "latency": round(m.latency_ms / 1000, 3),
        "error": round(m.error_rate, 3),
        "queue": round(m.queue_depth, 1),
    }
    return [PromSample(PROM_NAMES[k], system.id, system.layer.value, v)
            for k, v in vals.items()]


# Dominant-symptom -> synthetic log lines (cause-agnostic on purpose).
_LOG_TEMPLATES = {
    "mem": [("WARN", "GC overhead high: heap at {mem}% utilisation"),
            ("ERROR", "Allocation failure; pausing request threads")],
    "error": [("ERROR", "5xx ratio {err}; a fraction of requests are failing"),
              ("WARN", "Handshake/upstream errors observed on ingress")],
    "queue": [("WARN", "Consumer lag rising: {queue} messages pending"),
              ("ERROR", "Processing backlog exceeds threshold")],
    "disk": [("ERROR", "No space left on device: filesystem at {disk}%"),
             ("WARN", "Log/temp growth accelerating")],
    "latency": [("WARN", "Slow responses: p95={lat}ms"),
                ("ERROR", "Downstream call exceeded timeout budget")],
}


def _dominant(system: System) -> str | None:
    m = system.metrics
    if m.error_rate >= 0.5:
        return "error"
    if m.disk_pct >= 88:
        return "disk"
    if m.mem_pct >= 82:
        return "mem"
    if m.queue_depth >= 100:
        return "queue"
    if m.latency_ms > SLA_LATENCY_MS:
        return "latency"
    return None


def logs(system: System, tick: int) -> list[LogLine]:
    key = _dominant(system)
    if key is None:
        return []
    m = system.metrics
    fmt = {"mem": round(m.mem_pct), "err": round(m.error_rate, 2),
           "queue": round(m.queue_depth), "disk": round(m.disk_pct),
           "lat": round(m.latency_ms)}
    return [LogLine(tick, system.id, lvl, msg.format(**fmt))
            for lvl, msg in _LOG_TEMPLATES[key]]


def alerts(system: System) -> list[Alert]:
    m = system.metrics
    out: list[Alert] = []
    if m.error_rate > SLA_ERROR_RATE:
        out.append(Alert("HighErrorRate", "critical" if m.error_rate > 0.5 else "warning",
                         system.id, f"error ratio {m.error_rate:.2f}", PROM_NAMES["error"]))
    if m.latency_ms > SLA_LATENCY_MS:
        out.append(Alert("HighLatency", "critical" if m.latency_ms > 2000 else "warning",
                         system.id, f"p95 {round(m.latency_ms)}ms", PROM_NAMES["latency"]))
    if m.mem_pct > 85:
        out.append(Alert("HighMemory", "warning", system.id,
                         f"heap {round(m.mem_pct)}%", PROM_NAMES["mem"]))
    if m.disk_pct > 85:
        out.append(Alert("DiskPressure", "critical" if m.disk_pct > 95 else "warning",
                         system.id, f"disk {round(m.disk_pct)}%", PROM_NAMES["disk"]))
    if m.queue_depth > 100:
        out.append(Alert("QueueBacklog", "warning", system.id,
                         f"{round(m.queue_depth)} pending", PROM_NAMES["queue"]))
    return out


# Runbooks (PRD §12): documentation an operator consults. Actions are ActionKind
# values, so an agent can read a runbook and emit a valid action directly.
RUNBOOKS: dict[str, dict] = {
    "RB-MEM": {
        "title": "High memory / heap pressure",
        "triggers": ["HighMemory"],
        "checks": ["Confirm heap trend is monotonic (leak) vs spike (OOM).",
                   "Check GC pause frequency."],
        "actions": ["rolling_restart", "restart", "increase_heap"],
    },
    "RB-LATENCY": {
        "title": "High latency / slow responses",
        "triggers": ["HighLatency"],
        "checks": ["Is a single query slow (DB) or all endpoints (upstream/net)?",
                   "Check DB locks and index health."],
        "actions": ["kill_slow_query", "reindex", "failover", "scale_out", "restart"],
    },
    "RB-ERROR": {
        "title": "Elevated error rate / outage",
        "triggers": ["HighErrorRate"],
        "checks": ["Check TLS/cert validity and instance health first.",
                   "Correlate with recent deploys."],
        "actions": ["renew_certificate", "failover", "scale_out", "restart"],
    },
    "RB-DISK": {
        "title": "Disk pressure",
        "triggers": ["DiskPressure"],
        "checks": ["Identify largest growth (logs, temp, tables)."],
        "actions": ["cleanup_logs", "add_disk"],
    },
    "RB-QUEUE": {
        "title": "Queue backlog / consumer lag",
        "triggers": ["QueueBacklog"],
        "checks": ["Are workers alive? Is the producer spiking?"],
        "actions": ["flush_queue", "restart_worker", "scale_out"],
    },
}


def runbook_index() -> list[dict]:
    return [{"id": rid, "title": rb["title"], "triggers": rb["triggers"]}
            for rid, rb in RUNBOOKS.items()]


def signals(system: System, tick: int) -> dict:
    """The full tool-shaped signal bundle for one system."""
    return {
        "prometheus": [asdict(s) for s in prometheus(system)],
        "logs": [asdict(x) for x in logs(system, tick)],
        "alerts": [asdict(a) for a in alerts(system)],
    }
