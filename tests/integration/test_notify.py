"""Notifications: critical batteries at once, the rest in a daily digest."""

from datetime import datetime, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_get_persistent_notifications,
    async_mock_service,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.battery_care.manager import BatteryCareManager

from .common import (
    BATTERY,
    add_device,
    add_entity,
    finish_first_run,
    setup_battery_care,
)

PARIS = ZoneInfo("Europe/Paris")
NOON = datetime(2026, 10, 6, 12, 0, tzinfo=PARIS)


async def at(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime
) -> None:
    """Move the clock to a local time and run the timers that are due."""
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()


def add_phone(hass: HomeAssistant, name: str = "Pixel") -> list[ServiceCall]:
    """Register a phone with the mobile app, and capture its pushes."""
    MockConfigEntry(
        domain="mobile_app", title=name, data={"device_name": name}
    ).add_to_hass(hass)
    return async_mock_service(hass, "notify", f"mobile_app_{name.lower()}")


def add_battery(hass: HomeAssistant, name: str, level: str) -> str:
    """Add a battery device with a name, and return its battery entity."""
    device = add_device(hass, name)
    return add_entity(
        hass,
        f"{name.lower().replace(' ', '_')}_battery",
        level,
        device_id=device.id,
        attributes=BATTERY,
    )


@pytest.fixture
async def started(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> tuple[BatteryCareManager, str, str, list[ServiceCall]]:
    """Battery Care at noon in Paris, past its first run, with one phone."""
    await hass.config.async_set_time_zone("Europe/Paris")
    freezer.move_to(NOON)
    calls = add_phone(hass)
    entity_id = add_battery(hass, "Front Door", "50")
    manager = await setup_battery_care(hass)
    await finish_first_run(hass, freezer)
    manager.async_update_settings({"notify_targets": ["mobile_app_pixel"]})
    (key,) = manager.inventory.devices
    return manager, key, entity_id, calls


def notifications(hass: HomeAssistant) -> dict[str, str]:
    """Return the Home Assistant notifications, by id."""
    return {
        notification_id: notification["message"]
        for notification_id, notification in async_get_persistent_notifications(
            hass
        ).items()
    }


async def test_a_critical_battery_is_told_at_once(
    hass: HomeAssistant,
    started: tuple[BatteryCareManager, str, str, list[ServiceCall]],
) -> None:
    """In Home Assistant and on the phone, linked to the battery's sheet."""
    _, key, entity_id, calls = started

    hass.states.async_set(entity_id, "5", BATTERY)
    await hass.async_block_till_done()

    tag = f"battery_care_{key}"
    assert notifications(hass) == {
        tag: "Front Door: battery critical, 5% left\n\n"
        "[Open Battery Care](/battery-care)"
    }
    assert [call.data for call in calls] == [
        {
            "title": "Battery Care",
            "message": "Front Door: battery critical, 5% left",
            "data": {
                "tag": tag,
                "url": f"/battery-care?device={key}",
                "clickAction": f"/battery-care?device={key}",
            },
        }
    ]

    hass.states.async_set(entity_id, "80", BATTERY)
    await hass.async_block_till_done()
    assert tag not in notifications(hass)


async def test_everything_else_waits_for_the_daily_digest(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    started: tuple[BatteryCareManager, str, str, list[ServiceCall]],
) -> None:
    """At 18:00, one message about what changed during the day."""
    _, _, entity_id, calls = started
    other = add_battery(hass, "Remote", "60")
    await at(hass, freezer, NOON + timedelta(minutes=30))

    hass.states.async_set(entity_id, "15", BATTERY)
    hass.states.async_set(other, "unavailable", BATTERY)
    await hass.async_block_till_done()
    assert calls == []
    assert notifications(hass) == {}

    await at(hass, freezer, NOON.replace(hour=18))

    assert notifications(hass) == {
        "battery_care_digest": "Front Door: battery low, 15% left\n\n"
        "[Open Battery Care](/battery-care)"
    }
    assert [call.data["data"]["tag"] for call in calls] == ["battery_care_digest"]

    # The next day: the remote stopped responding a day ago, the door is fixed.
    hass.states.async_set(entity_id, "90", BATTERY)
    await hass.async_block_till_done()
    await at(hass, freezer, NOON.replace(hour=18) + timedelta(days=1))
    assert calls[-1].data["message"] == (
        "1 battery needs attention:\n• Remote: not responding\n\n"
        "Back to normal:\n• Front Door: back to normal"
    )


async def test_quiet_hours_hold_critical_alerts(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    started: tuple[BatteryCareManager, str, str, list[ServiceCall]],
) -> None:
    """A critical battery at night is told at 08:00."""
    _, key, entity_id, calls = started
    await at(hass, freezer, NOON.replace(hour=23))

    hass.states.async_set(entity_id, "5", BATTERY)
    await hass.async_block_till_done()
    assert calls == []

    await at(hass, freezer, NOON.replace(hour=8) + timedelta(days=1))

    assert [call.data["data"]["tag"] for call in calls] == [f"battery_care_{key}"]


async def test_held_alerts_go_out_together_after_a_restart(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    started: tuple[BatteryCareManager, str, str, list[ServiceCall]],
) -> None:
    """Two critical batteries at night make one push at 08:00, restart or not."""
    manager, _, entity_id, calls = started
    other = add_battery(hass, "Remote", "60")
    await at(hass, freezer, NOON.replace(hour=23))
    hass.states.async_set(entity_id, "5", BATTERY)
    hass.states.async_set(other, "4", BATTERY)
    await hass.async_block_till_done()
    assert len(manager.state.held) == 2

    (entry,) = hass.config_entries.async_entries("battery_care")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.state.held == manager.state.held
    await at(hass, freezer, NOON.replace(hour=8) + timedelta(days=1))

    assert [call.data["message"] for call in calls] == [
        "2 batteries need attention:\n"
        "• Front Door: battery critical, 5% left\n"
        "• Remote: battery critical, 4% left"
    ]
    assert calls[0].data["data"]["tag"] == "battery_care_alerts"
    assert entry.runtime_data.state.held == []


async def test_a_digest_due_in_quiet_hours_waits_for_their_end(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    started: tuple[BatteryCareManager, str, str, list[ServiceCall]],
) -> None:
    """A digest at 23:00 inside quiet hours goes out at 08:00 instead."""
    manager, _, entity_id, calls = started
    manager.async_update_settings({"digest_minute": 23 * 60})
    hass.states.async_set(entity_id, "15", BATTERY)
    await hass.async_block_till_done()

    await at(hass, freezer, NOON.replace(hour=23))
    assert calls == []
    await at(hass, freezer, NOON.replace(hour=8) + timedelta(days=1))

    assert [call.data["data"]["tag"] for call in calls] == ["battery_care_digest"]


async def test_a_snoozed_battery_is_not_told(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    started: tuple[BatteryCareManager, str, str, list[ServiceCall]],
) -> None:
    """Snoozing holds the digest line until the snooze ends."""
    manager, key, entity_id, calls = started
    hass.states.async_set(entity_id, "15", BATTERY)
    await hass.async_block_till_done()

    manager.async_snooze(key, NOON + timedelta(days=2))
    await at(hass, freezer, NOON.replace(hour=18))

    assert calls == []


async def test_a_failing_phone_is_reported_once_a_day(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    started: tuple[BatteryCareManager, str, str, list[ServiceCall]],
) -> None:
    """Delivery problems never stop Battery Care, and do not flood the log."""
    manager, _, entity_id, _ = started

    async def refuse(call: ServiceCall) -> None:
        raise HomeAssistantError("phone unreachable")

    hass.services.async_register("notify", "mobile_app_broken", refuse)
    manager.async_update_settings({"notify_targets": ["mobile_app_broken"]})

    with caplog.at_level(logging.WARNING):
        for level in ("5", "50", "4"):
            hass.states.async_set(entity_id, level, BATTERY)
            await hass.async_block_till_done()

    assert caplog.text.count("Could not notify mobile_app_broken") == 1


async def test_the_first_run_sends_one_summary(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Existing problems are told once, when the silent first run ends."""
    await hass.config.async_set_time_zone("Europe/Paris")
    freezer.move_to(NOON)
    add_battery(hass, "Front Door", "5")
    add_battery(hass, "Remote", "15")
    await setup_battery_care(hass)
    assert notifications(hass) == {}

    await finish_first_run(hass, freezer)

    assert notifications(hass)["battery_care_digest"].startswith(
        "2 batteries need attention:\n"
        "• Front Door: battery critical, 5% left\n"
        "• Remote: battery low, 15% left"
    )


async def test_commands_for_the_panel(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Phones listed in Settings, a test message, and a snooze on a battery."""
    calls = add_phone(hass)
    add_battery(hass, "Front Door", "50")
    manager = await setup_battery_care(hass)
    await finish_first_run(hass, freezer)
    (key,) = manager.inventory.devices
    manager.async_update_settings(
        {"notify_targets": ["mobile_app_pixel", "mobile_app_old"]}
    )
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "battery_care/settings/get"})
    view: dict[str, Any] = (await client.receive_json())["result"]
    assert view["targets"] == [
        {"service": "mobile_app_pixel", "name": "Pixel", "available": True},
        {"service": "mobile_app_old", "name": "mobile_app_old", "available": False},
    ]

    await client.send_json_auto_id({"type": "battery_care/notify/test"})
    result = (await client.receive_json())["result"]
    assert result["persistent"] is True
    assert result["phones"][0] == {
        "service": "mobile_app_pixel",
        "name": "Pixel",
        "error": None,
    }
    assert result["phones"][1]["error"]
    assert "battery_care_test" in notifications(hass)
    assert calls[-1].data["data"]["tag"] == "battery_care_test"

    await client.send_json_auto_id(
        {"type": "battery_care/device/snooze", "key": key, "days": 3}
    )
    details = (await client.receive_json())["result"]
    assert details["snoozed_until"] is not None
    await client.send_json_auto_id(
        {"type": "battery_care/device/snooze", "key": key, "days": 0}
    )
    assert (await client.receive_json())["result"]["snoozed_until"] is None
    await client.send_json_auto_id(
        {"type": "battery_care/device/snooze", "key": key, "days": 2}
    )
    assert (await client.receive_json())["error"]["code"] == "invalid_format"
