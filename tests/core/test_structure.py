"""Structural rules and performance of the core."""

import ast
from pathlib import Path
import time

from custom_components.battery_care.core.discovery import discover
from custom_components.battery_care.core.models import DeviceRecord, EntityRecord

CORE = (
    Path(__file__).resolve().parents[2] / "custom_components" / "battery_care" / "core"
)
DISCOVERY_BUDGET = 0.25


def test_core_does_not_import_home_assistant() -> None:
    """The core stays testable and reusable without Home Assistant."""
    modules = sorted(CORE.glob("*.py"))
    assert modules
    imported: list[str] = []
    for path in modules:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.append(node.module)
    assert [name for name in imported if name.split(".")[0] == "homeassistant"] == []


def test_discovery_of_a_large_home_fits_the_budget() -> None:
    """1,000 battery devices among 6,000 entities are grouped in under 250 ms."""
    devices = {
        f"dev{i}": DeviceRecord(f"dev{i}", name=f"Sensor {i}") for i in range(1000)
    }
    entities = [
        EntityRecord(
            f"sensor.dev{i}_{suffix}",
            platform="zha",
            registry_id=f"id{i}{suffix}",
            device_id=f"dev{i}",
            device_class=device_class,
            unit=unit,
        )
        for i in range(1000)
        for suffix, device_class, unit in (
            ("battery", "battery", "%"),
            ("temperature", "temperature", "°C"),
            ("humidity", "humidity", "%"),
            ("voltage", "voltage", "V"),
            ("signal", "signal_strength", "dBm"),
        )
    ]
    entities += [EntityRecord(f"light.light_{i}", platform="hue") for i in range(1000)]

    started = time.perf_counter()
    inventory = discover(entities, devices)
    elapsed = time.perf_counter() - started

    assert len(inventory.devices) == 1000
    assert elapsed < DISCOVERY_BUDGET
