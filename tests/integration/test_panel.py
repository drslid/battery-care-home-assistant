"""The Battery Care panel in the Home Assistant sidebar."""

from http import HTTPStatus

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.battery_care.const import DOMAIN, NAME, PANEL_URL_PATH
from custom_components.battery_care.panel import bundle_version

from .common import setup_battery_care


def panels(hass: HomeAssistant) -> dict[str, frontend.Panel]:
    """Return the panels the frontend lists."""
    return hass.data.get(frontend.DATA_PANELS, {})


async def test_every_user_gets_the_panel(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """The sidebar entry loads the bundle, under a URL that changes with it."""
    await setup_battery_care(hass)

    panel = panels(hass)[PANEL_URL_PATH].to_response()
    assert panel["title"] == NAME
    assert panel["icon"] == "mdi:battery-heart-variant"
    assert panel["require_admin"] is False
    config = panel["config"]
    assert config is not None
    custom = config["_panel_custom"]
    assert custom["name"] == "battery-care-panel"
    assert custom["embed_iframe"] is False
    version = await hass.async_add_executor_job(bundle_version)
    assert custom["module_url"] == (
        f"/battery_care_static/battery-care-panel.js?v={version}"
    )

    client = await hass_client()
    response = await client.get(custom["module_url"])
    assert response.status == HTTPStatus.OK
    assert "battery-care-panel" in await response.text()


async def test_unloading_removes_the_panel(hass: HomeAssistant) -> None:
    """A reload puts it back; disabling the integration takes it away."""
    await setup_battery_care(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    assert await hass.config_entries.async_reload(entry.entry_id)
    assert PANEL_URL_PATH in panels(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert PANEL_URL_PATH not in panels(hass)


async def test_a_dashboard_at_the_same_address_is_reported(hass: HomeAssistant) -> None:
    """Battery Care says what to change instead of replacing the dashboard."""
    assert await async_setup_component(hass, "frontend", {})
    frontend.async_register_built_in_panel(
        hass, "lovelace", frontend_url_path=PANEL_URL_PATH
    )
    entry = MockConfigEntry(domain=DOMAIN, title=NAME)
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "panel_taken"
    assert panels(hass)[PANEL_URL_PATH].component_name == "lovelace"
