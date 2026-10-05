"""What Battery Care remembers about each battery device between evaluations."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from .timestamps import format_time, parse_time

MAX_LEVEL = 100
TIMES = (
    "low_off_since",
    "unavailable_since",
    "evidence_at",
    "snoozed_until",
    "acknowledged_at",
    "next_reminder_at",
)
FLAGS = ("last_low", "not_responding", "stale")


class Severity(StrEnum):
    """How urgently a battery needs replacing or charging."""

    NORMAL = "normal"
    LOW = "low"
    CRITICAL = "critical"


RANK = {Severity.NORMAL: 0, Severity.LOW: 1, Severity.CRITICAL: 2}


@dataclass(frozen=True, slots=True)
class Runtime:
    """The alert engine's memory of one device; the defaults describe a new one."""

    severity: Severity = Severity.NORMAL
    last_level: float | None = None
    last_low: bool | None = None
    # When the low flag turned off; it still counts until the recovery delay ends.
    low_off_since: datetime | None = None
    unavailable_since: datetime | None = None
    not_responding: bool = False
    # The latest sign of life, or when Battery Care started watching.
    evidence_at: datetime | None = None
    stale: bool = False
    snoozed_until: datetime | None = None
    acknowledged_at: datetime | None = None
    next_reminder_at: datetime | None = None


def runtime_to_storage(runtime: Runtime) -> dict[str, Any]:
    """Return the storage form of a runtime state, without its empty values."""
    stored: dict[str, Any] = {"severity": runtime.severity.value}
    if runtime.last_level is not None:
        stored["last_level"] = runtime.last_level
    for name in FLAGS:
        if (flag := getattr(runtime, name)) is not None:
            stored[name] = flag
    for name in TIMES:
        if (time := format_time(getattr(runtime, name))) is not None:
            stored[name] = time
    return stored


def runtime_from_storage(raw: object) -> tuple[Runtime, list[str]]:
    """Rebuild a runtime state; an invalid value falls back to its default.

    Returns:
        The runtime state, and the names of the values that were ignored.
    """
    if not isinstance(raw, Mapping):
        return Runtime(), ["*"]
    problems: list[str] = []
    values: dict[str, Any] = {}
    for name, parse in PARSERS.items():
        if (value := raw.get(name)) is None:
            continue
        if (parsed := parse(value)) is None:
            problems.append(name)
        else:
            values[name] = parsed
    return Runtime(**values), problems


def _severity(value: object) -> Severity | None:
    if not isinstance(value, str):
        return None
    try:
        return Severity(value)
    except ValueError:
        return None


def _level(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    # NaN fails both comparisons.
    return float(value) if 0 <= value <= MAX_LEVEL else None


def _flag(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


PARSERS: dict[str, Callable[[object], object]] = {
    "severity": _severity,
    "last_level": _level,
    **dict.fromkeys(FLAGS, _flag),
    **dict.fromkeys(TIMES, parse_time),
}
