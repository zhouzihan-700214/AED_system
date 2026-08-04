"""Field-level optimistic concurrency checks for AED Excel updates."""
from __future__ import annotations

from typing import Any, Mapping


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def detect_field_conflicts(
    original_values: Mapping[str, Any],
    current_values: Mapping[str, Any],
    desired_values: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    safe_changes: dict[str, Any] = {}
    already_applied: dict[str, Any] = {}
    conflicts: dict[str, dict[str, str]] = {}

    for field, desired in desired_values.items():
        original = _text(original_values.get(field, ""))
        current = _text(current_values.get(field, ""))
        desired_text = _text(desired)
        if current == desired_text:
            already_applied[field] = desired
        elif current == original:
            safe_changes[field] = desired
        else:
            conflicts[field] = {
                "original": original,
                "current": current,
                "desired": desired_text,
            }

    return {
        "safe_changes": safe_changes,
        "already_applied": already_applied,
        "conflicts": conflicts,
    }
