"""The summary entities of the Battery Care service device."""

from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.battery_care.const import DOMAIN
from custom_components.battery_care.core.models import Importance
from custom_components.battery_care.core.policy import DeviceMode

from .common import BATTERY, add_device, add_entity, setup_battery_care

ENTITIES = {
    "sensor.battery_care_battery_health": "health",
    "sensor.battery_care_batteries_needing_attention": "attention",
    "sensor.battery_care_low_batteries": "low",
    "sensor.battery_care_critical_batteries": "critical",
    "sensor.battery_care_monitored_batteries": "monitored",
    "binary_sensor.battery_care_attention_required": "attention_required",
}


def states(hass: HomeAssistant) -> dict[str, str]:
    """Return the state of every summary entity, by key."""
    return {
        key: state.state
        for entity_id, key in ENTITIES.items()
        if (state := hass.states.get(entity_id)) is not None
    }


def last_reports(hass: HomeAssistant) -> dict[str, datetime]:
    """Return when each summary entity last wrote its state."""
    return {
        entity_id: state.last_reported
        for entity_id in ENTITIES
        if (state := hass.states.get(entity_id)) is not None
    }


async def test_the_service_device_and_its_entities(hass: HomeAssistant) -> None:
    """Six translated entities on one service device, with stable unique ids."""
    manager = await setup_battery_care(hass)
    (entry,) = hass.config_entries.async_entries(DOMAIN)

    registry = er.async_get(hass)
    device_ids = set()
    for entity_id, key in ENTITIES.items():
        entity = registry.async_get(entity_id)
        assert entity is not None, entity_id
        assert entity.unique_id == f"{entry.entry_id}-{key}"
        device_ids.add(entity.device_id)
    (device_id,) = device_ids
    assert device_id is not None
    device = dr.async_get(hass).async_get(device_id)
    assert isinstance(device, dr.DeviceEntry)
    assert device.name == "Battery Care"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert (DOMAIN, entry.entry_id) in device.identifiers
    assert manager.ready
    assert states(hass) == {
        "health": STATE_UNKNOWN,
        "attention": "0",
        "low": "0",
        "critical": "0",
        "monitored": "0",
        "attention_required": STATE_OFF,
    }


async def test_the_counts_follow_the_batteries(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Values change with the statuses; unchanged values are not rewritten."""
    door = add_device(hass, "Front Door")
    door_id = add_entity(
        hass, "door_battery", "50", device_id=door.id, attributes=BATTERY
    )
    add_entity(hass, "remote_battery", "8", attributes=BATTERY)
    manager = await setup_battery_care(hass)

    assert states(hass) == {
        "health": "50",
        "attention": "1",
        "low": "0",
        "critical": "1",
        "monitored": "2",
        "attention_required": STATE_ON,
    }
    health = hass.states.get("sensor.battery_care_battery_health")
    assert health is not None
    assert health.attributes["unit_of_measurement"] == "%"

    reported = last_reports(hass)
    changes = async_capture_events(hass, "state_changed")
    freezer.tick(1)
    hass.states.async_set(door_id, "49", BATTERY)
    await hass.async_block_till_done()
    assert [event.data["entity_id"] for event in changes] == [door_id]
    assert last_reports(hass) == reported

    hass.states.async_set(door_id, "15", BATTERY)
    await hass.async_block_till_done()
    assert states(hass)["low"] == "1"
    assert states(hass)["health"] == "30"

    manager.async_configure_device(
        f"d:{door.id}", mode=DeviceMode.IGNORED, importance=Importance.LOW
    )
    await hass.async_block_till_done()
    assert states(hass) == {
        "health": "0",
        "attention": "1",
        "low": "0",
        "critical": "1",
        "monitored": "1",
        "attention_required": STATE_ON,
    }


async def test_the_entities_wait_for_home_assistant_to_start(
    hass: HomeAssistant,
) -> None:
    """Before the inventory exists, the counts are unavailable, not zero."""
    hass.set_state(CoreState.starting)
    await setup_battery_care(hass)

    assert set(states(hass).values()) == {STATE_UNAVAILABLE}
