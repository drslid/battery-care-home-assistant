"""Reading the sources of a battery device."""

from custom_components.battery_care.core.models import (
    BatteryClass,
    BatteryDevice,
    BatterySource,
    Importance,
    SourceKind,
)
from custom_components.battery_care.core.readings import Reading, parse_level, read

DEVICE = BatteryDevice(
    key="d:remote",
    name="Remote",
    sources=(
        BatterySource("sensor.left", SourceKind.LEVEL),
        BatterySource("sensor.right", SourceKind.LEVEL),
        BatterySource("binary_sensor.low", SourceKind.LOW),
        BatterySource("binary_sensor.charging", SourceKind.CHARGING),
    ),
    battery_class=BatteryClass.UNKNOWN,
    class_reason="default",
    suggested_importance=Importance.NORMAL,
)


def test_parse_level() -> None:
    """Only finite percentages between 0 and 100 are battery levels."""
    assert parse_level("78") == 78
    assert parse_level("0") == 0
    assert parse_level("99.5") == 99.5
    for invalid in ("abc", "", "-1", "100.1", "nan", "inf"):
        assert parse_level(invalid) is None


def test_the_worst_level_wins() -> None:
    """A cell at 5 % must not hide behind one at 90 %."""
    reading = read(
        DEVICE,
        {"sensor.left": "90", "sensor.right": "5", "binary_sensor.low": "off"},
    )

    assert reading == Reading(level=5, low=False, charging=False, available=True)


def test_invalid_values_are_reported() -> None:
    """Out-of-range or non-numeric values are never used as a level."""
    reading = read(
        DEVICE,
        {"sensor.left": "120", "sensor.right": "abc", "binary_sensor.low": "maybe"},
    )

    assert reading.level is None
    assert reading.low is None
    assert reading.available
    assert reading.invalid == ("sensor.left", "sensor.right", "binary_sensor.low")


def test_unknown_is_available_without_value() -> None:
    """Unknown means the device is there but has not reported yet."""
    reading = read(DEVICE, {"sensor.left": "unknown", "sensor.right": "unavailable"})

    assert reading == Reading(level=None, low=None, charging=False, available=True)


def test_unavailable_or_missing_sources() -> None:
    """Without any reachable source, the device is not available."""
    assert not read(DEVICE, {"sensor.left": "unavailable"}).available
    assert not read(DEVICE, {}).available


def test_low_flag_and_charging() -> None:
    """Any low flag counts; charging is read from its own source."""
    reading = read(
        DEVICE,
        {
            "sensor.left": "40",
            "binary_sensor.low": "on",
            "binary_sensor.charging": "on",
        },
    )

    assert reading.low is True
    assert reading.charging is True
    assert reading.level == 40
