"""The health score: one number for the state of every monitored battery."""

from collections.abc import Iterable
import math

from .models import Importance
from .status import Status

WEIGHTS = {
    Importance.LOW: 0.5,
    Importance.NORMAL: 1.0,
    Importance.IMPORTANT: 2.0,
    Importance.CRITICAL: 3.0,
}
PENALTIES = {
    Status.CRITICAL: 1.0,
    Status.NOT_RESPONDING: 0.5,
    Status.LOW: 0.4,
    Status.STALE: 0.2,
}
# A critical battery never leaves the score in the healthy ranges.
CRITICAL_CAP = 69
ATTENTION_CAP = 89


def health_score(devices: Iterable[tuple[Status, Importance]]) -> int | None:
    """Return the health of the monitored devices, or None when there are none.

    Args:
        devices: the status and importance of each device whose alerts are on.
    """
    total = penalty = 0.0
    statuses: set[Status] = set()
    for status, importance in devices:
        weight = WEIGHTS[importance]
        total += weight
        penalty += weight * PENALTIES.get(status, 0.0)
        statuses.add(status)
    if not total:
        return None
    # The epsilon keeps a float error from dropping a whole point.
    score = math.floor(100 * (1 - penalty / total) + 1e-9)
    if Status.CRITICAL in statuses:
        return min(score, CRITICAL_CAP)
    if statuses & {Status.LOW, Status.NOT_RESPONDING}:
        return min(score, ATTENTION_CAP)
    return score
