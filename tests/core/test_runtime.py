"""The stored form of runtime states."""

from datetime import UTC, datetime

from custom_components.battery_care.core.runtime import (
    Runtime,
    Severity,
    runtime_from_storage,
    runtime_to_storage,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def test_a_runtime_state_survives_storage() -> None:
    """Every field comes back; empty ones are not written."""
    runtime = Runtime(
        severity=Severity.CRITICAL,
        last_level=7.5,
        last_low=False,
        low_off_since=NOW,
        unavailable_since=NOW,
        not_responding=True,
        evidence_at=NOW,
        stale=True,
        snoozed_until=NOW,
        acknowledged_at=NOW,
        next_reminder_at=NOW,
    )

    assert runtime_from_storage(runtime_to_storage(runtime)) == (runtime, [])
    assert runtime_to_storage(Runtime()) == {
        "severity": "normal",
        "not_responding": False,
        "stale": False,
    }


def test_invalid_values_fall_back_to_their_defaults() -> None:
    """Each bad value is reported by name; the others are kept."""
    runtime, problems = runtime_from_storage(
        {
            "severity": "dead",
            "last_level": 150,
            "last_low": "yes",
            "stale": True,
            "snoozed_until": "tomorrow",
            "next_reminder_at": "2026-01-15T12:00:00",
        }
    )

    assert runtime == Runtime(stale=True, next_reminder_at=NOW)
    assert problems == ["severity", "last_level", "last_low", "snoozed_until"]
    assert runtime_from_storage({"severity": 3, "last_level": True}) == (
        Runtime(),
        ["severity", "last_level"],
    )
    assert runtime_from_storage("low") == (Runtime(), ["*"])
