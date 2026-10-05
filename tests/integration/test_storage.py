"""Battery Care keeps the user's choices across restarts and cleans up after itself."""

from datetime import timedelta
import logging
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.battery_care.const import DOMAIN, NAME
from custom_components.battery_care.core.models import BatteryClass, Importance
from custom_components.battery_care.core.policy import DeviceMode
from custom_components.battery_care.core.runtime import Runtime, Severity
from custom_components.battery_care.core.settings import SettingsError
from custom_components.battery_care.manager import BatteryCareManager
from custom_components.battery_care.storage import (
    CONFIG_KEY,
    STATE_KEY,
    ConfigData,
    StateData,
    config_from_raw,
    state_from_raw,
)

from .common import BATTERY, add_device, add_entity, pass_rebuild_cooldown


def stored(
    key: str, data: Any, *, version: int = 1, minor_version: int = 1
) -> dict[str, Any]:
    """Return a storage file as Home Assistant writes it."""
    return {
        "version": version,
        "minor_version": minor_version,
        "key": key,
        "data": data,
    }


async def start(hass: HomeAssistant) -> tuple[MockConfigEntry, BatteryCareManager]:
    """Add and set up the entry."""
    entry = MockConfigEntry(domain=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, entry.runtime_data


async def restart(hass: HomeAssistant, entry: MockConfigEntry) -> BatteryCareManager:
    """Unload and set up the entry again, as a restart does."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager: BatteryCareManager = entry.runtime_data
    return manager


async def test_choices_survive_a_restart(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Global settings and device choices come back; only differences are stored."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "50", device_id=door.id, attributes=BATTERY)
    key = f"d:{door.id}"
    entry, manager = await start(hass)

    manager.async_update_settings({"low_threshold": 25})
    manager.async_configure_device(
        key,
        mode=DeviceMode.CUSTOM,
        overrides={"low_threshold": 30, "reminder_hours": 24},
        importance=Importance.CRITICAL,
    )
    manager.async_update_class(BatteryClass.UPS, {"critical_threshold": 30})
    manager = await restart(hass, entry)

    assert hass_storage[CONFIG_KEY]["data"] == {
        "settings": {"low_threshold": 25},
        "devices": {
            key: {
                "mode": "custom",
                "overrides": {"low_threshold": 30},
                "importance": "critical",
            }
        },
        "classes": {"ups": {"critical_threshold": 30}},
    }
    assert manager.settings.low_threshold == 25
    assert manager.effective_settings(key).low_threshold == 30
    assert manager.device_config(key).importance is Importance.CRITICAL
    assert manager.config.classes == {BatteryClass.UPS: {"critical_threshold": 30}}


async def test_changes_are_written_after_a_short_delay(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    """Writes are grouped, but a change reaches the disk within seconds."""
    _, manager = await start(hass)

    manager.async_update_settings({"stale_days": 14})
    assert CONFIG_KEY not in hass_storage

    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[CONFIG_KEY]["data"]["settings"] == {"stale_days": 14}


async def test_invalid_changes_change_nothing(hass: HomeAssistant) -> None:
    """Refused changes leave the settings and the stores untouched."""
    _, manager = await start(hass)

    with pytest.raises(SettingsError):
        manager.async_update_settings({"low_threshold": 5})
    with pytest.raises(SettingsError) as error:
        manager.async_configure_device("d:unknown", mode=DeviceMode.IGNORED)

    assert error.value.code == "unknown_device"
    assert manager.settings.low_threshold == 20


async def test_choosing_automatic_again_removes_the_device_record(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A device back to fully automatic leaves nothing in storage."""
    add_entity(hass, "door_battery", "50", attributes=BATTERY)
    entry, manager = await start(hass)
    (key,) = manager.inventory.devices

    manager.async_configure_device(key, mode=DeviceMode.IGNORED)
    manager.async_configure_device(key, mode=DeviceMode.AUTOMATIC)
    await restart(hass, entry)

    assert hass_storage[CONFIG_KEY]["data"]["devices"] == {}


async def test_built_in_class_values_are_not_stored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Setting a class back to its built-in values removes its record."""
    entry, manager = await start(hass)

    manager.async_update_class(BatteryClass.VEHICLE, {"alerts_enabled": True})
    assert manager.config.classes == {BatteryClass.VEHICLE: {"alerts_enabled": True}}
    settings = manager.async_update_class(
        BatteryClass.VEHICLE, {"alerts_enabled": False}
    )
    await restart(hass, entry)

    assert not settings.alerts_enabled
    assert hass_storage[CONFIG_KEY]["data"]["classes"] == {}


async def test_invalid_stored_values_fall_back_to_defaults(
    hass: HomeAssistant, hass_storage: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Data edited by hand or by other tools is validated on load, never trusted."""
    hass_storage[CONFIG_KEY] = stored(
        CONFIG_KEY,
        {
            "settings": {"low_threshold": "high", "reminder_hours": 48},
            "devices": {
                "d:door": {"mode": "custom", "overrides": {"low_threshold": 500}}
            },
        },
    )
    hass_storage[STATE_KEY] = stored(STATE_KEY, {"known": {"d:door": "Front Door"}})

    with caplog.at_level(logging.WARNING):
        _, manager = await start(hass)

    assert manager.settings.low_threshold == 20
    assert manager.settings.reminder_hours == 48
    assert manager.device_config("d:door").mode is DeviceMode.CUSTOM
    assert manager.device_config("d:door").overrides == {}
    assert (
        "Ignored invalid stored values, using defaults instead: "
        "settings.low_threshold, devices.d:door.overrides.low_threshold, known.d:door"
    ) in caplog.text


async def test_malformed_files_fall_back_to_defaults() -> None:
    """Whole sections of the wrong shape are reported and replaced."""
    assert config_from_raw(None) == (ConfigData(), [])
    assert config_from_raw(["settings"]) == (ConfigData(), ["*"])
    assert config_from_raw({"devices": ["d:door"]}) == (ConfigData(), ["devices.*"])
    data, problems = config_from_raw(
        {"devices": {"d:door": {"mode": "automatic"}, "d:hall": {"mode": "ignored"}}}
    )
    assert list(data.devices) == ["d:hall"]
    assert problems == []
    assert state_from_raw(None) == (StateData(), [])
    assert state_from_raw("known") == (StateData(), ["*"])
    assert state_from_raw({"devices": ["d:door"]}) == (StateData(), ["devices.*"])
    state, problems = state_from_raw(
        {
            "devices": {
                "d:door": {"severity": "low", "last_level": 17, "stale": "no"},
                "d:hall": "low",
            },
            "baseline_done": "yes",
        }
    )
    assert state == StateData(
        devices={"d:door": Runtime(severity=Severity.LOW, last_level=17.0)}
    )
    assert problems == ["devices.d:door.stale", "devices.d:hall", "baseline_done"]


async def test_data_from_a_newer_minor_version_is_read(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Minor versions only add fields, so an older Battery Care can still read them."""
    hass_storage[CONFIG_KEY] = stored(
        CONFIG_KEY,
        {"settings": {"low_threshold": 30}, "devices": {}, "added_later": True},
        minor_version=2,
    )

    entry, manager = await start(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert manager.settings.low_threshold == 30


async def test_data_from_a_newer_major_version_blocks_setup(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Rather than risk overwriting it, setup stops with an explanation."""
    hass_storage[CONFIG_KEY] = stored(CONFIG_KEY, {"settings": {}}, version=2)
    entry = MockConfigEntry(domain=DOMAIN, title=NAME)
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert hass_storage[CONFIG_KEY]["version"] == 2


async def test_removing_the_integration_deletes_its_data(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    """Uninstalling leaves nothing behind."""
    add_entity(hass, "door_battery", "50", attributes=BATTERY)
    entry, manager = await start(hass)
    manager.async_update_settings({"low_threshold": 25})
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert {CONFIG_KEY, STATE_KEY} <= hass_storage.keys()

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert CONFIG_KEY not in hass_storage
    assert STATE_KEY not in hass_storage


async def test_choices_of_a_removed_device_are_kept_for_30_days(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    """A device re-added within 30 days keeps its choices; after that they go."""
    entity_id = add_entity(hass, "door_battery", "50", attributes=BATTERY)
    entry, manager = await start(hass)
    (key,) = manager.inventory.devices
    manager.async_configure_device(key, mode=DeviceMode.IGNORED)

    er.async_get(hass).async_remove(entity_id)
    hass.states.async_remove(entity_id)
    await pass_rebuild_cooldown(hass, freezer)
    assert manager.device_config(key).mode is DeviceMode.IGNORED

    freezer.tick(timedelta(days=31))
    add_entity(hass, "remote_battery", "70", attributes=BATTERY)
    await pass_rebuild_cooldown(hass, freezer)
    assert manager.device_config(key).mode is DeviceMode.AUTOMATIC

    await restart(hass, entry)
    assert key not in hass_storage[CONFIG_KEY]["data"]["devices"]
    assert key not in hass_storage[STATE_KEY]["data"]["known"]


async def test_disabled_devices_keep_their_choices(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Disabling a device is not removing it: its choices are not forgotten."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "50", device_id=door.id, attributes=BATTERY)
    _, manager = await start(hass)
    key = f"d:{door.id}"
    manager.async_configure_device(key, mode=DeviceMode.IGNORED)

    er.async_get(hass).async_update_entity(
        "sensor.door_battery", disabled_by=er.RegistryEntryDisabler.USER
    )
    await pass_rebuild_cooldown(hass, freezer)
    freezer.tick(timedelta(days=31))
    add_entity(hass, "remote_battery", "70", attributes=BATTERY)
    await pass_rebuild_cooldown(hass, freezer)

    assert key not in manager.inventory.devices
    assert manager.device_config(key).mode is DeviceMode.IGNORED
