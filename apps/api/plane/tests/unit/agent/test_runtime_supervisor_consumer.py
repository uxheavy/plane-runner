# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only

from plane.db.management.commands import agent_supervisor_consumer


def test_supervisor_consumer_dispatches_one_available_invocation(monkeypatch):
    calls = []
    command = agent_supervisor_consumer.Command()
    monkeypatch.setattr(command, "_next_invocation_ref", lambda: "invocation:test")
    monkeypatch.setattr(agent_supervisor_consumer, "call_command", lambda *args, **kwargs: calls.append((args, kwargs)))

    command.handle(once=True, poll_interval=1.0, worker_id="worker:test")

    assert calls == [
        (
            ("agent_supervisor",),
            {
                "invocation_ref": "invocation:test",
                "worker_id": "worker:test",
                "stdout": command.stdout,
                "stderr": command.stderr,
            },
        )
    ]
