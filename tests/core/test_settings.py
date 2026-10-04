"""Global settings: validation, defaults and storage form."""

from dataclasses import replace

import pytest

from custom_components.battery_care.core.settings import (
    DEFAULTS,
    Settings,
    SettingsError,
    settings_from_storage,
    settings_to_storage,
    updated,
)


def test_defaults_work_without_any_configuration() -> None:
    """Low at 20 % (like Home Assistant's Maintenance dashboard), critical at 10 %."""
    assert DEFAULTS.low_threshold == 20
    assert DEFAULTS.critical_threshold == 10
    assert DEFAULTS.hysteresis == 5
    assert DEFAULTS.alerts_enabled


def test_valid_changes_are_applied() -> None:
    """Changes return new settings; the original stays untouched."""
    changed = updated(DEFAULTS, {"low_threshold": 25, "reminder_hours": 24})

    assert changed == replace(DEFAULTS, low_threshold=25, reminder_hours=24)
    assert DEFAULTS.low_threshold == 20


@pytest.mark.parametrize(
    ("changes", "code", "key"),
    [
        ({"low_threshold": "25"}, "not_integer", "low_threshold"),
        ({"low_threshold": True}, "not_integer", "low_threshold"),
        ({"alerts_enabled": 1}, "not_boolean", "alerts_enabled"),
        ({"low_threshold": 0}, "out_of_range", "low_threshold"),
        ({"stale_days": 91}, "out_of_range", "stale_days"),
        ({"colour": "red"}, "unknown_setting", "colour"),
        ({"low_threshold": 10}, "critical_not_below_low", "critical_threshold"),
        (
            {"low_threshold": 95, "hysteresis": 6},
            "recovery_above_maximum",
            "hysteresis",
        ),
    ],
)
def test_invalid_changes_are_refused(
    changes: dict[str, object], code: str, key: str
) -> None:
    """Each refusal carries a stable code for a translated message."""
    with pytest.raises(SettingsError) as error:
        updated(DEFAULTS, changes)

    assert (error.value.code, error.value.key) == (code, key)


def test_only_differences_are_stored() -> None:
    """Untouched values follow future default improvements."""
    assert settings_to_storage(DEFAULTS) == {}
    assert settings_to_storage(replace(DEFAULTS, low_threshold=30)) == {
        "low_threshold": 30
    }


def test_storage_round_trip() -> None:
    """What is stored is what comes back."""
    settings = Settings(low_threshold=30, critical_threshold=15, stale_detection=False)

    assert settings_from_storage(settings_to_storage(settings)) == (settings, [])


def test_invalid_stored_values_fall_back_to_defaults() -> None:
    """Each bad value is reported and replaced by its default."""
    settings, problems = settings_from_storage(
        {"low_threshold": "high", "reminder_hours": 48, "dark_mode": True}
    )

    assert settings == replace(DEFAULTS, reminder_hours=48)
    assert problems == ["low_threshold", "dark_mode"]


def test_contradictory_stored_thresholds_are_reset() -> None:
    """A critical level above the low level would never make sense."""
    settings, problems = settings_from_storage(
        {"low_threshold": 15, "critical_threshold": 30}
    )

    assert (settings.low_threshold, settings.critical_threshold) == (20, 10)
    assert problems == ["thresholds"]


def test_missing_or_malformed_section() -> None:
    """No data means defaults; garbage is reported."""
    assert settings_from_storage(None) == (DEFAULTS, [])
    assert settings_from_storage(["low_threshold", 30]) == (DEFAULTS, ["*"])
