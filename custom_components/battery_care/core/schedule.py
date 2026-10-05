"""Times of day in local time: the daily digest and quiet hours."""

from datetime import datetime, time, timedelta


def clock(minute: int) -> time:
    """Return the time of day that is this many minutes after midnight."""
    return time(minute // 60, minute % 60)


def minute_of(local: datetime) -> int:
    """Return how many minutes after midnight a local time is."""
    return local.hour * 60 + local.minute


def in_quiet_hours(minute: int, start: int, end: int) -> bool:
    """Return whether a minute of the day is in quiet hours, which may span midnight."""
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def next_at(local: datetime, minute: int) -> datetime:
    """Return the next local time at this time of day, strictly after now."""
    today = datetime.combine(local.date(), clock(minute), tzinfo=local.tzinfo)
    # Wall clock times of the same zone compare without their offsets.
    if today > local:
        return today
    return datetime.combine(
        local.date() + timedelta(days=1), clock(minute), tzinfo=local.tzinfo
    )
