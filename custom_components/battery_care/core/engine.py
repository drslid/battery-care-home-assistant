"""The alert engine: what changed for a battery device, and what to tell about it.

evaluate() is a pure function of the previous runtime state, the current
observation, the device's policy and the time, so that every rule is tested
without Home Assistant.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum

from .models import Importance
from .runtime import RANK, Runtime, Severity
from .settings import Settings

MIN_REMINDER = timedelta(hours=6)
# The less a dead battery matters, the less often Battery Care reminds.
REMINDER_FACTORS = {
    Importance.LOW: 2.0,
    Importance.NORMAL: 1.0,
    Importance.IMPORTANT: 0.5,
    Importance.CRITICAL: 0.25,
}
IMPORTANT = frozenset({Importance.IMPORTANT, Importance.CRITICAL})


class Problem(StrEnum):
    """What an alert is about."""

    LOW = "low"
    CRITICAL = "critical"
    NOT_RESPONDING = "not_responding"
    STALE = "stale"


REMINDED = frozenset({Problem.LOW, Problem.CRITICAL, Problem.NOT_RESPONDING})


@dataclass(frozen=True, slots=True)
class Observation:
    """What a battery device reports now."""

    level: float | None
    low: bool | None
    charging: bool
    available: bool
    # The latest report that proves the device is alive, if any.
    evidence_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Policy:
    """The rules for one device, from its effective settings and importance."""

    alerts: bool
    low_threshold: int
    critical_threshold: int
    hysteresis: int
    low_recovery: timedelta
    reminder: timedelta
    unavailable_alerts: bool
    unavailable_grace: timedelta
    stale_after: timedelta | None
    importance: Importance


def make_policy(settings: Settings, importance: Importance) -> Policy:
    """Return the rules that the effective settings set for a device."""
    reminder = timedelta(hours=settings.reminder_hours * REMINDER_FACTORS[importance])
    return Policy(
        alerts=settings.alerts_enabled,
        low_threshold=settings.low_threshold,
        critical_threshold=settings.critical_threshold,
        hysteresis=settings.hysteresis,
        low_recovery=timedelta(minutes=settings.binary_recovery_minutes),
        reminder=max(reminder, MIN_REMINDER),
        unavailable_alerts=settings.unavailable_alerts,
        unavailable_grace=timedelta(hours=settings.unavailable_grace_hours),
        stale_after=timedelta(days=settings.stale_days)
        if settings.stale_detection
        else None,
        importance=importance,
    )


@dataclass(frozen=True, slots=True)
class Alert:
    """A new or worse problem, or a reminder of one."""

    problem: Problem
    # The battery severity before, or the problem itself for a reminder.
    previous: str
    notify: bool
    urgent: bool = False
    reminder: bool = False


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The new runtime state, what to tell, and when to evaluate again."""

    runtime: Runtime
    alerts: tuple[Alert, ...] = ()
    recovered: tuple[Problem, ...] = ()
    wake_at: datetime | None = None


def level_severity(previous: Severity, level: float, policy: Policy) -> Severity:
    """Return the severity of a level; leaving Low or Critical needs the hysteresis."""
    low, critical = policy.low_threshold, policy.critical_threshold
    margin = policy.hysteresis
    if level <= critical or (
        previous is Severity.CRITICAL and level < critical + margin
    ):
        return Severity.CRITICAL
    if level <= low or (previous is not Severity.NORMAL and level < low + margin):
        return Severity.LOW
    return Severity.NORMAL


def evaluate(
    previous: Runtime | None,
    observation: Observation,
    policy: Policy,
    now: datetime,
    *,
    silent: bool = False,
) -> Evaluation:
    """Evaluate one battery device.

    Args:
        previous: the state after the last evaluation, or None for a new device.
        observation: what the device reports now.
        policy: the rules for this device.
        now: the current time.
        silent: update the state without telling anything, as on the first run.
    """
    before = previous or Runtime()
    outcome = _Outcome()
    runtime = _observe(before, observation, policy, now, outcome)
    runtime = _rate_battery(before, runtime, observation, policy, outcome)
    runtime = _check_presence(runtime, observation, policy, now, outcome)
    runtime = _check_staleness(runtime, observation, policy, now, outcome)
    runtime = _plan_reminders(runtime, observation, policy, now, outcome)
    wake_at = min(outcome.wakes, default=None)
    if silent or not policy.alerts:
        return Evaluation(runtime, wake_at=wake_at)
    return Evaluation(runtime, tuple(outcome.alerts), tuple(outcome.recovered), wake_at)


@dataclass(slots=True)
class _Outcome:
    """What an evaluation decides, collected step by step."""

    alerts: list[Alert] = field(default_factory=list)
    recovered: list[Problem] = field(default_factory=list)
    wakes: list[datetime] = field(default_factory=list)


def _observe(
    before: Runtime,
    observation: Observation,
    policy: Policy,
    now: datetime,
    outcome: _Outcome,
) -> Runtime:
    """Record the reading, the low flag with its recovery delay, and signs of life."""
    level = observation.level
    level_changed = level is not None and level != before.last_level
    signs = [
        before.evidence_at,
        observation.evidence_at,
        now if level_changed else None,
    ]
    last_low, low_off_since = _low_flag(before, observation.low, now)
    # The low flag still counts until it has stayed off for the recovery delay.
    if low_off_since is not None:
        if now < low_off_since + policy.low_recovery:
            outcome.wakes.append(low_off_since + policy.low_recovery)
        else:
            low_off_since = None
    return replace(
        before,
        last_level=level if level is not None else before.last_level,
        last_low=last_low,
        low_off_since=low_off_since,
        # Without any sign of life, the clock for staleness starts now.
        evidence_at=max((sign for sign in signs if sign is not None), default=now),
    )


def _low_flag(
    before: Runtime, low: bool | None, now: datetime
) -> tuple[bool | None, datetime | None]:
    """Return the last known low flag, and since when it has been off."""
    if low is None:
        return before.last_low, before.low_off_since
    if low:
        return True, None
    return False, before.low_off_since or (now if before.last_low else None)


def _rate_battery(
    before: Runtime,
    runtime: Runtime,
    observation: Observation,
    policy: Policy,
    outcome: _Outcome,
) -> Runtime:
    """Update the severity from the level, or the last known one, and the low flag."""
    # An unknown reading keeps the severity; charging holds it until it stops.
    if observation.charging or (observation.level is None and observation.low is None):
        return runtime
    level = runtime.last_level
    severity = (
        Severity.NORMAL
        if level is None
        else level_severity(before.severity, level, policy)
    )
    if severity is Severity.NORMAL and (
        runtime.last_low or runtime.low_off_since is not None
    ):
        severity = Severity.LOW
    if RANK[severity] > RANK[before.severity]:
        outcome.alerts.append(
            Alert(
                Problem(severity.value),
                before.severity.value,
                notify=True,
                urgent=severity is Severity.CRITICAL,
            )
        )
    elif severity is Severity.NORMAL and before.severity is not Severity.NORMAL:
        outcome.recovered.append(Problem(before.severity.value))
    return replace(runtime, severity=severity)


def _check_presence(
    runtime: Runtime,
    observation: Observation,
    policy: Policy,
    now: datetime,
    outcome: _Outcome,
) -> Runtime:
    """Flag a device whose sources stay unavailable for the grace period."""
    since = runtime.unavailable_since
    if observation.available:
        if not runtime.not_responding:
            return replace(runtime, unavailable_since=None)
        # Restored states look available after a restart: recovery needs a sign of life.
        evidence = runtime.evidence_at
        if since is not None and evidence is not None and evidence <= since:
            return runtime
        outcome.recovered.append(Problem.NOT_RESPONDING)
        return replace(runtime, not_responding=False, unavailable_since=None)
    since = since or now
    if runtime.not_responding:
        return replace(runtime, unavailable_since=since)
    if now < since + policy.unavailable_grace:
        outcome.wakes.append(since + policy.unavailable_grace)
        return replace(runtime, unavailable_since=since)
    outcome.alerts.append(
        Alert(
            Problem.NOT_RESPONDING,
            runtime.severity.value,
            notify=policy.unavailable_alerts,
            urgent=policy.importance in IMPORTANT,
        )
    )
    return replace(runtime, unavailable_since=since, not_responding=True)


def _check_staleness(
    runtime: Runtime,
    observation: Observation,
    policy: Policy,
    now: datetime,
    outcome: _Outcome,
) -> Runtime:
    """Flag a device that looks available but has not reported for too long."""
    if policy.stale_after is None:
        return replace(runtime, stale=False)
    # A device that is unavailable is a matter for the grace period instead.
    if not observation.available or runtime.evidence_at is None:
        return runtime
    due = runtime.evidence_at + policy.stale_after
    if now < due:
        outcome.wakes.append(due)
        if runtime.stale:
            outcome.recovered.append(Problem.STALE)
        return replace(runtime, stale=False)
    if not runtime.stale:
        outcome.alerts.append(
            Alert(
                Problem.STALE,
                runtime.severity.value,
                notify=policy.importance in IMPORTANT,
            )
        )
    return replace(runtime, stale=True)


def _snooze(runtime: Runtime, now: datetime, outcome: _Outcome) -> datetime | None:
    """Return when the snooze ends, holding notifications until then."""
    snoozed_until = runtime.snoozed_until
    # Becoming critical ends a snooze.
    if (
        snoozed_until is None
        or now >= snoozed_until
        or any(alert.problem is Problem.CRITICAL for alert in outcome.alerts)
    ):
        return None
    outcome.alerts[:] = [replace(alert, notify=False) for alert in outcome.alerts]
    outcome.wakes.append(snoozed_until)
    return snoozed_until


def _plan_reminders(
    runtime: Runtime,
    observation: Observation,
    policy: Policy,
    now: datetime,
    outcome: _Outcome,
) -> Runtime:
    """Apply the snooze and acknowledgement, and remind of problems when due."""
    snoozed_until = _snooze(runtime, now, outcome)
    acknowledged_at = runtime.acknowledged_at
    if any(alert.problem in REMINDED for alert in outcome.alerts):
        acknowledged_at = None
    next_reminder_at = runtime.next_reminder_at
    active = _reminded_problem(runtime, observation, policy)
    if active is None or not policy.alerts:
        next_reminder_at = None
        if active is None:
            acknowledged_at = None
    elif any(alert.notify and alert.problem in REMINDED for alert in outcome.alerts):
        next_reminder_at = now + policy.reminder
    elif next_reminder_at is None:
        next_reminder_at = snoozed_until or now + policy.reminder
    elif snoozed_until is None and acknowledged_at is None and now >= next_reminder_at:
        outcome.alerts.append(Alert(active, active.value, notify=True, reminder=True))
        next_reminder_at = now + policy.reminder
    if next_reminder_at and not (acknowledged_at or snoozed_until):
        outcome.wakes.append(next_reminder_at)
    return replace(
        runtime,
        snoozed_until=snoozed_until,
        acknowledged_at=acknowledged_at,
        next_reminder_at=next_reminder_at,
    )


def _reminded_problem(
    runtime: Runtime, observation: Observation, policy: Policy
) -> Problem | None:
    """Return the problem that reminders are about, if any."""
    battery_shown = not observation.charging
    if runtime.severity is Severity.CRITICAL and battery_shown:
        return Problem.CRITICAL
    if runtime.not_responding and policy.unavailable_alerts:
        return Problem.NOT_RESPONDING
    if runtime.severity is Severity.LOW and battery_shown:
        return Problem.LOW
    return None
