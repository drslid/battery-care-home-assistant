"""Battery Care: battery monitoring and maintenance for Home Assistant."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .manager import BatteryCareManager

type BatteryCareConfigEntry = ConfigEntry[BatteryCareManager]


async def async_setup_entry(hass: HomeAssistant, entry: BatteryCareConfigEntry) -> bool:
    """Set up Battery Care from its config entry."""
    manager = BatteryCareManager(hass)
    entry.runtime_data = manager
    manager.async_start()
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BatteryCareConfigEntry
) -> bool:
    """Unload Battery Care."""
    entry.runtime_data.async_shutdown()
    return True
