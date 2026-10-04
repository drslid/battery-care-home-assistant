"""Turn the states of battery sources into one reading per battery device."""

from collections.abc import Mapping
from dataclasses import dataclass

from .models import BatteryDevice, SourceKind

STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"
STATE_ON = "on"
STATE_OFF = "off"
MAX_LEVEL = 100


@dataclass(frozen=True, slots=True)
class Reading:
    """What the sources of a battery device currently say."""

    level: float | None
    low: bool | None
    charging: bool
    available: bool
    invalid: tuple[str, ...] = ()


def parse_level(state: str) -> float | None:
    """Return a battery percentage, or None when the value is not a valid one."""
    try:
        value = float(state)
    except ValueError:
        return None
    # NaN fails both comparisons.
    return value if 0 <= value <= MAX_LEVEL else None


def read(device: BatteryDevice, states: Mapping[str, str | None]) -> Reading:
    """Read a battery device; the level is the worst of its level sources."""
    levels: list[float] = []
    lows: list[bool] = []
    invalid: list[str] = []
    available = False
    charging = False
    for source in device.sources:
        state = states.get(source.entity_id)
        if source.kind is SourceKind.CHARGING:
            charging = charging or state == STATE_ON
            continue
        if state is None or state == STATE_UNAVAILABLE:
            continue
        available = True
        if state == STATE_UNKNOWN:
            continue
        if source.kind is SourceKind.LEVEL:
            level = parse_level(state)
            if level is None:
                invalid.append(source.entity_id)
            else:
                levels.append(level)
        elif state in (STATE_ON, STATE_OFF):
            lows.append(state == STATE_ON)
        else:
            invalid.append(source.entity_id)
    return Reading(
        level=min(levels) if levels else None,
        low=any(lows) if lows else None,
        charging=charging,
        available=available,
        invalid=tuple(invalid),
    )
