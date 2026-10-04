"""Config flow for Battery Care: one confirmation, nothing to configure."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .adapters.registry import async_inventory
from .const import DOMAIN, NAME


class BatteryCareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup of Battery Care."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a confirmation, then create the single entry."""
        if user_input is None:
            return self.async_show_form(step_id="user")
        found = len(async_inventory(self.hass).devices)
        return self.async_create_entry(
            title=NAME,
            data={},
            description="devices_found",
            description_placeholders={"count": str(found)},
        )
