"""Global settings: defaults, limits, validation and storage form."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

MAX_LEVEL = 100


@dataclass(frozen=True, slots=True)
class Settings:
    """How Battery Care watches batteries, unless a device says otherwise."""

    alerts_enabled: bool = True
    low_threshold: int = 20
    critical_threshold: int = 10
    hysteresis: int = 5
    binary_recovery_minutes: int = 60
    reminder_hours: int = 24
    unavailable_alerts: bool = True
    unavailable_grace_hours: int = 24
    stale_detection: bool = True
    stale_days: int = 7


DEFAULTS = Settings()
LIMITS: dict[str, tuple[int, int]] = {
    "low_threshold": (1, 95),
    "critical_threshold": (0, 94),
    "hysteresis": (0, 20),
    "binary_recovery_minutes": (0, 1440),
    "reminder_hours": (6, 720),
    "unavailable_grace_hours": (1, 168),
    "stale_days": (1, 90),
}
THRESHOLD_KEYS = ("low_threshold", "critical_threshold", "hysteresis")


class SettingsError(ValueError):
    """A setting, or a combination of settings, is not allowed."""

    def __init__(self, code: str, key: str) -> None:
        """Keep a stable code for translated messages, and the key at fault."""
        super().__init__(f"{key}: {code}")
        self.code = code
        self.key = key


def check_value(key: str, value: object) -> None:
    """Raise SettingsError unless the value is allowed for this setting."""
    if not hasattr(DEFAULTS, key):
        raise SettingsError("unknown_setting", key)
    if isinstance(getattr(DEFAULTS, key), bool):
        if not isinstance(value, bool):
            raise SettingsError("not_boolean", key)
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError("not_integer", key)
    minimum, maximum = LIMITS[key]
    if not minimum <= value <= maximum:
        raise SettingsError("out_of_range", key)


def check_combination(settings: Settings) -> None:
    """Raise SettingsError when the thresholds contradict each other."""
    if settings.critical_threshold >= settings.low_threshold:
        raise SettingsError("critical_not_below_low", "critical_threshold")
    if settings.low_threshold + settings.hysteresis > MAX_LEVEL:
        raise SettingsError("recovery_above_maximum", "hysteresis")


def updated(settings: Settings, changes: Mapping[str, Any]) -> Settings:
    """Return the settings with the changes applied, validated as a whole."""
    for key, value in changes.items():
        check_value(key, value)
    result = replace(settings, **changes)
    check_combination(result)
    return result


def settings_from_storage(raw: object) -> tuple[Settings, list[str]]:
    """Rebuild settings from storage; anything invalid falls back to its default.

    Returns:
        The settings, and the names of the values that were ignored.
    """
    problems: list[str] = []
    if raw is None:
        raw = {}
    elif not isinstance(raw, Mapping):
        return DEFAULTS, ["*"]
    values = asdict(DEFAULTS)
    for key, value in raw.items():
        try:
            check_value(key, value)
        except SettingsError:
            problems.append(str(key))
        else:
            values[key] = value
    settings = Settings(**values)
    try:
        check_combination(settings)
    except SettingsError:
        problems.append("thresholds")
        settings = replace(
            settings, **{key: getattr(DEFAULTS, key) for key in THRESHOLD_KEYS}
        )
    return settings, problems


def settings_to_storage(settings: Settings) -> dict[str, Any]:
    """Store only what differs from the defaults, so better defaults reach everyone."""
    return {
        key: value
        for key, value in asdict(settings).items()
        if value != getattr(DEFAULTS, key)
    }
