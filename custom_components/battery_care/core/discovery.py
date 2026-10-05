"""Find battery entities and group them into battery devices."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
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
SUGGESTION_NAME = re.compile(r"batt|bater", re.IGNORECASE)
KIND_ORDER = {SourceKind.LEVEL: 0, SourceKind.LOW: 1, SourceKind.CHARGING: 2}

type Candidate = tuple[EntityRecord, SourceKind]


def source_kind(entity: EntityRecord) -> SourceKind | None:
    """Return what the entity says about a battery, if anything."""
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


def is_suggestion(entity: EntityRecord) -> bool:
    """Return whether a percentage sensor without device class looks like a battery."""
    return (
        entity.domain == "sensor"
        and entity.device_class is None
        and entity.unit == "%"
        and SUGGESTION_NAME.search(entity.name or entity.entity_id) is not None
    )


def _drop_redundant_helpers(candidates: list[Candidate]) -> list[Candidate]:
    """Keep helper sources only where the device has no native equivalent."""
    native = {
        kind for entity, kind in candidates if entity.platform not in HELPER_PLATFORMS
    }
    return [
        (entity, kind)
        for entity, kind in candidates
        if entity.platform not in HELPER_PLATFORMS
        or not (
            kind in native or (kind is SourceKind.LOW and SourceKind.LEVEL in native)
        )
    ]


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
        candidates, key=lambda item: (KIND_ORDER[item[1]], item[0].entity_id)
    )
    primary = next(
        entity for entity, kind in ordered if kind is not SourceKind.CHARGING
    )
    traits = DeviceTraits(
        integration=primary.platform,
        has_charging=any(kind is SourceKind.CHARGING for _, kind in ordered),
        domains=frozenset(entity.domain for entity in siblings),
        device_classes=frozenset(
            (entity.domain, entity.device_class)
            for entity in siblings
            if entity.device_class
        ),
        battery_type=metadata.battery_type if metadata else None,
    )
    battery_class, reason = classify(traits)
    area_id = next((entity.area_id for entity, _ in ordered if entity.area_id), None)
    if area_id is None and device is not None:
        area_id = device.area_id
    platforms = {entity.platform for entity, _ in ordered}
    evidence = {entity.entity_id for entity, _ in ordered} | {
        entity.entity_id for entity in siblings if entity.platform in platforms
    }
    return BatteryDevice(
        key=key,
        name=_name(ordered, device),
        sources=tuple(
            BatterySource(entity.entity_id, kind) for entity, kind in ordered
        ),
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
    possible_suggestions: list[EntityRecord] = []
    for entity in entities:
        if entity.device_id and not entity.disabled:
            siblings[entity.device_id].append(entity)
        if entity.platform == OWN_PLATFORM or entity.platform in MIRROR_PLATFORMS:
            continue
        kind = source_kind(entity)
        if kind is not None:
            candidates[group_key(entity)].append((entity, kind))
        elif not entity.disabled and is_suggestion(entity):
            possible_suggestions.append(entity)

    found: dict[str, BatteryDevice] = {}
    not_monitored: list[NotMonitored] = []
    for key, group in candidates.items():
        device_id = group[0][0].device_id
        device = devices.get(device_id) if device_id else None
        device_disabled = device is not None and device.disabled
        active = [
            (entity, kind)
            for entity, kind in group
            if not (entity.disabled or device_disabled)
        ]
        if not any(kind is not SourceKind.CHARGING for _, kind in active):
            if any(kind is not SourceKind.CHARGING for _, kind in group):
                not_monitored.append(
                    NotMonitored(key, _name(group, device), "disabled")
                )
            continue
        found[key] = _build(
            key,
            _drop_redundant_helpers(active),
            device=device,
            siblings=siblings.get(device_id, []) if device_id else [],
            floors=floors or {},
            metadata=(metadata or {}).get(key),
        )

    suggestions = sorted(
        entity.entity_id
        for entity in possible_suggestions
        if not (
            (battery_device := found.get(group_key(entity)))
            and battery_device.entity_ids(SourceKind.LEVEL)
        )
    )
    return Inventory(
        devices=dict(sorted(found.items())),
        suggestions=tuple(suggestions),
        not_monitored=tuple(sorted(not_monitored, key=lambda item: item.key)),
    )
