"""Global settings: defaults, limits, validation and storage form."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import re
from typing import Any

MAX_LEVEL = 100
MAX_TARGETS = 50
# Notify services such as mobile_app_pixel_8.
TARGET = re.compile(r"[a-z0-9_]{1,100}")


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
    persistent_notifications: bool = True
    notify_targets: tuple[str, ...] = ()
    notify_recovered: bool = True
    # Times are minutes after midnight, local time.
    digest_minute: int = 18 * 60
    quiet_hours: bool = True
    quiet_start_minute: int = 22 * 60
    quiet_end_minute: int = 8 * 60


DEFAULTS = Settings()
LIMITS: dict[str, tuple[int, int]] = {
    "low_threshold": (1, 95),
    "critical_threshold": (0, 94),
    "hysteresis": (0, 20),
    "binary_recovery_minutes": (0, 1440),
    "reminder_hours": (6, 720),
    "unavailable_grace_hours": (1, 168),
    "stale_days": (1, 90),
    "digest_minute": (0, 1439),
    "quiet_start_minute": (0, 1439),
    "quiet_end_minute": (0, 1439),
}
THRESHOLD_KEYS = ("low_threshold", "critical_threshold", "hysteresis")
QUIET_KEYS = ("quiet_hours", "quiet_start_minute", "quiet_end_minute")


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
    default = getattr(DEFAULTS, key)
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise SettingsError("not_boolean", key)
        return
    if isinstance(default, tuple):
        if (
            not isinstance(value, list | tuple)
            or len(value) > MAX_TARGETS
            or len(set(value)) != len(value)
            or not all(
                isinstance(item, str) and TARGET.fullmatch(item) for item in value
            )
        ):
            raise SettingsError("invalid_targets", key)
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError("not_integer", key)
    minimum, maximum = LIMITS[key]
    if not minimum <= value <= maximum:
        raise SettingsError("out_of_range", key)


def check_combination(settings: Settings) -> None:
    """Raise SettingsError when settings contradict each other."""
    if settings.critical_threshold >= settings.low_threshold:
        raise SettingsError("critical_not_below_low", "critical_threshold")
    if settings.low_threshold + settings.hysteresis > MAX_LEVEL:
        raise SettingsError("recovery_above_maximum", "hysteresis")
    if (
        settings.quiet_hours
        and settings.quiet_start_minute == settings.quiet_end_minute
    ):
        raise SettingsError("quiet_hours_empty", "quiet_end_minute")


def _stored(key: str, value: Any) -> Any:
    """Return a validated value in the form the settings keep it."""
    return tuple(value) if isinstance(getattr(DEFAULTS, key), tuple) else value


def updated(settings: Settings, changes: Mapping[str, Any]) -> Settings:
    """Return the settings with the changes applied, validated as a whole."""
    for key, value in changes.items():
        check_value(key, value)
    result = replace(
        settings, **{key: _stored(key, value) for key, value in changes.items()}
    )
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
            values[key] = _stored(key, value)
    settings = Settings(**values)
    # Each failed rule resets its own group of settings; there are only two.
    for _ in range(2):
        try:
            check_combination(settings)
        except SettingsError as err:
            quiet = err.key in QUIET_KEYS
            problems.append("quiet_hours" if quiet else "thresholds")
            group = QUIET_KEYS if quiet else THRESHOLD_KEYS
            settings = replace(
                settings, **{key: getattr(DEFAULTS, key) for key in group}
            )
        else:
            break
    return settings, problems


def settings_to_storage(settings: Settings) -> dict[str, Any]:
    """Store only what differs from the defaults, so better defaults reach everyone."""
    return {
        key: value
        for key, value in asdict(settings).items()
        if value != getattr(DEFAULTS, key)
    }
