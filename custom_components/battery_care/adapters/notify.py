"""Deliver notifications to Home Assistant and to phones with the mobile app."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util, slugify

_LOGGER = logging.getLogger(__name__)

NOTIFY = "notify"
MOBILE_APP = "mobile_app"
WARNING_INTERVAL = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class Target:
    """A phone or tablet with the Home Assistant app."""

    service: str
    name: str


@dataclass(frozen=True, slots=True)
class Message:
    """One notification, in both forms."""

    title: str
    # For Home Assistant notifications, which render Markdown.
    markdown: str
    # For phones, which show plain text.
    text: str
    # Replaces the previous notification with the same tag.
    tag: str
    # The page that tapping the notification opens.
    url: str


@callback
def phone_targets(hass: HomeAssistant) -> list[Target]:
    """Return the devices of the mobile app that can receive pushes."""
    targets: list[Target] = []
    for entry in hass.config_entries.async_entries(MOBILE_APP):
        name = entry.data.get("device_name") or entry.title
        # The mobile app names its notify services after the device name.
        service = f"{MOBILE_APP}_{slugify(name)}"
        if hass.services.has_service(NOTIFY, service):
            targets.append(Target(service, name))
    return sorted(targets, key=lambda target: target.name.casefold())


class Notifier:
    """Send messages; report a failing target at most once a day."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the notifier."""
        self._hass = hass
        self._warned: dict[str, datetime] = {}

    @callback
    def async_send(
        self, message: Message, *, persistent: bool, phones: Iterable[str]
    ) -> None:
        """Show the message in Home Assistant and push it to the phones."""
        if persistent:
            persistent_notification.async_create(
                self._hass, message.markdown, message.title, message.tag
            )
        for service in phones:
            self._hass.async_create_background_task(
                self._async_push_or_warn(service, message),
                f"battery_care push to {service}",
            )

    @callback
    def async_dismiss(self, tag: str) -> None:
        """Remove a notification from Home Assistant."""
        persistent_notification.async_dismiss(self._hass, tag)

    async def async_push(self, service: str, message: Message) -> str | None:
        """Push a message to one phone; return the error, if any."""
        try:
            await self._hass.services.async_call(
                NOTIFY,
                service,
                {
                    "title": message.title,
                    "message": message.text,
                    "data": {
                        "tag": message.tag,
                        "url": message.url,
                        "clickAction": message.url,
                    },
                },
                blocking=True,
            )
        except HomeAssistantError as err:
            return str(err) or type(err).__name__
        return None

    async def _async_push_or_warn(self, service: str, message: Message) -> None:
        if (error := await self.async_push(service, message)) is None:
            return
        now = dt_util.utcnow()
        last = self._warned.get(service)
        if last is None or now - last >= WARNING_INTERVAL:
            self._warned[service] = now
            _LOGGER.warning("Could not notify %s: %s", service, error)
