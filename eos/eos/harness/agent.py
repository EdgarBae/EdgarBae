"""Operator protocol and the seam where an AI agent plugs into the harness.

The harness treats an operator as a black box with one job: look at an
:class:`Observation` and return actions. ``RuleBasedOperator`` is the built-in
baseline. ``AgentOperator`` is the adapter that lets an *external policy* — an
LLM, an MCP tool-calling agent, a human — drive the enterprise and be scored on
the exact same footing.

Plugging in an LLM looks like::

    def llm_policy(obs: dict) -> list[dict]:
        # 1. serialise `obs` into a prompt (system screens, tickets, warnings)
        # 2. let the model call tools / emit actions
        # 3. return [{"system": "sap-pm", "action": "restart",
        #             "diagnosis": "memory_leak", "rationale": "mem 92%"}]
        ...

    operator = AgentOperator(llm_policy, operator_id="op-llm")
    result = run_scenario(lambda: operator, seed=7, ticks=240)

The action dict schema is the whole contract:
    system     — system id to act on (required)
    action     — one of ActionKind values (required)
    diagnosis  — a FaultKind value for a reactive fix, or null/omitted for
                 preventive maintenance
    rationale  — free text, recorded in the transcript
"""
from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from ..domain.enums import ActionKind, FaultKind
from ..domain.organization import Enterprise
from ..engines.aging_engine import AgingEngine
from ..engines.time_engine import SimClock
from ..ops.helpdesk import HelpDesk
from ..ops.operator import Command
from .observation import Observation

Policy = Callable[[dict], list[dict]]


@runtime_checkable
class Operator(Protocol):
    """What the simulator requires of any operator, human or AI."""

    id: str

    def decide(
        self, enterprise: Enterprise, helpdesk: HelpDesk,
        aging_warnings: list[tuple[str, str]],
    ) -> list[Command]: ...

    def notify_recovered(self, system_id: str) -> None: ...


class AgentOperator:
    """Adapts an external ``policy(observation_dict) -> [action_dict]`` to an
    :class:`Operator`. This is how an LLM/MCP agent is benchmarked by the harness.
    """

    def __init__(self, policy: Policy, operator_id: str = "op-agent"):
        self.id = operator_id
        self.policy = policy
        self._aging: AgingEngine | None = None

    def bind_aging(self, aging: AgingEngine) -> None:
        """The simulator calls this so the observation can surface warnings."""
        self._aging = aging

    def decide(self, enterprise, helpdesk, aging_warnings) -> list[Command]:
        aging = self._aging or _StubAging(aging_warnings)
        obs = Observation.capture(enterprise, helpdesk, aging, _clock_of(enterprise), 0.0)
        actions = self.policy(obs.to_dict()) or []
        return [c for c in (self._parse(a, enterprise) for a in actions) if c]

    def notify_recovered(self, system_id: str) -> None:  # noqa: D401 - stateless
        pass

    @staticmethod
    def _parse(action: dict, enterprise: Enterprise) -> Command | None:
        sid = action.get("system")
        if sid not in enterprise.systems:
            return None
        try:
            act = ActionKind(action["action"])
        except (KeyError, ValueError):
            return None
        diag_raw = action.get("diagnosis")
        diag = None
        if diag_raw:
            try:
                diag = FaultKind(diag_raw)
            except ValueError:
                diag = None
        return Command(
            system_id=sid, action=act, diagnosed_kind=diag,
            rationale=action.get("rationale", "agent action"),
        )


class HumanOperator(AgentOperator):
    """A human-in-the-loop operator: actions arrive from an external queue.

    Each tick it drains ``pending`` (a list of action dicts a UI or CLI appended)
    and applies them. Demonstrates the human-vs-AI operator substitution the
    harness exists to measure.
    """

    def __init__(self, operator_id: str = "op-human"):
        self.pending: list[dict] = []
        super().__init__(self._drain, operator_id)

    def _drain(self, _obs: dict) -> list[dict]:
        actions, self.pending = self.pending, []
        return actions


class _StubAging:
    """Lets AgentOperator build an Observation from pre-computed warnings."""

    def __init__(self, warnings: list[tuple[str, str]]):
        self._w = warnings

    def warnings(self, _enterprise) -> list[tuple[str, str]]:
        return self._w


def _clock_of(enterprise: Enterprise) -> SimClock:
    # The simulator owns the real clock; when unavailable the tick is stamped
    # by the transcript layer. A zeroed clock keeps capture() total.
    return getattr(enterprise, "_clock", SimClock())
