# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane-owned schedule control state and normal-assignment firing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from plane.agent.lifecycle import AgentDomainError, create_assignment
from plane.db.models import (
    AgentActor,
    AgentSchedule,
    AgentScheduleFire,
    AgentScheduleFireState,
    AgentScheduleState,
)


class AgentScheduleError(ValidationError):
    """Base error for schedule definitions and trigger control."""


_SCHEDULE_STATE_TRANSITIONS = {
    AgentScheduleState.ENABLED: {
        AgentScheduleState.ENABLED,
        AgentScheduleState.PAUSED,
        AgentScheduleState.DISABLED,
    },
    AgentScheduleState.PAUSED: {
        AgentScheduleState.ENABLED,
        AgentScheduleState.PAUSED,
        AgentScheduleState.DISABLED,
    },
    AgentScheduleState.DISABLED: {AgentScheduleState.DISABLED},
}


def _schedule_state(value: str) -> AgentScheduleState:
    try:
        return AgentScheduleState(value)
    except (TypeError, ValueError) as exc:
        raise AgentScheduleError(f"Unknown schedule state: {value}") from exc


def _non_empty(value: str, field: str, limit: int = 65_536) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > limit:
        raise AgentScheduleError(f"{field} must be a non-empty string within {limit} UTF-8 bytes")
    return value


def _get_zone(name: str) -> ZoneInfo:
    name = _non_empty(name, "timezone_name", 64)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise AgentScheduleError(f"Unknown schedule timezone: {name}") from exc


@dataclass(frozen=True)
class _CronFields:
    minutes: set[int]
    hours: set[int]
    days: set[int]
    months: set[int]
    weekdays: set[int]
    days_unrestricted: bool
    weekdays_unrestricted: bool


def _field_values(field: str, lower: int, upper: int) -> tuple[set[int], bool]:
    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if not token:
            raise AgentScheduleError("Cron fields cannot contain empty values")
        base, separator, raw_step = token.partition("/")
        if separator:
            try:
                step = int(raw_step)
            except ValueError as exc:
                raise AgentScheduleError("Cron step must be an integer") from exc
            if step < 1:
                raise AgentScheduleError("Cron step must be positive")
        else:
            step = 1
        if base == "*":
            start, end = lower, upper
        elif "-" in base:
            parts = base.split("-")
            if len(parts) != 2:
                raise AgentScheduleError("Cron ranges must have one hyphen")
            try:
                start, end = (int(part) for part in parts)
            except ValueError as exc:
                raise AgentScheduleError("Cron range values must be integers") from exc
        else:
            try:
                start = end = int(base)
            except ValueError as exc:
                raise AgentScheduleError("Cron values must be integers, ranges, or steps") from exc
            if separator:
                end = upper
        if start < lower or end > upper or start > end:
            raise AgentScheduleError("Cron range is outside its field")
        values.update(range(start, end + 1, step))
    return values, values == set(range(lower, upper + 1))


def _weekday_values(field: str) -> tuple[set[int], bool]:
    values, unrestricted = _field_values(field, 0, 7)
    normalized = {0 if value == 7 else value for value in values}
    return normalized, unrestricted or normalized == set(range(7))


def _cron_fields(expression: str) -> _CronFields:
    fields = _non_empty(expression, "cron_expression", 255).split()
    if len(fields) != 5:
        raise AgentScheduleError("Cron expressions must contain five fields")
    minutes, _ = _field_values(fields[0], 0, 59)
    hours, _ = _field_values(fields[1], 0, 23)
    days, days_unrestricted = _field_values(fields[2], 1, 31)
    months, _ = _field_values(fields[3], 1, 12)
    weekdays, weekdays_unrestricted = _weekday_values(fields[4])
    return _CronFields(
        minutes=minutes,
        hours=hours,
        days=days,
        months=months,
        weekdays=weekdays,
        days_unrestricted=days_unrestricted,
        weekdays_unrestricted=weekdays_unrestricted,
    )


def parse_cron_expression(expression: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """Parse standard five-field cron values (Sunday is both 0 and 7)."""

    parsed = _cron_fields(expression)
    return (
        parsed.minutes,
        parsed.hours,
        parsed.days,
        parsed.months,
        parsed.weekdays,
    )


def _cron_day_matches(parsed: _CronFields, local: datetime) -> bool:
    day_of_month_matches = local.day in parsed.days
    cron_weekday = (local.weekday() + 1) % 7
    day_of_week_matches = cron_weekday in parsed.weekdays
    if parsed.days_unrestricted and parsed.weekdays_unrestricted:
        return True
    if parsed.days_unrestricted:
        return day_of_week_matches
    if parsed.weekdays_unrestricted:
        return day_of_month_matches
    return day_of_month_matches or day_of_week_matches


def _resolve_local_minute(local_naive: datetime, zone: ZoneInfo) -> datetime | None:
    """Return the first valid UTC occurrence for a local minute.

    Nonexistent spring-forward minutes return ``None``.  Ambiguous fall-back
    minutes deterministically choose the earlier UTC occurrence (fold 0); a
    schedule therefore fires once for that local wall-clock minute.
    """

    candidates: set[datetime] = set()
    for fold in (0, 1):
        candidate = local_naive.replace(tzinfo=zone, fold=fold)
        utc_candidate = candidate.astimezone(dt_timezone.utc)
        round_trip = utc_candidate.astimezone(zone)
        if round_trip.replace(tzinfo=None) == local_naive:
            candidates.add(utc_candidate)
    return min(candidates) if candidates else None


def next_schedule_fire(expression: str, timezone_name: str, after: datetime) -> datetime:
    """Return the next standard-cron minute as an aware UTC datetime.

    The search is chronological in UTC, while matching uses local calendar
    fields.  This explicitly skips nonexistent local minutes and chooses the
    first UTC occurrence of an ambiguous fall-back minute.
    """

    parsed = _cron_fields(expression)
    zone = _get_zone(timezone_name)
    if after.tzinfo is None or after.utcoffset() is None:
        raise AgentScheduleError("Schedule calculations require an aware datetime")
    candidate = after.astimezone(dt_timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 370):
        local = candidate.astimezone(zone)
        if (
            local.minute in parsed.minutes
            and local.hour in parsed.hours
            and local.month in parsed.months
            and _cron_day_matches(parsed, local)
        ):
            local_naive = local.replace(tzinfo=None)
            if _resolve_local_minute(local_naive, zone) == candidate:
                return candidate
        candidate += timedelta(minutes=1)
    raise AgentScheduleError("Cron expression has no fire within the supported horizon")


def _retry_policy(value: dict | None) -> dict[str, int]:
    value = value or {}
    if not isinstance(value, dict):
        raise AgentScheduleError("retry_policy must be an object")
    max_attempts = value.get("maxAttempts", value.get("max_attempts", 3))
    backoff = value.get("backoffSeconds", value.get("backoff_seconds", 60))
    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or max_attempts < 1
        or max_attempts > 10
        or not isinstance(backoff, int)
        or isinstance(backoff, bool)
        or backoff < 0
        or backoff > 86_400
    ):
        raise AgentScheduleError("retry_policy must contain bounded maxAttempts and backoffSeconds")
    return {"maxAttempts": max_attempts, "backoffSeconds": backoff}


@transaction.atomic
def create_schedule(
    actor: AgentActor,
    *,
    name: str,
    cron_expression: str,
    timezone_name: str = "UTC",
    target_ref: str,
    objective: str,
    acceptance_criteria: list | None = None,
    context_refs: list | None = None,
    retry_policy: dict | None = None,
    starts_at: datetime | None = None,
) -> AgentSchedule:
    """Create Plane schedule control state; it creates no assignment yet."""

    actor = AgentActor.objects.get(pk=actor.pk)
    if not actor.is_active:
        raise AgentScheduleError("Inactive Agent actors cannot own enabled schedules")
    starts_at = starts_at or timezone.now()
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise AgentScheduleError("starts_at must be an aware datetime")
    next_fire_at = next_schedule_fire(cron_expression, timezone_name, starts_at)
    acceptance_criteria = acceptance_criteria or [objective]
    return AgentSchedule.objects.create(
        workspace=actor.workspace,
        project=actor.project,
        actor=actor,
        name=_non_empty(name, "name", 255),
        cron_expression=_non_empty(cron_expression, "cron_expression", 255),
        timezone_name=timezone_name,
        target_ref=_non_empty(target_ref, "target_ref", 255),
        objective=_non_empty(objective, "objective"),
        acceptance_criteria=acceptance_criteria or [],
        context_refs=context_refs or [],
        retry_policy=_retry_policy(retry_policy),
        next_fire_at=next_fire_at,
    )


@transaction.atomic
def transition_schedule(schedule: AgentSchedule, target: str) -> AgentSchedule:
    """Apply one legal, idempotent Plane-owned schedule control transition.

    Pausing preserves the next due slot for a later resume.  Cancellation is
    represented by the terminal ``disabled`` state and clears future trigger
    eligibility.  Existing fires and their assignments are never rewritten by
    schedule control.
    """

    target = _schedule_state(target)
    locked_schedule = AgentSchedule.objects.select_for_update().get(pk=schedule.pk)
    if target not in _SCHEDULE_STATE_TRANSITIONS[locked_schedule.state]:
        raise AgentScheduleError(
            f"Schedule state {locked_schedule.state} cannot move to {target}; disabled is terminal"
        )
    if locked_schedule.state == target:
        return locked_schedule
    locked_schedule.state = target
    update_fields = ["state", "updated_at"]
    if target == AgentScheduleState.DISABLED:
        locked_schedule.next_fire_at = None
        update_fields.append("next_fire_at")
    locked_schedule.save(update_fields=update_fields)
    return locked_schedule


def _fire_key(schedule: AgentSchedule, scheduled_for: datetime, idempotency_key: str | None) -> str:
    if idempotency_key is not None:
        return _non_empty(idempotency_key, "schedule fire idempotency_key", 128)
    return f"schedule-fire:{schedule.id}:{int(scheduled_for.timestamp())}"


def _record_failure(
    fire: AgentScheduleFire,
    *,
    now: datetime,
    error: Exception,
    retry_policy: dict,
) -> AgentScheduleFire:
    fire.error = str(error)[:8_000]
    if fire.attempt >= retry_policy["maxAttempts"]:
        fire.state = AgentScheduleFireState.EXHAUSTED
        fire.next_retry_at = None
    else:
        fire.state = AgentScheduleFireState.FAILED
        fire.next_retry_at = now + timedelta(seconds=retry_policy["backoffSeconds"])
    fire.save(update_fields=["state", "error", "next_retry_at", "updated_at"])
    return fire


@transaction.atomic
def fire_schedule(
    schedule: AgentSchedule,
    *,
    scheduled_for: datetime,
    now: datetime | None = None,
    idempotency_key: str | None = None,
    created_by=None,
) -> AgentScheduleFire:
    """Fire or replay one schedule slot into exactly one normal assignment."""

    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise AgentScheduleError("scheduled_for must be an aware datetime")
    now = now or timezone.now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise AgentScheduleError("now must be an aware datetime")
    locked_schedule = AgentSchedule.objects.select_for_update().get(pk=schedule.pk)
    key = _fire_key(locked_schedule, scheduled_for, idempotency_key)
    existing_key = AgentScheduleFire.all_objects.filter(idempotency_key=key).first()
    if existing_key and (existing_key.schedule_id != locked_schedule.id or existing_key.scheduled_for != scheduled_for):
        raise AgentScheduleError("Schedule fire idempotency key is bound to another slot")
    fire = (
        AgentScheduleFire.objects.select_for_update()
        .filter(schedule=locked_schedule, scheduled_for=scheduled_for)
        .first()
    )
    if locked_schedule.state != AgentScheduleState.ENABLED:
        if fire is not None:
            return fire
        raise AgentScheduleError(f"Schedule is {locked_schedule.state}; no new fire may be created")
    if fire is None:
        fire = AgentScheduleFire.objects.create(
            workspace=locked_schedule.workspace,
            project=locked_schedule.project,
            schedule=locked_schedule,
            scheduled_for=scheduled_for,
            idempotency_key=key,
            created_by=created_by,
        )
    elif fire.idempotency_key != key:
        raise AgentScheduleError("Schedule slot is bound to another idempotency key")
    if fire.state == AgentScheduleFireState.CREATED:
        return fire
    if fire.state == AgentScheduleFireState.EXHAUSTED:
        return fire
    if fire.state == AgentScheduleFireState.FAILED:
        if fire.next_retry_at and now < fire.next_retry_at:
            return fire
        fire.attempt += 1
        fire.state = AgentScheduleFireState.PENDING
        fire.error = ""
        fire.save(update_fields=["attempt", "state", "error", "updated_at"])
    retry_policy = _retry_policy(locked_schedule.retry_policy)
    try:
        with transaction.atomic():
            assignment = create_assignment(
                locked_schedule.actor,
                project=locked_schedule.project,
                target_ref=locked_schedule.target_ref,
                objective=locked_schedule.objective,
                acceptance_criteria=locked_schedule.acceptance_criteria,
                context_refs=locked_schedule.context_refs,
                created_by=created_by,
            )
    except (AgentDomainError, ValidationError) as exc:
        return _record_failure(fire, now=now, error=exc, retry_policy=retry_policy)
    fire.assignment = assignment
    fire.state = AgentScheduleFireState.CREATED
    fire.fired_at = now
    fire.next_retry_at = None
    fire.error = ""
    fire.save(update_fields=["assignment", "state", "fired_at", "next_retry_at", "error", "updated_at"])
    locked_schedule.last_fired_at = now
    locked_schedule.next_fire_at = next_schedule_fire(
        locked_schedule.cron_expression,
        locked_schedule.timezone_name,
        scheduled_for,
    )
    locked_schedule.save(update_fields=["last_fired_at", "next_fire_at", "updated_at"])
    return fire


def retry_schedule_fire(fire: AgentScheduleFire, *, now: datetime | None = None, created_by=None) -> AgentScheduleFire:
    return fire_schedule(
        fire.schedule,
        scheduled_for=fire.scheduled_for,
        now=now,
        idempotency_key=fire.idempotency_key,
        created_by=created_by,
    )


def fire_due_schedules(*, workspace=None, now: datetime | None = None, created_by=None) -> list[AgentScheduleFire]:
    now = now or timezone.now()
    schedules = AgentSchedule.objects.filter(state=AgentScheduleState.ENABLED, next_fire_at__lte=now)
    if workspace is not None:
        schedules = schedules.filter(workspace=workspace)
    schedules = schedules.order_by("next_fire_at", "id")
    return [
        fire_schedule(schedule, scheduled_for=schedule.next_fire_at, now=now, created_by=created_by)
        for schedule in schedules
    ]
