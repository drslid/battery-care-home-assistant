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
CLASS_KEYS = frozenset({"alerts_enabled", "critical_threshold", "low_threshold"})
# Built-in defaults of each class, over the global settings (D-007).
CLASS_DEFAULTS: dict[BatteryClass, dict[str, Any]] = {
    BatteryClass.RECHARGEABLE: {"alerts_enabled": False},
    BatteryClass.ROBOT: {"alerts_enabled": False},
    BatteryClass.VEHICLE: {"alerts_enabled": False},
    BatteryClass.UPS: {"low_threshold": 50, "critical_threshold": 20},
    BatteryClass.HOME_BATTERY: {
        "alerts_enabled": False,
        "low_threshold": 10,
        "critical_threshold": 5,
    },
}

type ClassChoices = Mapping[BatteryClass, Mapping[str, Any]]


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


def class_settings(
    settings: Settings, chosen_class: BatteryClass, classes: ClassChoices
) -> Settings:
    """Return the settings of a class: global, then built-in, then the user's."""
    builtin = replace(settings, **CLASS_DEFAULTS.get(chosen_class, {}))
    merged = replace(builtin, **classes.get(chosen_class, {}))
    if not settings.alerts_enabled:
        merged = replace(merged, alerts_enabled=False)
    return _keep_valid_thresholds(merged, builtin)


def _keep_valid_thresholds(settings: Settings, fallback: Settings) -> Settings:
    """Use the fallback pair when a later change made the thresholds contradict."""
    try:
        check_combination(settings)
    except SettingsError:
        return replace(
            settings,
            low_threshold=fallback.low_threshold,
            critical_threshold=fallback.critical_threshold,
        )
    return settings


def effective_settings(
    settings: Settings,
    device: BatteryDevice,
    config: DeviceConfig,
    classes: ClassChoices,
) -> Settings:
    """Return the settings the alert engine applies to this device."""
    base = class_settings(settings, battery_class(device, config), classes)
    if config.mode is DeviceMode.IGNORED:
        return replace(base, alerts_enabled=False)
    if config.mode is DeviceMode.AUTOMATIC or not config.overrides:
        return base
    merged = replace(base, **config.overrides)
    if not settings.alerts_enabled:
        merged = replace(merged, alerts_enabled=False)
    return _keep_valid_thresholds(merged, base)


def check_override(key: str, value: object) -> None:
    """Raise SettingsError unless a device may override this setting so."""
    if key not in OVERRIDABLE:
        raise SettingsError("not_overridable", key)
    check_value(key, value)


def make_config(
    settings: Settings,
    device: BatteryDevice,
    classes: ClassChoices,
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
    base = class_settings(settings, chosen_class or device.battery_class, classes)
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


def check_class_value(key: str, value: object) -> None:
    """Raise SettingsError unless a battery class may set this setting so."""
    if key not in CLASS_KEYS:
        raise SettingsError("not_a_class_setting", key)
    check_value(key, value)


def make_class_choice(
    settings: Settings, chosen_class: BatteryClass, changes: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the user's settings for a class; keep what differs from built-in."""
    for key, value in changes.items():
        check_class_value(key, value)
    builtin = replace(settings, **CLASS_DEFAULTS.get(chosen_class, {}))
    check_combination(replace(builtin, **changes))
    return {
        key: value for key, value in changes.items() if getattr(builtin, key) != value
    }


def classes_from_storage(
    raw: object,
) -> tuple[dict[BatteryClass, dict[str, Any]], list[str]]:
    """Rebuild the user's settings per class, dropping whatever is invalid.

    Returns:
        The settings by class, and the dotted names of the values that were ignored.
    """
    if raw is None:
        return {}, []
    if not isinstance(raw, Mapping):
        return {}, ["*"]
    classes: dict[BatteryClass, dict[str, Any]] = {}
    problems: list[str] = []
    for name, stored in raw.items():
        try:
            chosen_class = BatteryClass(name)
        except ValueError:
            problems.append(str(name))
            continue
        if not isinstance(stored, Mapping):
            problems.append(str(name))
            continue
        choice: dict[str, Any] = {}
        for key, value in stored.items():
            try:
                check_class_value(str(key), value)
            except SettingsError:
                problems.append(f"{name}.{key}")
            else:
                choice[key] = value
        if choice:
            classes[chosen_class] = choice
    return classes, problems


def classes_to_storage(classes: ClassChoices) -> dict[str, Any]:
    """Return the storage form of the user's settings per class."""
    return {
        chosen_class.value: dict(choice)
        for chosen_class, choice in classes.items()
        if choice
    }


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
