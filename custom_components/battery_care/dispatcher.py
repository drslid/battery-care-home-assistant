"""Decide when notifications go out: critical batteries at once, the rest daily."""

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util

from .adapters.notify import Message, Notifier, phone_targets
from .core.engine import Alert, Problem
from .core.messages import CATALOGUE, PROBLEMS, Line, compose, language_of
from .core.schedule import in_quiet_hours, minute_of, next_at
from .core.settings import Settings
from .storage import StateData

PANEL = "/battery-care"
DIGEST_TAG = "battery_care_digest"
ALERTS_TAG = "battery_care_alerts"
TEST_TAG = "battery_care_test"
# Most urgent first in a digest.
ORDER = {problem: rank for rank, problem in enumerate(PROBLEMS)}


def device_tag(key: str) -> str:
    """Return the notification id and phone tag of one battery device."""
    return f"battery_care_{key}"


def device_url(key: str) -> str:
    """Return the panel page of one battery device."""
    return f"{PANEL}?device={key}"


class Dispatcher:
    """Send what the alert engine decided, at the right time and place."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        state: Callable[[], StateData],
        settings: Callable[[], Settings],
        describe: Callable[[str], Line | None],
        save: Callable[[], None],
    ) -> None:
        """Initialize the dispatcher; describe returns None for a battery to skip."""
        self._hass = hass
        self._state = state
        self._settings = settings
        self._describe = describe
        self._save = save
        self.notifier = Notifier(hass)
        self._cancel_digest: CALLBACK_TYPE | None = None
        self._cancel_quiet_end: CALLBACK_TYPE | None = None

    @callback
    def async_start(self) -> None:
        """Schedule the digest, and send alerts held before a restart."""
        self.async_settings_changed()

    @callback
    def async_stop(self) -> None:
        """Cancel the timers."""
        for cancel in (self._cancel_digest, self._cancel_quiet_end):
            if cancel is not None:
                cancel()
        self._cancel_digest = self._cancel_quiet_end = None

    @callback
    def async_settings_changed(self) -> None:
        """Follow new times: the digest, then alerts that quiet hours held."""
        if self._cancel_digest is not None:
            self._cancel_digest()
        settings = self._settings()
        minute = settings.digest_minute
        # A digest due in quiet hours waits for their end.
        if settings.quiet_hours and in_quiet_hours(
            minute, settings.quiet_start_minute, settings.quiet_end_minute
        ):
            minute = settings.quiet_end_minute
        self._cancel_digest = async_track_time_change(
            self._hass,
            self._async_digest_time,
            hour=minute // 60,
            minute=minute % 60,
            second=0,
        )
        self._async_release_held()

    @callback
    def async_handle(
        self, key: str, alerts: Iterable[Alert], recovered: Iterable[Problem]
    ) -> None:
        """Send or queue what one evaluation of a device decided to tell."""
        state = self._state()
        queued = list(state.digest)
        urgent = False
        for alert in alerts:
            if not alert.notify:
                continue
            if alert.urgent and not alert.reminder:
                urgent = True
            elif key not in queued:
                queued.append(key)
        for problem in recovered:
            if problem in (Problem.LOW, Problem.CRITICAL):
                self.notifier.async_dismiss(device_tag(key))
            if self._settings().notify_recovered and key not in queued:
                queued.append(key)
        if queued != state.digest:
            state.digest = queued
            self._save()
        if not urgent:
            return
        if self._quiet_now():
            if key not in state.held:
                state.held = [*state.held, key]
                self._save()
            self._async_schedule_quiet_end()
        else:
            self._async_send_alerts([key])

    @callback
    def async_summary(self, keys: Iterable[str]) -> None:
        """Tell about the batteries that need attention when the first run ends."""
        state = self._state()
        state.digest = list(dict.fromkeys([*state.digest, *keys]))
        self._save()
        if not self._quiet_now():
            self.async_send_digest()

    @callback
    def async_send_digest(self) -> None:
        """Send one message about every battery queued since the last digest."""
        state = self._state()
        keys, state.digest = state.digest, []
        if keys:
            self._save()
        problems: list[Line] = []
        recovered: list[Line] = []
        for key in keys:
            if (line := self._describe(key)) is None:
                continue
            if line.status in PROBLEMS:
                problems.append(line)
            elif self._settings().notify_recovered:
                recovered.append(line)
        problems.sort(key=lambda line: (ORDER[line.status], line.name.casefold()))
        recovered.sort(key=lambda line: line.name.casefold())
        if lines := [*problems, *recovered]:
            self._deliver(self._message(lines, DIGEST_TAG, PANEL))

    async def async_test(self) -> dict[str, Any]:
        """Send a test message to every target now, and report what failed."""
        settings = self._settings()
        language = language_of(self._hass.config.language)
        words = CATALOGUE[language]
        message = Message(words["title"], words["test"], words["test"], TEST_TAG, PANEL)
        if settings.persistent_notifications:
            self.notifier.async_send(message, persistent=True, phones=())
        names = {target.service: target.name for target in phone_targets(self._hass)}
        phones = [
            {
                "service": service,
                "name": names.get(service, service),
                "error": await self.notifier.async_push(service, message),
            }
            for service in settings.notify_targets
        ]
        return {"persistent": settings.persistent_notifications, "phones": phones}

    def _quiet_now(self) -> bool:
        settings = self._settings()
        return settings.quiet_hours and in_quiet_hours(
            minute_of(dt_util.now()),
            settings.quiet_start_minute,
            settings.quiet_end_minute,
        )

    @callback
    def _async_digest_time(self, _now: datetime) -> None:
        self.async_send_digest()

    @callback
    def _async_schedule_quiet_end(self) -> None:
        if self._cancel_quiet_end is not None:
            return
        self._cancel_quiet_end = async_track_point_in_time(
            self._hass,
            self._async_quiet_over,
            next_at(dt_util.now(), self._settings().quiet_end_minute),
        )

    @callback
    def _async_quiet_over(self, _now: datetime) -> None:
        self._cancel_quiet_end = None
        self._async_release_held()

    @callback
    def _async_release_held(self) -> None:
        """Send held alerts, unless it is still quiet."""
        state = self._state()
        if not state.held:
            return
        if self._quiet_now():
            if self._cancel_quiet_end is not None:
                self._cancel_quiet_end()
                self._cancel_quiet_end = None
            self._async_schedule_quiet_end()
            return
        keys, state.held = state.held, []
        self._save()
        self._async_send_alerts(keys)

    @callback
    def _async_send_alerts(self, keys: Sequence[str]) -> None:
        """Tell at once about batteries that are still critical."""
        critical: list[tuple[str, Line]] = []
        for key in keys:
            line = self._describe(key)
            if line is not None and line.status == "critical":
                critical.append((key, line))
        if not critical:
            return
        settings = self._settings()
        if settings.persistent_notifications:
            for key, line in critical:
                self.notifier.async_send(
                    self._message([line], device_tag(key), device_url(key)),
                    persistent=True,
                    phones=(),
                )
        if len(critical) == 1:
            key, line = critical[0]
            message = self._message([line], device_tag(key), device_url(key))
        else:
            message = self._message([line for _, line in critical], ALERTS_TAG, PANEL)
        self.notifier.async_send(
            message, persistent=False, phones=settings.notify_targets
        )

    def _deliver(self, message: Message) -> None:
        settings = self._settings()
        self.notifier.async_send(
            message,
            persistent=settings.persistent_notifications,
            phones=settings.notify_targets,
        )

    def _message(self, lines: Sequence[Line], tag: str, url: str) -> Message:
        language = language_of(self._hass.config.language)
        return Message(
            title=CATALOGUE[language]["title"],
            markdown=compose(lines, language, markdown=True),
            text=compose(lines, language, markdown=False),
            tag=tag,
            url=url,
        )
