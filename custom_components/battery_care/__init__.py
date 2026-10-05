"""Battery Care: battery monitoring and maintenance for Home Assistant."""

from functools import partial

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, UnsupportedStorageVersionError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import panel, websocket
from .const import DOMAIN, PANEL_URL_PATH
from .manager import BatteryCareConfigEntry, BatteryCareManager
from .storage import async_remove_stores

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the panel files and register the WebSocket commands, once per run."""
    await panel.async_register_static_path(hass)
    websocket.async_register_commands(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BatteryCareConfigEntry) -> bool:
    """Set up Battery Care from its config entry."""
    manager = BatteryCareManager(hass)
    try:
        await manager.async_load()
    except UnsupportedStorageVersionError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="storage_too_new"
        ) from err
    try:
        await panel.async_register_panel(hass)
    except ValueError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="panel_taken",
            translation_placeholders={"path": f"/{PANEL_URL_PATH}"},
        ) from err
    entry.async_on_unload(partial(panel.async_remove_panel, hass))
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    manager.async_start()
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BatteryCareConfigEntry
) -> bool:
    """Unload Battery Care, writing pending changes first."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_unload()
    return True


async def async_remove_entry(
    hass: HomeAssistant, entry: BatteryCareConfigEntry
) -> None:
    """Delete Battery Care's data when the integration is removed."""
    await async_remove_stores(hass)
