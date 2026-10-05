"""Serve the Battery Care panel and list it in the sidebar."""

from hashlib import sha256
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import NAME, PANEL_URL_PATH

PANEL_ELEMENT = "battery-care-panel"
PANEL_ICON = "mdi:battery-heart-variant"
STATIC_URL = "/battery_care_static"
FRONTEND_DIR = Path(__file__).parent / "frontend"
BUNDLE = "battery-care-panel.js"


def bundle_version() -> str:
    """Return a hash of the bundle, so that browsers fetch every new build."""
    return sha256((FRONTEND_DIR / BUNDLE).read_bytes()).hexdigest()[:16]


async def async_register_static_path(hass: HomeAssistant) -> None:
    """Serve the panel files; a route cannot be removed, so once per run."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=True)]
    )


async def async_register_panel(hass: HomeAssistant) -> None:
    """Add Battery Care to the sidebar; raise ValueError if the path is taken."""
    version = await hass.async_add_executor_job(bundle_version)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=NAME,
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL}/{BUNDLE}?v={version}",
        require_admin=False,
    )


@callback
def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove Battery Care from the sidebar."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
