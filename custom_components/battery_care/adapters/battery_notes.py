"""Read the battery metadata Battery Notes exposes, without depending on it."""

from collections.abc import Mapping
from typing import Any

from ..core.models import BatteryMetadata

DOMAIN = "battery_notes"
SOURCE = "battery_notes"
MAX_TYPE_LENGTH = 32
MAX_QUANTITY = 24


def parse_metadata(attributes: Mapping[str, Any]) -> BatteryMetadata | None:
    """Return type and quantity from a Battery Notes entity, or None if unusable."""
    battery_type = attributes.get("battery_type")
    if not isinstance(battery_type, str):
        return None
    battery_type = battery_type.strip()
    if not battery_type or len(battery_type) > MAX_TYPE_LENGTH:
        return None
    # A missing quantity means one battery.
    quantity = attributes.get("battery_quantity", 1)
    if isinstance(quantity, str) and quantity.strip().isdigit():
        quantity = int(quantity)
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        return None
    if not 1 <= quantity <= MAX_QUANTITY:
        return None
    return BatteryMetadata(battery_type=battery_type, quantity=quantity, source=SOURCE)
