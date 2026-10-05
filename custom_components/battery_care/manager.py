"""Coordinate discovery, tracking, readings and storage for the Battery Care entry."""

from collections.abc import Mapping
from functools import partial
import logging
from typing import Any, Protocol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .adapters.registry import async_inventory
from .adapters.tracking import InventoryTracker
from .core.known import KnownDevice, track
from .core.models import BatteryClass, BatteryDevice, Importance, Inventory
from .core.policy import (
    AUTOMATIC,
    DeviceConfig,
    DeviceMode,
    effective_settings,
    make_config,
)
from .core.readings import Reading, read
from .core.settings import Settings, SettingsError, updated
from .storage import (
    CONFIG_KEY,
    CONFIG_SAVE_DELAY,
    STATE_KEY,
    STATE_SAVE_DELAY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
    BatteryCareStore,
    ConfigData,
    config_from_raw,
    config_to_raw,
    state_from_raw,
    state_to_raw,
)

_LOGGER = logging.getLogger(__name__)

type BatteryCareConfigEntry = ConfigEntry[BatteryCareManager]


class Subscriber(Protocol):
    """Something that follows the manager, such as an open panel."""

    def async_changed(self, keys: frozenset[str] | None) -> None:
        """Handle a change to these devices, or to anything when keys is None."""

    def async_closed(self) -> None:
        """Handle the manager stopping."""


class BatteryCareManager:
    """Own the inventory of battery devices, their readings and the user's choices."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize an empty manager; call async_load, then async_start."""
        self.hass = hass
        self.ready = False
        self.inventory = Inventory(devices={})
        self.readings: dict[str, Reading] = {}
        self.config = ConfigData()
        self._subscribers: set[Subscriber] = set()
        self._known: dict[str, KnownDevice] = {}
        self._keys_by_entity: dict[str, str] = {}
        self._tracker = InventoryTracker(
            hass, self._async_rebuild, self._async_source_changed
        )
        self._cancel_start: CALLBACK_TYPE | None = None
        self._config_store = BatteryCareStore(
            hass, STORAGE_VERSION, CONFIG_KEY, minor_version=STORAGE_MINOR_VERSION
        )
        self._state_store = BatteryCareStore(
            hass, STORAGE_VERSION, STATE_KEY, minor_version=STORAGE_MINOR_VERSION
        )
        self._config_dirty = False
        self._state_dirty = False

    async def async_load(self) -> None:
        """Load the stored data; invalid values are ignored with a warning."""
        self.config, config_problems = config_from_raw(
            await self._config_store.async_load()
        )
        self._known, state_problems = state_from_raw(
            await self._state_store.async_load()
        )
        if problems := config_problems + state_problems:
            _LOGGER.warning(
                "Ignored invalid stored values, using defaults instead: %s",
                ", ".join(problems),
            )

    @callback
    def async_start(self) -> None:
        """Discover once Home Assistant has started, so integrations are loaded."""
        self._cancel_start = async_at_started(self.hass, self._async_hass_started)

    @callback
    def async_shutdown(self) -> None:
        """Stop every listener, and tell subscribers."""
        if self._cancel_start is not None:
            self._cancel_start()
            self._cancel_start = None
        self._tracker.async_stop()
        subscribers, self._subscribers = self._subscribers, set()
        for subscriber in subscribers:
            subscriber.async_closed()

    @callback
    def async_subscribe(self, subscriber: Subscriber) -> CALLBACK_TYPE:
        """Follow changes until the returned callback is called."""
        self._subscribers.add(subscriber)
        return partial(self._subscribers.discard, subscriber)

    async def async_unload(self) -> None:
        """Stop, then write pending changes so a reload reads them."""
        self.async_shutdown()
        if self._config_dirty:
            await self._config_store.async_save(config_to_raw(self.config))
            self._config_dirty = False
        if self._state_dirty:
            await self._state_store.async_save(state_to_raw(self._known))
            self._state_dirty = False

    @property
    def settings(self) -> Settings:
        """Return the global settings."""
        return self.config.settings

    def device_config(self, key: str) -> DeviceConfig:
        """Return what the user chose for a device."""
        return self.config.devices.get(key, AUTOMATIC)

    def effective_settings(self, key: str) -> Settings:
        """Return the settings that apply to one battery device."""
        return effective_settings(
            self.config.settings, self.inventory.devices[key], self.device_config(key)
        )

    @callback
    def async_update_settings(self, changes: Mapping[str, Any]) -> Settings:
        """Change global settings; raise SettingsError and change nothing if invalid."""
        self.config.settings = updated(self.config.settings, changes)
        self._async_save_config()
        self._async_notify()
        return self.config.settings

    @callback
    def async_configure_device(
        self,
        key: str,
        *,
        mode: DeviceMode,
        overrides: Mapping[str, Any] | None = None,
        importance: Importance | None = None,
        battery_class: BatteryClass | None = None,
    ) -> DeviceConfig:
        """Change what the user chose for a device; raise SettingsError if invalid."""
        if (device := self.inventory.devices.get(key)) is None:
            raise SettingsError("unknown_device", key)
        config = make_config(
            self.config.settings,
            device,
            mode=mode,
            overrides=overrides,
            chosen_importance=importance,
            chosen_class=battery_class,
        )
        if config.is_default:
            self.config.devices.pop(key, None)
        else:
            self.config.devices[key] = config
        self._async_save_config()
        self._async_notify()
        return config

    @callback
    def _async_save_config(self) -> None:
        self._config_dirty = True
        self._config_store.async_delay_save(self._config_snapshot, CONFIG_SAVE_DELAY)

    def _config_snapshot(self) -> dict[str, Any]:
        self._config_dirty = False
        return config_to_raw(self.config)

    def _state_snapshot(self) -> dict[str, Any]:
        self._state_dirty = False
        return state_to_raw(self._known)

    @callback
    def _async_notify(self, keys: frozenset[str] | None = None) -> None:
        for subscriber in list(self._subscribers):
            subscriber.async_changed(keys)

    @callback
    def _async_hass_started(self, _hass: HomeAssistant) -> None:
        self._cancel_start = None
        self.ready = True
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
        self._async_remember_devices()
        self._async_notify()
        _LOGGER.debug(
            "Inventory: %d battery devices, %d suggestions, %d not monitored",
            len(self.inventory.devices),
            len(self.inventory.suggestions),
            len(self.inventory.not_monitored),
        )

    @callback
    def _async_remember_devices(self) -> None:
        """Track known devices; forget the choices of devices gone for too long."""
        present = {key: device.name for key, device in self.inventory.devices.items()}
        present |= {item.key: item.name for item in self.inventory.not_monitored}
        known, expired = track(self._known, present, dt_util.utcnow())
        if known != self._known:
            self._known = known
            self._state_dirty = True
            self._state_store.async_delay_save(self._state_snapshot, STATE_SAVE_DELAY)
        if expired & self.config.devices.keys():
            for key in expired:
                self.config.devices.pop(key, None)
            self._async_save_config()

    @callback
    def _async_source_changed(self, entity_id: str) -> None:
        # Tracked entities and this index are rebuilt together.
        key = self._keys_by_entity[entity_id]
        reading = self._read(self.inventory.devices[key])
        if reading != self.readings.get(key):
            self.readings[key] = reading
            self._async_notify(frozenset({key}))

    def _read(self, device: BatteryDevice) -> Reading:
        states = {
            source.entity_id: state.state
            if (state := self.hass.states.get(source.entity_id))
            else None
            for source in device.sources
        }
        return read(device, states)
