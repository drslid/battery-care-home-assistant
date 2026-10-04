"""Choosing the battery class and the suggested importance."""

import pytest

from custom_components.battery_care.core.classification import (
    DeviceTraits,
    classify,
    normalize_battery_type,
    suggest_importance,
)
from custom_components.battery_care.core.models import BatteryClass, Importance


@pytest.mark.parametrize(
    ("traits", "expected"),
    [
        (
            DeviceTraits(
                has_charging=True,
                device_classes=frozenset({("sensor", "energy_storage")}),
            ),
            (BatteryClass.NOT_MAINTAINED, "energy_storage"),
        ),
        (
            DeviceTraits(integration="tesla_fleet", has_charging=True),
            (BatteryClass.NOT_MAINTAINED, "integration"),
        ),
        (
            DeviceTraits(integration="zha", has_charging=True),
            (BatteryClass.RECHARGEABLE, "charging_sensor"),
        ),
        (
            DeviceTraits(domains=frozenset({"vacuum", "sensor"})),
            (BatteryClass.RECHARGEABLE, "robot"),
        ),
        (
            DeviceTraits(integration="mobile_app"),
            (BatteryClass.RECHARGEABLE, "mobile_app"),
        ),
        (
            DeviceTraits(battery_type="Rechargeable"),
            (BatteryClass.RECHARGEABLE, "battery_type"),
        ),
        (
            DeviceTraits(battery_type="cr 2032"),
            (BatteryClass.REPLACEABLE, "battery_type"),
        ),
        (DeviceTraits(battery_type="AAA"), (BatteryClass.REPLACEABLE, "battery_type")),
        (DeviceTraits(battery_type="Irreplaceable"), (BatteryClass.UNKNOWN, "default")),
        (DeviceTraits(integration="zha"), (BatteryClass.UNKNOWN, "default")),
    ],
)
def test_classify(traits: DeviceTraits, expected: tuple[BatteryClass, str]) -> None:
    """Storage and vehicles first, then charging evidence, then the battery type."""
    assert classify(traits) == expected


def test_normalize_battery_type() -> None:
    """Spaces and case do not matter."""
    assert normalize_battery_type(" cr123a ") == "CR123A"
    assert normalize_battery_type("CR 2450") == "CR2450"


@pytest.mark.parametrize(
    ("traits", "expected"),
    [
        (DeviceTraits(domains=frozenset({"lock"})), Importance.IMPORTANT),
        (
            DeviceTraits(device_classes=frozenset({("binary_sensor", "smoke")})),
            Importance.IMPORTANT,
        ),
        (
            DeviceTraits(device_classes=frozenset({("binary_sensor", "moisture")})),
            Importance.IMPORTANT,
        ),
        (
            DeviceTraits(device_classes=frozenset({("sensor", "moisture")})),
            Importance.NORMAL,
        ),
        (
            DeviceTraits(domains=frozenset({"sensor", "binary_sensor"})),
            Importance.NORMAL,
        ),
    ],
)
def test_suggest_importance(traits: DeviceTraits, expected: Importance) -> None:
    """Locks and safety detectors are suggested as Important; never Critical."""
    assert suggest_importance(traits) is expected
