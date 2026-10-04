"""Remember known devices, so a device that comes back keeps its history."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

ORPHAN_RETENTION = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class KnownDevice:
    """A battery device seen at least once."""

    name: str
    orphaned_at: datetime | None = None


def track(
    known: Mapping[str, KnownDevice], present: Mapping[str, str], now: datetime
) -> tuple[dict[str, KnownDevice], set[str]]:
    """Update the index with the devices present now, by key and name.

    Missing devices become orphans; orphans older than the retention are dropped.

    Returns:
        The new index, and the keys whose data must be deleted.
    """
    result = {key: KnownDevice(name) for key, name in present.items()}
    expired: set[str] = set()
    for key, entry in known.items():
        if key in present:
            continue
        orphaned_at = entry.orphaned_at or now
        if now - orphaned_at >= ORPHAN_RETENTION:
            expired.add(key)
        else:
            result[key] = KnownDevice(entry.name, orphaned_at)
    return result, expired


def known_from_storage(raw: object) -> tuple[dict[str, KnownDevice], list[str]]:
    """Rebuild the index, dropping malformed entries.

    Returns:
        The index, and the keys that were ignored.
    """
    if not isinstance(raw, Mapping):
        return {}, [] if raw is None else ["*"]
    known: dict[str, KnownDevice] = {}
    problems: list[str] = []
    for key, entry in raw.items():
        name = entry.get("name") if isinstance(entry, Mapping) else None
        if not isinstance(key, str) or not isinstance(name, str):
            problems.append(str(key))
            continue
        known[key] = KnownDevice(name, _parse_time(entry.get("orphaned_at")))
    return known, problems


def known_to_storage(known: Mapping[str, KnownDevice]) -> dict[str, Any]:
    """Return the storage form of the index."""
    return {
        key: {
            "name": entry.name,
            "orphaned_at": entry.orphaned_at.isoformat() if entry.orphaned_at else None,
        }
        for key, entry in known.items()
    }


def _parse_time(value: object) -> datetime | None:
    """Read an aware timestamp; anything else counts as unknown."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
