import json
import sqlite3
import sys
import textwrap

import pytest

from plane.agent.runtime import RuntimeDispatchError, SubprocessRuntimeTransport


SNAPSHOT = json.dumps(
    {"actorRef": "actor:test", "runId": "run:test", "workspaceRef": "workspace:test"},
    sort_keys=True,
    separators=(",", ":"),
)
ENVELOPE = json.dumps(
    {"invocationId": "invocation:test", "runId": "run:test"},
    sort_keys=True,
    separators=(",", ":"),
)


def _command(source: str, *arguments: str) -> tuple[str, ...]:
    return (sys.executable, "-c", textwrap.dedent(source), *arguments)


def test_subprocess_transport_commits_and_replays_exact_frames(tmp_path):
    counter = tmp_path / "counter"
    command = _command(
        """
        import json
        import pathlib
        import sys

        path = pathlib.Path(sys.argv[1])
        current = int(path.read_text() or "0") if path.exists() else 0
        path.write_text(str(current + 1))
        request = json.load(sys.stdin)
        print(json.dumps({"invocationId": request["invocation"]["invocationId"]}, separators=(",", ":")))
        """,
        str(counter),
    )
    transport = SubprocessRuntimeTransport(command=command, ledger_path=tmp_path / "ledger.sqlite")

    first = transport.dispatch(SNAPSHOT, ENVELOPE)
    replay = transport.dispatch(SNAPSHOT, ENVELOPE)

    assert first == replay == ('{"invocationId":"invocation:test"}',)
    assert counter.read_text() == "1"


def test_changed_replay_is_denied_without_starting_another_process(tmp_path):
    counter = tmp_path / "counter"
    command = _command(
        """
        import pathlib
        import sys

        path = pathlib.Path(sys.argv[1])
        current = int(path.read_text() or "0") if path.exists() else 0
        path.write_text(str(current + 1))
        print("{}")
        """,
        str(counter),
    )
    transport = SubprocessRuntimeTransport(command=command, ledger_path=tmp_path / "ledger.sqlite")
    transport.dispatch(SNAPSHOT, ENVELOPE)
    changed_snapshot = json.dumps(
        {"actorRef": "actor:changed", "runId": "run:test", "workspaceRef": "workspace:test"},
        sort_keys=True,
        separators=(",", ":"),
    )

    with pytest.raises(RuntimeDispatchError, match="changed runtime replay"):
        transport.dispatch(changed_snapshot, ENVELOPE)
    assert counter.read_text() == "1"


def test_timeout_marks_outcome_unknown_and_never_blindly_replays(tmp_path):
    command = _command(
        """
        import time
        time.sleep(1)
        """
    )
    transport = SubprocessRuntimeTransport(
        command=command,
        ledger_path=tmp_path / "ledger.sqlite",
        timeout_seconds=0.05,
    )

    with pytest.raises(RuntimeDispatchError, match="durable terminal result"):
        transport.dispatch(SNAPSHOT, ENVELOPE)
    with pytest.raises(RuntimeDispatchError, match="outcome is unknown"):
        transport.dispatch(SNAPSHOT, ENVELOPE)


def test_diagnostics_are_bounded_and_never_persisted(tmp_path):
    canary = "runtime-secret-canary"
    command = _command(
        """
        import sys
        sys.stderr.write(sys.argv[1])
        sys.exit(1)
        """,
        canary,
    )
    ledger = tmp_path / "ledger.sqlite"
    transport = SubprocessRuntimeTransport(
        command=command,
        ledger_path=ledger,
        max_diagnostics_bytes=32,
    )

    with pytest.raises(RuntimeDispatchError) as error:
        transport.dispatch(SNAPSHOT, ENVELOPE)
    assert canary not in str(error.value)
    assert canary not in ledger.read_bytes().decode("utf-8", errors="ignore")

    with sqlite3.connect(ledger) as connection:
        assert connection.execute(
            "SELECT state FROM plane_runtime_dispatch_ledger WHERE invocation_id = ?",
            ("invocation:test",),
        ).fetchone() == ("outcome_unknown",)
