"""Reading and changing settings from the panel: types, devices and permissions."""

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.typing import (
    MockHAClientWebSocket,
    WebSocketGenerator,
)

from .common import BATTERY, add_device, add_entity, setup_battery_care


async def call(client: MockHAClientWebSocket, **message: Any) -> dict[str, Any]:
    """Send a command and return the whole response."""
    await client.send_json_auto_id(message)
    response: dict[str, Any] = await client.receive_json()
    return response


async def test_the_settings_page_reads_every_class(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Global settings, limits, and each class with its devices and values."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "50", device_id=door.id, attributes=BATTERY)
    ups = add_device(hass, "UPS", integration="nut")
    add_entity(
        hass, "ups_battery", "100", platform="nut", device_id=ups.id, attributes=BATTERY
    )
    await setup_battery_care(hass)
    client = await hass_ws_client(hass)

    result = (await call(client, type="battery_care/settings/get"))["result"]

    assert result["settings"]["reminder_hours"] == 24
    assert result["limits"]["low_threshold"] == [1, 95]
    classes = {row["battery_class"]: row for row in result["classes"]}
    assert list(classes) == [
        "replaceable",
        "rechargeable",
        "robot",
        "vehicle",
        "ups",
        "home_battery",
        "unknown",
    ]
    assert classes["ups"] == {
        "battery_class": "ups",
        "devices": 1,
        "custom": False,
        "alerts_enabled": True,
        "low_threshold": 50,
        "critical_threshold": 20,
    }
    assert classes["unknown"]["devices"] == 1
    assert classes["vehicle"]["alerts_enabled"] is False
    assert result["ignored"] == []


async def test_changing_global_and_class_settings(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Changes are validated as a whole and apply to the batteries at once."""
    entity_id = add_entity(hass, "door_battery", "25", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    client = await hass_ws_client(hass)
    (key,) = manager.inventory.devices

    response = await call(
        client,
        type="battery_care/class/update",
        battery_class="unknown",
        changes={"low_threshold": 30},
    )
    assert response["success"], response
    unknown = next(
        row
        for row in response["result"]["classes"]
        if row["battery_class"] == "unknown"
    )
    assert (unknown["low_threshold"], unknown["custom"]) == (30, True)
    assert manager.status(key).value == "low"

    response = await call(
        client, type="battery_care/settings/update", changes={"reminder_hours": 48}
    )
    assert response["result"]["settings"]["reminder_hours"] == 48

    refused = await call(
        client,
        type="battery_care/class/update",
        battery_class="unknown",
        changes={"critical_threshold": 40},
    )
    assert refused["error"] == {
        "code": "invalid_setting",
        "message": "critical_threshold: critical_not_below_low",
    }
    hass.states.async_set(entity_id, "34", BATTERY)
    await hass.async_block_till_done()
    assert manager.status(key).value == "low"


async def test_ignoring_and_customizing_a_device(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Ignore silences a battery; Customize keeps only what differs."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "15", device_id=door.id, attributes=BATTERY)
    manager = await setup_battery_care(hass)
    client = await hass_ws_client(hass)
    key = f"d:{door.id}"
    assert manager.summary.attention == 1

    ignored = await call(
        client, type="battery_care/device/update", key=key, mode="ignored"
    )
    assert ignored["result"]["device"]["status"] == "ignored"
    assert manager.summary.attention == 0
    settings = (await call(client, type="battery_care/settings/get"))["result"]
    assert settings["ignored"] == [{"key": key, "name": "Front Door"}]

    custom = await call(
        client,
        type="battery_care/device/update",
        key=key,
        mode="custom",
        overrides={"low_threshold": 10, "critical_threshold": 5, "reminder_hours": 24},
        importance="critical",
        battery_class="replaceable",
    )
    details = custom["result"]
    assert details["mode"] == "custom"
    assert details["overrides"] == {"low_threshold": 10, "critical_threshold": 5}
    assert details["inherited"]["low_threshold"] == 20
    assert (details["chosen_class"], details["detected_class"]) == (
        "replaceable",
        "unknown",
    )
    assert (details["chosen_importance"], details["suggested_importance"]) == (
        "critical",
        "normal",
    )
    assert details["device"]["status"] == "ok"

    automatic = await call(
        client, type="battery_care/device/update", key=key, mode="automatic"
    )
    assert automatic["result"]["chosen_class"] is None
    assert manager.device_config(key).is_default


async def test_invalid_updates_are_refused(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """Unknown devices, keys and values change nothing."""
    add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    client = await hass_ws_client(hass)
    (key,) = manager.inventory.devices

    missing = await call(
        client, type="battery_care/device/update", key="d:missing", mode="ignored"
    )
    assert missing["error"]["code"] == "not_found"
    not_overridable = await call(
        client,
        type="battery_care/device/update",
        key=key,
        mode="custom",
        overrides={"hysteresis": 2},
    )
    assert not_overridable["error"]["code"] == "invalid_format"
    automatic_with_overrides = await call(
        client,
        type="battery_care/device/update",
        key=key,
        mode="automatic",
        overrides={"low_threshold": 30},
    )
    assert automatic_with_overrides["error"]["message"] == (
        "overrides: overrides_need_custom_mode"
    )
    out_of_range = await call(
        client, type="battery_care/settings/update", changes={"stale_days": 500}
    )
    assert out_of_range["error"]["message"] == "stale_days: out_of_range"
    wrong_type = await call(
        client, type="battery_care/settings/update", changes={"stale_days": "week"}
    )
    assert wrong_type["error"]["code"] == "invalid_format"
    assert manager.device_config(key).is_default
    assert manager.settings.stale_days == 7


async def test_only_admins_can_change_settings(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Other users read the settings but cannot change them."""
    add_entity(hass, "door_battery", "50", attributes=BATTERY)
    manager = await setup_battery_care(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    (key,) = manager.inventory.devices

    assert (await call(client, type="battery_care/settings/get"))["success"]
    for message in (
        {"type": "battery_care/settings/update", "changes": {"stale_days": 3}},
        {
            "type": "battery_care/class/update",
            "battery_class": "ups",
            "changes": {"alerts_enabled": False},
        },
        {"type": "battery_care/device/update", "key": key, "mode": "ignored"},
    ):
        response = await call(client, **message)
        assert response["error"]["code"] == "unauthorized", message
    assert manager.device_config(key).is_default


async def test_settings_need_a_loaded_entry(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """After an unload, the commands say so instead of failing."""
    await setup_battery_care(hass)
    (entry,) = hass.config_entries.async_entries("battery_care")
    assert await hass.config_entries.async_unload(entry.entry_id)
    client = await hass_ws_client(hass)

    for message in (
        {"type": "battery_care/settings/get"},
        {"type": "battery_care/settings/update", "changes": {}},
        {"type": "battery_care/class/update", "battery_class": "ups", "changes": {}},
        {"type": "battery_care/device/update", "key": "d:door", "mode": "ignored"},
    ):
        response = await call(client, **message)
        assert response["error"]["code"] == "not_loaded", message
