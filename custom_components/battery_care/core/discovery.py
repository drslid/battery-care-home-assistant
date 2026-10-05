"""Find battery entities and group them into battery devices."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from enum import IntEnum
import re

from .classification import DeviceTraits, classify, suggest_importance
from .models import (
    BatteryDevice,
    BatteryMetadata,
    BatterySource,
    DeviceRecord,
    EntityRecord,
    Inventory,
    NotMonitored,
    SourceKind,
)

OWN_PLATFORM = "battery_care"
# Mirrors and aggregates of other battery entities: never a battery of their own.
MIRROR_PLATFORMS = frozenset(
    {"battery_notes", "filter", "group", "min_max", "statistics"}
)
# Helpers that build a battery value: used only when the device has no native one.
HELPER_PLATFORMS = frozenset({"compensation", "template", "threshold", "trend"})
BATTERY_NAME = re.compile(r"batt|bater|akku|\bpiles?\b", re.IGNORECASE)
BATTERY_LEVEL_ATTRIBUTE = "battery_level"
KIND_ORDER = {
    SourceKind.LEVEL: 0,
    SourceKind.STATE: 1,
    SourceKind.LOW: 2,
    SourceKind.CHARGING: 3,
}


class Rank(IntEnum):
    """How far a source can be trusted; weaker ones only stand in for stronger."""

    NATIVE = 0
    HELPER = 1
    NAMED = 2
    ATTRIBUTE = 3
    TEXT = 4


type Candidate = tuple[EntityRecord, BatterySource, Rank]


def source_kind(entity: EntityRecord) -> SourceKind | None:
    """Return what the device class of an entity says about a battery, if anything."""
    if entity.domain == "sensor":
        if entity.device_class == "battery" and entity.unit == "%":
            return SourceKind.LEVEL
    elif entity.domain == "binary_sensor":
        if entity.device_class == "battery":
            return SourceKind.LOW
        if entity.device_class == "battery_charging":
            return SourceKind.CHARGING
    return None


def group_key(entity: EntityRecord) -> str:
    """Return the key of the battery device an entity belongs to."""
    if entity.device_id:
        return f"d:{entity.device_id}"
    if entity.registry_id:
        return f"e:{entity.registry_id}"
    return f"s:{entity.entity_id}"


def named_like_a_battery(entity: EntityRecord) -> bool:
    """Return whether the name of an entity says it is about a battery."""
    return BATTERY_NAME.search(entity.name or entity.entity_id) is not None


def candidates_of(entity: EntityRecord) -> list[Candidate]:
    """Return the battery sources an entity can provide, with their trust."""
    found: list[Candidate] = []
    if (kind := source_kind(entity)) is not None:
        rank = Rank.HELPER if entity.platform in HELPER_PLATFORMS else Rank.NATIVE
        found.append((entity, BatterySource(entity.entity_id, kind), rank))
    elif entity.domain == "sensor":
        named = named_like_a_battery(entity)
        if named and entity.device_class is None and entity.unit == "%":
            source = BatterySource(entity.entity_id, SourceKind.LEVEL)
            found.append((entity, source, Rank.NAMED))
        elif entity.text_state and (
            entity.device_class == "battery"
            or (named and entity.device_class in (None, "enum"))
        ):
            source = BatterySource(entity.entity_id, SourceKind.STATE)
            found.append((entity, source, Rank.TEXT))
    if entity.battery_level:
        source = BatterySource(
            entity.entity_id, SourceKind.LEVEL, BATTERY_LEVEL_ATTRIBUTE
        )
        found.append((entity, source, Rank.ATTRIBUTE))
    return found


def _drop_redundant_helpers(candidates: list[Candidate]) -> list[Candidate]:
    """Keep helper sources only where the device has no native equivalent."""
    native = {source.kind for _, source, rank in candidates if rank is Rank.NATIVE}
    return [
        (entity, source, rank)
        for entity, source, rank in candidates
        if rank is not Rank.HELPER
        or not (
            source.kind in native
            or (source.kind is SourceKind.LOW and SourceKind.LEVEL in native)
        )
    ]


def _select(candidates: list[Candidate]) -> list[Candidate]:
    """Keep the trusted sources; weaker kinds only stand in when there are none."""
    charging = [item for item in candidates if item[1].kind is SourceKind.CHARGING]
    values = [item for item in candidates if item[1].kind is not SourceKind.CHARGING]
    if trusted := [item for item in values if item[2] <= Rank.HELPER]:
        return _drop_redundant_helpers(trusted + charging)
    best = min(rank for _, _, rank in values)
    return [item for item in values if item[2] == best] + charging


def _name(candidates: list[Candidate], device: DeviceRecord | None) -> str:
    if device is not None and device.name:
        return device.name
    entity = candidates[0][0]
    return entity.name or entity.entity_id


def _build(
    key: str,
    candidates: list[Candidate],
    *,
    device: DeviceRecord | None,
    siblings: list[EntityRecord],
    floors: Mapping[str, str | None],
    metadata: BatteryMetadata | None,
) -> BatteryDevice:
    ordered = sorted(
        candidates,
        key=lambda item: (
            KIND_ORDER[item[1].kind],
            item[1].entity_id,
            item[1].attribute or "",
        ),
    )
    primary = next(
        entity
        for entity, source, _ in ordered
        if source.kind is not SourceKind.CHARGING
    )
    traits = DeviceTraits(
        integration=primary.platform,
        has_charging=any(
            source.kind is SourceKind.CHARGING for _, source, _ in ordered
        ),
        domains=frozenset(entity.domain for entity in siblings),
        device_classes=frozenset(
            (entity.domain, entity.device_class)
            for entity in siblings
            if entity.device_class
        ),
        battery_type=metadata.battery_type if metadata else None,
    )
    battery_class, reason = classify(traits)
    area_id = next((entity.area_id for entity, _, _ in ordered if entity.area_id), None)
    if area_id is None and device is not None:
        area_id = device.area_id
    platforms = {entity.platform for entity, _, _ in ordered}
    evidence = {entity.entity_id for entity, _, _ in ordered} | {
        entity.entity_id for entity in siblings if entity.platform in platforms
    }
    return BatteryDevice(
        key=key,
        name=_name(ordered, device),
        sources=tuple(source for _, source, _ in ordered),
        battery_class=battery_class,
        class_reason=reason,
        suggested_importance=suggest_importance(traits),
        device_id=primary.device_id,
        area_id=area_id,
        floor_id=floors.get(area_id) if area_id else None,
        integration=primary.platform,
        manufacturer=device.manufacturer if device else None,
        model=device.model if device else None,
        metadata=metadata,
        evidence=tuple(sorted(evidence)),
    )


def discover(
    entities: Iterable[EntityRecord],
    devices: Mapping[str, DeviceRecord],
    *,
    floors: Mapping[str, str | None] | None = None,
    metadata: Mapping[str, BatteryMetadata] | None = None,
) -> Inventory:
    """Group battery entities into battery devices.

    Args:
        entities: every entity, so that siblings can reveal what a device is.
        devices: devices by id.
        floors: floor id by area id.
        metadata: battery metadata by battery device key.
    """
    candidates: dict[str, list[Candidate]] = defaultdict(list)
    siblings: dict[str, list[EntityRecord]] = defaultdict(list)
    for entity in entities:
        if entity.device_id and not entity.disabled:
            siblings[entity.device_id].append(entity)
        if entity.platform == OWN_PLATFORM or entity.platform in MIRROR_PLATFORMS:
            continue
        if found := candidates_of(entity):
            candidates[group_key(entity)].extend(found)

    found_devices: dict[str, BatteryDevice] = {}
    not_monitored: list[NotMonitored] = []
    for key, group in candidates.items():
        device_id = group[0][0].device_id
        device = devices.get(device_id) if device_id else None
        device_disabled = device is not None and device.disabled
        active = [item for item in group if not (item[0].disabled or device_disabled)]
        if not any(source.kind is not SourceKind.CHARGING for _, source, _ in active):
            if any(source.kind is not SourceKind.CHARGING for _, source, _ in group):
                not_monitored.append(
                    NotMonitored(key, _name(group, device), "disabled")
                )
            continue
        found_devices[key] = _build(
            key,
            _select(active),
            device=device,
            siblings=siblings.get(device_id, []) if device_id else [],
            floors=floors or {},
            metadata=(metadata or {}).get(key),
        )

    return Inventory(
        devices=dict(sorted(found_devices.items())),
        not_monitored=tuple(sorted(not_monitored, key=lambda item: item.key)),
    )
