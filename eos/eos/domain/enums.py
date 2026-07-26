"""Core enumerations shared across the EOS domain model."""
from __future__ import annotations

from enum import Enum


class OrgUnit(str, Enum):
    """Virtual enterprise organizational units (from PRD §3)."""

    PURCHASING = "purchasing"
    PRODUCTION = "production"
    MAINTENANCE = "maintenance"
    SHE = "she"  # Safety, Health, Environment
    MANAGEMENT = "management_support"
    IT = "it"
    DX = "dx"


class SystemLayer(str, Enum):
    """Layer of the reference architecture (PRD §4).

    Users -> Web -> Application -> Database, optionally linked via EAI.
    """

    WEB = "web"
    APPLICATION = "application"
    DATABASE = "database"
    INTEGRATION = "integration"
    INFRASTRUCTURE = "infrastructure"
    OBSERVABILITY = "observability"
    SECURITY = "security"


class SystemState(str, Enum):
    """Coarse operational state of a system, derived from its metrics."""

    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"


class Metric(str, Enum):
    """The observable signals every system exposes."""

    CPU = "cpu_pct"
    MEMORY = "mem_pct"
    DISK = "disk_pct"
    LATENCY = "latency_ms"
    ERROR_RATE = "error_rate"
    QUEUE_DEPTH = "queue_depth"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> float:
        return {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}[self.value]


class FaultKind(str, Enum):
    """Failure modes the Chaos and Aging engines can inject (PRD §9, §10)."""

    MEMORY_LEAK = "memory_leak"
    JVM_OOM = "jvm_oom"
    QUEUE_OVERFLOW = "queue_overflow"
    SSL_EXPIRED = "ssl_expired"
    WORKER_DOWN = "worker_down"
    SLOW_QUERY = "slow_query"
    NETWORK_DELAY = "network_delay"
    EC2_FAILURE = "ec2_failure"
    DISK_FULL = "disk_full"
    API_TIMEOUT = "api_timeout"
    DB_LOCK = "db_lock"
    INDEX_FRAGMENTATION = "index_fragmentation"


class ActionKind(str, Enum):
    """Configuration / recovery actions an operator can perform (PRD §8)."""

    RESTART = "restart"
    ROLLING_RESTART = "rolling_restart"
    SCALE_OUT = "scale_out"
    INCREASE_HEAP = "increase_heap"
    INCREASE_POOL = "increase_connection_pool"
    CLEAR_CACHE = "clear_cache"
    FLUSH_QUEUE = "flush_queue"
    RENEW_CERT = "renew_certificate"
    KILL_SLOW_QUERY = "kill_slow_query"
    REINDEX = "reindex"
    CLEANUP_LOGS = "cleanup_logs"
    ADD_DISK = "add_disk"
    RESTART_WORKER = "restart_worker"
    FAILOVER = "failover"
    PATCH = "patch"


class TicketType(str, Enum):
    INCIDENT = "incident"
    SERVICE_REQUEST = "service_request"
    CHANGE_REQUEST = "change_request"


class TicketState(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"


class TimePhase(str, Enum):
    """Phase of the simulated working day (PRD §11)."""

    NIGHT = "night"
    MORNING = "morning"
    BUSINESS = "business"
    LUNCH = "lunch"
    EVENING = "evening"
