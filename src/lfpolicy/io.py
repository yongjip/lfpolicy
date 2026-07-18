"""File IO helpers for guardrail state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Type, TypeVar

from .models import CurrentState, DesiredState, GuardrailState


TState = TypeVar("TState", bound=GuardrailState)


class StateFormatError(ValueError):
    """Raised when a desired/current state file cannot be parsed."""


def load_desired(path: str) -> DesiredState:
    return load_state(Path(path), DesiredState)


def load_current(path: str) -> CurrentState:
    return load_state(Path(path), CurrentState)


def load_state(path: Path, state_type: Type[TState]) -> TState:
    raw = _load_mapping(path)
    return state_type.from_dict(raw)


def _load_mapping(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StateFormatError("Could not read {}: {}".format(path, exc)) from exc

    suffix = path.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            data = _load_yaml(text, path)
        else:
            data = json.loads(text)
    except ValueError as exc:
        raise StateFormatError("Could not parse {}: {}".format(path, exc)) from exc

    if not isinstance(data, Mapping):
        raise StateFormatError("{} must contain a JSON/YAML object".format(path))
    return data


def _load_yaml(text: str, path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise StateFormatError(
            "{} is YAML, but PyYAML is not installed. Install lfpolicy[yaml].".format(path)
        ) from exc
    return yaml.safe_load(text)


def dumps_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def dumps_yaml(data: Any) -> str:
    try:
        import yaml  # type: ignore
    except ImportError:
        return "\n".join(_dump_simple_yaml_lines(data)) + "\n"
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def _dump_simple_yaml_lines(value: Any, *, indent: int = 0) -> list:
    prefix = " " * indent
    if isinstance(value, Mapping):
        lines = []
        for key, item in value.items():
            rendered_key = _yaml_scalar(key)
            if isinstance(item, (Mapping, list, tuple)):
                lines.append("{}{}:".format(prefix, rendered_key))
                lines.extend(_dump_simple_yaml_lines(item, indent=indent + 2))
            else:
                lines.append("{}{}: {}".format(prefix, rendered_key, _yaml_scalar(item)))
        return lines
    if isinstance(value, (list, tuple)):
        lines = []
        for item in value:
            if isinstance(item, Mapping):
                items = list(item.items())
                if not items:
                    lines.append("{}- {{}}".format(prefix))
                    continue
                first_key, first_value = items[0]
                rendered_key = _yaml_scalar(first_key)
                if isinstance(first_value, (Mapping, list, tuple)):
                    lines.append("{}- {}:".format(prefix, rendered_key))
                    lines.extend(_dump_simple_yaml_lines(first_value, indent=indent + 4))
                else:
                    lines.append("{}- {}: {}".format(prefix, rendered_key, _yaml_scalar(first_value)))
                for key, item_value in items[1:]:
                    rendered_key = _yaml_scalar(key)
                    if isinstance(item_value, (Mapping, list, tuple)):
                        lines.append("{}  {}:".format(prefix, rendered_key))
                        lines.extend(_dump_simple_yaml_lines(item_value, indent=indent + 4))
                    else:
                        lines.append("{}  {}: {}".format(prefix, rendered_key, _yaml_scalar(item_value)))
            elif isinstance(item, (list, tuple)):
                lines.append("{}-".format(prefix))
                lines.extend(_dump_simple_yaml_lines(item, indent=indent + 2))
            else:
                lines.append("{}- {}".format(prefix, _yaml_scalar(item)))
        return lines
    return ["{}{}".format(prefix, _yaml_scalar(value))]


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if (
        not text
        or text.strip() != text
        or text.lower() in {"false", "null", "true"}
        or any(token in text for token in (": ", "#", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "%", "@", "`"))
    ):
        return json.dumps(text)
    return text
