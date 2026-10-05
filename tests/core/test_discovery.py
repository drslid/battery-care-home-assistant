"""Finding battery entities and grouping them into battery devices."""

from dataclasses import replace
from typing import Any

from custom_components.battery_care.core.discovery import (
    discover,
    group_key,
    source_kind,
)
from custom_components.battery_care.core.models import (
    BatteryClass,
    BatteryMetadata,
    BatterySource,
    DeviceRecord,
    EntityRecord,
    Importance,
    NotMonitored,
    SourceKind,
)

DEVICES = {
    "door": DeviceRecord(
        "door", name="Front Door", area_id="entrance", manufacturer="Aqara"
    ),
    "phone": DeviceRecord("phone", name="Pixel"),
    "remote": DeviceRecord("remote", name="Remote", disabled=True),
}


def level(entity_id: str, **changes: Any) -> EntityRecord:
    """Return a battery percentage sensor of the door, with changes."""
    record = EntityRecord(
        entity_id,
        platform="zha",
        registry_id=f"id-{entity_id}",
        device_id="door",
        device_class="battery",
        unit="%",
    )
    return replace(record, **changes)


def flag(entity_id: str, device_class: str = "battery", **changes: Any) -> EntityRecord:
    """Return a battery binary sensor of the door, with changes."""
    record = EntityRecord(
        entity_id,
        platform="zha",
        registry_id=f"id-{entity_id}",
        device_id="door",
        device_class=device_class,
    )
    return replace(record, **changes)


def test_source_kinds() -> None:
    """Device class and unit decide; names never do."""
    assert source_kind(level("sensor.a")) is SourceKind.LEVEL
    assert source_kind(flag("binary_sensor.a")) is SourceKind.LOW
    assert (
        source_kind(flag("binary_sensor.b", "battery_charging")) is SourceKind.CHARGING
    )
    assert source_kind(level("sensor.millivolts", unit="mV")) is None
    assert source_kind(level("sensor.humidity", device_class="humidity")) is None
    assert source_kind(flag("binary_sensor.door", "door")) is None
    assert source_kind(level("switch.battery")) is None


def test_group_keys() -> None:
    """Devices group their entities; others stand alone, by registry id if possible."""
    assert group_key(level("sensor.a")) == "d:door"
    assert group_key(level("sensor.b", device_id=None)) == "e:id-sensor.b"
    assert (
        group_key(level("sensor.c", device_id=None, registry_id=None)) == "s:sensor.c"
    )


def test_entities_of_one_device_form_one_battery_device() -> None:
    """Level and low flag are grouped; other sensors only describe the device."""
    inventory = discover(
        [
            level("sensor.door_battery"),
            flag("binary_sensor.door_battery_low"),
            level("sensor.door_voltage", device_class="voltage", unit="V"),
            flag("binary_sensor.door_contact", "door"),
        ],
        DEVICES,
    )

    assert list(inventory.devices) == ["d:door"]
    device = inventory.devices["d:door"]
    assert device.name == "Front Door"
    assert device.sources == (
        BatterySource("sensor.door_battery", SourceKind.LEVEL),
        BatterySource("binary_sensor.door_battery_low", SourceKind.LOW),
    )
    assert device.integration == "zha"
    assert device.manufacturer == "Aqara"
    assert device.area_id == "entrance"
    assert device.battery_class is BatteryClass.UNKNOWN
    assert device.suggested_importance is Importance.NORMAL
    assert device.stable


def test_entities_without_device_stand_alone() -> None:
    """A registered entity keeps its key across renames; a state-only one cannot."""
    inventory = discover(
        [
            level("sensor.diy_battery", device_id=None, name="DIY sensor battery"),
            level("sensor.yaml_battery", device_id=None, registry_id=None),
        ],
        {},
    )

    registered = inventory.devices["e:id-sensor.diy_battery"]
    assert registered.name == "DIY sensor battery"
    assert registered.stable
    state_only = inventory.devices["s:sensor.yaml_battery"]
    assert state_only.name == "sensor.yaml_battery"
    assert not state_only.stable


def test_mirrors_and_aggregates_are_never_batteries() -> None:
    """Battery Notes duplicates and sensor groups would double every alert."""
    inventory = discover(
        [
            level("sensor.door_battery"),
            level("sensor.door_battery_plus", platform="battery_notes"),
            flag("binary_sensor.door_battery_plus_low", platform="battery_notes"),
            level("sensor.lowest_battery", platform="group", device_id=None),
            level("sensor.min_battery", platform="min_max", device_id=None),
        ],
        DEVICES,
    )

    assert list(inventory.devices) == ["d:door"]
    assert inventory.devices["d:door"].entity_ids(SourceKind.LEVEL) == (
        "sensor.door_battery",
    )
    assert inventory.devices["d:door"].entity_ids(SourceKind.LOW) == ()


def test_helpers_only_fill_gaps() -> None:
    """A template level helps a device that only has a low flag, and nothing else."""
    inventory = discover(
        [
            flag("binary_sensor.door_battery_low"),
            level("sensor.door_estimated_battery", platform="template"),
            flag("binary_sensor.phone_low", platform="template", device_id="phone"),
            level("sensor.phone_battery", platform="mobile_app", device_id="phone"),
            level("sensor.phone_template", platform="template", device_id="phone"),
            level("sensor.diy_battery", platform="template", device_id=None),
        ],
        DEVICES,
    )

    door = inventory.devices["d:door"]
    assert door.entity_ids(SourceKind.LEVEL) == ("sensor.door_estimated_battery",)
    assert door.entity_ids(SourceKind.LOW) == ("binary_sensor.door_battery_low",)
    assert door.integration == "template"
    phone = inventory.devices["d:phone"]
    assert phone.sources == (BatterySource("sensor.phone_battery", SourceKind.LEVEL),)
    assert "e:id-sensor.diy_battery" in inventory.devices


def test_charging_alone_is_not_a_battery() -> None:
    """A charging flag describes a battery; it does not make one."""
    inventory = discover([flag("binary_sensor.charging", "battery_charging")], DEVICES)

    assert inventory.devices == {}


def test_charging_flag_marks_a_rechargeable_device() -> None:
    """The charging flag joins the device and makes it rechargeable."""
    inventory = discover(
        [
            level("sensor.phone_battery", platform="mobile_app", device_id="phone"),
            flag("binary_sensor.phone_charging", "battery_charging", device_id="phone"),
        ],
        DEVICES,
    )

    phone = inventory.devices["d:phone"]
    assert phone.entity_ids(SourceKind.CHARGING) == ("binary_sensor.phone_charging",)
    assert phone.battery_class is BatteryClass.RECHARGEABLE
    assert phone.class_reason == "charging_sensor"


def test_disabled_batteries_are_listed_as_not_monitored() -> None:
    """Disabled entities and devices are reported, not silently dropped."""
    inventory = discover(
        [
            level("sensor.door_battery", disabled=True),
            level("sensor.remote_battery", device_id="remote"),
            flag("binary_sensor.solo_charging", "battery_charging", disabled=True),
        ],
        DEVICES,
    )

    assert inventory.devices == {}
    assert inventory.not_monitored == (
        NotMonitored("d:door", "Front Door", "disabled"),
        NotMonitored("d:remote", "Remote", "disabled"),
    )


def test_own_entities_are_ignored() -> None:
    """Battery Care's summary sensors must never be discovered as batteries."""
    inventory = discover(
        [level("sensor.battery_care_health", platform="battery_care")], DEVICES
    )

    assert inventory.devices == {}


def test_names_attributes_and_words_stand_in_for_missing_sources() -> None:
    """Weaker forms are used only when a device has nothing better."""
    records = [
        level(
            "sensor.remote_batterie",
            device_class=None,
            name="Remote Batterie",
            device_id=None,
        ),
        level("sensor.door_batt", device_class=None, name="Door batt"),
        level("sensor.door_battery"),
        level("sensor.off_battery", device_class=None, disabled=True, device_id=None),
        level("sensor.humidity", device_class=None, name="Humidity", device_id=None),
        EntityRecord("vacuum.robot", platform="roborock", battery_level=True),
        EntityRecord(
            "sensor.lock_battery_state",
            platform="august",
            registry_id="id-lock",
            device_class="enum",
            name="Lock battery state",
            text_state=True,
        ),
        EntityRecord(
            "sensor.hall_weather", platform="met", device_class="enum", text_state=True
        ),
    ]

    inventory = discover(records, DEVICES)

    assert inventory.devices["d:door"].sources == (
        BatterySource("sensor.door_battery", SourceKind.LEVEL),
    )
    assert inventory.devices["e:id-sensor.remote_batterie"].sources == (
        BatterySource("sensor.remote_batterie", SourceKind.LEVEL),
    )
    assert inventory.devices["s:vacuum.robot"].sources == (
        BatterySource("vacuum.robot", SourceKind.LEVEL, "battery_level"),
    )
    assert inventory.devices["e:id-lock"].sources == (
        BatterySource("sensor.lock_battery_state", SourceKind.STATE),
    )
    assert set(inventory.devices) == {
        "d:door",
        "e:id-lock",
        "e:id-sensor.remote_batterie",
        "s:vacuum.robot",
    }
    assert inventory.not_monitored == (
        NotMonitored("e:id-sensor.off_battery", "sensor.off_battery", "disabled"),
    )


def test_the_best_weak_form_wins() -> None:
    """Without a battery sensor, a named sensor beats an attribute and a word."""
    records = [
        level("sensor.robot_battery", device_class=None, name="Robot battery"),
        level("vacuum.robot", device_class=None, unit=None, battery_level=True),
        level(
            "sensor.robot_battery_state",
            device_class="battery",
            unit=None,
            text_state=True,
        ),
    ]

    (device,) = discover(records, DEVICES).devices.values()

    assert device.sources == (BatterySource("sensor.robot_battery", SourceKind.LEVEL),)


def test_area_and_floor() -> None:
    """The entity area wins over the device area; the floor follows the area."""
    floors = {"entrance": "ground", "garage": None}
    inventory = discover(
        [
            level("sensor.door_battery"),
            level("sensor.garage_battery", device_id=None, area_id="garage"),
        ],
        DEVICES,
        floors=floors,
    )

    assert inventory.devices["d:door"].floor_id == "ground"
    garage = inventory.devices["e:id-sensor.garage_battery"]
    assert garage.area_id == "garage"
    assert garage.floor_id is None


def test_metadata_is_attached_and_used() -> None:
    """A known primary cell makes the device replaceable."""
    metadata = BatteryMetadata("CR2032", 1, "battery_notes")
    inventory = discover(
        [level("sensor.door_battery")], DEVICES, metadata={"d:door": metadata}
    )

    device = inventory.devices["d:door"]
    assert device.metadata == metadata
    assert device.battery_class is BatteryClass.REPLACEABLE
    assert device.class_reason == "battery_type"


def test_results_are_sorted() -> None:
    """The same registries always produce the same inventory."""
    records = [
        level("sensor.b", device_id=None),
        level("sensor.a", device_id=None),
        level("sensor.door_battery"),
    ]
    first = discover(records, DEVICES)
    second = discover(reversed(records), DEVICES)

    assert list(first.devices) == ["d:door", "e:id-sensor.a", "e:id-sensor.b"]
    assert first == second


def test_signs_of_life_come_from_the_integration_of_the_device() -> None:
    """Entities that other integrations attach report nothing about the device."""
    records = [
        level("sensor.door_battery"),
        level("sensor.door_signal", device_class="signal_strength", unit="dBm"),
        level("sensor.door_quiet", device_class=None, disabled=True),
        level("sensor.door_battery_type", platform="battery_notes", device_class=None),
        level("sensor.garden_battery", platform="template", device_id=None),
    ]

    inventory = discover(records, DEVICES)

    assert inventory.devices["d:door"].evidence == (
        "sensor.door_battery",
        "sensor.door_signal",
    )
    assert inventory.devices["e:id-sensor.garden_battery"].evidence == (
        "sensor.garden_battery",
    )
