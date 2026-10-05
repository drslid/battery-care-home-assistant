"""Device status from thresholds alone, and the summary counts."""

from dataclasses import replace

import pytest

from custom_components.battery_care.core.policy import DeviceMode
from custom_components.battery_care.core.readings import Reading
from custom_components.battery_care.core.settings import DEFAULTS
from custom_components.battery_care.core.status import (
    Status,
    Summary,
    device_status,
    needs_attention,
    summarize,
)


def reading(
    level: float | None = None,
    *,
    low: bool | None = None,
    charging: bool = False,
    available: bool = True,
) -> Reading:
    """Return a reading with only the values a test cares about."""
    return Reading(level=level, low=low, charging=charging, available=available)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (100, Status.OK),
        (21, Status.OK),
        (20, Status.LOW),
        (11, Status.LOW),
        (10, Status.CRITICAL),
        (0, Status.CRITICAL),
    ],
)
def test_the_level_is_compared_with_the_thresholds(
    level: float, expected: Status
) -> None:
    """At the threshold counts as below it, as in the brief (20 % is low)."""
    assert device_status(reading(level), DEFAULTS, DeviceMode.AUTOMATIC) is expected


def test_the_device_thresholds_apply() -> None:
    """The effective settings of the device decide, not the global ones."""
    custom = replace(DEFAULTS, low_threshold=30)

    assert device_status(reading(25), custom, DeviceMode.CUSTOM) is Status.LOW


def test_a_low_flag_means_low_even_with_a_good_level() -> None:
    """The device's own low flag is trusted."""
    assert device_status(reading(80, low=True), DEFAULTS, DeviceMode.AUTOMATIC) is (
        Status.LOW
    )
    assert device_status(reading(low=True), DEFAULTS, DeviceMode.AUTOMATIC) is (
        Status.LOW
    )
    assert device_status(reading(low=False), DEFAULTS, DeviceMode.AUTOMATIC) is (
        Status.OK
    )


def test_a_critical_level_wins_over_a_clear_low_flag() -> None:
    """The level is more precise than the flag."""
    assert device_status(reading(5, low=False), DEFAULTS, DeviceMode.AUTOMATIC) is (
        Status.CRITICAL
    )


def test_charging_and_unavailable_come_before_the_level() -> None:
    """A charging device is not low, and an unavailable one has no level."""
    assert device_status(reading(5, charging=True), DEFAULTS, DeviceMode.AUTOMATIC) is (
        Status.CHARGING
    )
    assert device_status(
        reading(available=False, charging=True), DEFAULTS, DeviceMode.AUTOMATIC
    ) is (Status.NOT_RESPONDING)


def test_no_value_yet_is_unknown() -> None:
    """Sources that exist but report nothing usable."""
    assert device_status(reading(), DEFAULTS, DeviceMode.AUTOMATIC) is Status.UNKNOWN


def test_an_ignored_device_shows_as_ignored() -> None:
    """Ignoring a device hides its battery problems."""
    assert device_status(reading(5), DEFAULTS, DeviceMode.IGNORED) is Status.IGNORED


def test_attention_needs_alerts_on() -> None:
    """Without alerts, a low battery is shown but not raised."""
    quiet = replace(DEFAULTS, alerts_enabled=False)

    assert needs_attention(Status.CRITICAL, DEFAULTS)
    assert needs_attention(Status.NOT_RESPONDING, DEFAULTS)
    assert not needs_attention(Status.CRITICAL, quiet)
    assert not needs_attention(Status.OK, DEFAULTS)
    assert not needs_attention(Status.UNKNOWN, DEFAULTS)


def test_the_summary_counts_only_monitored_problems() -> None:
    """Devices with alerts off count in the total only; no reading is not healthy."""
    summary = summarize(
        [
            (Status.CRITICAL, True),
            (Status.LOW, True),
            (Status.LOW, True),
            (Status.NOT_RESPONDING, True),
            (Status.OK, True),
            (Status.CHARGING, True),
            (Status.UNKNOWN, True),
            (Status.LOW, False),
            (Status.IGNORED, False),
        ]
    )

    assert summary == Summary(
        total=9,
        monitored=7,
        healthy=2,
        attention=4,
        critical=1,
        low=2,
        not_responding=1,
        unknown=1,
    )


def test_an_empty_home_has_an_empty_summary() -> None:
    """No battery device at all."""
    assert summarize([]) == Summary()
