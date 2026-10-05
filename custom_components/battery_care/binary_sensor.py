"""A problem sensor that is on while a battery needs attention."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import BatteryCareEntity
from .manager import BatteryCareConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BatteryCareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the attention sensor."""
    async_add_entities([BatteryCareAttention(entry)])


class BatteryCareAttention(BatteryCareEntity, BinarySensorEntity):
    """On while at least one monitored battery needs attention."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry: BatteryCareConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(entry, "attention_required")

    @property
    def is_on(self) -> bool:
        """Return whether a battery needs attention."""
        return self.manager.summary.attention > 0

    def shown_value(self) -> object:
        """Return the value of the state."""
        return self.is_on
