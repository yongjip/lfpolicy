"""Current-state provider interfaces for lfpolicy integrations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol

from .io import StateFormatError, dumps_json, load_current
from .models import CurrentState, DesiredState


CURRENT_STATE_CACHE_SCHEMA_VERSION = "lfpolicy.current-cache.v1"


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

    The cache is scoped to both a fingerprint of the desired state passed to
    ``load_current_state_for`` and a provider context. If the file is missing,
    expired, refreshed, or scoped to a different desired state/provider context,
    the upstream provider is used and the cache is rewritten.

    Use ``for_aws(...)`` for live AWS providers. For custom providers, pass a
    ``provider_context`` that identifies the source environment; the empty
    default is intended only for provider-independent snapshots or tests.
    """

    upstream: CurrentStateProvider
    path: str
    refresh: bool = False
    max_age_seconds: Optional[int] = None
    clock: Callable[[], float] = time.time
    provider_context: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def for_aws(
        cls,
        upstream: CurrentStateProvider,
        path: str,
        *,
        profile_name: Optional[str] = None,
        region_name: Optional[str] = None,
        catalog_id: Optional[str] = None,
        refresh: bool = False,
        max_age_seconds: Optional[int] = None,
        clock: Callable[[], float] = time.time,
    ) -> "CachedCurrentStateProvider":
        """Create a cache provider scoped to the default AWS Lake Formation context."""

        return cls(
            upstream,
            path,
            refresh=refresh,
            max_age_seconds=max_age_seconds,
            clock=clock,
            provider_context=aws_current_state_provider_context(
                profile_name=profile_name,
                region_name=region_name,
                catalog_id=catalog_id,
            ),
        )

    def __post_init__(self) -> None:
        if self.max_age_seconds is not None and self.max_age_seconds < 0:
            raise ValueError("max_age_seconds must be >= 0")

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        cache_path = Path(self.path)
        desired_fingerprint = desired_state_fingerprint(desired)
        provider_fingerprint = provider_context_fingerprint(self.provider_context)
        if not self.refresh:
            cached = self._load_cached_state(cache_path, desired_fingerprint, provider_fingerprint)
            if cached is not None:
                return cached
        current = self.upstream.load_current_state_for(desired)
        self._write_cached_state(cache_path, desired_fingerprint, provider_fingerprint, current)
        return current

    def _load_cached_state(
        self,
        path: Path,
        desired_fingerprint: str,
        provider_fingerprint: str,
    ) -> Optional[CurrentState]:
        if not path.exists():
            return None
        envelope = _load_cache_envelope(path)
        if envelope.get("schema_version") != CURRENT_STATE_CACHE_SCHEMA_VERSION:
            raise StateFormatError(
                "{} must contain a {} cache object".format(path, CURRENT_STATE_CACHE_SCHEMA_VERSION)
            )
        if envelope.get("desired_fingerprint") != desired_fingerprint:
            return None
        if envelope.get("provider_fingerprint") != provider_fingerprint:
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

    def _write_cached_state(
        self,
        path: Path,
        desired_fingerprint: str,
        provider_fingerprint: str,
        current: CurrentState,
    ) -> None:
        now = float(self.clock())
        payload = {
            "schema_version": CURRENT_STATE_CACHE_SCHEMA_VERSION,
            "created_at": _format_epoch(now),
            "created_at_epoch": now,
            "desired_fingerprint": desired_fingerprint,
            "provider_fingerprint": provider_fingerprint,
            "provider_context": _normalize_json(self.provider_context),
            "current": current.to_dict(),
        }
        tmp_path: Optional[Path] = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix="{}.tmp.".format(path.name),
                delete=False,
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(dumps_json(payload))
            tmp_path.replace(path)
        except OSError as exc:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise StateFormatError("Could not write current-state cache {}: {}".format(path, exc)) from exc


def aws_current_state_provider_context(
    *,
    profile_name: Optional[str] = None,
    region_name: Optional[str] = None,
    catalog_id: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Mapping[str, Any]:
    """Return a stable cache context for AWS Lake Formation current-state providers."""

    env = os.environ if environ is None else environ
    return {
        "provider": "aws-lakeformation",
        "profile": _context_value(
            profile_name,
            env.get("AWS_PROFILE"),
            env.get("AWS_DEFAULT_PROFILE"),
            default="__default__",
        ),
        "region": _context_value(
            region_name,
            env.get("AWS_REGION"),
            env.get("AWS_DEFAULT_REGION"),
            default="__default__",
        ),
        "catalog_id": _context_value(catalog_id),
    }


def desired_state_fingerprint(desired: DesiredState) -> str:
    """Return a stable fingerprint for the desired-state provider scope."""

    return _json_fingerprint(desired.to_dict())


def provider_context_fingerprint(context: Mapping[str, Any]) -> str:
    """Return a stable fingerprint for the upstream current-state provider context."""

    return _json_fingerprint(_normalize_json(context))


def _json_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _context_value(*values: Optional[str], default: Optional[str] = None) -> Optional[str]:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return default


def _normalize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_json(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, set):
        return [_normalize_json(item) for item in sorted(value, key=str)]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


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
