"""Current-state provider interfaces for lfguard integrations."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol

from .io import StateFormatError, dumps_json, load_current
from .models import CurrentState, DesiredState


CURRENT_STATE_CACHE_SCHEMA_VERSION = "lfguard.current-cache.v1"


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


@dataclass(frozen=True)
class LazyCurrentStateProvider:
    """Provider that builds another provider only when current state is needed."""

    factory: Callable[[], CurrentStateProvider]

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        return self.factory().load_current_state_for(desired)


@dataclass(frozen=True)
class CachedCurrentStateProvider:
    """Read-through current-state provider backed by a JSON cache file.

    The cache is scoped to a fingerprint of the desired state passed to
    ``load_current_state_for``. If the file is missing, expired, refreshed, or
    scoped to a different desired state, the upstream provider is used and the
    cache is rewritten.
    """

    upstream: CurrentStateProvider
    path: str
    refresh: bool = False
    max_age_seconds: Optional[int] = None
    clock: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        if self.max_age_seconds is not None and self.max_age_seconds < 0:
            raise ValueError("max_age_seconds must be >= 0")

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        cache_path = Path(self.path)
        desired_fingerprint = desired_state_fingerprint(desired)
        if not self.refresh:
            cached = self._load_cached_state(cache_path, desired_fingerprint)
            if cached is not None:
                return cached
        current = self.upstream.load_current_state_for(desired)
        self._write_cached_state(cache_path, desired_fingerprint, current)
        return current

    def _load_cached_state(self, path: Path, desired_fingerprint: str) -> Optional[CurrentState]:
        if not path.exists():
            return None
        envelope = _load_cache_envelope(path)
        if envelope.get("schema_version") != CURRENT_STATE_CACHE_SCHEMA_VERSION:
            raise StateFormatError(
                "{} must contain a {} cache object".format(path, CURRENT_STATE_CACHE_SCHEMA_VERSION)
            )
        if envelope.get("desired_fingerprint") != desired_fingerprint:
            return None
        if self._is_expired(envelope):
            return None
        current = envelope.get("current")
        if not isinstance(current, Mapping):
            raise StateFormatError("{} cache entry must contain a current state object".format(path))
        return CurrentState.from_dict(current)

    def _is_expired(self, envelope: Mapping[str, Any]) -> bool:
        if self.max_age_seconds is None:
            return False
        created_at_epoch = envelope.get("created_at_epoch")
        if not isinstance(created_at_epoch, (int, float)):
            return True
        return self.clock() - float(created_at_epoch) > self.max_age_seconds

    def _write_cached_state(self, path: Path, desired_fingerprint: str, current: CurrentState) -> None:
        now = float(self.clock())
        payload = {
            "schema_version": CURRENT_STATE_CACHE_SCHEMA_VERSION,
            "created_at": _format_epoch(now),
            "created_at_epoch": now,
            "desired_fingerprint": desired_fingerprint,
            "current": current.to_dict(),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_name("{}.tmp".format(path.name))
            tmp_path.write_text(dumps_json(payload), encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            raise StateFormatError("Could not write current-state cache {}: {}".format(path, exc)) from exc


def desired_state_fingerprint(desired: DesiredState) -> str:
    """Return a stable fingerprint for the desired-state provider scope."""

    encoded = json.dumps(desired.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_cache_envelope(path: Path) -> Mapping[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StateFormatError("Could not read current-state cache {}: {}".format(path, exc)) from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise StateFormatError("Could not parse current-state cache {}: {}".format(path, exc)) from exc
    if not isinstance(data, Mapping):
        raise StateFormatError("{} must contain a JSON object".format(path))
    return data


def _format_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
