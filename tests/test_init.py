"""Loading, reloading and unloading Battery Care."""

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.battery_care.const import DOMAIN, NAME


def state_of(entry: ConfigEntry) -> ConfigEntryState:
    """Read the state afresh: it changes while the test awaits."""
    return entry.state


async def test_reload_and_unload_leave_no_listener_behind(hass: HomeAssistant) -> None:
    """Setting up and tearing down the entry is symmetrical."""
    entry = MockConfigEntry(domain=DOMAIN, title=NAME)
    entry.add_to_hass(hass)

    # The first setup also loads the integration itself; measure after it.
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    baseline = hass.bus.async_listeners()

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert state_of(entry) is ConfigEntryState.LOADED

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert state_of(entry) is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert state_of(entry) is ConfigEntryState.NOT_LOADED
    assert hass.bus.async_listeners() == baseline
