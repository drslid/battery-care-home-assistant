"""Device status from the alert engine's conclusions, and the summary counts."""

from dataclasses import replace

import pytest

from custom_components.battery_care.core.policy import DeviceMode
from custom_components.battery_care.core.runtime import Runtime, Severity
from custom_components.battery_care.core.settings import DEFAULTS
from custom_components.battery_care.core.status import (
    Status,
    Summary,
    device_status,
    needs_attention,
    summarize,
)

SEEN = Runtime(last_level=50)


@pytest.mark.parametrize(
    ("runtime", "expected"),
    [
        (replace(SEEN, severity=Severity.CRITICAL), Status.CRITICAL),
        (replace(SEEN, severity=Severity.LOW), Status.LOW),
        (SEEN, Status.OK),
        (Runtime(last_low=False), Status.OK),
        (replace(SEEN, stale=True), Status.STALE),
        (Runtime(), Status.UNKNOWN),
    ],
)
def test_the_status_follows_the_engine(runtime: Runtime, expected: Status) -> None:
    """Severity first, then staleness; a device never read is unknown."""
    assert device_status(runtime, False, DeviceMode.AUTOMATIC) is expected


def test_not_responding_and_charging_come_before_the_severity() -> None:
    """A silent device has no current level, and a charging one is not low."""
    critical = replace(SEEN, severity=Severity.CRITICAL)

    assert device_status(critical, True, DeviceMode.AUTOMATIC) is Status.CHARGING
    assert (
        device_status(replace(critical, not_responding=True), True, DeviceMode.CUSTOM)
        is Status.NOT_RESPONDING
    )


def test_an_ignored_device_shows_as_ignored() -> None:
    """Ignoring a device hides its battery problems."""
    critical = replace(SEEN, severity=Severity.CRITICAL, not_responding=True)

    assert device_status(critical, False, DeviceMode.IGNORED) is Status.IGNORED


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
