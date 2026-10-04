"""Persist Battery Care's own data with Home Assistant's storage helper."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .core.known import KnownDevice, known_from_storage, known_to_storage
from .core.policy import DeviceConfig, config_from_storage, config_to_storage
from .core.settings import (
    DEFAULTS,
    Settings,
    settings_from_storage,
    settings_to_storage,
)

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1
CONFIG_KEY = f"{DOMAIN}.config"
STATE_KEY = f"{DOMAIN}.state"
CONFIG_SAVE_DELAY = 1
STATE_SAVE_DELAY = 15


class BatteryCareStore(Store[dict[str, Any]]):
    """A store of the Battery Care schema."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Accept data from a newer minor version: minor versions only add fields."""
        return old_data


@dataclass(slots=True)
class ConfigData:
    """Everything the user decided: global settings and per-device choices."""

    settings: Settings = DEFAULTS
    devices: dict[str, DeviceConfig] = field(default_factory=dict)


def config_from_raw(raw: object) -> tuple[ConfigData, list[str]]:
    """Rebuild the configuration from storage, ignoring invalid values.

    Returns:
        The configuration, and the dotted names of the values that were ignored.
    """
    if raw is None:
        return ConfigData(), []
    if not isinstance(raw, Mapping):
        return ConfigData(), ["*"]
    settings, settings_problems = settings_from_storage(raw.get("settings"))
    problems = [f"settings.{name}" for name in settings_problems]
    stored_devices = raw.get("devices") or {}
    if not isinstance(stored_devices, Mapping):
        problems.append("devices.*")
        stored_devices = {}
    devices: dict[str, DeviceConfig] = {}
    for key, value in stored_devices.items():
        config, device_problems = config_from_storage(value)
        problems.extend(f"devices.{key}.{name}" for name in device_problems)
        if isinstance(key, str) and not config.is_default:
            devices[key] = config
    return ConfigData(settings, devices), problems


def config_to_raw(data: ConfigData) -> dict[str, Any]:
    """Return the storage form of the configuration."""
    return {
        "settings": settings_to_storage(data.settings),
        "devices": {
            key: config_to_storage(config) for key, config in data.devices.items()
        },
    }


def state_from_raw(raw: object) -> tuple[dict[str, KnownDevice], list[str]]:
    """Rebuild the runtime state from storage, ignoring invalid values."""
    if raw is None:
        return {}, []
    if not isinstance(raw, Mapping):
        return {}, ["*"]
    known, problems = known_from_storage(raw.get("known"))
    return known, [f"known.{name}" for name in problems]


def state_to_raw(known: Mapping[str, KnownDevice]) -> dict[str, Any]:
    """Return the storage form of the runtime state."""
    return {"known": known_to_storage(known)}


async def async_remove_stores(hass: HomeAssistant) -> None:
    """Delete everything Battery Care stored."""
    for key in (CONFIG_KEY, STATE_KEY):
        await BatteryCareStore(
            hass, STORAGE_VERSION, key, minor_version=STORAGE_MINOR_VERSION
        ).async_remove()
