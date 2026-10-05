"""What the panel shows for each battery device, and the counts it summarizes.

Until the alert engine exists, the status comes from the current reading and
the thresholds alone: there is no grace period, delay or history yet.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from .policy import DeviceMode
from .readings import Reading
from .settings import Settings


class Status(StrEnum):
    """The state of a battery device, as the panel labels it."""

    CRITICAL = "critical"
    LOW = "low"
    NOT_RESPONDING = "not_responding"
    CHARGING = "charging"
    OK = "ok"
    UNKNOWN = "unknown"
    IGNORED = "ignored"


ATTENTION = frozenset({Status.CRITICAL, Status.LOW, Status.NOT_RESPONDING})

type Rule = Callable[[Reading, Settings], bool]

# The first matching rule wins; a device that matches none is OK.
RULES: tuple[tuple[Rule, Status], ...] = (
    (lambda reading, _settings: not reading.available, Status.NOT_RESPONDING),
    (lambda reading, _settings: reading.charging, Status.CHARGING),
    (
        lambda reading, settings: (
            reading.level is not None and reading.level <= settings.critical_threshold
        ),
        Status.CRITICAL,
    ),
    (
        lambda reading, settings: (
            bool(reading.low)
            or (reading.level is not None and reading.level <= settings.low_threshold)
        ),
        Status.LOW,
    ),
    (
        lambda reading, _settings: reading.level is None and reading.low is None,
        Status.UNKNOWN,
    ),
)


def device_status(reading: Reading, settings: Settings, mode: DeviceMode) -> Status:
    """Return the status of a device from its reading and effective settings."""
    if mode is DeviceMode.IGNORED:
        return Status.IGNORED
    return next(
        (status for rule, status in RULES if rule(reading, settings)), Status.OK
    )


def needs_attention(status: Status, settings: Settings) -> bool:
    """Return whether Battery Care asks the user to act on this device."""
    return settings.alerts_enabled and status in ATTENTION


@dataclass(frozen=True, slots=True)
class Summary:
    """Counts of battery devices; only devices with alerts on are monitored.

    A monitored device without any reading yet is neither healthy nor a
    problem: it counts as unknown.
    """

    total: int = 0
    monitored: int = 0
    healthy: int = 0
    attention: int = 0
    critical: int = 0
    low: int = 0
    not_responding: int = 0
    unknown: int = 0


def summarize(devices: Iterable[tuple[Status, bool]]) -> Summary:
    """Count devices, each given as its status and whether its alerts are on."""
    total = monitored = unknown = 0
    attention = dict.fromkeys(ATTENTION, 0)
    for status, alerts_enabled in devices:
        total += 1
        if not alerts_enabled:
            continue
        monitored += 1
        if status in attention:
            attention[status] += 1
        elif status is Status.UNKNOWN:
            unknown += 1
    needing = sum(attention.values())
    return Summary(
        total=total,
        monitored=monitored,
        healthy=monitored - needing - unknown,
        attention=needing,
        critical=attention[Status.CRITICAL],
        low=attention[Status.LOW],
        not_responding=attention[Status.NOT_RESPONDING],
        unknown=unknown,
    )
