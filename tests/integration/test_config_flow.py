"""Adding Battery Care from Devices & Services."""

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.battery_care.const import DOMAIN, NAME

from .common import BATTERY, add_device, add_entity


def add_phone(hass: HomeAssistant, name: str) -> str:
    """Register a mobile app device that can receive pushes."""
    MockConfigEntry(
        domain="mobile_app", title=name, data={"device_name": name}
    ).add_to_hass(hass)
    service = f"mobile_app_{name.lower().replace(' ', '_')}"
    async_mock_service(hass, "notify", service)
    return service


async def test_one_click_creates_the_entry(hass: HomeAssistant) -> None:
    """The defaults work as they are; the flow reports what it found."""
    door = add_device(hass, "Front Door")
    add_entity(hass, "door_battery", "78", device_id=door.id, attributes=BATTERY)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["data_schema"] is not None
    assert list(result["data_schema"].schema) == [
        "digest_time",
        "quiet_hours",
        "quiet_start",
        "quiet_end",
    ]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {
        "settings": {
            "notify_targets": [],
            "digest_minute": 1080,
            "quiet_hours": True,
            "quiet_start_minute": 1320,
            "quiet_end_minute": 480,
        }
    }
    assert result["description"] == "devices_found"
    assert result["description_placeholders"] == {
        "count": "1",
        "panel_url": "/battery-care",
    }
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].state is ConfigEntryState.LOADED


async def test_choices_at_setup_become_the_settings(hass: HomeAssistant) -> None:
    """Phones, the digest time and quiet hours chosen at setup are used."""
    service = add_phone(hass, "Pixel 8")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["data_schema"] is not None
    assert "phones" in result["data_schema"].schema
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "phones": [service],
            "digest_time": "09:30:00",
            "quiet_hours": True,
            "quiet_start": "23:00:00",
            "quiet_end": "07:15:00",
        },
    )
    await hass.async_block_till_done()

    (entry,) = hass.config_entries.async_entries(DOMAIN)
    settings = entry.runtime_data.settings
    assert settings.notify_targets == (service,)
    assert (settings.digest_minute, settings.quiet_start_minute) == (570, 1380)
    assert settings.quiet_end_minute == 435


async def test_quiet_hours_need_two_different_times(hass: HomeAssistant) -> None:
    """The form is shown again with an error, and the choices are kept."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    choices = {
        "digest_time": "18:00:00",
        "quiet_hours": True,
        "quiet_start": "22:00:00",
        "quiet_end": "22:00:00",
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], choices)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"quiet_end": "quiet_hours_empty"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**choices, "quiet_hours": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_a_second_entry_is_refused(hass: HomeAssistant) -> None:
    """Battery Care exists once per Home Assistant instance."""
    MockConfigEntry(domain=DOMAIN, title=NAME).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
