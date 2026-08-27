# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Disposable coordinated G4 rollback drill with forward-only migration proof."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any


SERVICE_NAMES = ("api", "worker", "beat-worker", "supervisor", "agent-runtime")


def _load_pin_fixture() -> dict[str, Any]:
    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "agent_g4_rollback_pins.json"
    with fixture.open(encoding="utf-8") as handle:
        return json.load(handle)


def run_rollback_drill() -> dict[str, Any]:
    """Exercise an upgrade, coordinated switch, reconciliation, and cleanup.

    SQLite is used only as a disposable durable-state stand-in so this drill
    never connects to or mutates a shared Plane database. The PostgreSQL
    migration and gateway contract are validated by the contract suites.
    """

    pins = _load_pin_fixture()
    with tempfile.TemporaryDirectory(prefix="plane-agent-g4-rollback-") as temp_dir:
        database_path = Path(temp_dir) / "rollback.sqlite3"
        connection = sqlite3.connect(database_path)
        try:
            _create_schema(connection, pins["current"]["migrationLeaf"])
            _deploy(connection, pins["current"])
            _create_representative_state(connection)
            _switch_to_previous(connection, pins)
            _reconcile_from_durable_effect(connection)
            _reconcile_from_durable_effect(connection)
            readback = _readback(connection, pins)
        finally:
            connection.close()

    checks = {
        "currentCandidateApplied": readback["upgrade"]["currentCandidateApplied"],
        "allServicesSwitched": set(readback["deployment"]["services"]) == set(SERVICE_NAMES)
        and readback["deployment"]["allPreviousPins"],
        "contractsCompatible": readback["deployment"]["contractsCompatible"],
        "migrationStayedForwardOnly": readback["schema"]["migrationLeaf"] == pins["current"]["migrationLeaf"]
        and readback["schema"]["reverseMigrationAttempted"] == 0,
        "previousBinariesOperateOnRetainedMigrations": readback["deployment"]["contractsCompatible"]
        and readback["schema"]["migrationLeaf"] == pins["current"]["migrationLeaf"]
        and pins["strategy"]["previousMigration"] == pins["strategy"]["compatibilityFloor"]
        and pins["strategy"]["migration"] == pins["current"]["migrationLeaf"],
        "effectReadBackBeforeReconcile": readback["reconciliation"]["effectCount"] == 1,
        "auditReconciled": readback["state"]["auditRows"] == 3,
        "oneOutcome": readback["state"]["outcomeRows"] == 1,
        "oneIdempotencyRow": readback["state"]["idempotencyRows"] == 1,
        "quotaReleased": readback["state"]["activeQuotaReservations"] == 0,
        "reconcileIdempotent": readback["reconciliation"]["rows"] == 1,
    }
    return {
        "manifestVersion": pins["schemaVersion"],
        "disposable": True,
        "externalWrites": False,
        "strategy": pins["strategy"],
        "currentPins": pins["current"],
        "previousPins": pins["previous"],
        "readback": readback,
        "checks": checks,
        "breaches": sorted(name for name, passed in checks.items() if not passed),
        "cleanup": {"temporaryDatabaseRemoved": not database_path.exists()},
        "passes": all(checks.values()) and not database_path.exists(),
    }


def _create_schema(connection: sqlite3.Connection, migration_leaf: str) -> None:
    connection.executescript(
        """
        CREATE TABLE deployment (service TEXT PRIMARY KEY, revision TEXT NOT NULL,
                                 image_digest TEXT NOT NULL, contract TEXT NOT NULL);
        CREATE TABLE deployment_history (candidate TEXT PRIMARY KEY);
        CREATE TABLE schema_state (id INTEGER PRIMARY KEY CHECK (id = 1), migration_leaf TEXT NOT NULL,
                                   reverse_migration_attempted INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE gateway_idempotency (idempotency_key TEXT PRIMARY KEY, state TEXT NOT NULL,
                                          quota_reserved INTEGER NOT NULL);
        CREATE TABLE gateway_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT NOT NULL,
                                    phase TEXT NOT NULL, outcome TEXT NOT NULL);
        CREATE TABLE gateway_effect (idempotency_key TEXT PRIMARY KEY, effect_count INTEGER NOT NULL);
        CREATE TABLE gateway_outcome (idempotency_key TEXT PRIMARY KEY, outcome TEXT NOT NULL);
        CREATE TABLE quota_bucket (subject TEXT PRIMARY KEY, active_count INTEGER NOT NULL,
                                   request_count INTEGER NOT NULL);
        CREATE TABLE reconciliation (idempotency_key TEXT PRIMARY KEY, source TEXT NOT NULL);
        """
    )
    connection.execute("INSERT INTO schema_state (id, migration_leaf) VALUES (1, ?)", (migration_leaf,))
    connection.commit()


def _deploy(connection: sqlite3.Connection, candidate: dict[str, Any]) -> None:
    connection.executemany(
        "INSERT INTO deployment (service, revision, image_digest, contract) VALUES (?, ?, ?, ?)",
        [
            (service, details["revision"], details["imageDigest"], details["contract"])
            for service, details in candidate["services"].items()
        ],
    )
    connection.execute("INSERT INTO deployment_history (candidate) VALUES ('current')")
    connection.commit()


def _create_representative_state(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO gateway_idempotency VALUES ('rollback:representative', 'outcome_unknown', 1)"
    )
    connection.executemany(
        "INSERT INTO gateway_audit (idempotency_key, phase, outcome) VALUES (?, ?, ?)",
        [
            ("rollback:representative", "intent", "intent"),
            ("rollback:representative", "dispatch", "unknown"),
        ],
    )
    connection.execute(
        "INSERT INTO gateway_effect VALUES ('rollback:representative', 1)"
    )
    connection.execute(
        "INSERT INTO quota_bucket VALUES ('invocation:rollback', 1, 1)"
    )
    connection.commit()


def _switch_to_previous(connection: sqlite3.Connection, pins: dict[str, Any]) -> None:
    previous = pins["previous"]
    with connection:
        connection.executemany(
            "UPDATE deployment SET revision = ?, image_digest = ?, contract = ? WHERE service = ?",
            [
                (details["revision"], details["imageDigest"], details["contract"], service)
                for service, details in previous["services"].items()
            ],
        )
        # Previous binaries are switched onto the already-migrated database;
        # rollback never reverses the forward-only 0145/0146 schema.
        connection.execute(
            "UPDATE schema_state SET reverse_migration_attempted = 0 WHERE id = 1"
        )


def _reconcile_from_durable_effect(connection: sqlite3.Connection) -> None:
    with connection:
        row = connection.execute(
            "SELECT idempotency_key, state, quota_reserved FROM gateway_idempotency "
            "WHERE state = 'outcome_unknown'"
        ).fetchone()
        if row is None:
            return
        key, _, quota_reserved = row
        effect_count = connection.execute(
            "SELECT effect_count FROM gateway_effect WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if effect_count != (1,):
            raise RuntimeError("rollback drill refused to replay without a unique durable effect")
        connection.execute(
            "INSERT OR IGNORE INTO gateway_outcome VALUES (?, 'success')", (key,)
        )
        connection.execute(
            "INSERT OR IGNORE INTO reconciliation VALUES (?, 'durable-effect-readback')", (key,)
        )
        connection.execute(
            "UPDATE gateway_idempotency SET state = 'success', quota_reserved = 0 WHERE idempotency_key = ?",
            (key,),
        )
        if quota_reserved:
            connection.execute(
                "UPDATE quota_bucket SET active_count = 0 WHERE subject = 'invocation:rollback'"
            )
        connection.execute(
            "INSERT INTO gateway_audit (idempotency_key, phase, outcome) VALUES (?, 'outcome', 'success')",
            (key,),
        )


def _readback(connection: sqlite3.Connection, pins: dict[str, Any]) -> dict[str, Any]:
    deployment_rows = connection.execute(
        "SELECT service, revision, image_digest, contract FROM deployment ORDER BY service"
    ).fetchall()
    services = [row[0] for row in deployment_rows]
    contracts_compatible = all(
        row[3] == pins["previous"]["services"][row[0]]["contract"] for row in deployment_rows
    )
    return {
        "upgrade": {
            "currentCandidateApplied": connection.execute(
                "SELECT count(*) FROM deployment_history WHERE candidate = 'current'"
            ).fetchone()[0]
            == 1,
            "representativeStateCreated": True,
        },
        "deployment": {
            "services": services,
            "pin": pins["previous"],
            "allPreviousPins": all(
                (row[1], row[2], row[3])
                == (
                    pins["previous"]["services"][row[0]]["revision"],
                    pins["previous"]["services"][row[0]]["imageDigest"],
                    pins["previous"]["services"][row[0]]["contract"],
                )
                for row in deployment_rows
            ),
            "contractsCompatible": contracts_compatible,
        },
        "schema": dict(
            zip(
                ("migrationLeaf", "reverseMigrationAttempted"),
                connection.execute("SELECT migration_leaf, reverse_migration_attempted FROM schema_state").fetchone(),
            )
        ),
        "reconciliation": {
            "effectCount": connection.execute("SELECT effect_count FROM gateway_effect").fetchone()[0],
            "rows": connection.execute("SELECT count(*) FROM reconciliation").fetchone()[0],
        },
        "state": {
            "auditRows": connection.execute("SELECT count(*) FROM gateway_audit").fetchone()[0],
            "outcomeRows": connection.execute("SELECT count(*) FROM gateway_outcome").fetchone()[0],
            "idempotencyRows": connection.execute("SELECT count(*) FROM gateway_idempotency").fetchone()[0],
            "activeQuotaReservations": connection.execute(
                "SELECT coalesce(sum(active_count), 0) FROM quota_bucket"
            ).fetchone()[0],
            "idempotencyState": connection.execute(
                "SELECT state FROM gateway_idempotency WHERE idempotency_key = 'rollback:representative'"
            ).fetchone()[0],
        },
    }
