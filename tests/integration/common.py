"""Helpers that populate Home Assistant registries for the tests."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.battery_care.adapters.tracking import REBUILD_COOLDOWN
from custom_components.battery_care.const import DOMAIN, NAME
from custom_components.battery_care.manager import BatteryCareManager

BATTERY = {"device_class": "battery", "unit_of_measurement": "%"}


def add_device(
    hass: HomeAssistant,
    name: str,
    *,
    integration: str = "zha",
    area_id: str | None = None,
) -> dr.DeviceEntry:
    """Register a device owned by a config entry of the given integration."""
    entry = MockConfigEntry(domain=integration)
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(integration, name)}, name=name
    )
    if area_id is None:
        return device
    updated = registry.async_update_device(device.id, area_id=area_id)
    assert updated is not None
    return updated


def add_entity(
    hass: HomeAssistant,
    object_id: str,
    state: str,
    *,
    domain: str = "sensor",
    platform: str = "zha",
    device_id: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> str:
    """Register an entity and give it a state with the given attributes."""
    attributes = attributes or {}
    entry = er.async_get(hass).async_get_or_create(
        domain,
        platform,
        object_id,
        suggested_object_id=object_id,
        device_id=device_id,
        original_device_class=attributes.get("device_class"),
        unit_of_measurement=attributes.get("unit_of_measurement"),
    )
    hass.states.async_set(entry.entity_id, state, attributes)
    return entry.entity_id


async def setup_battery_care(hass: HomeAssistant) -> BatteryCareManager:
    """Set up the integration and return its manager."""
    entry = MockConfigEntry(domain=DOMAIN, title=NAME)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager: BatteryCareManager = entry.runtime_data
    return manager


async def pass_rebuild_cooldown(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Let a debounced inventory rebuild run."""
    freezer.tick(timedelta(seconds=REBUILD_COOLDOWN + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
