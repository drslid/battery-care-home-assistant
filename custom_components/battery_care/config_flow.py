"""Config flow for Battery Care: one step, with defaults that work as they are."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)
import voluptuous as vol

from .adapters.notify import Target, phone_targets
from .adapters.registry import async_inventory
from .const import DOMAIN, NAME, PANEL_URL_PATH
from .core.settings import DEFAULTS


def _time(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}:00"


def _minute(value: str) -> int:
    hours, minutes = value.split(":")[:2]
    return int(hours) * 60 + int(minutes)


def _schema(targets: list[Target]) -> vol.Schema:
    fields: dict[vol.Marker, Any] = {}
    if targets:
        fields[vol.Optional("phones", default=[])] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=target.service, label=target.name)
                    for target in targets
                ],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
    fields[vol.Required("digest_time", default=_time(DEFAULTS.digest_minute))] = (
        TimeSelector()
    )
    fields[vol.Required("quiet_hours", default=DEFAULTS.quiet_hours)] = (
        BooleanSelector()
    )
    fields[vol.Required("quiet_start", default=_time(DEFAULTS.quiet_start_minute))] = (
        TimeSelector()
    )
    fields[vol.Required("quiet_end", default=_time(DEFAULTS.quiet_end_minute))] = (
        TimeSelector()
    )
    return vol.Schema(fields)


class BatteryCareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup of Battery Care."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask how to be notified, then create the single entry."""
        schema = _schema(phone_targets(self.hass))
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=schema)
        settings = {
            "notify_targets": user_input.get("phones", []),
            "digest_minute": _minute(user_input["digest_time"]),
            "quiet_hours": user_input["quiet_hours"],
            "quiet_start_minute": _minute(user_input["quiet_start"]),
            "quiet_end_minute": _minute(user_input["quiet_end"]),
        }
        if (
            settings["quiet_hours"]
            and settings["quiet_start_minute"] == settings["quiet_end_minute"]
        ):
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors={"quiet_end": "quiet_hours_empty"},
            )
        found = len(async_inventory(self.hass).devices)
        return self.async_create_entry(
            title=NAME,
            data={"settings": settings},
            description="devices_found",
            description_placeholders={
                "count": str(found),
                "panel_url": f"/{PANEL_URL_PATH}",
            },
        )
