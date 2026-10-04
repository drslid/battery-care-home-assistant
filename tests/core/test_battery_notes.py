"""Reading Battery Notes metadata defensively."""

from typing import Any

import pytest

from custom_components.battery_care.adapters.battery_notes import parse_metadata
from custom_components.battery_care.core.models import BatteryMetadata


def test_type_and_quantity() -> None:
    """The usual attributes of a Battery Notes entity."""
    assert parse_metadata({"battery_type": " CR123A ", "battery_quantity": 2}) == (
        BatteryMetadata("CR123A", 2, "battery_notes")
    )


def test_quantity_written_as_text_or_missing() -> None:
    """A numeric string is accepted; a missing quantity means one battery."""
    assert parse_metadata({"battery_type": "AAA", "battery_quantity": "4"}) == (
        BatteryMetadata("AAA", 4, "battery_notes")
    )
    assert parse_metadata({"battery_type": "CR2032"}) == BatteryMetadata(
        "CR2032", 1, "battery_notes"
    )


@pytest.mark.parametrize(
    "attributes",
    [
        {},
        {"battery_type": None},
        {"battery_type": 2032},
        {"battery_type": "   "},
        {"battery_type": "X" * 33},
        {"battery_type": "AA", "battery_quantity": True},
        {"battery_type": "AA", "battery_quantity": 0},
        {"battery_type": "AA", "battery_quantity": 25},
        {"battery_type": "AA", "battery_quantity": "two"},
        {"battery_type": "AA", "battery_quantity": 1.5},
    ],
)
def test_unusable_attributes(attributes: dict[str, Any]) -> None:
    """Anything doubtful is ignored rather than guessed."""
    assert parse_metadata(attributes) is None
