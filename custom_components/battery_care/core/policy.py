"""Per-device choices and the settings that result for each device."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from .models import BatteryClass, BatteryDevice, Importance
from .settings import Settings, SettingsError, check_combination, check_value


class DeviceMode(StrEnum):
    """How a device follows the global settings."""

    AUTOMATIC = "automatic"
    CUSTOM = "custom"
    IGNORED = "ignored"


OVERRIDABLE = frozenset(
    {
        "alerts_enabled",
        "critical_threshold",
        "low_threshold",
        "reminder_hours",
        "stale_days",
        "stale_detection",
        "unavailable_alerts",
        "unavailable_grace_hours",
    }
)
# Charging is part of using these devices; alerts are opt-in for them.
QUIET_CLASSES = frozenset({BatteryClass.NOT_MAINTAINED, BatteryClass.RECHARGEABLE})


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    """What the user chose for one device; empty means fully automatic."""

    mode: DeviceMode = DeviceMode.AUTOMATIC
    overrides: dict[str, Any] = field(default_factory=dict)
    importance: Importance | None = None
    battery_class: BatteryClass | None = None

    @property
    def is_default(self) -> bool:
        """Return whether nothing differs from the automatic behaviour."""
        return self == DeviceConfig()


AUTOMATIC = DeviceConfig()


def battery_class(device: BatteryDevice, config: DeviceConfig) -> BatteryClass:
    """Return the class the user chose, or the detected one."""
    return config.battery_class or device.battery_class


def importance(device: BatteryDevice, config: DeviceConfig) -> Importance:
    """Return the importance the user chose, or the suggested one."""
    return config.importance or device.suggested_importance


def automatic_settings(settings: Settings, chosen_class: BatteryClass) -> Settings:
    """Return the global settings as they apply to a device of this class."""
    if chosen_class in QUIET_CLASSES:
        return replace(settings, alerts_enabled=False)
    return settings


def effective_settings(
    settings: Settings, device: BatteryDevice, config: DeviceConfig
) -> Settings:
    """Return the settings the alert engine applies to this device."""
    base = automatic_settings(settings, battery_class(device, config))
    if config.mode is DeviceMode.IGNORED:
        return replace(base, alerts_enabled=False)
    if config.mode is DeviceMode.AUTOMATIC or not config.overrides:
        return base
    merged = replace(base, **config.overrides)
    if not settings.alerts_enabled:
        merged = replace(merged, alerts_enabled=False)
    try:
        check_combination(merged)
    except SettingsError:
        # A later global change can contradict a device's pair: use the global one.
        merged = replace(
            merged,
            low_threshold=base.low_threshold,
            critical_threshold=base.critical_threshold,
        )
    return merged


def check_override(key: str, value: object) -> None:
    """Raise SettingsError unless a device may override this setting so."""
    if key not in OVERRIDABLE:
        raise SettingsError("not_overridable", key)
    check_value(key, value)


def make_config(
    settings: Settings,
    device: BatteryDevice,
    *,
    mode: DeviceMode,
    overrides: Mapping[str, Any] | None = None,
    chosen_importance: Importance | None = None,
    chosen_class: BatteryClass | None = None,
) -> DeviceConfig:
    """Validate a device configuration and keep only the overrides that matter."""
    overrides = dict(overrides or {})
    if overrides and mode is not DeviceMode.CUSTOM:
        raise SettingsError("overrides_need_custom_mode", "overrides")
    for key, value in overrides.items():
        check_override(key, value)
    base = automatic_settings(settings, chosen_class or device.battery_class)
    check_combination(replace(base, **overrides))
    return DeviceConfig(
        mode=mode,
        overrides={
            key: value
            for key, value in overrides.items()
            if getattr(base, key) != value
        },
        importance=chosen_importance,
        battery_class=chosen_class,
    )


def config_from_storage(raw: object) -> tuple[DeviceConfig, list[str]]:
    """Rebuild a device configuration, dropping whatever is invalid.

    Returns:
        The configuration, and the names of the values that were ignored.
    """
    if not isinstance(raw, Mapping):
        return AUTOMATIC, ["*"]
    problems: list[str] = []

    def enum_value[E: StrEnum](enum: type[E], name: str) -> E | None:
        value = raw.get(name)
        if value is None:
            return None
        try:
            return enum(value)
        except ValueError:
            problems.append(name)
            return None

    mode = enum_value(DeviceMode, "mode") or DeviceMode.AUTOMATIC
    overrides: dict[str, Any] = {}
    stored = raw.get("overrides") or {}
    if not isinstance(stored, Mapping):
        problems.append("overrides")
        stored = {}
    for key, value in stored.items():
        try:
            check_override(str(key), value)
        except SettingsError:
            problems.append(f"overrides.{key}")
        else:
            overrides[key] = value
    config = DeviceConfig(
        mode=mode,
        overrides=overrides if mode is DeviceMode.CUSTOM else {},
        importance=enum_value(Importance, "importance"),
        battery_class=enum_value(BatteryClass, "battery_class"),
    )
    return config, problems


def config_to_storage(config: DeviceConfig) -> dict[str, Any]:
    """Return the storage form of a device configuration."""
    stored: dict[str, Any] = {"mode": config.mode.value}
    if config.overrides:
        stored["overrides"] = dict(config.overrides)
    if config.importance is not None:
        stored["importance"] = config.importance.value
    if config.battery_class is not None:
        stored["battery_class"] = config.battery_class.value
    return stored
