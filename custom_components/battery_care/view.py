"""Build what the panel shows from the manager's data."""

from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import area_registry as ar
from homeassistant.loader import IntegrationNotLoaded, async_get_loaded_integration

from .core.models import BatterySource, Importance
from .core.policy import battery_class, importance
from .core.status import needs_attention
from .manager import BatteryCareManager

API_VERSION = 1


def _area_names(hass: HomeAssistant) -> dict[str, str]:
    return {area.id: area.name for area in ar.async_get(hass).async_list_areas()}


def _device(
    manager: BatteryCareManager, key: str, areas: dict[str, str]
) -> dict[str, Any]:
    device = manager.inventory.devices[key]
    config = manager.device_config(key)
    status = manager.status(key)
    metadata = device.metadata
    level = manager.readings[key].level
    if level is None and (runtime := manager.state.devices.get(key)) is not None:
        # The last known level, for a device that is silent right now.
        level = runtime.last_level
    return {
        "key": key,
        "name": device.name,
        "area": areas.get(device.area_id) if device.area_id else None,
        "level": level,
        "status": status.value,
        "attention": needs_attention(status, manager.effective_settings(key)),
        "battery": None
        if metadata is None
        else {"type": metadata.battery_type, "quantity": metadata.quantity},
        "battery_class": battery_class(device, config).value,
        "importance": importance(device, config).value,
    }


def _message(
    hass: HomeAssistant,
    manager: BatteryCareManager,
    message_type: str,
    keys: Iterable[str],
) -> dict[str, Any]:
    areas = _area_names(hass)
    return {
        "api": API_VERSION,
        "type": message_type,
        "summary": asdict(manager.summary),
        "devices": [_device(manager, key, areas) for key in keys],
    }


def snapshot(hass: HomeAssistant, manager: BatteryCareManager) -> dict[str, Any]:
    """Return everything the panel shows."""
    message = _message(hass, manager, "snapshot", manager.inventory.devices)
    message["ready"] = manager.ready
    return message


def patch(
    hass: HomeAssistant, manager: BatteryCareManager, keys: Iterable[str]
) -> dict[str, Any]:
    """Return the summary and the devices that changed."""
    return _message(hass, manager, "patch", sorted(keys))


def _integration_name(hass: HomeAssistant, domain: str | None) -> str | None:
    if domain is None:
        return None
    try:
        return async_get_loaded_integration(hass, domain).name
    except IntegrationNotLoaded:
        return domain


def device_details(
    hass: HomeAssistant, manager: BatteryCareManager, key: str
) -> dict[str, Any]:
    """Return everything the device sheet shows."""
    device = manager.inventory.devices[key]
    config = manager.device_config(key)
    settings = manager.effective_settings(key)
    states = {
        source.entity_id: hass.states.get(source.entity_id) for source in device.sources
    }
    reported = [
        state.last_reported
        for state in states.values()
        if state is not None and state.state != STATE_UNAVAILABLE
    ]
    if config.importance is not None:
        importance_source = "user"
    elif device.suggested_importance is not Importance.NORMAL:
        importance_source = "suggested"
    else:
        importance_source = "default"
    return {
        "api": API_VERSION,
        "device": _device(manager, key, _area_names(hass)),
        "integration": _integration_name(hass, device.integration),
        "manufacturer": device.manufacturer,
        "model": device.model,
        "class_reason": "user" if config.battery_class else device.class_reason,
        "importance_source": importance_source,
        "mode": config.mode.value,
        "alerts": settings.alerts_enabled,
        "low_threshold": settings.low_threshold,
        "critical_threshold": settings.critical_threshold,
        "stable": device.stable,
        "last_report": max(reported).isoformat() if reported else None,
        "sources": [
            _source(source, states[source.entity_id]) for source in device.sources
        ],
    }


def _source(source: BatterySource, state: State | None) -> dict[str, Any]:
    return {
        "entity_id": source.entity_id,
        "kind": source.kind.value,
        "name": state.name if state else source.entity_id,
        "state": state.state if state else None,
    }
