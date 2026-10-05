"""Turn Home Assistant registries and states into discovery records."""

from dataclasses import replace

from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from ..core.discovery import discover, group_key
from ..core.models import (
    BatteryMetadata,
    BatterySource,
    DeviceRecord,
    EntityRecord,
    Inventory,
)
from ..core.readings import parse_level, text_state
from .battery_notes import DOMAIN as BATTERY_NOTES, parse_metadata

STATE_ONLY_DOMAINS = ("sensor", "binary_sensor")


def has_battery_level(state: State | None) -> bool:
    """Return whether a state carries a battery percentage as an attribute."""
    if state is None or (level := state.attributes.get(ATTR_BATTERY_LEVEL)) is None:
        return False
    return not isinstance(level, bool) and parse_level(str(level)) is not None


def has_text_state(state: State | None) -> bool:
    """Return whether a state, or its options, are battery words such as low."""
    if state is None:
        return False
    options = state.attributes.get("options")
    words = [state.state, *(options if isinstance(options, list) else [])]
    return any(isinstance(word, str) and text_state(word) for word in words)


def source_value(state: State | None, source: BatterySource) -> str | None:
    """Return what a source says now, from its state or its attribute."""
    if state is None:
        return None
    if source.attribute is None or state.state == STATE_UNAVAILABLE:
        return state.state
    value = state.attributes.get(source.attribute)
    return STATE_UNKNOWN if value is None else str(value)


def entity_record(entry: er.RegistryEntry, state: State | None) -> EntityRecord:
    """Describe a registered entity; its state carries the effective device class."""
    attributes = state.attributes if state is not None else {}
    return EntityRecord(
        entity_id=entry.entity_id,
        platform=entry.platform,
        registry_id=entry.id,
        device_id=entry.device_id,
        device_class=attributes.get(ATTR_DEVICE_CLASS)
        or entry.device_class
        or entry.original_device_class,
        unit=attributes.get(ATTR_UNIT_OF_MEASUREMENT) or entry.unit_of_measurement,
        name=attributes.get(ATTR_FRIENDLY_NAME) or entry.name or entry.original_name,
        area_id=entry.area_id,
        disabled=entry.disabled_by is not None,
        battery_level=has_battery_level(state),
        text_state=has_text_state(state),
    )


def state_record(state: State) -> EntityRecord:
    """Describe an entity that exists only in the state machine."""
    return EntityRecord(
        entity_id=state.entity_id,
        device_class=state.attributes.get(ATTR_DEVICE_CLASS),
        unit=state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
        name=state.attributes.get(ATTR_FRIENDLY_NAME),
        battery_level=has_battery_level(state),
        text_state=has_text_state(state),
    )


def async_inventory(hass: HomeAssistant) -> Inventory:
    """Discover the battery devices of Home Assistant right now."""
    records: list[EntityRecord] = []
    notes: list[tuple[EntityRecord, State]] = []
    for entry in er.async_get(hass).entities.values():
        state = hass.states.get(entry.entity_id)
        record = entity_record(entry, state)
        records.append(record)
        if entry.platform == BATTERY_NOTES and state is not None:
            notes.append((record, state))
    registered = {record.entity_id for record in records}
    records.extend(
        state_record(state)
        for state in hass.states.async_all()
        if state.entity_id not in registered
        and (state.domain in STATE_ONLY_DOMAINS or has_battery_level(state))
    )
    devices, main_ids = _device_records(hass, records)
    if main_ids:
        records = [
            replace(record, device_id=main_ids[record.device_id])
            if record.device_id in main_ids
            else record
            for record in records
        ]

    by_entity_id = {record.entity_id: record for record in records}
    metadata: dict[str, BatteryMetadata] = {}
    for record, state in notes:
        if (parsed := parse_metadata(state.attributes)) is None:
            continue
        if record.device_id:
            key = f"d:{main_ids.get(record.device_id, record.device_id)}"
        elif source := by_entity_id.get(state.attributes.get("source_entity_id", "")):
            key = group_key(source)
        else:
            continue
        metadata.setdefault(key, parsed)

    floors = {area.id: area.floor_id for area in ar.async_get(hass).async_list_areas()}
    return discover(records, devices, floors=floors, metadata=metadata)


def _device_records(
    hass: HomeAssistant, records: list[EntityRecord]
) -> tuple[dict[str, DeviceRecord], dict[str, str]]:
    """Describe the referenced devices, and map child devices to their parent."""
    registry = dr.async_get(hass)
    devices: dict[str, DeviceRecord] = {}
    main_ids: dict[str, str] = {}
    # DeviceRegistry.devices changed shape in 2026.9; lookups by id work everywhere.
    for device_id in {record.device_id for record in records if record.device_id}:
        device = registry.async_get(device_id)
        # Child devices (Home Assistant 2026.9+) run on the battery of their parent.
        if parent_id := getattr(device, "parent_device_id", None):
            main_ids[device_id] = parent_id
            device = registry.async_get(parent_id)
        if device is None:
            continue
        devices[device.id] = DeviceRecord(
            device_id=device.id,
            name=device.name_by_user or device.name,
            area_id=device.area_id,
            manufacturer=getattr(device, "manufacturer", None),
            model=getattr(device, "model", None),
            disabled=device.disabled,
        )
    return devices, main_ids
