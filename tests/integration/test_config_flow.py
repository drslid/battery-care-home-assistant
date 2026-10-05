"""Adding Battery Care from Devices & Services."""

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.battery_care.const import DOMAIN, NAME

from .common import BATTERY, add_device, add_entity


async def test_one_confirmation_creates_the_entry(hass: HomeAssistant) -> None:
    """The flow asks for nothing but a confirmation, then reports what it found."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "78", device_id=door.id, attributes=BATTERY)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["data_schema"] is None

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {}
    assert result["description"] == "devices_found"
    assert result["description_placeholders"] == {
        "count": "1",
        "panel_url": "/battery-care",
    }
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].state is ConfigEntryState.LOADED


async def test_a_second_entry_is_refused(hass: HomeAssistant) -> None:
    """Battery Care exists once per Home Assistant instance."""
    MockConfigEntry(domain=DOMAIN, title=NAME).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
