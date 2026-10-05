"""Discovering batteries in a running Home Assistant and following changes."""

import time
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.battery_care.adapters.registry import async_inventory
from custom_components.battery_care.core.models import (
    BatteryClass,
    BatteryMetadata,
    Importance,
    SourceKind,
)
from custom_components.battery_care.core.readings import Reading

from .common import (
    BATTERY,
    add_device,
    add_entity,
    pass_rebuild_cooldown,
    setup_battery_care,
)

INVENTORY_BUDGET = 1.0  # Four times the target, so slow CI runners do not flake.


async def test_existing_batteries_are_discovered(hass: HomeAssistant) -> None:
    """Devices, Battery Notes data, phones and YAML sensors are found at setup."""
    floor = fr.async_get(hass).async_create("Ground floor")
    area = ar.async_get(hass).async_create("Entrance", floor_id=floor.floor_id)
    door = add_device(hass, "Front Door", area_id=area.id)
    add_entity(hass, "door_battery", "8", device_id=door.id, attributes=BATTERY)
    add_entity(
        hass,
        "door_battery_low",
        "on",
        domain="binary_sensor",
        device_id=door.id,
        attributes={"device_class": "battery"},
    )
    add_entity(hass, "door_lock", "locked", domain="lock", device_id=door.id)
    add_entity(
        hass,
        "door_battery_plus",
        "8",
        platform="battery_notes",
        device_id=door.id,
        attributes=BATTERY,
    )
    add_entity(
        hass,
        "door_battery_type",
        "2x CR123A",
        platform="battery_notes",
        device_id=door.id,
        attributes={"battery_type": "CR123A", "battery_quantity": 2},
    )
    phone = add_device(hass, "Pixel", integration="mobile_app")
    add_entity(
        hass,
        "pixel_battery_level",
        "64",
        platform="mobile_app",
        device_id=phone.id,
        attributes=BATTERY,
    )
    hass.states.async_set(
        "sensor.yaml_battery", "55", {**BATTERY, "friendly_name": "YAML battery"}
    )

    manager = await setup_battery_care(hass)

    inventory = manager.inventory
    assert set(inventory.devices) == {
        f"d:{door.id}",
        f"d:{phone.id}",
        "s:sensor.yaml_battery",
    }
    front_door = inventory.devices[f"d:{door.id}"]
    assert front_door.name == "Front Door"
    assert front_door.sources[0].entity_id == "sensor.door_battery"
    assert front_door.entity_ids(SourceKind.LOW) == ("binary_sensor.door_battery_low",)
    assert front_door.area_id == area.id
    assert front_door.floor_id == floor.floor_id
    assert front_door.metadata == BatteryMetadata("CR123A", 2, "battery_notes")
    assert front_door.battery_class is BatteryClass.REPLACEABLE
    assert front_door.suggested_importance is Importance.IMPORTANT
    assert manager.readings[f"d:{door.id}"] == Reading(
        level=8, low=True, charging=False, available=True
    )
    assert inventory.devices[f"d:{phone.id}"].battery_class is BatteryClass.RECHARGEABLE
    assert inventory.devices["s:sensor.yaml_battery"].name == "YAML battery"


@pytest.mark.skipif(
    not hasattr(dr.DeviceRegistry, "async_get_or_create_child"),
    reason="Child devices exist since Home Assistant 2026.9",
)
async def test_child_devices_share_the_battery_of_their_parent(
    hass: HomeAssistant,
) -> None:
    """A switch channel exposed as a child device is the same physical battery."""
    remote = add_device(hass, "Remote")
    registry: Any = dr.async_get(hass)
    child = registry.async_get_or_create_child(
        config_entry_id=remote.config_entry_id,
        identifiers={("zha", "remote-button-2")},
        name="Button 2",
        parent_device_id=remote.id,
    )
    add_entity(hass, "remote_battery", "64", device_id=remote.id, attributes=BATTERY)
    add_entity(
        hass,
        "button_2_battery_low",
        "off",
        domain="binary_sensor",
        device_id=child.id,
        attributes={"device_class": "battery"},
    )

    manager = await setup_battery_care(hass)

    assert list(manager.inventory.devices) == [f"d:{remote.id}"]
    assert manager.inventory.devices[f"d:{remote.id}"].entity_ids(SourceKind.LOW) == (
        "binary_sensor.button_2_battery_low",
    )


async def test_battery_notes_for_an_entity_without_device(hass: HomeAssistant) -> None:
    """Battery Notes can describe a lone entity; its source entity says which."""
    add_entity(hass, "diy_battery", "70", platform="esphome", attributes=BATTERY)
    add_entity(
        hass,
        "diy_battery_type",
        "2x AA",
        platform="battery_notes",
        attributes={
            "battery_type": "AA",
            "battery_quantity": 2,
            "source_entity_id": "sensor.diy_battery",
        },
    )
    add_entity(
        hass,
        "orphan_battery_type",
        "CR2032",
        platform="battery_notes",
        attributes={"battery_type": "CR2032"},
    )

    manager = await setup_battery_care(hass)

    (device,) = manager.inventory.devices.values()
    assert device.metadata == BatteryMetadata("AA", 2, "battery_notes")
    assert device.battery_class is BatteryClass.REPLACEABLE


async def test_discovery_waits_for_home_assistant_to_start(hass: HomeAssistant) -> None:
    """Integrations are still loading before the start; discovery waits for it."""
    add_entity(hass, "door_battery", "50", attributes=BATTERY)
    hass.set_state(CoreState.starting)

    manager = await setup_battery_care(hass)
    assert manager.inventory.devices == {}

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert len(manager.inventory.devices) == 1


async def test_a_new_battery_appears_without_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A device paired tomorrow shows up once its burst of changes settles."""
    manager = await setup_battery_care(hass)
    remote = add_device(hass, "Remote")
    add_entity(hass, "remote_battery", "64", device_id=remote.id, attributes=BATTERY)
    await hass.async_block_till_done()
    assert manager.inventory.devices == {}

    await pass_rebuild_cooldown(hass, freezer)

    assert list(manager.inventory.devices) == [f"d:{remote.id}"]
    assert manager.readings[f"d:{remote.id}"].level == 64


async def test_a_new_yaml_battery_appears(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Entities without registry entry are noticed when their state appears."""
    manager = await setup_battery_care(hass)

    hass.states.async_set("sensor.yaml_battery", "55", BATTERY)
    hass.states.async_set(
        "sensor.outdoor_temperature", "12", {"unit_of_measurement": "°C"}
    )
    await pass_rebuild_cooldown(hass, freezer)

    assert list(manager.inventory.devices) == ["s:sensor.yaml_battery"]


async def test_state_changes_update_readings_at_once(hass: HomeAssistant) -> None:
    """Battery levels do not wait for the rebuild cooldown."""
    entity_id = add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    (key,) = manager.inventory.devices

    hass.states.async_set(entity_id, "15", BATTERY)
    await hass.async_block_till_done()

    assert manager.readings[key].level == 15


async def test_a_renamed_entity_keeps_its_battery_device(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Settings will be keyed by the registry id, which a rename keeps."""
    entity_id = add_entity(
        hass, "diy_battery", "50", platform="esphome", attributes=BATTERY
    )
    manager = await setup_battery_care(hass)
    (key,) = manager.inventory.devices

    er.async_get(hass).async_update_entity(
        entity_id, new_entity_id="sensor.workshop_battery"
    )
    hass.states.async_remove(entity_id)
    hass.states.async_set("sensor.workshop_battery", "40", BATTERY)
    await pass_rebuild_cooldown(hass, freezer)

    assert list(manager.inventory.devices) == [key]
    assert (
        manager.inventory.devices[key].sources[0].entity_id == "sensor.workshop_battery"
    )
    hass.states.async_set("sensor.workshop_battery", "35", BATTERY)
    await hass.async_block_till_done()
    assert manager.readings[key].level == 35


async def test_a_removed_battery_disappears(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Removing the entity removes the battery device."""
    entity_id = add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    assert len(manager.inventory.devices) == 1

    er.async_get(hass).async_remove(entity_id)
    hass.states.async_remove(entity_id)
    await pass_rebuild_cooldown(hass, freezer)

    assert manager.inventory.devices == {}
    assert manager.readings == {}


async def test_unload_stops_following_changes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """After unload, neither states nor registries are followed."""
    entity_id = add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    (key,) = manager.inventory.devices
    for entry in hass.config_entries.async_entries("battery_care"):
        assert await hass.config_entries.async_unload(entry.entry_id)

    hass.states.async_set(entity_id, "10", BATTERY)
    add_entity(hass, "remote_battery", "70", attributes=BATTERY)
    await pass_rebuild_cooldown(hass, freezer)

    assert manager.readings[key].level == 50
    assert list(manager.inventory.devices) == [key]


async def test_a_large_home_is_inventoried_quickly(hass: HomeAssistant) -> None:
    """1,000 battery devices among 5,000 registered entities."""
    entry = MockConfigEntry(domain="zha")
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    for i in range(1000):
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={("zha", f"dev{i}")},
            name=f"Sensor {i}",
        )
        add_entity(
            hass, f"dev{i}_battery", "80", device_id=device.id, attributes=BATTERY
        )
        for kind in ("temperature", "humidity", "voltage", "linkquality"):
            add_entity(hass, f"dev{i}_{kind}", "1", device_id=device.id)

    started = time.perf_counter()
    inventory = async_inventory(hass)
    elapsed = time.perf_counter() - started

    assert len(inventory.devices) == 1000
    assert elapsed < INVENTORY_BUDGET


async def test_attributes_and_text_states_are_followed(hass: HomeAssistant) -> None:
    """A vacuum with a battery attribute and a lock with a text state are read."""
    robot = add_device(hass, "Robot", integration="roborock")
    vacuum_id = add_entity(
        hass,
        "robot",
        "docked",
        domain="vacuum",
        platform="roborock",
        device_id=robot.id,
        attributes={"battery_level": 80},
    )
    lock = add_device(hass, "Front Door", integration="august")
    state_id = add_entity(
        hass,
        "door_battery_state",
        "Full",
        platform="august",
        device_id=lock.id,
        attributes={
            "device_class": "enum",
            "friendly_name": "Front Door battery state",
            "options": ["Full", "Low", "Empty"],
        },
    )
    # A registered entity without any state yet is simply not a battery.
    er.async_get(hass).async_get_or_create("sensor", "august", "no_state_yet")
    manager = await setup_battery_care(hass)
    robot_key, lock_key = f"d:{robot.id}", f"d:{lock.id}"

    assert manager.inventory.devices[robot_key].battery_class is BatteryClass.ROBOT
    assert manager.readings[robot_key].level == 80
    assert manager.readings[lock_key].low is False

    hass.states.async_set(vacuum_id, "cleaning", {"battery_level": 35})
    hass.states.async_set(state_id, "Empty", {"device_class": "enum"})
    await hass.async_block_till_done()

    assert manager.readings[robot_key].level == 35
    assert manager.readings[lock_key].critical is True
    assert manager.status(lock_key).value == "critical"
