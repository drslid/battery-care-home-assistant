"""Remembering devices, so one that comes back keeps its history."""

from datetime import UTC, datetime, timedelta

from custom_components.battery_care.core.known import (
    ORPHAN_RETENTION,
    KnownDevice,
    known_from_storage,
    known_to_storage,
    track,
)

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def test_present_devices_are_known() -> None:
    """Devices seen now are recorded with their current name."""
    known, expired = track({}, {"d:door": "Front Door"}, NOW)

    assert known == {"d:door": KnownDevice("Front Door")}
    assert expired == set()


def test_missing_devices_become_orphans_then_expire() -> None:
    """A removed device is kept for the retention period, then its data goes."""
    known, _ = track({"d:door": KnownDevice("Front Door")}, {}, NOW)
    assert known == {"d:door": KnownDevice("Front Door", NOW)}

    later = NOW + ORPHAN_RETENTION - timedelta(minutes=1)
    assert track(known, {}, later) == (known, set())

    assert track(known, {}, NOW + ORPHAN_RETENTION) == ({}, {"d:door"})


def test_a_returning_device_is_no_longer_an_orphan() -> None:
    """Home Assistant restores a deleted device id when the same device returns."""
    orphan = {"d:door": KnownDevice("Front Door", NOW)}

    known, expired = track(orphan, {"d:door": "Front Door"}, NOW + timedelta(days=3))

    assert known == {"d:door": KnownDevice("Front Door")}
    assert expired == set()


def test_storage_round_trip() -> None:
    """Names and orphan timestamps survive storage."""
    known = {"d:door": KnownDevice("Front Door"), "e:abc": KnownDevice("DIY", NOW)}

    assert known_from_storage(known_to_storage(known)) == (known, [])


def test_invalid_stored_entries_are_dropped() -> None:
    """Malformed entries are reported; doubtful timestamps count as unknown."""
    known, problems = known_from_storage(
        {
            "d:door": {"name": "Front Door", "orphaned_at": "2026-10-01T08:00:00"},
            "d:hall": {"name": "Hall", "orphaned_at": "yesterday"},
            "d:bad": {"orphaned_at": None},
            "d:worse": "Front Door",
        }
    )

    assert known == {
        "d:door": KnownDevice("Front Door", datetime(2026, 10, 1, 8, tzinfo=UTC)),
        "d:hall": KnownDevice("Hall"),
    }
    assert problems == ["d:bad", "d:worse"]
    assert known_from_storage(None) == ({}, [])
    assert known_from_storage([]) == ({}, ["*"])
