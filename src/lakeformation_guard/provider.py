"""Current-state provider interfaces for lfguard integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .io import load_current
from .models import CurrentState, DesiredState


class CurrentStateProvider(Protocol):
    """Provider that can load the current Lake Formation state for a desired scope."""

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        """Return current state for the resources and grants represented by desired."""


@dataclass(frozen=True)
class SnapshotCurrentStateProvider:
    """Current-state provider backed by an already loaded snapshot."""

    current: CurrentState

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        return self.current


@dataclass(frozen=True)
class SnapshotFileCurrentStateProvider:
    """Current-state provider backed by a JSON/YAML snapshot file."""

    path: str

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        return load_current(self.path)
