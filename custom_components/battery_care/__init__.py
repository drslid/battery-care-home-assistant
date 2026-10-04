"""Battery Care: battery monitoring and maintenance for Home Assistant."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, UnsupportedStorageVersionError

from .const import DOMAIN
from .manager import BatteryCareManager
from .storage import async_remove_stores

type BatteryCareConfigEntry = ConfigEntry[BatteryCareManager]


async def async_setup_entry(hass: HomeAssistant, entry: BatteryCareConfigEntry) -> bool:
    """Set up Battery Care from its config entry."""
    manager = BatteryCareManager(hass)
    try:
        await manager.async_load()
    except UnsupportedStorageVersionError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="storage_too_new"
        ) from err
    entry.runtime_data = manager
    manager.async_start()
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BatteryCareConfigEntry
) -> bool:
    """Unload Battery Care, writing pending changes first."""
    await entry.runtime_data.async_unload()
    return True


async def async_remove_entry(
    hass: HomeAssistant, entry: BatteryCareConfigEntry
) -> None:
    """Delete Battery Care's data when the integration is removed."""
    await async_remove_stores(hass)
