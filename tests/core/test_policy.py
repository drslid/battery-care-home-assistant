"""Per-device choices and the settings that result from them."""

from dataclasses import replace
from typing import Any

import pytest

from custom_components.battery_care.core.models import (
    BatteryClass,
    BatteryDevice,
    Importance,
)
from custom_components.battery_care.core.policy import (
    AUTOMATIC,
    DeviceConfig,
    DeviceMode,
    battery_class,
    config_from_storage,
    config_to_storage,
    effective_settings,
    importance,
    make_config,
)
from custom_components.battery_care.core.settings import DEFAULTS, SettingsError

SENSOR = BatteryDevice(
    key="d:door",
    name="Front Door",
    sources=(),
    battery_class=BatteryClass.UNKNOWN,
    class_reason="default",
    suggested_importance=Importance.IMPORTANT,
)
PHONE = replace(SENSOR, key="d:phone", battery_class=BatteryClass.RECHARGEABLE)


def custom(**overrides: Any) -> DeviceConfig:
    """Return a validated custom configuration for the door sensor."""
    return make_config(DEFAULTS, SENSOR, mode=DeviceMode.CUSTOM, overrides=overrides)


def test_user_choices_win_over_detection() -> None:
    """Detection only provides the starting point."""
    assert battery_class(SENSOR, AUTOMATIC) is BatteryClass.UNKNOWN
    assert importance(SENSOR, AUTOMATIC) is Importance.IMPORTANT
    chosen = DeviceConfig(
        importance=Importance.LOW, battery_class=BatteryClass.REPLACEABLE
    )
    assert battery_class(SENSOR, chosen) is BatteryClass.REPLACEABLE
    assert importance(SENSOR, chosen) is Importance.LOW


def test_automatic_devices_follow_the_global_settings() -> None:
    """Rechargeable and not-maintained devices start with alerts off."""
    assert effective_settings(DEFAULTS, SENSOR, AUTOMATIC) == DEFAULTS
    assert not effective_settings(DEFAULTS, PHONE, AUTOMATIC).alerts_enabled
    not_maintained = replace(SENSOR, battery_class=BatteryClass.NOT_MAINTAINED)
    assert not effective_settings(DEFAULTS, not_maintained, AUTOMATIC).alerts_enabled


def test_choosing_a_class_changes_the_defaults() -> None:
    """A phone called replaceable gets alerts; a sensor called rechargeable not."""
    as_replaceable = DeviceConfig(battery_class=BatteryClass.REPLACEABLE)
    as_rechargeable = DeviceConfig(battery_class=BatteryClass.RECHARGEABLE)

    assert effective_settings(DEFAULTS, PHONE, as_replaceable).alerts_enabled
    assert not effective_settings(DEFAULTS, SENSOR, as_rechargeable).alerts_enabled


def test_custom_overrides_and_ignored_devices() -> None:
    """Custom values apply on top of the global ones; ignoring silences alerts."""
    config = custom(low_threshold=30, reminder_hours=24)

    assert effective_settings(DEFAULTS, SENSOR, config) == replace(
        DEFAULTS, low_threshold=30, reminder_hours=24
    )
    ignored = DeviceConfig(mode=DeviceMode.IGNORED)
    assert not effective_settings(DEFAULTS, SENSOR, ignored).alerts_enabled


def test_global_switches_still_apply_to_custom_devices() -> None:
    """Turning all alerts off globally silences custom devices too."""
    config = custom(low_threshold=30)
    silenced = replace(DEFAULTS, alerts_enabled=False)

    assert not effective_settings(silenced, SENSOR, config).alerts_enabled


def test_a_contradiction_after_a_global_change_uses_the_global_pair() -> None:
    """A custom critical level that the new global low level overtakes is dropped."""
    config = custom(critical_threshold=15)
    lowered = replace(DEFAULTS, low_threshold=12, critical_threshold=5)

    result = effective_settings(lowered, SENSOR, config)

    assert (result.low_threshold, result.critical_threshold) == (12, 5)


def test_only_real_overrides_are_kept() -> None:
    """A value equal to the global one is not an override, so it keeps following it."""
    assert custom(low_threshold=20, reminder_hours=24).overrides == {
        "reminder_hours": 24
    }
    assert custom(low_threshold=20).overrides == {}


@pytest.mark.parametrize(
    ("mode", "overrides", "code"),
    [
        (DeviceMode.AUTOMATIC, {"low_threshold": 30}, "overrides_need_custom_mode"),
        (DeviceMode.CUSTOM, {"hysteresis": 3}, "not_overridable"),
        (DeviceMode.CUSTOM, {"low_threshold": 200}, "out_of_range"),
        (DeviceMode.CUSTOM, {"critical_threshold": 25}, "critical_not_below_low"),
    ],
)
def test_invalid_configurations_are_refused(
    mode: DeviceMode, overrides: dict[str, Any], code: str
) -> None:
    """Nothing invalid reaches storage."""
    with pytest.raises(SettingsError) as error:
        make_config(DEFAULTS, SENSOR, mode=mode, overrides=overrides)

    assert error.value.code == code


def test_storage_round_trip() -> None:
    """Every field survives storage."""
    config = make_config(
        DEFAULTS,
        SENSOR,
        mode=DeviceMode.CUSTOM,
        overrides={"low_threshold": 30},
        chosen_importance=Importance.CRITICAL,
        chosen_class=BatteryClass.REPLACEABLE,
    )

    assert config_from_storage(config_to_storage(config)) == (config, [])
    assert config_to_storage(AUTOMATIC) == {"mode": "automatic"}
    assert AUTOMATIC.is_default


def test_invalid_stored_values_are_dropped() -> None:
    """Bad values are reported; the rest of the device configuration is kept."""
    config, problems = config_from_storage(
        {
            "mode": "custom",
            "overrides": {
                "low_threshold": 30,
                "hysteresis": 2,
                "reminder_hours": "soon",
            },
            "importance": "vital",
            "battery_class": "replaceable",
        }
    )

    assert config == DeviceConfig(
        mode=DeviceMode.CUSTOM,
        overrides={"low_threshold": 30},
        battery_class=BatteryClass.REPLACEABLE,
    )
    assert problems == [
        "overrides.hysteresis",
        "overrides.reminder_hours",
        "importance",
    ]


def test_malformed_stored_configurations() -> None:
    """Unusable records fall back to automatic."""
    assert config_from_storage("custom") == (AUTOMATIC, ["*"])
    assert config_from_storage({"mode": "manual"}) == (AUTOMATIC, ["mode"])
    assert config_from_storage({"mode": "custom", "overrides": [1]}) == (
        DeviceConfig(mode=DeviceMode.CUSTOM),
        ["overrides"],
    )
    assert config_from_storage(
        {"mode": "ignored", "overrides": {"low_threshold": 30}}
    ) == (
        DeviceConfig(mode=DeviceMode.IGNORED),
        [],
    )
