"""The Enterprise aggregate — systems, users, and their relationships."""
from __future__ import annotations

from dataclasses import dataclass, field

from .systems import System
from .users import VirtualUser


@dataclass
class Enterprise:
    """A virtual enterprise: a graph of systems plus the users who rely on them."""

    name: str
    systems: dict[str, System] = field(default_factory=dict)
    users: list[VirtualUser] = field(default_factory=list)

    def add_system(self, system: System) -> System:
        self.systems[system.id] = system
        return system

    def add_user(self, user: VirtualUser) -> VirtualUser:
        self.users.append(user)
        return user

    def users_of(self, system_id: str) -> list[VirtualUser]:
        return [u for u in self.users if u.system_id == system_id]

    def dependents_of(self, system_id: str) -> list[System]:
        """Systems that declare a dependency on ``system_id``."""
        return [s for s in self.systems.values() if system_id in s.depends_on]
