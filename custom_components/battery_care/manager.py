"""Coordinate discovery, tracking, the alert engine and storage for the entry."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from functools import partial
import logging
from typing import Any, Protocol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .adapters.registry import async_inventory, source_value
from .adapters.tracking import InventoryTracker
from .const import DOMAIN
from .core.engine import Alert, Evaluation, Observation, evaluate, make_policy
from .core.health import health_score
from .core.known import track
from .core.messages import Line
from .core.models import BatteryClass, BatteryDevice, Importance, Inventory
from .core.policy import (
    AUTOMATIC,
    DeviceConfig,
    DeviceMode,
    class_settings,
    effective_settings,
    importance,
    make_class_choice,
    make_config,
)
from .core.readings import Reading, read
from .core.runtime import Runtime
from .core.settings import Settings, SettingsError, updated
from .core.status import ATTENTION, Status, Summary, device_status, summarize
from .dispatcher import Dispatcher
from .storage import (
    CONFIG_KEY,
    CONFIG_MINOR_VERSION,
    CONFIG_SAVE_DELAY,
    STATE_KEY,
    STATE_MINOR_VERSION,
    STATE_SAVE_DELAY,
    STORAGE_VERSION,
    BatteryCareStore,
    ConfigData,
    StateData,
    config_from_raw,
    config_to_raw,
    state_from_raw,
    state_to_raw,
)

_LOGGER = logging.getLogger(__name__)

# Home Assistant rewrites every state while it starts: those reports prove nothing.
STARTUP_WINDOW = timedelta(minutes=10)
EVIDENCE_INTERVAL = timedelta(hours=1)
EVENT_ALERT = f"{DOMAIN}_alert"
EVENT_RECOVERED = f"{DOMAIN}_recovered"
EVENT_VERSION = 1
NOT_REPORTS = frozenset({STATE_UNAVAILABLE, STATE_UNKNOWN})
NEW = Runtime()
# What notifications say about each status; others are not told.
TOLD = {
    Status.CRITICAL: "critical",
    Status.LOW: "low",
    Status.NOT_RESPONDING: "not_responding",
    Status.STALE: "stale",
    Status.OK: "recovered",
}

type BatteryCareConfigEntry = ConfigEntry[BatteryCareManager]


class Subscriber(Protocol):
    """Something that follows the manager, such as an open panel."""

    def async_changed(self, keys: frozenset[str] | None) -> None:
        """Handle a change to these devices, or to anything when keys is None."""

    def async_closed(self) -> None:
        """Handle the manager stopping."""


class BatteryCareManager:
    """Own the battery devices, what Battery Care concluded, and the user's choices."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize an empty manager; call async_load, then async_start."""
        self.hass = hass
        self.ready = False
        self.inventory = Inventory(devices={})
        self.readings: dict[str, Reading] = {}
        self.config = ConfigData()
        self.state = StateData()
        self.summary = Summary()
        self.health: int | None = None
        self._rows: dict[str, tuple[Status, bool, Importance]] = {}
        self._subscribers: set[Subscriber] = set()
        self._keys_by_entity: dict[str, str] = {}
        self._wake_at: dict[str, datetime] = {}
        self._wake_time: datetime | None = None
        self._cancel_wake: CALLBACK_TYPE | None = None
        self._cancel_timers: list[CALLBACK_TYPE] = []
        self._cancel_start: CALLBACK_TYPE | None = None
        # Set again when Home Assistant has started.
        self._reports_after = dt_util.utcnow() + STARTUP_WINDOW
        self._tracker = InventoryTracker(
            hass, self._async_rebuild, self._async_source_changed
        )
        self._config_store = BatteryCareStore(
            hass, STORAGE_VERSION, CONFIG_KEY, minor_version=CONFIG_MINOR_VERSION
        )
        self._state_store = BatteryCareStore(
            hass, STORAGE_VERSION, STATE_KEY, minor_version=STATE_MINOR_VERSION
        )
        self._config_dirty = False
        self._state_dirty = False
        self.dispatcher = Dispatcher(
            hass,
            state=lambda: self.state,
            settings=lambda: self.config.settings,
            describe=self._describe,
            save=self._async_save_state,
        )

    async def async_load(self, initial: Mapping[str, Any] | None = None) -> None:
        """Load the stored data; invalid values are ignored with a warning.

        Args:
            initial: settings chosen at setup, used until the first save.
        """
        raw_config = await self._config_store.async_load()
        self.config, config_problems = config_from_raw(raw_config)
        self.state, state_problems = state_from_raw(
            await self._state_store.async_load()
        )
        if problems := config_problems + state_problems:
            _LOGGER.warning(
                "Ignored invalid stored values, using defaults instead: %s",
                ", ".join(problems),
            )
        if raw_config is None and initial:
            try:
                self.config.settings = updated(self.config.settings, initial)
            except SettingsError as err:
                _LOGGER.warning("Ignored the settings chosen at setup: %s", err)
            else:
                self._async_save_config()

    @callback
    def async_start(self) -> None:
        """Discover once Home Assistant has started, so integrations are loaded."""
        self._cancel_start = async_at_started(self.hass, self._async_hass_started)

    @callback
    def async_shutdown(self) -> None:
        """Stop every listener and timer, and tell subscribers."""
        if self._cancel_start is not None:
            self._cancel_start()
            self._cancel_start = None
        for cancel in self._cancel_timers:
            cancel()
        self._cancel_timers.clear()
        if self._cancel_wake is not None:
            self._cancel_wake()
            self._cancel_wake = None
        self._wake_time = None
        self.dispatcher.async_stop()
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
            await self._state_store.async_save(state_to_raw(self.state))
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
            self.config.settings,
            self.inventory.devices[key],
            self.device_config(key),
            self.config.classes,
        )

    def status(self, key: str) -> Status:
        """Return what the panel shows for one battery device."""
        return device_status(
            self.state.devices.get(key, NEW),
            self.readings[key].charging,
            self.device_config(key).mode,
        )

    @callback
    def async_update_settings(self, changes: Mapping[str, Any]) -> Settings:
        """Change global settings; raise SettingsError and change nothing if invalid."""
        self.config.settings = updated(self.config.settings, changes)
        self._async_save_config()
        self._async_evaluate_all(everything=True)
        if self.ready:
            self.dispatcher.async_settings_changed()
        return self.config.settings

    @callback
    def async_snooze(self, key: str, until: datetime | None) -> None:
        """Hold the notifications of a device until a time, or stop holding them."""
        runtime = self.state.devices.get(key, NEW)
        self.state.devices[key] = replace(runtime, snoozed_until=until)
        self._async_save_state()
        self._async_evaluate(key, dt_util.utcnow())
        self._async_schedule_wake()
        self._async_changed(frozenset({key}))

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
            self.config.classes,
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
        self._async_evaluate_all(everything=True)
        return config

    @callback
    def async_update_class(
        self, chosen_class: BatteryClass, changes: Mapping[str, Any]
    ) -> Settings:
        """Change the settings of a battery class; raise SettingsError if invalid."""
        choice = make_class_choice(
            self.config.settings,
            chosen_class,
            {**self.config.classes.get(chosen_class, {}), **changes},
        )
        if choice:
            self.config.classes[chosen_class] = choice
        else:
            self.config.classes.pop(chosen_class, None)
        self._async_save_config()
        self._async_evaluate_all(everything=True)
        return class_settings(self.config.settings, chosen_class, self.config.classes)

    @callback
    def _async_save_config(self) -> None:
        self._config_dirty = True
        self._config_store.async_delay_save(self._config_snapshot, CONFIG_SAVE_DELAY)

    def _config_snapshot(self) -> dict[str, Any]:
        self._config_dirty = False
        return config_to_raw(self.config)

    @callback
    def _async_save_state(self) -> None:
        self._state_dirty = True
        self._state_store.async_delay_save(self._state_snapshot, STATE_SAVE_DELAY)

    def _state_snapshot(self) -> dict[str, Any]:
        self._state_dirty = False
        return state_to_raw(self.state)

    @callback
    def _async_changed(self, keys: frozenset[str] | None) -> None:
        """Recount, then tell subscribers about these devices, or about everything."""
        if keys is None:
            self._rows = {key: self._row(key) for key in self.inventory.devices}
        elif keys:
            self._rows.update((key, self._row(key)) for key in keys)
        else:
            return
        self.summary = summarize(
            (status, alerts) for status, alerts, _ in self._rows.values()
        )
        self.health = health_score(
            (status, weight) for status, alerts, weight in self._rows.values() if alerts
        )
        for subscriber in list(self._subscribers):
            subscriber.async_changed(keys)

    def _row(self, key: str) -> tuple[Status, bool, Importance]:
        device = self.inventory.devices[key]
        return (
            self.status(key),
            self.effective_settings(key).alerts_enabled,
            importance(device, self.device_config(key)),
        )

    @callback
    def _async_hass_started(self, _hass: HomeAssistant) -> None:
        self._cancel_start = None
        self._reports_after = dt_util.utcnow() + STARTUP_WINDOW
        self.ready = True
        self._cancel_timers.append(
            async_track_time_interval(self.hass, self._async_tick, EVIDENCE_INTERVAL)
        )
        if not self.state.baseline_done:
            self._cancel_timers.append(
                async_track_point_in_utc_time(
                    self.hass, self._async_finish_baseline, self._reports_after
                )
            )
        self._async_rebuild()
        self._tracker.async_start()
        self.dispatcher.async_start()

    @callback
    def _async_finish_baseline(self, _now: datetime) -> None:
        """End the silent first run, then sum up what needs attention."""
        self.state.baseline_done = True
        self._async_save_state()
        self.dispatcher.async_summary(
            key
            for key, (status, alerts, _) in self._rows.items()
            if alerts and status in ATTENTION
        )

    @callback
    def _async_tick(self, _now: datetime) -> None:
        """Look for signs of life and staleness, which state events do not reveal."""
        self._async_evaluate_all()

    @callback
    def _async_wake(self, _now: datetime) -> None:
        self._cancel_wake = None
        self._wake_time = None
        self._async_evaluate_all()

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
        self._wake_at = {
            key: when
            for key, when in self._wake_at.items()
            if key in self.inventory.devices
        }
        self._async_evaluate_all(everything=True)
        _LOGGER.debug(
            "Inventory: %d battery devices, %d not monitored",
            len(self.inventory.devices),
            len(self.inventory.not_monitored),
        )

    @callback
    def _async_remember_devices(self) -> None:
        """Track known devices; forget the data of devices gone for too long."""
        present = {key: device.name for key, device in self.inventory.devices.items()}
        present |= {item.key: item.name for item in self.inventory.not_monitored}
        known, expired = track(self.state.known, present, dt_util.utcnow())
        if known != self.state.known:
            self.state.known = known
            for key in expired:
                self.state.devices.pop(key, None)
            self._async_save_state()
        if expired & self.config.devices.keys():
            for key in expired:
                self.config.devices.pop(key, None)
            self._async_save_config()

    @callback
    def _async_source_changed(self, entity_id: str) -> None:
        # Tracked entities and this index are rebuilt together.
        key = self._keys_by_entity[entity_id]
        reading = self._read(self.inventory.devices[key])
        reading_changed = reading != self.readings.get(key)
        self.readings[key] = reading
        state_changed = self._async_evaluate(key, dt_util.utcnow())
        self._async_schedule_wake()
        if reading_changed or state_changed:
            self._async_changed(frozenset({key}))

    @callback
    def _async_evaluate_all(self, *, everything: bool = False) -> None:
        """Evaluate every device, then report the changes, or everything."""
        now = dt_util.utcnow()
        changed = {
            key for key in self.inventory.devices if self._async_evaluate(key, now)
        }
        self._async_schedule_wake()
        self._async_changed(None if everything else frozenset(changed))

    @callback
    def _async_evaluate(self, key: str, now: datetime) -> bool:
        """Evaluate one device and act on it; return whether its state changed."""
        device = self.inventory.devices[key]
        reading = self.readings[key]
        previous = self.state.devices.get(key)
        result = evaluate(
            previous,
            Observation(
                level=reading.level,
                low=reading.low,
                charging=reading.charging,
                available=reading.available,
                evidence_at=self._evidence_at(device),
                critical=reading.critical,
            ),
            make_policy(
                self.effective_settings(key),
                importance(device, self.device_config(key)),
            ),
            now,
            silent=not self.state.baseline_done,
        )
        if result.wake_at is None:
            self._wake_at.pop(key, None)
        else:
            self._wake_at[key] = result.wake_at
        changed = result.runtime != previous
        if changed:
            self.state.devices[key] = result.runtime
            self._async_save_state()
        # Notifications describe the new state, so it is stored first.
        self._async_announce(key, result)
        return changed

    @callback
    def _async_announce(self, key: str, result: Evaluation) -> None:
        """Fire the events of an evaluation, and pass it on to be notified."""
        level = result.runtime.last_level
        for alert in result.alerts:
            self.hass.bus.async_fire(EVENT_ALERT, self._alert_data(key, alert, level))
        for problem in result.recovered:
            self.hass.bus.async_fire(
                EVENT_RECOVERED,
                {
                    "version": EVENT_VERSION,
                    "device_key": key,
                    "device_id": self.inventory.devices[key].device_id,
                    "previous_severity": problem.value,
                    "level": level,
                },
            )
        if result.alerts or result.recovered:
            self.dispatcher.async_handle(key, result.alerts, result.recovered)

    def _describe(self, key: str) -> Line | None:
        """Describe a battery for a notification; None when it must not be told."""
        if (device := self.inventory.devices.get(key)) is None:
            return None
        runtime = self.state.devices.get(key, NEW)
        if (
            runtime.snoozed_until is not None
            and runtime.snoozed_until > dt_util.utcnow()
        ):
            return None
        if not self.effective_settings(key).alerts_enabled:
            return None
        if (told := TOLD.get(self.status(key))) is None:
            return None
        level = self.readings[key].level
        metadata = device.metadata
        battery = None
        if metadata is not None:
            battery = metadata.battery_type
            if metadata.quantity > 1:
                battery = f"{metadata.quantity} \N{MULTIPLICATION SIGN} {battery}"
        return Line(
            name=device.name,
            status=told,
            level=runtime.last_level if level is None else level,
            area=self._area_name(device),
            battery=battery,
        )

    def _area_name(self, device: BatteryDevice) -> str | None:
        if device.area_id is None:
            return None
        area = ar.async_get(self.hass).async_get_area(device.area_id)
        return area.name if area else None

    def _alert_data(
        self, key: str, alert: Alert, level: float | None
    ) -> dict[str, Any]:
        device = self.inventory.devices[key]
        metadata = device.metadata
        return {
            "version": EVENT_VERSION,
            "device_key": key,
            "device_id": device.device_id,
            # Charging sources sort last, and every device has another source.
            "entity_id": device.sources[0].entity_id,
            "name": device.name,
            "area": self._area_name(device),
            "severity": alert.problem.value,
            "previous_severity": alert.previous,
            "level": level,
            "reminder": alert.reminder,
            "battery_type": metadata.battery_type if metadata else None,
            "battery_quantity": metadata.quantity if metadata else None,
            "importance": importance(device, self.device_config(key)).value,
        }

    def _evidence_at(self, device: BatteryDevice) -> datetime | None:
        """Return the latest report from the device after the startup window."""
        latest = self._reports_after
        found = False
        for entity_id in device.evidence:
            state = self.hass.states.get(entity_id)
            if (
                state is not None
                and state.state not in NOT_REPORTS
                and state.last_reported > latest
            ):
                latest, found = state.last_reported, True
        return latest if found else None

    @callback
    def _async_schedule_wake(self) -> None:
        """Keep a single timer, set for the earliest time a device needs a look."""
        when = min(self._wake_at.values(), default=None)
        if when == self._wake_time:
            return
        if self._cancel_wake is not None:
            self._cancel_wake()
            self._cancel_wake = None
        self._wake_time = when
        if when is not None:
            self._cancel_wake = async_track_point_in_utc_time(
                self.hass, self._async_wake, when
            )

    def _read(self, device: BatteryDevice) -> Reading:
        return read(
            device,
            {
                source: source_value(self.hass.states.get(source.entity_id), source)
                for source in device.sources
            },
        )
