"""The alert engine at work in Home Assistant: events, timers and restarts."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import area_registry as ar
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.battery_care.core.runtime import Severity
from custom_components.battery_care.core.status import Status
from custom_components.battery_care.manager import (
    EVENT_ALERT,
    EVENT_RECOVERED,
    STARTUP_WINDOW,
)
from custom_components.battery_care.storage import STATE_KEY

from .common import (
    BATTERY,
    add_device,
    add_entity,
    advance,
    finish_first_run,
    setup_battery_care,
)


def payloads(events: list[Event[Any]]) -> list[dict[str, Any]]:
    """Return the data of the captured events, and forget them."""
    data = [dict(event.data) for event in events]
    events.clear()
    return data


async def test_crossing_a_threshold_fires_one_alert(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """One event per transition, with everything an automation needs."""
    area = ar.async_get(hass).async_create("Entrance")
    door = add_device(hass, "Front Door", area_id=area.id)
    entity_id = add_entity(
        hass, "door_battery", "50", device_id=door.id, attributes=BATTERY
    )
    await setup_battery_care(hass)
    await finish_first_run(hass, freezer)
    alerts = async_capture_events(hass, EVENT_ALERT)
    recoveries = async_capture_events(hass, EVENT_RECOVERED)

    hass.states.async_set(entity_id, "15", BATTERY)
    hass.states.async_set(entity_id, "14", BATTERY)
    await hass.async_block_till_done()

    assert payloads(alerts) == [
        {
            "version": 1,
            "device_key": f"d:{door.id}",
            "device_id": door.id,
            "entity_id": entity_id,
            "name": "Front Door",
            "area": "Entrance",
            "severity": "low",
            "previous_severity": "normal",
            "level": 15,
            "reminder": False,
            "battery_type": None,
            "battery_quantity": None,
            "importance": "normal",
        }
    ]

    hass.states.async_set(entity_id, "30", BATTERY)
    await hass.async_block_till_done()

    assert payloads(alerts) == []
    assert payloads(recoveries) == [
        {
            "version": 1,
            "device_key": f"d:{door.id}",
            "device_id": door.id,
            "previous_severity": "low",
            "level": 30,
        }
    ]


async def test_the_first_run_is_silent(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Existing problems are taken as they are; later changes are told."""
    entity_id = add_entity(hass, "door_battery", "5", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    alerts = async_capture_events(hass, EVENT_ALERT)
    (key,) = manager.inventory.devices

    assert manager.status(key) is Status.CRITICAL
    hass.states.async_set(entity_id, "30", BATTERY)
    hass.states.async_set(entity_id, "15", BATTERY)
    await hass.async_block_till_done()
    assert payloads(alerts) == []

    await finish_first_run(hass, freezer)
    await advance(hass, freezer, timedelta(seconds=20))
    assert hass_storage[STATE_KEY]["data"]["baseline_done"] is True

    hass.states.async_set(entity_id, "5", BATTERY)
    await hass.async_block_till_done()
    assert [alert["severity"] for alert in payloads(alerts)] == ["critical"]


async def test_not_responding_after_the_grace_period(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A day without any source; back once the device reports again."""
    entity_id = add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    await finish_first_run(hass, freezer)
    alerts = async_capture_events(hass, EVENT_ALERT)
    recoveries = async_capture_events(hass, EVENT_RECOVERED)
    (key,) = manager.inventory.devices

    hass.states.async_set(entity_id, "unavailable", BATTERY)
    await advance(hass, freezer, timedelta(hours=23))
    assert payloads(alerts) == []
    assert manager.status(key) is Status.OK

    await advance(hass, freezer, timedelta(hours=1))
    assert [alert["severity"] for alert in payloads(alerts)] == ["not_responding"]
    assert manager.status(key) is Status.NOT_RESPONDING

    hass.states.async_set(entity_id, "48", BATTERY)
    await hass.async_block_till_done()
    assert [event["previous_severity"] for event in payloads(recoveries)] == [
        "not_responding"
    ]


async def test_a_restart_while_low_tells_nothing_new(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The persisted state matches the reading after the restart."""
    entity_id = add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    await finish_first_run(hass, freezer)
    hass.states.async_set(entity_id, "15", BATTERY)
    await hass.async_block_till_done()
    (entry,) = hass.config_entries.async_entries("battery_care")
    alerts = async_capture_events(hass, EVENT_ALERT)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, freezer, STARTUP_WINDOW)

    manager = entry.runtime_data
    (key,) = manager.inventory.devices
    assert manager.state.devices[key].severity is Severity.LOW
    assert manager.state.baseline_done
    assert payloads(alerts) == []


async def test_a_silent_device_becomes_stale(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Reports during the startup window prove nothing; later ones do."""
    entity_id = add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    alerts = async_capture_events(hass, EVENT_ALERT)
    recoveries = async_capture_events(hass, EVENT_RECOVERED)
    (key,) = manager.inventory.devices

    await advance(hass, freezer, timedelta(minutes=5))
    hass.states.async_set(entity_id, "50", BATTERY, force_update=True)
    await advance(hass, freezer, timedelta(days=7) - timedelta(minutes=5))
    await advance(hass, freezer, timedelta(hours=1))

    assert manager.status(key) is Status.STALE
    assert [alert["severity"] for alert in payloads(alerts)] == ["stale"]

    hass.states.async_set(entity_id, "50", BATTERY, force_update=True)
    await advance(hass, freezer, timedelta(hours=1))
    assert manager.status(key) is Status.OK
    assert [event["previous_severity"] for event in payloads(recoveries)] == ["stale"]


async def test_new_thresholds_apply_at_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Raising the low threshold makes a battery low right away."""
    add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    await finish_first_run(hass, freezer)
    alerts = async_capture_events(hass, EVENT_ALERT)

    manager.async_update_settings({"low_threshold": 60, "critical_threshold": 30})
    await hass.async_block_till_done()

    assert [alert["severity"] for alert in payloads(alerts)] == ["low"]
