"""Coordinate discovery, tracking and readings for the Battery Care entry."""

import logging

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.start import async_at_started

from .adapters.registry import async_inventory
from .adapters.tracking import InventoryTracker
from .core.models import BatteryDevice, Inventory
from .core.readings import Reading, read

_LOGGER = logging.getLogger(__name__)


class BatteryCareManager:
    """Own the inventory of battery devices and their current readings."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize an empty manager; discovery starts with async_start."""
        self.hass = hass
        self.inventory = Inventory(devices={})
        self.readings: dict[str, Reading] = {}
        self._keys_by_entity: dict[str, str] = {}
        self._tracker = InventoryTracker(
            hass, self._async_rebuild, self._async_source_changed
        )
        self._cancel_start: CALLBACK_TYPE | None = None

    @callback
    def async_start(self) -> None:
        """Discover once Home Assistant has started, so integrations are loaded."""
        self._cancel_start = async_at_started(self.hass, self._async_hass_started)

    @callback
    def async_shutdown(self) -> None:
        """Stop every listener."""
        if self._cancel_start is not None:
            self._cancel_start()
            self._cancel_start = None
        self._tracker.async_stop()

    @callback
    def _async_hass_started(self, _hass: HomeAssistant) -> None:
        self._cancel_start = None
        self._async_rebuild()
        self._tracker.async_start()

    @callback
    def _async_rebuild(self) -> None:
        self.inventory = async_inventory(self.hass)
        self._keys_by_entity = {
            source.entity_id: key
            for key, device in self.inventory.devices.items()
            for source in device.sources
        }
        self.readings = {
            key: self._read(device) for key, device in self.inventory.devices.items()
        }
        self._tracker.async_track_sources(self._keys_by_entity)
        _LOGGER.debug(
            "Inventory: %d battery devices, %d suggestions, %d not monitored",
            len(self.inventory.devices),
            len(self.inventory.suggestions),
            len(self.inventory.not_monitored),
        )

    @callback
    def _async_source_changed(self, entity_id: str) -> None:
        key = self._keys_by_entity.get(entity_id)
        if key is not None and (device := self.inventory.devices.get(key)) is not None:
            self.readings[key] = self._read(device)

    def _read(self, device: BatteryDevice) -> Reading:
        states = {
            source.entity_id: state.state
            if (state := self.hass.states.get(source.entity_id))
            else None
            for source in device.sources
        }
        return read(device, states)
