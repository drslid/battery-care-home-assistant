"""The base of the summary entities, attached to the Battery Care service device."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME
from .manager import BatteryCareConfigEntry, BatteryCareManager


class BatteryCareEntity(Entity):
    """An entity that the manager updates when its counts change."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: BatteryCareConfigEntry, key: str) -> None:
        """Attach the entity to the service device of the entry."""
        self.manager: BatteryCareManager = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._shown: tuple[bool, object] | None = None

    @property
    def available(self) -> bool:
        """Return whether Battery Care has built its inventory yet."""
        return self.manager.ready

    def shown_value(self) -> object:
        """Return the value of the state, to skip writes that change nothing."""
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Follow the manager."""
        self._shown = (self.available, self.shown_value())
        self.async_on_remove(self.manager.async_subscribe(self))

    @callback
    def async_changed(self, keys: frozenset[str] | None) -> None:
        """Write the state when what it shows has changed."""
        if (shown := (self.available, self.shown_value())) != self._shown:
            self._shown = shown
            self.async_write_ha_state()

    @callback
    def async_closed(self) -> None:
        """Do nothing: the platforms unload these entities before the manager."""
