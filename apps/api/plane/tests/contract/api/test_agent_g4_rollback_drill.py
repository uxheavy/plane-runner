"""Contract proof for the disposable coordinated G4 rollback drill."""

import json

import pytest

from plane.operation_gateway.rollback_drill import run_rollback_drill


@pytest.mark.contract
def test_g4_rollback_drill_switches_all_services_and_reconciles_forward_only_schema():
    result = run_rollback_drill()

    assert result["passes"] is True, json.dumps(result, sort_keys=True)
    assert result["externalWrites"] is False
    assert result["strategy"]["reverseMigrationAllowed"] is False
    assert result["readback"]["schema"]["migrationLeaf"] == "db.0141_operationgateway_quotas"
    assert result["readback"]["state"] == {
        "auditRows": 3,
        "outcomeRows": 1,
        "idempotencyRows": 1,
        "activeQuotaReservations": 0,
        "idempotencyState": "success",
    }
    assert result["readback"]["reconciliation"] == {"effectCount": 1, "rows": 1}
