"""WebSocket commands for the Battery Care panel."""

from datetime import datetime
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.const import MAX_LENGTH_STATE_ENTITY_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
import voluptuous as vol

from .const import DOMAIN
from .manager import BatteryCareConfigEntry, BatteryCareManager
from .view import API_VERSION, device_details, patch, snapshot

# At most four messages per second for each open panel.
PATCH_INTERVAL = 0.25
ERR_NOT_LOADED = "not_loaded"
# Keys are "d:", "e:" or "s:" followed by an id, at most an entity id.
MAX_KEY_LENGTH = 2 + MAX_LENGTH_STATE_ENTITY_ID


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the commands; they find the manager when they run."""
    websocket_api.async_register_command(hass, websocket_subscribe)
    websocket_api.async_register_command(hass, websocket_device_get)


def _loaded_manager(hass: HomeAssistant) -> BatteryCareManager | None:
    entries: list[BatteryCareConfigEntry] = hass.config_entries.async_loaded_entries(
        DOMAIN
    )
    return entries[0].runtime_data if entries else None


class _Feed:
    """Send one panel a snapshot, then the changes, coalesced."""

    def __init__(
        self,
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg_id: int,
        manager: BatteryCareManager,
    ) -> None:
        self._hass = hass
        self._connection = connection
        self._msg_id = msg_id
        self._manager = manager
        self._keys: set[str] = set()
        self._everything = False
        self._cancel_flush: CALLBACK_TYPE | None = None
        self._unsubscribe: CALLBACK_TYPE | None = manager.async_subscribe(self)

    def send(self, payload: dict[str, Any]) -> None:
        self._connection.send_message(
            websocket_api.event_message(self._msg_id, payload)
        )

    @callback
    def async_changed(self, keys: frozenset[str] | None) -> None:
        if keys is None:
            self._everything = True
        else:
            self._keys |= keys
        if self._cancel_flush is None:
            self._cancel_flush = async_call_later(
                self._hass, PATCH_INTERVAL, self._async_flush
            )

    @callback
    def async_closed(self) -> None:
        """Tell the panel; it unsubscribes, then subscribes again later."""
        self._unsubscribe = None
        self._async_cancel_flush()
        self.send({"api": API_VERSION, "type": "closed"})

    @callback
    def async_stop(self) -> None:
        """Stop when the panel unsubscribes or disconnects."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._async_cancel_flush()

    @callback
    def _async_cancel_flush(self) -> None:
        if self._cancel_flush is not None:
            self._cancel_flush()
            self._cancel_flush = None

    @callback
    def _async_flush(self, _now: datetime) -> None:
        self._cancel_flush = None
        if self._everything:
            self.send(snapshot(self._hass, self._manager))
        else:
            self.send(patch(self._hass, self._manager, self._keys))
        self._keys = set()
        self._everything = False


def _send_not_loaded(connection: websocket_api.ActiveConnection, msg_id: int) -> None:
    connection.send_error(msg_id, ERR_NOT_LOADED, "Battery Care is not loaded")


@websocket_api.websocket_command(
    # A schema with only the type is not validated at all; this form rejects
    # unknown keys.
    vol.All(vol.Schema({vol.Required("type"): "battery_care/subscribe"}))
)
@callback
def websocket_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send a snapshot of every battery device, then the changes."""
    if (manager := _loaded_manager(hass)) is None:
        _send_not_loaded(connection, msg["id"])
        return
    feed = _Feed(hass, connection, msg["id"], manager)
    connection.subscriptions[msg["id"]] = feed.async_stop
    connection.send_result(msg["id"])
    feed.send(snapshot(hass, manager))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "battery_care/device/get",
        vol.Required("key"): vol.All(str, vol.Length(min=1, max=MAX_KEY_LENGTH)),
    }
)
@callback
def websocket_device_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the details of one battery device."""
    if (manager := _loaded_manager(hass)) is None:
        _send_not_loaded(connection, msg["id"])
        return
    if msg["key"] not in manager.inventory.devices:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown battery device"
        )
        return
    connection.send_result(msg["id"], device_details(hass, manager, msg["key"]))
