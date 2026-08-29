# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

from celery import shared_task

from .services import fire_due_schedules


@shared_task
def fire_due_agent_schedules() -> int:
    return len(fire_due_schedules())
