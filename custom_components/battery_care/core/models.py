"""Records exchanged between the Home Assistant adapters and the pure core."""

from dataclasses import dataclass
from enum import StrEnum


class SourceKind(StrEnum):
    """What a battery entity tells about its device."""

    LEVEL = "level"
    LOW = "low"
    CHARGING = "charging"


class BatteryClass(StrEnum):
    """How the battery of a device is maintained."""

    REPLACEABLE = "replaceable"
    RECHARGEABLE = "rechargeable"
    NOT_MAINTAINED = "not_maintained"
    UNKNOWN = "unknown"


class Importance(StrEnum):
    """How much a dead battery would matter."""

    LOW = "low"
    NORMAL = "normal"
    IMPORTANT = "important"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class EntityRecord:
    """The facts discovery needs about one entity."""

    entity_id: str
    platform: str | None = None
    registry_id: str | None = None
    device_id: str | None = None
    device_class: str | None = None
    unit: str | None = None
    name: str | None = None
    area_id: str | None = None
    disabled: bool = False

    @property
    def domain(self) -> str:
        """Return the entity domain, such as sensor."""
        return self.entity_id.partition(".")[0]


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    """The facts discovery needs about one device."""

    device_id: str
    name: str | None = None
    area_id: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class BatteryMetadata:
    """Battery type and quantity, with where they come from."""

    battery_type: str
    quantity: int
    source: str


@dataclass(frozen=True, slots=True)
class BatterySource:
    """An entity that reports on the battery of a device."""

    entity_id: str
    kind: SourceKind


@dataclass(frozen=True, slots=True)
class BatteryDevice:
    """One battery-powered thing, with all the entities that describe it."""

    key: str
    name: str
    sources: tuple[BatterySource, ...]
    battery_class: BatteryClass
    class_reason: str
    suggested_importance: Importance
    device_id: str | None = None
    area_id: str | None = None
    floor_id: str | None = None
    integration: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    metadata: BatteryMetadata | None = None

    @property
    def stable(self) -> bool:
        """Return whether the key survives a rename of the entity."""
        return not self.key.startswith("s:")

    def entity_ids(self, kind: SourceKind) -> tuple[str, ...]:
        """Return the entities of one kind."""
        return tuple(source.entity_id for source in self.sources if source.kind is kind)


@dataclass(frozen=True, slots=True)
class NotMonitored:
    """A device with battery entities that Battery Care does not watch."""

    key: str
    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class Inventory:
    """Everything discovery found."""

    devices: dict[str, BatteryDevice]
    suggestions: tuple[str, ...] = ()
    not_monitored: tuple[NotMonitored, ...] = ()
