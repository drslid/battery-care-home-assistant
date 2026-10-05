"""The health score and its invariants."""

from hypothesis import given, strategies as st
import pytest

from custom_components.battery_care.core.health import health_score
from custom_components.battery_care.core.models import Importance
from custom_components.battery_care.core.status import Status

NORMAL = Importance.NORMAL


def test_the_example_of_the_brief() -> None:
    """43 OK, 3 low and 1 critical: a raw 95, capped by the critical battery."""
    devices = (
        [(Status.OK, NORMAL)] * 43
        + [(Status.LOW, NORMAL)] * 3
        + [(Status.CRITICAL, NORMAL)]
    )

    assert health_score(devices) == 69


@pytest.mark.parametrize(
    ("devices", "expected"),
    [
        ([], None),
        ([(Status.OK, NORMAL), (Status.CHARGING, NORMAL)], 100),
        ([(Status.UNKNOWN, NORMAL)], 100),
        ([(Status.STALE, NORMAL)] + [(Status.OK, NORMAL)] * 99, 99),
        ([(Status.LOW, NORMAL)] + [(Status.OK, NORMAL)] * 99, 89),
        ([(Status.NOT_RESPONDING, NORMAL), (Status.OK, NORMAL)], 75),
        ([(Status.CRITICAL, Importance.CRITICAL), (Status.OK, Importance.LOW)], 14),
    ],
)
def test_scores(devices: list[tuple[Status, Importance]], expected: int | None) -> None:
    """Weights by importance, penalties by state, and the caps."""
    assert health_score(devices) == expected


devices = st.lists(st.tuples(st.sampled_from(Status), st.sampled_from(Importance)))


@given(devices, st.integers(1, 200))
def test_invariants(found: list[tuple[Status, Importance]], healthy: int) -> None:
    """Always 0 to 100; a critical battery always means action required."""
    score = health_score(found)
    assert (score is None) == (not found)
    if score is not None:
        assert 0 <= score <= 100
    with_critical = health_score([*found, (Status.CRITICAL, Importance.LOW)])
    assert with_critical is not None
    assert with_critical <= 69
    one_low = health_score([(Status.LOW, NORMAL)] + [(Status.OK, NORMAL)] * healthy)
    assert one_low is not None
    assert one_low <= 89
