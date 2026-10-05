"""Summary sensors: the health score and the number of batteries in each state."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import BatteryCareEntity
from .manager import BatteryCareConfigEntry, BatteryCareManager


@dataclass(frozen=True, kw_only=True)
class BatteryCareSensorDescription(SensorEntityDescription):
    """A summary sensor, and where its value comes from."""

    value: Callable[[BatteryCareManager], int | None]


SENSORS = (
    BatteryCareSensorDescription(
        key="health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda manager: manager.health,
    ),
    BatteryCareSensorDescription(
        key="attention",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda manager: manager.summary.attention,
    ),
    BatteryCareSensorDescription(
        key="low",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda manager: manager.summary.low,
    ),
    BatteryCareSensorDescription(
        key="critical",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda manager: manager.summary.critical,
    ),
    BatteryCareSensorDescription(
        key="monitored",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda manager: manager.summary.monitored,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BatteryCareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the summary sensors."""
    async_add_entities(BatteryCareSensor(entry, description) for description in SENSORS)


class BatteryCareSensor(BatteryCareEntity, SensorEntity):
    """A number that summarizes every battery."""

    entity_description: BatteryCareSensorDescription

    def __init__(
        self, entry: BatteryCareConfigEntry, description: BatteryCareSensorDescription
    ) -> None:
        """Initialize the sensor from its description."""
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        """Return the current value."""
        return self.entity_description.value(self.manager)

    def shown_value(self) -> object:
        """Return the value of the state."""
        return self.native_value
