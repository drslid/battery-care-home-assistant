"""Decide how a battery is maintained and how much a dead battery would matter."""

from collections.abc import Callable
from dataclasses import dataclass

from .models import BatteryClass, Importance

UPS_INTEGRATIONS = frozenset({"apcupsd", "nut"})
VEHICLE_INTEGRATIONS = frozenset(
    {"bmw_connected_drive", "mazda", "nissan_leaf", "renault", "subaru", "volvo"}
)
# These serve both cars and Powerwalls; only the cars have a location.
TESLA_INTEGRATIONS = frozenset({"tesla_fleet", "teslemetry", "tessie"})
HOME_BATTERY_INTEGRATIONS = frozenset(
    {
        "enphase_envoy",
        "fronius",
        "goodwe",
        "growatt_server",
        "imeon_inverter",
        "powerwall",
        "sma",
        "solaredge",
        "solarlog",
        "solax",
        "victron_remote_monitoring",
    }
)
ROBOT_DOMAINS = frozenset({"lawn_mower", "vacuum"})
SAFETY_BINARY_SENSOR_CLASSES = frozenset(
    {"carbon_monoxide", "gas", "moisture", "smoke"}
)
PRIMARY_CELLS = frozenset(
    {
        "9V",
        "A23",
        "A27",
        "AA",
        "AAA",
        "AAAA",
        "C",
        "CR11108",
        "CR1220",
        "CR123A",
        "CR15270",
        "CR1616",
        "CR1620",
        "CR1632",
        "CR17345",
        "CR2",
        "CR2016",
        "CR2025",
        "CR2032",
        "CR2430",
        "CR2450",
        "CR2477",
        "D",
        "ER14250",
        "ER14505",
        "FR03",
        "FR6",
        "LR03",
        "LR1130",
        "LR14",
        "LR20",
        "LR41",
        "LR44",
        "LR6",
        "LR61",
        "SR44",
    }
)
# Battery Notes names built-in rechargeable batteries this way.
RECHARGEABLE_TYPE = "RECHARGEABLE"


@dataclass(frozen=True, slots=True)
class DeviceTraits:
    """What the other entities and the metadata of a device reveal."""

    integration: str | None = None
    has_charging: bool = False
    domains: frozenset[str] = frozenset()
    device_classes: frozenset[tuple[str, str]] = frozenset()
    battery_type: str | None = None


def normalize_battery_type(battery_type: str) -> str:
    """Return a comparable form of a battery type, such as CR123A."""
    return "".join(battery_type.split()).upper()


type Rule = tuple[Callable[[DeviceTraits, str], bool], BatteryClass, str]

# First match wins: vehicles, home batteries and robots also have charging sensors.
RULES: tuple[Rule, ...] = (
    (
        lambda traits, _: traits.integration in UPS_INTEGRATIONS,
        BatteryClass.UPS,
        "integration",
    ),
    (
        lambda traits, _: (
            traits.integration in VEHICLE_INTEGRATIONS
            or (
                traits.integration in TESLA_INTEGRATIONS
                and "device_tracker" in traits.domains
            )
        ),
        BatteryClass.VEHICLE,
        "integration",
    ),
    (
        lambda traits, _: (
            traits.integration in HOME_BATTERY_INTEGRATIONS | TESLA_INTEGRATIONS
        ),
        BatteryClass.HOME_BATTERY,
        "integration",
    ),
    (
        lambda traits, _: ("sensor", "energy_storage") in traits.device_classes,
        BatteryClass.HOME_BATTERY,
        "energy_storage",
    ),
    (
        lambda traits, _: bool(traits.domains & ROBOT_DOMAINS),
        BatteryClass.ROBOT,
        "robot",
    ),
    (
        lambda traits, _: traits.has_charging,
        BatteryClass.RECHARGEABLE,
        "charging_sensor",
    ),
    (
        lambda traits, _: traits.integration == "mobile_app",
        BatteryClass.RECHARGEABLE,
        "mobile_app",
    ),
    (
        lambda _, battery_type: battery_type == RECHARGEABLE_TYPE,
        BatteryClass.RECHARGEABLE,
        "battery_type",
    ),
    (
        lambda _, battery_type: battery_type in PRIMARY_CELLS,
        BatteryClass.REPLACEABLE,
        "battery_type",
    ),
)


def classify(traits: DeviceTraits) -> tuple[BatteryClass, str]:
    """Return the automatic class of a battery and the reason for it."""
    battery_type = normalize_battery_type(traits.battery_type or "")
    for matches, battery_class, reason in RULES:
        if matches(traits, battery_type):
            return battery_class, reason
    return BatteryClass.UNKNOWN, "default"


def suggest_importance(traits: DeviceTraits) -> Importance:
    """Suggest Important for locks and safety sensors; never suggest Critical."""
    if "lock" in traits.domains or any(
        ("binary_sensor", device_class) in traits.device_classes
        for device_class in SAFETY_BINARY_SENSOR_CLASSES
    ):
        return Importance.IMPORTANT
    return Importance.NORMAL
