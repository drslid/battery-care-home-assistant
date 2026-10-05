"""Read and write timestamps in Battery Care's stored data."""

from datetime import UTC, datetime


def parse_time(value: object) -> datetime | None:
    """Read an ISO timestamp, naive ones as UTC; anything else counts as unknown."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def format_time(value: datetime | None) -> str | None:
    """Return the stored form of a timestamp."""
    return value.isoformat() if value is not None else None
