"""Quiet hours and the next local occurrence of a time of day, across DST."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.battery_care.core.schedule import (
    clock,
    in_quiet_hours,
    minute_of,
    next_at,
)

PARIS = ZoneInfo("Europe/Paris")


@pytest.mark.parametrize(
    ("minute", "quiet"),
    [
        (21 * 60 + 59, False),
        (22 * 60, True),
        (0, True),
        (7 * 60 + 59, True),
        (480, False),
    ],
)
def test_quiet_hours_across_midnight(minute: int, quiet: bool) -> None:
    """22:00 to 08:00 includes the start and excludes the end."""
    assert in_quiet_hours(minute, 22 * 60, 8 * 60) is quiet


def test_quiet_hours_within_a_day() -> None:
    """13:00 to 15:00, for a nap."""
    assert in_quiet_hours(14 * 60, 13 * 60, 15 * 60)
    assert not in_quiet_hours(15 * 60, 13 * 60, 15 * 60)
    assert not in_quiet_hours(12 * 60, 13 * 60, 15 * 60)


def test_minutes_and_clock() -> None:
    """Minutes after midnight, both ways."""
    local = datetime(2026, 10, 25, 18, 30, tzinfo=PARIS)
    assert minute_of(local) == 1110
    assert clock(1110).isoformat() == "18:30:00"


def test_the_next_time_is_today_or_tomorrow() -> None:
    """Strictly after now: a time equal to now is tomorrow."""
    now = datetime(2026, 7, 1, 18, 0, tzinfo=PARIS)

    assert next_at(now, 18 * 60 + 1) == datetime(2026, 7, 1, 18, 1, tzinfo=PARIS)
    assert next_at(now, 18 * 60) == datetime(2026, 7, 2, 18, 0, tzinfo=PARIS)


def test_daylight_saving_keeps_the_wall_clock() -> None:
    """08:00 after a DST change is still 08:00 local, one hour apart in UTC."""
    before_autumn = datetime(2026, 10, 24, 22, 0, tzinfo=PARIS)
    before_spring = datetime(2026, 3, 28, 22, 0, tzinfo=PARIS)

    autumn = next_at(before_autumn, 8 * 60)
    spring = next_at(before_spring, 8 * 60)

    assert (autumn.hour, autumn.utcoffset()) == (
        8,
        datetime(2026, 1, 1, tzinfo=PARIS).utcoffset(),
    )
    assert autumn.astimezone(UTC).hour == 7
    assert spring.astimezone(UTC).hour == 6
