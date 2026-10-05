"""The WebSocket API that feeds the Battery Care panel."""

from datetime import timedelta
import time
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.helpers.json import json_bytes
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.typing import (
    MockHAClientWebSocket,
    WebSocketGenerator,
)

from custom_components.battery_care.const import DOMAIN
from custom_components.battery_care.core.models import BatteryClass, Importance
from custom_components.battery_care.core.policy import DeviceMode
from custom_components.battery_care.view import API_VERSION, snapshot
from custom_components.battery_care.websocket import PATCH_INTERVAL

from .common import (
    BATTERY,
    add_device,
    add_entity,
    pass_rebuild_cooldown,
    setup_battery_care,
)

SNAPSHOT_BUDGET = 0.05
SNAPSHOT_MAX_BYTES = 300_000


async def next_event(client: MockHAClientWebSocket) -> dict[str, Any]:
    """Return the payload of the next event."""
    message = await client.receive_json()
    assert message["type"] == "event", message
    event: dict[str, Any] = message["event"]
    return event


async def subscribe(client: MockHAClientWebSocket) -> dict[str, Any]:
    """Subscribe and return the first snapshot."""
    await client.send_json_auto_id({"type": "battery_care/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    return await next_event(client)


async def assert_nothing_pending(client: MockHAClientWebSocket) -> None:
    """Messages arrive in order: a pong first means nothing else was sent."""
    await client.send_json_auto_id({"type": "ping"})
    assert (await client.receive_json())["type"] == "pong"


async def pass_patch_interval(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Let a coalesced message go."""
    freezer.tick(timedelta(seconds=PATCH_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def by_key(devices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index device views by key."""
    return {device["key"]: device for device in devices}


async def test_a_panel_gets_every_battery_and_a_summary(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """The backend decides the status, the attention flag and the counts."""
    area = ar.async_get(hass).async_create("Entrance")
    door = add_device(hass, "Front Door", area_id=area.id)
    add_entity(hass, "door_battery", "8", device_id=door.id, attributes=BATTERY)
    remote = add_device(hass, "Remote")
    add_entity(hass, "remote_battery", "64", device_id=remote.id, attributes=BATTERY)
    await setup_battery_care(hass)
    client = await hass_ws_client(hass)

    message = await subscribe(client)

    assert message["api"] == API_VERSION
    assert message["type"] == "snapshot"
    assert message["ready"] is True
    assert message["summary"] == {
        "total": 2,
        "monitored": 2,
        "healthy": 1,
        "attention": 1,
        "critical": 1,
        "low": 0,
        "not_responding": 0,
        "unknown": 0,
    }
    assert by_key(message["devices"]) == {
        f"d:{door.id}": {
            "key": f"d:{door.id}",
            "name": "Front Door",
            "area": "Entrance",
            "level": 8,
            "status": "critical",
            "attention": True,
            "battery": None,
            "battery_class": "unknown",
            "importance": "normal",
        },
        f"d:{remote.id}": {
            "key": f"d:{remote.id}",
            "name": "Remote",
            "area": None,
            "level": 64,
            "status": "ok",
            "attention": False,
            "battery": None,
            "battery_class": "unknown",
            "importance": "normal",
        },
    }


async def test_level_changes_are_coalesced(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Several changes within the interval make one patch."""
    door = add_device(hass, "Front Door")
    entity_id = add_entity(
        hass, "door_battery", "80", device_id=door.id, attributes=BATTERY
    )
    await setup_battery_care(hass)
    client = await hass_ws_client(hass)
    await subscribe(client)

    hass.states.async_set(entity_id, "30", BATTERY)
    hass.states.async_set(entity_id, "15", BATTERY)
    await pass_patch_interval(hass, freezer)

    message = await next_event(client)
    assert message["type"] == "patch"
    assert [device["level"] for device in message["devices"]] == [15]
    assert message["devices"][0]["status"] == "low"
    assert message["summary"]["low"] == 1
    await assert_nothing_pending(client)

    # An attribute change does not change the reading.
    hass.states.async_set(entity_id, "15", {**BATTERY, "voltage": 2.9})
    await pass_patch_interval(hass, freezer)
    await assert_nothing_pending(client)


async def test_new_batteries_and_choices_send_a_new_snapshot(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Changes that can touch every device resend everything."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "25", device_id=door.id, attributes=BATTERY)
    manager = await setup_battery_care(hass)
    client = await hass_ws_client(hass)
    await subscribe(client)

    add_entity(hass, "remote_battery", "64", attributes=BATTERY)
    await pass_rebuild_cooldown(hass, freezer)
    await pass_patch_interval(hass, freezer)
    message = await next_event(client)
    assert message["type"] == "snapshot"
    assert len(message["devices"]) == 2

    manager.async_update_settings({"low_threshold": 30})
    manager.async_configure_device(
        f"d:{door.id}", mode=DeviceMode.AUTOMATIC, importance=Importance.CRITICAL
    )
    await pass_patch_interval(hass, freezer)
    message = await next_event(client)
    assert message["type"] == "snapshot"
    door_view = by_key(message["devices"])[f"d:{door.id}"]
    assert door_view["status"] == "low"
    assert door_view["importance"] == "critical"
    await assert_nothing_pending(client)


async def test_the_snapshot_tells_when_discovery_has_not_run(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """While Home Assistant starts, an empty list does not mean no battery."""
    add_entity(hass, "door_battery", "50", attributes=BATTERY)
    hass.set_state(CoreState.starting)
    await setup_battery_care(hass)
    client = await hass_ws_client(hass)

    message = await subscribe(client)
    assert message["ready"] is False
    assert message["devices"] == []

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    await pass_patch_interval(hass, freezer)
    message = await next_event(client)
    assert message["ready"] is True
    assert len(message["devices"]) == 1


async def test_unsubscribing_stops_the_feed(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A change waiting to be sent is dropped too."""
    entity_id = add_entity(hass, "door_battery", "80", attributes=BATTERY)
    await setup_battery_care(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "battery_care/subscribe"})
    subscription = (await client.receive_json())["id"]
    await next_event(client)

    hass.states.async_set(entity_id, "50", BATTERY)
    await client.send_json_auto_id(
        {"type": "unsubscribe_events", "subscription": subscription}
    )
    assert (await client.receive_json())["success"]
    await pass_patch_interval(hass, freezer)

    await assert_nothing_pending(client)


async def test_unloading_closes_the_feed(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The panel is told, can unsubscribe cleanly, and waits for a new entry."""
    entity_id = add_entity(hass, "door_battery", "80", attributes=BATTERY)
    await setup_battery_care(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "battery_care/subscribe"})
    subscription = (await client.receive_json())["id"]
    await next_event(client)

    hass.states.async_set(entity_id, "50", BATTERY)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await next_event(client) == {"api": API_VERSION, "type": "closed"}
    await pass_patch_interval(hass, freezer)
    await assert_nothing_pending(client)

    await client.send_json_auto_id(
        {"type": "unsubscribe_events", "subscription": subscription}
    )
    assert (await client.receive_json())["success"]
    await client.send_json_auto_id({"type": "battery_care/subscribe"})
    response = await client.receive_json()
    assert response["error"]["code"] == "not_loaded"
    await client.send_json_auto_id({"type": "battery_care/device/get", "key": "d:x"})
    response = await client.receive_json()
    assert response["error"]["code"] == "not_loaded"


@pytest.mark.parametrize(
    "message",
    [
        {"type": "battery_care/subscribe", "since": 0},
        {"type": "battery_care/device/get"},
        {"type": "battery_care/device/get", "key": ""},
        {"type": "battery_care/device/get", "key": 12},
        {"type": "battery_care/device/get", "key": "s:" + "x" * 256},
        {"type": "battery_care/device/get", "key": "d:x", "extra": True},
    ],
)
async def test_malformed_messages_are_refused(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    message: dict[str, Any],
) -> None:
    """Types, lengths and unknown keys are all checked."""
    await setup_battery_care(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(message)
    response = await client.receive_json()

    assert response["success"] is False
    assert response["error"]["code"] == "invalid_format"


async def test_device_details(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """The sheet gets the sources, the effective policy and the explanations."""
    await async_get_integration(hass, "zha")
    lock = add_device(hass, "Front Door")
    level_id = add_entity(
        hass, "door_battery", "8", device_id=lock.id, attributes=BATTERY
    )
    add_entity(hass, "door_lock", "locked", domain="lock", device_id=lock.id)
    yaml_id = "sensor.garden_battery"
    hass.states.async_set(yaml_id, "unavailable", BATTERY)
    manager = await setup_battery_care(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": "battery_care/device/get", "key": f"d:{lock.id}"}
    )
    response = await client.receive_json()
    assert response["success"], response
    details = response["result"]
    assert details["api"] == API_VERSION
    assert details["device"]["status"] == "critical"
    assert details["device"]["importance"] == "important"
    assert details["integration"] == "Zigbee Home Automation"
    assert details["class_reason"] == "default"
    assert details["importance_source"] == "suggested"
    assert details["mode"] == "automatic"
    assert details["alerts"] is True
    assert (details["low_threshold"], details["critical_threshold"]) == (20, 10)
    assert details["stable"] is True
    assert dt_util.parse_datetime(details["last_report"]) is not None
    assert details["sources"] == [
        {"entity_id": level_id, "kind": "level", "name": "door battery", "state": "8"}
    ]

    manager.async_configure_device(
        f"d:{lock.id}",
        mode=DeviceMode.IGNORED,
        importance=Importance.LOW,
        battery_class=BatteryClass.REPLACEABLE,
    )
    await client.send_json_auto_id(
        {"type": "battery_care/device/get", "key": f"d:{lock.id}"}
    )
    details = (await client.receive_json())["result"]
    assert details["device"]["status"] == "ignored"
    assert details["device"]["attention"] is False
    assert details["class_reason"] == "user"
    assert details["importance_source"] == "user"
    assert details["mode"] == "ignored"
    assert details["alerts"] is False

    await client.send_json_auto_id(
        {"type": "battery_care/device/get", "key": f"s:{yaml_id}"}
    )
    details = (await client.receive_json())["result"]
    # Unavailable from the start: no data yet, and still within the grace period.
    assert details["device"]["status"] == "unknown"
    assert details["integration"] is None
    assert details["stable"] is False
    assert details["last_report"] is None
    assert details["importance_source"] == "default"

    await client.send_json_auto_id(
        {"type": "battery_care/device/get", "key": "d:missing"}
    )
    assert (await client.receive_json())["error"]["code"] == "not_found"


async def test_an_integration_that_is_not_loaded_shows_its_domain(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """The name of the integration is only known once it has loaded."""
    door = add_device(hass, "Front Door", integration="acme")
    add_entity(
        hass,
        "door_battery",
        "80",
        platform="acme",
        device_id=door.id,
        attributes=BATTERY,
    )
    await setup_battery_care(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": "battery_care/device/get", "key": f"d:{door.id}"}
    )

    assert (await client.receive_json())["result"]["integration"] == "acme"


async def test_users_who_are_not_admins_can_read(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Looking at batteries needs no administrator rights."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "80", device_id=door.id, attributes=BATTERY)
    await setup_battery_care(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)

    assert len((await subscribe(client))["devices"]) == 1
    await client.send_json_auto_id(
        {"type": "battery_care/device/get", "key": f"d:{door.id}"}
    )
    assert (await client.receive_json())["success"]


async def test_a_large_snapshot_is_small_and_quick(hass: HomeAssistant) -> None:
    """500 battery devices fit the snapshot budget."""
    entry = MockConfigEntry(domain="zha")
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    for i in range(500):
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={("zha", f"dev{i}")},
            name=f"Living room motion sensor {i}",
        )
        add_entity(
            hass,
            f"dev{i}_battery",
            str(i % 101),
            device_id=device.id,
            attributes=BATTERY,
        )
    manager = await setup_battery_care(hass)

    started = time.perf_counter()
    payload = json_bytes(snapshot(hass, manager))
    elapsed = time.perf_counter() - started

    assert len(manager.inventory.devices) == 500
    assert elapsed < SNAPSHOT_BUDGET
    assert len(payload) < SNAPSHOT_MAX_BYTES
