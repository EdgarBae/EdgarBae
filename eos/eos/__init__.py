"""Enterprise Operations Simulator (EOS) — Phase 1 MVP.

A virtual enterprise you can run through time, break with chaos and aging,
and hand to an operator (rule-based today, LLM-driven tomorrow) whose
performance is scored by an Enterprise Health Score.
"""
from __future__ import annotations

from .domain.organization import Enterprise
from .enterprise_factory import build_default_enterprise
from .metrics.health import HealthLedger
from .ops.operator import RuleBasedOperator
from .simulation import Simulator

__all__ = [
    "Enterprise",
    "build_default_enterprise",
    "HealthLedger",
    "RuleBasedOperator",
    "Simulator",
]

__version__ = "0.1.0"
