"""Keep the inventory current as registries, entities and states change."""

from collections.abc import Callable, Iterable
import logging
from typing import Any

from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
)
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_state_change_event,
)

_LOGGER = logging.getLogger(__name__)

REBUILD_COOLDOWN = 1.0
REGISTRY_EVENTS = (
    er.EVENT_ENTITY_REGISTRY_UPDATED,
    dr.EVENT_DEVICE_REGISTRY_UPDATED,
    ar.EVENT_AREA_REGISTRY_UPDATED,
    fr.EVENT_FLOOR_REGISTRY_UPDATED,
)
BATTERY_DEVICE_CLASSES = frozenset({"battery", "battery_charging"})


class InventoryTracker:
    """Ask for a debounced rebuild on structural changes; report source states."""

    def __init__(
        self,
        hass: HomeAssistant,
        rebuild: Callable[[], None],
        source_changed: Callable[[str], None],
    ) -> None:
        """Initialize the tracker; nothing is watched until async_start."""
        self._hass = hass
        self._source_changed = source_changed
        self._debouncer = Debouncer(
            hass, _LOGGER, cooldown=REBUILD_COOLDOWN, immediate=False, function=rebuild
        )
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._unsubscribe_sources: CALLBACK_TYPE | None = None
        self._sources: frozenset[str] = frozenset()

    @callback
    def async_start(self) -> None:
        """Watch registries and new sensors."""
        self._unsubscribers.extend(
            self._hass.bus.async_listen(event_type, self._async_structure_changed)
            for event_type in REGISTRY_EVENTS
        )
        self._unsubscribers.append(
            async_track_state_added_domain(
                self._hass, ("sensor", "binary_sensor"), self._async_state_added
            )
        )

    @callback
    def async_track_sources(self, entity_ids: Iterable[str]) -> None:
        """Follow the states of exactly these source entities."""
        sources = frozenset(entity_ids)
        if sources == self._sources:
            return
        self._async_untrack_sources()
        self._sources = sources
        if sources:
            self._unsubscribe_sources = async_track_state_change_event(
                self._hass, sorted(sources), self._async_source_changed
            )

    @callback
    def async_stop(self) -> None:
        """Stop watching and drop any pending rebuild."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._async_untrack_sources()
        self._sources = frozenset()
        self._debouncer.async_shutdown()

    @callback
    def _async_untrack_sources(self) -> None:
        if self._unsubscribe_sources is not None:
            self._unsubscribe_sources()
            self._unsubscribe_sources = None

    @callback
    def _async_structure_changed(self, _event: Event[Any]) -> None:
        self._debouncer.async_schedule_call()

    @callback
    def _async_state_added(self, event: Event[EventStateChangedData]) -> None:
        if (state := event.data["new_state"]) is not None and (
            state.attributes.get(ATTR_DEVICE_CLASS) in BATTERY_DEVICE_CLASSES
            or state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == "%"
            or ATTR_BATTERY_LEVEL in state.attributes
            or "options" in state.attributes
        ):
            self._debouncer.async_schedule_call()

    @callback
    def _async_source_changed(self, event: Event[EventStateChangedData]) -> None:
        self._source_changed(event.data["entity_id"])
