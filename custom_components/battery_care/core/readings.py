"""Turn the states of battery sources into one reading per battery device."""

from collections.abc import Mapping
from dataclasses import dataclass

from .models import BatteryDevice, BatterySource, SourceKind

STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"
STATE_ON = "on"
STATE_OFF = "off"
MAX_LEVEL = 100
# Text states of batteries, written lower case with underscores.
CRITICAL_WORDS = frozenset({"critical", "depleted", "empty", "very_low"})
LOW_WORDS = CRITICAL_WORDS | {"low", "weak"}
OK_WORDS = frozenset(
    {"charged", "full", "good", "high", "medium", "middle", "normal", "ok"}
)
TEXT_STATES = LOW_WORDS | OK_WORDS


@dataclass(frozen=True, slots=True)
class Reading:
    """What the sources of a battery device currently say."""

    level: float | None
    low: bool | None
    charging: bool
    available: bool
    invalid: tuple[str, ...] = ()
    # A text state that says the battery is empty or critical.
    critical: bool | None = None


def parse_level(state: str) -> float | None:
    """Return a battery percentage, or None when the value is not a valid one."""
    try:
        value = float(state)
    except ValueError:
        return None
    # NaN fails both comparisons.
    return value if 0 <= value <= MAX_LEVEL else None


def text_state(value: str) -> str | None:
    """Return a known battery text state in its canonical form, or None."""
    word = value.strip().casefold().replace(" ", "_").replace("-", "_")
    return word if word in TEXT_STATES else None


def read(device: BatteryDevice, values: Mapping[BatterySource, str | None]) -> Reading:
    """Read a battery device; the level is the worst of its level sources.

    Args:
        device: the battery device.
        values: the state, or the attribute, of each source; None when missing.
    """
    levels: list[float] = []
    lows: list[bool] = []
    criticals: list[bool] = []
    invalid: list[str] = []
    available = False
    charging = False
    for source in device.sources:
        value = values.get(source)
        if source.kind is SourceKind.CHARGING:
            charging = charging or value == STATE_ON
            continue
        if value is None or value == STATE_UNAVAILABLE:
            continue
        available = True
        if value == STATE_UNKNOWN:
            continue
        if source.kind is SourceKind.LEVEL:
            level = parse_level(value)
            if level is None:
                invalid.append(source.entity_id)
            else:
                levels.append(level)
        elif source.kind is SourceKind.STATE:
            if (word := text_state(value)) is None:
                invalid.append(source.entity_id)
            else:
                lows.append(word in LOW_WORDS)
                criticals.append(word in CRITICAL_WORDS)
        elif value in (STATE_ON, STATE_OFF):
            lows.append(value == STATE_ON)
        else:
            invalid.append(source.entity_id)
    return Reading(
        level=min(levels) if levels else None,
        low=any(lows) if lows else None,
        charging=charging,
        available=available,
        invalid=tuple(invalid),
        critical=any(criticals) if criticals else None,
    )
