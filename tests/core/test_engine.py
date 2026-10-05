"""The alert engine: transitions, delays, reminders and their invariants."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings, strategies as st
import pytest

from custom_components.battery_care.core.engine import (
    Alert,
    Evaluation,
    Observation,
    Policy,
    Problem,
    evaluate,
    level_severity,
    make_policy,
)
from custom_components.battery_care.core.models import Importance
from custom_components.battery_care.core.runtime import RANK, Runtime, Severity
from custom_components.battery_care.core.settings import DEFAULTS, Settings

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
POLICY = make_policy(DEFAULTS, Importance.NORMAL)


def seen(
    level: float | None = None,
    *,
    low: bool | None = None,
    charging: bool = False,
    available: bool = True,
    evidence_at: datetime | None = None,
) -> Observation:
    """Return an observation with only the values a test cares about."""
    return Observation(level, low, charging, available, evidence_at)


def walk(
    levels: list[float], policy: Policy = POLICY
) -> tuple[Runtime | None, Evaluation]:
    """Take the first level silently, then evaluate the others an hour apart.

    Returns:
        The state before the last step, and the last evaluation.
    """
    result = evaluate(None, seen(levels[0]), policy, NOW, silent=True)
    before: Runtime | None = None
    for hours, level in enumerate(levels[1:], start=1):
        before = result.runtime
        result = evaluate(before, seen(level), policy, NOW + timedelta(hours=hours))
    return before, result


def problems(result: Evaluation) -> list[Problem]:
    """Return what the alerts of an evaluation are about."""
    return [alert.problem for alert in result.alerts]


@pytest.mark.parametrize(
    ("levels", "severity", "alerts", "recovered"),
    [
        ([21, 20], Severity.LOW, [Problem.LOW], []),
        ([21, 20, 19], Severity.LOW, [], []),
        ([11, 10], Severity.CRITICAL, [Problem.CRITICAL], []),
        ([11, 10, 9], Severity.CRITICAL, [], []),
        ([10, 14], Severity.CRITICAL, [], []),
        ([10, 14, 15], Severity.LOW, [], []),
        ([20, 24], Severity.LOW, [], []),
        ([20, 24, 25], Severity.NORMAL, [], [Problem.LOW]),
    ],
)
def test_the_boundaries_of_the_brief(
    levels: list[float],
    severity: Severity,
    alerts: list[Problem],
    recovered: list[Problem],
) -> None:
    """With L = 20, C = 10 and H = 5, the thresholds count as reached."""
    _, result = walk(levels)

    assert result.runtime.severity is severity
    assert problems(result) == alerts
    assert list(result.recovered) == recovered


def test_the_transition_table() -> None:
    """Alerts only get worse; going back down is silent until recovery."""
    _, critical = walk([50, 5])
    assert critical.alerts == (
        Alert(Problem.CRITICAL, "normal", notify=True, urgent=True),
    )
    _, escalated = walk([50, 15, 5])
    assert escalated.alerts == (
        Alert(Problem.CRITICAL, "low", notify=True, urgent=True),
    )
    _, low = walk([50, 15])
    assert low.alerts == (Alert(Problem.LOW, "normal", notify=True),)
    _, better = walk([50, 5, 22])
    assert (better.runtime.severity, better.alerts, better.recovered) == (
        Severity.LOW,
        (),
        (),
    )
    _, recovered = walk([50, 5, 25])
    assert recovered.recovered == (Problem.CRITICAL,)


def test_without_hysteresis_the_thresholds_alone_decide() -> None:
    """A margin of zero recovers as soon as the level is above the threshold."""
    policy = make_policy(Settings(hysteresis=0), Importance.NORMAL)

    assert level_severity(Severity.CRITICAL, 11, policy) is Severity.LOW
    assert level_severity(Severity.LOW, 21, policy) is Severity.NORMAL


def test_the_low_flag_needs_the_recovery_delay_to_clear() -> None:
    """On counts at once; off counts after staying off for an hour."""
    on = evaluate(Runtime(last_low=False), seen(low=True), POLICY, NOW)
    assert problems(on) == [Problem.LOW]

    off = evaluate(on.runtime, seen(low=False), POLICY, NOW + timedelta(minutes=5))
    assert off.runtime.severity is Severity.LOW
    assert off.runtime.low_off_since == NOW + timedelta(minutes=5)
    assert off.wake_at == NOW + timedelta(minutes=65)

    still = evaluate(off.runtime, seen(low=False), POLICY, NOW + timedelta(minutes=64))
    assert still.runtime.severity is Severity.LOW
    cleared = evaluate(
        still.runtime, seen(low=False), POLICY, NOW + timedelta(minutes=65)
    )
    assert cleared.runtime.severity is Severity.NORMAL
    assert cleared.runtime.low_off_since is None
    assert cleared.recovered == (Problem.LOW,)


def test_the_low_flag_overrides_a_good_level() -> None:
    """The device's own flag is trusted, and clears only after the delay."""
    flagged = evaluate(Runtime(last_level=80), seen(80, low=True), POLICY, NOW)
    assert problems(flagged) == [Problem.LOW]

    immediate = make_policy(Settings(binary_recovery_minutes=0), Importance.NORMAL)
    cleared = evaluate(flagged.runtime, seen(80, low=False), immediate, NOW)
    assert cleared.recovered == (Problem.LOW,)


def test_an_unknown_reading_keeps_the_severity() -> None:
    """No value and no flag: nothing changes, not even the last level."""
    _, low = walk([50, 15])

    result = evaluate(low.runtime, seen(), POLICY, NOW + timedelta(days=1))

    assert result.runtime.severity is Severity.LOW
    assert result.runtime.last_level == 15
    assert (result.alerts, result.recovered) == ((), ())


def test_charging_holds_the_severity_until_it_stops() -> None:
    """No alert while charging; the battery is judged again when it stops."""
    calm = evaluate(None, seen(50), POLICY, NOW, silent=True)
    charging = evaluate(calm.runtime, seen(15, charging=True), POLICY, NOW)
    assert charging.runtime.severity is Severity.NORMAL
    assert charging.alerts == ()

    unplugged = evaluate(charging.runtime, seen(18), POLICY, NOW)
    assert problems(unplugged) == [Problem.LOW]

    plugged = evaluate(unplugged.runtime, seen(18, charging=True), POLICY, NOW)
    assert plugged.runtime.next_reminder_at is None


def test_not_responding_after_the_grace_period() -> None:
    """The clock starts when the sources become unavailable, not at a restart."""
    _, calm = walk([50])
    gone = evaluate(calm.runtime, seen(available=False), POLICY, NOW)
    assert gone.runtime.unavailable_since == NOW
    assert gone.wake_at == NOW + timedelta(hours=24)
    assert gone.alerts == ()

    later = NOW + timedelta(hours=24)
    silent = evaluate(gone.runtime, seen(available=False), POLICY, later)
    assert silent.alerts == (Alert(Problem.NOT_RESPONDING, "normal", notify=True),)
    assert silent.runtime.not_responding

    important = make_policy(DEFAULTS, Importance.IMPORTANT)
    digest = evaluate(gone.runtime, seen(available=False), important, later)
    # Only critical batteries are urgent; this goes into the daily digest.
    assert not digest.alerts[0].urgent

    muted = make_policy(Settings(unavailable_alerts=False), Importance.NORMAL)
    unannounced = evaluate(gone.runtime, seen(available=False), muted, later)
    assert unannounced.alerts == (
        Alert(Problem.NOT_RESPONDING, "normal", notify=False),
    )
    assert unannounced.runtime.next_reminder_at is None


def test_recovery_from_not_responding_needs_a_sign_of_life() -> None:
    """A state restored at a restart looks available but proves nothing."""
    silent = Runtime(
        last_level=50,
        not_responding=True,
        unavailable_since=NOW - timedelta(days=2),
        evidence_at=NOW - timedelta(days=2),
    )

    restored = evaluate(silent, seen(50), POLICY, NOW)
    assert restored.runtime.not_responding
    assert restored.recovered == ()

    reported = evaluate(silent, seen(50, evidence_at=NOW), POLICY, NOW)
    assert not reported.runtime.not_responding
    assert reported.runtime.unavailable_since is None
    assert reported.recovered == (Problem.NOT_RESPONDING,)

    changed = evaluate(silent, seen(49), POLICY, NOW)
    assert changed.recovered == (Problem.NOT_RESPONDING,)


def test_a_silent_device_becomes_stale() -> None:
    """Seven days without a sign of life; any report clears it."""
    _, calm = walk([50])
    started = calm.runtime.evidence_at
    assert started == NOW
    assert calm.wake_at == NOW + timedelta(days=7)

    week = NOW + timedelta(days=7)
    stale = evaluate(calm.runtime, seen(50), POLICY, week)
    assert stale.alerts == (Alert(Problem.STALE, "normal", notify=True),)
    assert stale.runtime.stale
    still = evaluate(stale.runtime, seen(50), POLICY, week + timedelta(days=1))
    assert still.runtime.stale
    assert still.alerts == ()

    alive = evaluate(stale.runtime, seen(50, evidence_at=week), POLICY, week)
    assert not alive.runtime.stale
    assert alive.recovered == (Problem.STALE,)


def test_staleness_waits_while_unavailable_or_off() -> None:
    """An unavailable device is not responding instead; detection can be off."""
    _, calm = walk([50])
    week = NOW + timedelta(days=7)

    unavailable = evaluate(calm.runtime, seen(available=False), POLICY, week)
    assert not unavailable.runtime.stale

    off = make_policy(Settings(stale_detection=False), Importance.NORMAL)
    stale = replace(calm.runtime, stale=True)
    assert not evaluate(stale, seen(50), off, week).runtime.stale


@pytest.mark.parametrize(
    ("importance", "reminder_hours", "interval"),
    [
        (Importance.LOW, 72, timedelta(hours=144)),
        (Importance.NORMAL, 72, timedelta(hours=72)),
        (Importance.IMPORTANT, 72, timedelta(hours=36)),
        (Importance.CRITICAL, 72, timedelta(hours=18)),
        (Importance.CRITICAL, 6, timedelta(hours=6)),
    ],
)
def test_reminders_follow_the_importance(
    importance: Importance, reminder_hours: int, interval: timedelta
) -> None:
    """The interval scales with the importance, and is never under 6 hours."""
    policy = make_policy(Settings(reminder_hours=reminder_hours), importance)
    _, low = walk([50, 15], policy)
    alerted = NOW + timedelta(hours=1)
    assert low.runtime.next_reminder_at == alerted + interval
    assert low.wake_at == alerted + interval

    early = evaluate(low.runtime, seen(15), policy, alerted + interval / 2)
    assert early.alerts == ()
    due = evaluate(early.runtime, seen(15), policy, alerted + interval)
    assert due.alerts == (Alert(Problem.LOW, "low", notify=True, reminder=True),)
    assert due.runtime.next_reminder_at == alerted + 2 * interval


def test_recovery_stops_the_reminders() -> None:
    """Nothing left to remind of: the schedule and the acknowledgement go."""
    _, low = walk([50, 15])
    acknowledged = replace(low.runtime, acknowledged_at=NOW)

    result = evaluate(acknowledged, seen(30), POLICY, NOW + timedelta(hours=2))

    assert result.runtime.next_reminder_at is None
    assert result.runtime.acknowledged_at is None


def test_got_it_stops_reminders_until_it_gets_worse() -> None:
    """An acknowledgement holds for the current severity only."""
    _, low = walk([50, 15])
    acknowledged = replace(low.runtime, acknowledged_at=NOW)
    later = NOW + timedelta(days=30)

    quiet = evaluate(acknowledged, seen(15, evidence_at=later), POLICY, later)
    assert quiet.alerts == ()
    assert quiet.wake_at == later + timedelta(days=7)

    worse = evaluate(quiet.runtime, seen(5), POLICY, later)
    assert problems(worse) == [Problem.CRITICAL]
    assert worse.runtime.acknowledged_at is None


def test_a_snooze_holds_notifications_until_it_ends() -> None:
    """Reminders wait for the end of the snooze, then come at once."""
    _, low = walk([50, 15])
    until = NOW + timedelta(days=10)
    snoozed = replace(low.runtime, snoozed_until=until)

    day5 = NOW + timedelta(days=5)
    held = evaluate(snoozed, seen(15, evidence_at=day5), POLICY, day5)
    assert held.alerts == ()
    assert held.wake_at == until

    ended = evaluate(held.runtime, seen(15), POLICY, until)
    assert ended.runtime.snoozed_until is None
    assert ended.alerts == (Alert(Problem.LOW, "low", notify=True, reminder=True),)


def test_a_snooze_holds_new_alerts_except_critical_ones() -> None:
    """A new problem is recorded silently; becoming critical ends the snooze."""
    until = NOW + timedelta(days=3)
    snoozed = Runtime(last_level=50, evidence_at=NOW, snoozed_until=until)

    low = evaluate(snoozed, seen(15), POLICY, NOW)
    assert low.alerts == (Alert(Problem.LOW, "normal", notify=False),)
    assert low.runtime.next_reminder_at == until

    critical = evaluate(low.runtime, seen(5), POLICY, NOW)
    assert critical.alerts == (
        Alert(Problem.CRITICAL, "low", notify=True, urgent=True),
    )
    assert critical.runtime.snoozed_until is None


def test_a_restart_in_the_same_state_tells_nothing() -> None:
    """The persisted state matches: no replay, and the reminder plan is kept."""
    _, low = walk([50, 15])

    restarted = evaluate(low.runtime, seen(15), POLICY, NOW + timedelta(hours=2))

    assert restarted.runtime == low.runtime
    assert (restarted.alerts, restarted.recovered) == ((), ())


def test_a_change_while_home_assistant_was_off_tells_once() -> None:
    """From Normal straight to Critical: one alert, not one per threshold."""
    _, calm = walk([50])

    result = evaluate(calm.runtime, seen(8), POLICY, NOW + timedelta(days=2))

    assert problems(result) == [Problem.CRITICAL]


def test_the_first_run_takes_states_silently() -> None:
    """Silent evaluations tell nothing but plan reminders, as after a summary."""
    result = evaluate(None, seen(5), POLICY, NOW, silent=True)

    assert result.runtime.severity is Severity.CRITICAL
    assert (result.alerts, result.recovered) == ((), ())
    assert result.runtime.next_reminder_at == NOW + timedelta(hours=24)


def test_without_alerts_the_engine_only_keeps_track() -> None:
    """Ignored devices and quiet classes: the state follows, nothing is told."""
    policy = make_policy(Settings(alerts_enabled=False), Importance.NORMAL)

    result = evaluate(None, seen(5), policy, NOW)

    assert result.runtime.severity is Severity.CRITICAL
    assert (result.alerts, result.recovered) == ((), ())
    assert result.runtime.next_reminder_at is None


def test_a_new_device_follows_the_normal_rules() -> None:
    """A device paired after the first run alerts like any other."""
    result = evaluate(None, seen(15), POLICY, NOW)

    assert problems(result) == [Problem.LOW]


policies = st.builds(
    lambda low, critical, margin, minutes, hours, grace, stale, flags, importance: (
        make_policy(
            Settings(
                low_threshold=low,
                critical_threshold=min(critical, low - 1),
                hysteresis=min(margin, 100 - low),
                binary_recovery_minutes=minutes,
                reminder_hours=hours,
                unavailable_alerts=flags[0],
                unavailable_grace_hours=grace,
                stale_detection=stale is not None,
                stale_days=stale or 7,
                alerts_enabled=flags[1],
            ),
            importance,
        )
    ),
    st.integers(1, 95),
    st.integers(0, 94),
    st.integers(0, 20),
    st.integers(0, 120),
    st.integers(6, 720),
    st.integers(1, 168),
    st.none() | st.integers(1, 90),
    st.tuples(st.booleans(), st.booleans()),
    st.sampled_from(Importance),
)
steps = st.lists(
    st.tuples(
        st.integers(0, 7 * 24 * 3600),
        st.none() | st.integers(0, 100),
        st.none() | st.booleans(),
        st.booleans(),
        st.booleans(),
        st.none() | st.integers(0, 30 * 24 * 3600),
        st.sampled_from(["", "snooze", "got it"]),
    ),
    min_size=1,
    max_size=25,
)


@settings(max_examples=300, deadline=None)
@given(policies, steps)
def test_invariants(policy: Policy, sequence: list[tuple]) -> None:  # type: ignore[type-arg]
    """For any history: no alert without a cause, and a second look changes nothing."""
    runtime: Runtime | None = None
    now = NOW
    for delay, level, low, charging, available, report_age, action in sequence:
        now += timedelta(seconds=delay)
        if runtime is not None and action == "snooze":
            runtime = replace(runtime, snoozed_until=now + timedelta(days=1))
        elif runtime is not None and action == "got it":
            runtime = replace(runtime, acknowledged_at=now)
        observation = seen(
            level,
            low=low,
            charging=charging,
            available=available,
            evidence_at=None
            if report_age is None
            else now - timedelta(seconds=report_age),
        )
        before = runtime or Runtime()
        result = evaluate(runtime, observation, policy, now)
        after = result.runtime

        assert result.wake_at is None or result.wake_at > now
        for alert in result.alerts:
            if alert.reminder:
                assert before.next_reminder_at is not None
                assert now >= before.next_reminder_at
            elif alert.problem is Problem.NOT_RESPONDING:
                assert after.not_responding
                assert not before.not_responding
            elif alert.problem is Problem.STALE:
                assert after.stale
                assert not before.stale
            else:
                assert after.severity.value == alert.problem.value
                assert RANK[after.severity] > RANK[before.severity]
        assert len(problems(result)) == len(set(problems(result)))
        if not policy.alerts:
            assert (result.alerts, result.recovered) == ((), ())
        if level is not None and not charging:
            if level <= policy.critical_threshold:
                assert after.severity is Severity.CRITICAL
            flag_off = not after.last_low and after.low_off_since is None
            recovery = max(
                policy.low_threshold + policy.hysteresis, policy.low_threshold + 1
            )
            if level >= recovery and flag_off:
                assert after.severity is Severity.NORMAL

        again = evaluate(after, observation, policy, now)
        assert again.runtime == after
        assert (again.alerts, again.recovered) == ((), ())
        runtime = after
