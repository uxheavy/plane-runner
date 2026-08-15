"""Versioned semantic Plane operations exposed by the shared gateway.

The catalog is descriptive only.  It never grants permission; the Operation
Gateway evaluates the live Plane caller for every dispatch.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping

from .contracts import MAX_RESULT_BYTES, SCHEMA_VERSION, canonical_json

CatalogKind = Literal["read", "mutation"]
OperationKind = CatalogKind
AuthorizationScope = Literal["workspace", "project"]
CodeModeCallbackKind = Literal["search", "describe", "operation", "spill"]
ReconciliationStrategy = Literal[
    "read_after_write",
    "safe_idempotent_replay",
    "outcome_unknown_escalation",
]

RECONCILIATION_POLICY_VERSION = "plane-operation-gateway-reconciliation/v1"

# This is deliberately an exact, versioned registry rather than a default.
# Adding a mutation to the catalog requires choosing its recovery semantics in
# the same change; catalog construction below rejects both missing and extra
# rows.  A descriptor may still carry an explicit policy for a narrowly
# constructed operation outside the catalog.
MUTATION_RECONCILIATION_POLICIES: Mapping[str, ReconciliationStrategy] = MappingProxyType(
    {
        "work_item.rename": "read_after_write",
        "work_item_attachment.upload_from_url": "outcome_unknown_escalation",
        "work_item_attachment.delete": "outcome_unknown_escalation",
        "agent.outcome.submit": "safe_idempotent_replay",
        "agent.outcome.publish": "safe_idempotent_replay",
        "agent.assignment.delegate": "safe_idempotent_replay",
        "agent.assignment.cancel": "safe_idempotent_replay",
        "agent.hr.propose": "safe_idempotent_replay",
        "agent.hr.decide": "safe_idempotent_replay",
        "agent.outcome.evaluate": "safe_idempotent_replay",
        "agent.outcome.accept": "safe_idempotent_replay",
        "agent.outcome.request_revision": "safe_idempotent_replay",
        "work_item.create": "safe_idempotent_replay",
        "work_item.update": "safe_idempotent_replay",
        "work_item.delete": "safe_idempotent_replay",
        "cycle.create": "safe_idempotent_replay",
        "cycle.update": "safe_idempotent_replay",
        "cycle.delete": "safe_idempotent_replay",
        "module.create": "safe_idempotent_replay",
        "module.update": "safe_idempotent_replay",
        "module.delete": "safe_idempotent_replay",
        "project.create": "safe_idempotent_replay",
        "project.update": "safe_idempotent_replay",
        "project.delete": "safe_idempotent_replay",
        "state.create": "safe_idempotent_replay",
        "state.update": "safe_idempotent_replay",
        "state.delete": "safe_idempotent_replay",
        "label.create": "safe_idempotent_replay",
        "label.update": "safe_idempotent_replay",
        "label.delete": "safe_idempotent_replay",
        "link.create": "safe_idempotent_replay",
        "link.update": "safe_idempotent_replay",
        "link.delete": "safe_idempotent_replay",
        "comment.create": "safe_idempotent_replay",
        "comment.update": "safe_idempotent_replay",
        "comment.delete": "safe_idempotent_replay",
        "intake.create": "safe_idempotent_replay",
        "intake.update": "safe_idempotent_replay",
        "intake.delete": "safe_idempotent_replay",
        "work_item_relation.create": "safe_idempotent_replay",
        "cycle.transfer": "safe_idempotent_replay",
        "page.create": "safe_idempotent_replay",
        "cycle.work_item.manage": "safe_idempotent_replay",
        "cycle.archive": "safe_idempotent_replay",
        "cycle.complete": "safe_idempotent_replay",
        "module.work_item.manage": "safe_idempotent_replay",
        "module.archive": "safe_idempotent_replay",
        "project.archive": "safe_idempotent_replay",
        "project.features.update": "safe_idempotent_replay",
        "project.estimate.create": "safe_idempotent_replay",
        "project.estimate.update": "safe_idempotent_replay",
        "project.estimate.delete": "safe_idempotent_replay",
        "project.estimate.link": "safe_idempotent_replay",
        "project.estimate.points.create": "safe_idempotent_replay",
        "project.estimate.point.update": "safe_idempotent_replay",
        "project.estimate.point.delete": "safe_idempotent_replay",
        "work_item.assignee.manage": "safe_idempotent_replay",
        "work_item.label.manage": "safe_idempotent_replay",
        "work_item.archive": "safe_idempotent_replay",
        "work_item_relation.remove": "safe_idempotent_replay",
    }
)

CODE_MODE_CALLBACK_NAMES: Mapping[CodeModeCallbackKind, str] = MappingProxyType(
    {
        "search": "search_plane_operations",
        "describe": "describe_plane_operation",
        "operation": "call_plane_operation",
        "spill": "spill_plane_result",
    }
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


PermissionFamily = Literal["none", "workspace", "project"]


@dataclass(frozen=True)
class OperationDescriptor:
    operation_id: str
    schema_version: str
    kind: OperationKind
    family: str = ""
    summary: str = ""
    required_input: tuple[str, ...] = ()
    input_fields: tuple[str, ...] = ()
    max_result_bytes: int = MAX_RESULT_BYTES
    handler: str = ""
    result_key: str = "result"
    permission: PermissionFamily = "project"
    name: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    result_schema: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    authorization_scope: AuthorizationScope = "project"
    universal: bool = False
    reconciliation: ReconciliationStrategy | None = None

    def __post_init__(self) -> None:
        if isinstance(self.max_result_bytes, bool) or not isinstance(self.max_result_bytes, int):
            raise TypeError("max_result_bytes must be an integer")
        if not 1 <= self.max_result_bytes <= MAX_RESULT_BYTES:
            raise ValueError(f"max_result_bytes must be between 1 and {MAX_RESULT_BYTES} bytes")
        operation_name = self.name or {
            "work_item.read": "read_work_item",
            "work_item.rename": "rename_work_item",
        }.get(self.operation_id, self.operation_id.replace(".", "_"))
        handler_name = self.handler or self.operation_id.replace(".", "_")
        family = self.family or self.operation_id.split(".", 1)[0]
        input_schema = dict(self.input_schema)
        if not input_schema:
            input_schema = {
                "type": "object",
                "additionalProperties": False,
                "required": list(self.required_input),
                "properties": {field_name: {} for field_name in self.input_fields},
            }
        result_schema = dict(self.result_schema)
        if not result_schema:
            result_schema = {
                "type": "object",
                "additionalProperties": False,
                "required": [self.result_key],
                "properties": {self.result_key: {"type": "object"}},
            }
        authorization_scope = self.authorization_scope
        if self.permission == "workspace":
            authorization_scope = "workspace"
        reconciliation = self.reconciliation
        if self.kind == "mutation":
            reconciliation = reconciliation or MUTATION_RECONCILIATION_POLICIES.get(self.operation_id)
            if reconciliation is None:
                raise ValueError(
                    f"Mutation {self.operation_id!r} must have an explicit reconciliation policy in "
                    f"{RECONCILIATION_POLICY_VERSION}"
                )
            if reconciliation not in {
                "read_after_write",
                "safe_idempotent_replay",
                "outcome_unknown_escalation",
            }:
                raise ValueError(f"Unsupported mutation reconciliation policy: {reconciliation}")
        elif reconciliation is not None:
            raise ValueError("Read operations cannot declare mutation reconciliation")
        object.__setattr__(self, "name", operation_name)
        object.__setattr__(self, "handler", handler_name)
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "authorization_scope", authorization_scope)
        object.__setattr__(self, "input_schema", _freeze(input_schema))
        object.__setattr__(self, "result_schema", _freeze(result_schema))
        object.__setattr__(self, "reconciliation", reconciliation)

    @property
    def operation_ref(self) -> str:
        return f"operation:{self.operation_id}"

    @property
    def schema_digest(self) -> str:
        value = {"inputSchema": _thaw(self.input_schema), "resultSchema": _thaw(self.result_schema)}
        return f"content:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


_UUID = {"type": "string", "format": "uuid"}
_WORK_ITEM_READ_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["project_id", "issue_id"],
    "properties": {"project_id": _UUID, "issue_id": _UUID},
}
_WORK_ITEM_RENAME_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["project_id", "issue_id", "name"],
    "properties": {"project_id": _UUID, "issue_id": _UUID, "name": {"type": "string", "minLength": 1}},
}


def _descriptor(
    operation_id: str,
    *,
    kind: OperationKind,
    family: str,
    summary: str,
    required_input: tuple[str, ...] = (),
    input_fields: tuple[str, ...] = (),
    input_schema: Mapping[str, Any] | None = None,
    max_result_bytes: int = MAX_RESULT_BYTES,
    handler: str | None = None,
    result_key: str,
    permission: PermissionFamily = "project",
    reconciliation: ReconciliationStrategy | None = None,
) -> OperationDescriptor:
    return OperationDescriptor(
        operation_id=operation_id,
        schema_version=SCHEMA_VERSION,
        kind=kind,
        family=family,
        summary=summary,
        required_input=required_input,
        input_fields=input_fields,
        input_schema=input_schema or {},
        max_result_bytes=max_result_bytes,
        handler=handler or operation_id.replace(".", "_"),
        result_key=result_key,
        permission=permission,
        reconciliation=reconciliation,
    )


COMMON_PROJECT_FIELDS = ("project_id", "params", "cursor", "per_page", "order_by", "fields", "expand")
COMMON_RESOURCE_FIELDS = COMMON_PROJECT_FIELDS + (
    "name",
    "description",
    "description_html",
    "external_source",
    "external_id",
)


OPERATION_CATALOG: dict[str, OperationDescriptor] = {
    "user.me": _descriptor(
        "user.me",
        kind="read",
        family="user",
        summary="Read the authenticated Plane user projection.",
        result_key="user",
        permission="none",
        handler="user_me",
    ),
    "work_item.read": _descriptor(
        "work_item.read",
        kind="read",
        family="work_item",
        summary="Read one bounded Plane work item projection.",
        required_input=("project_id", "issue_id"),
        input_fields=("project_id", "issue_id"),
        input_schema=_WORK_ITEM_READ_INPUT,
        max_result_bytes=4096,
        result_key="work_item",
        handler="work_item_read",
    ),
    "work_item.rename": _descriptor(
        "work_item.rename",
        kind="mutation",
        family="work_item",
        summary="Rename one Plane work item through the existing issue service.",
        required_input=("project_id", "issue_id", "name"),
        input_fields=("project_id", "issue_id", "name"),
        max_result_bytes=4096,
        result_key="work_item",
        handler="work_item_rename",
        reconciliation="read_after_write",
    ),
    "work_item_attachment.list": _descriptor(
        "work_item_attachment.list",
        kind="read",
        family="work_item_attachment",
        summary="List bounded uploaded work-item attachments.",
        required_input=("project_id", "issue_id"),
        input_fields=("project_id", "issue_id"),
        result_key="attachments",
        handler="work_item_attachment_list",
    ),
    "work_item_attachment.download_url": _descriptor(
        "work_item_attachment.download_url",
        kind="read",
        family="work_item_attachment",
        summary="Issue one bounded attachment download URL.",
        required_input=("project_id", "issue_id", "attachment_id"),
        input_fields=("project_id", "issue_id", "attachment_id"),
        result_key="attachment",
        handler="work_item_attachment_download_url",
    ),
    "work_item_attachment.upload_from_url": _descriptor(
        "work_item_attachment.upload_from_url",
        kind="mutation",
        family="work_item_attachment",
        summary="Fetch one bounded public URL into work-item storage.",
        required_input=("project_id", "issue_id", "url"),
        input_fields=("project_id", "issue_id", "url", "name"),
        result_key="attachment",
        handler="work_item_attachment_upload_from_url",
        reconciliation="outcome_unknown_escalation",
    ),
    "work_item_attachment.delete": _descriptor(
        "work_item_attachment.delete",
        kind="mutation",
        family="work_item_attachment",
        summary="Delete one work-item attachment through Plane storage.",
        required_input=("project_id", "issue_id", "attachment_id"),
        input_fields=("project_id", "issue_id", "attachment_id"),
        result_key="deleted",
        handler="work_item_attachment_delete",
        reconciliation="outcome_unknown_escalation",
    ),
    "work_item_attachment.read": _descriptor(
        "work_item_attachment.read",
        kind="read",
        family="work_item_attachment",
        summary="Authorize one bounded work-item attachment read.",
        required_input=("project_id", "issue_id", "attachment_id"),
        input_fields=("project_id", "issue_id", "attachment_id"),
        result_key="attachment_read",
        handler="work_item_attachment_read",
    ),
}
_SEARCH_WORKSPACE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "maxLength": 255},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        "cursor": {"type": "string", "maxLength": 32},
    },
}
_CATALOG_SEARCH_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "maxLength": 255},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        "cursor": {"type": "string", "maxLength": 32},
    },
}
_CATALOG_DESCRIBE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operation_id"],
    "properties": {"operation_id": {"type": "string", "maxLength": 128, "minLength": 1}},
}
_WORK_ITEM_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["work_item"],
    "properties": {"work_item": {"type": "object"}},
}
_SEARCH_WORKSPACE_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {"type": "array", "maxItems": 50, "items": {"type": "object"}},
        "nextCursor": {"type": ["string", "null"]},
    },
}
_CATALOG_SEARCH_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operations"],
    "properties": {
        "operations": {"type": "array", "maxItems": 50, "items": {"type": "object"}},
        "nextCursor": {"type": ["string", "null"]},
    },
}
_CATALOG_DESCRIBE_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operation"],
    "properties": {"operation": {"type": "object"}},
}
_CODE_MODE_SPILL_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["size_bytes", "content_digest"],
    "properties": {
        "size_bytes": {"type": "integer", "minimum": 1, "maximum": 1_048_576},
        "content_digest": {"type": "string", "minLength": 8, "maxLength": 128},
    },
}
_CODE_MODE_SPILL_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["spill"],
    "properties": {"spill": {"type": "object"}},
}
_AGENT_OUTCOME_SUBMIT_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_ref", "summary"],
    "properties": {
        "run_ref": {"type": "string", "pattern": "^run:"},
        "summary": {"type": "string", "minLength": 1, "maxLength": 4096},
        "artifacts": {"type": "array", "maxItems": 64, "items": {}},
        "evidence": {"type": "array", "maxItems": 64, "items": {}},
    },
}
_AGENT_OUTCOME_SUBMIT_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outcome"],
    "properties": {"outcome": {"type": "object"}},
}
_AGENT_OUTCOME_PUBLISH_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["run_ref", "outcome_ref", "content"],
    "properties": {
        "run_ref": {"type": "string", "pattern": "^run:"},
        "outcome_ref": {"type": "string", "pattern": "^outcome-submission:"},
        "content": {"type": "string", "minLength": 1, "maxLength": 4096},
    },
}
_AGENT_OUTCOME_PUBLISH_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["published", "outcome"],
    "properties": {"published": {"type": "boolean"}, "outcome": {"type": "object"}},
}
_AGENT_DELEGATE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "parent_assignment_ref",
        "delegator_ref",
        "assignee_ref",
        "target_ref",
        "objective",
        "plan_rationale",
        "acceptance_criteria",
    ],
    "properties": {
        "parent_assignment_ref": {"type": "string", "pattern": "^assignment:"},
        "delegator_ref": {"type": "string", "pattern": "^agent-actor:"},
        "assignee_ref": {"type": "string", "pattern": "^agent-actor:"},
        "target_ref": {"type": "string", "minLength": 1, "maxLength": 255},
        "objective": {"type": "string", "minLength": 1, "maxLength": 4096},
        "plan_rationale": {"type": "string", "minLength": 1, "maxLength": 4096},
        "acceptance_criteria": {"type": "array", "minItems": 1, "maxItems": 32},
        "context_refs": {"type": "array", "maxItems": 64},
        "scope": {"type": "object"},
        "budget": {"type": "object"},
    },
}
_AGENT_HR_PROPOSE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposer_ref", "kind", "rationale"],
    "properties": {
        "proposer_ref": {"type": "string", "pattern": "^agent-actor:"},
        "kind": {"type": "string", "enum": ["hire", "role_change", "suspend", "retire", "reassign", "chief_of_staff"]},
        "rationale": {"type": "string", "minLength": 1, "maxLength": 4096},
        "subject_actor_ref": {"type": "string", "pattern": "^agent-actor:"},
        "subject_user_ref": {"type": "string", "pattern": "^user:"},
        "requested_principal_ref": {"type": "string", "pattern": "^user:"},
        "target_assignment_ref": {"type": "string", "pattern": "^assignment:"},
        "requested_assignee_ref": {"type": "string", "pattern": "^agent-actor:"},
        "requested_role": {"type": "string"},
        "requested_display_name": {"type": "string", "maxLength": 255},
        "requested_profile": {"type": "object"},
        "project_id": {"type": ["string", "null"]},
    },
}
_AGENT_HR_DECIDE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposal_ref", "approved"],
    "properties": {
        "proposal_ref": {"type": "string", "pattern": "^hr-proposal:"},
        "approved": {"type": "boolean"},
        "decision_note": {"type": "string", "maxLength": 4096},
    },
}
_AGENT_OUTCOME_EVALUATE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outcome_ref", "evaluator_ref", "verdict"],
    "properties": {
        "outcome_ref": {"type": "string", "pattern": "^outcome-submission:"},
        "evaluator_ref": {"type": "string", "pattern": "^agent-actor:"},
        "criteria": {"type": "array", "maxItems": 32},
        "verdict": {"type": "string", "enum": ["accept", "revision_requested"]},
        "feedback": {"type": "string", "maxLength": 4096},
        "provenance": {"type": "object"},
    },
}
_AGENT_OUTCOME_DECIDE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outcome_ref"],
    "properties": {
        "outcome_ref": {"type": "string", "pattern": "^outcome-submission:"},
        "decision_note": {"type": "string", "maxLength": 4096},
    },
}
_AGENT_ASSIGNMENT_CANCEL_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assignment_ref"],
    "properties": {"assignment_ref": {"type": "string", "pattern": "^assignment:"}},
}
_AGENT_GOVERNANCE_RESULT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["record"],
    "properties": {"record": {"type": "object"}},
}


OPERATION_CATALOG.update(
    {
        "search_workspace": OperationDescriptor(
            operation_id="search_workspace",
            schema_version=SCHEMA_VERSION,
            kind="read",
            family="core",
            summary="Search accessible Plane objects and return typed references.",
            required_input=("query",),
            input_fields=("query", "limit", "cursor"),
            max_result_bytes=MAX_RESULT_BYTES,
            handler="search_workspace",
            result_key="results",
            permission="workspace",
            name="search_workspace",
            input_schema=_SEARCH_WORKSPACE_INPUT,
            result_schema=_SEARCH_WORKSPACE_RESULT,
            tags=("core", "workspace", "search", "read"),
            authorization_scope="workspace",
            universal=True,
        ),
        "catalog.search": OperationDescriptor(
            operation_id="catalog.search",
            schema_version=SCHEMA_VERSION,
            kind="read",
            family="catalog",
            summary="Search the complete Plane operation catalog.",
            required_input=("query",),
            input_fields=("query", "limit", "cursor"),
            max_result_bytes=MAX_RESULT_BYTES,
            handler="catalog_search",
            result_key="operations",
            permission="workspace",
            name="search_plane_operations",
            input_schema=_CATALOG_SEARCH_INPUT,
            result_schema=_CATALOG_SEARCH_RESULT,
            tags=("catalog", "discovery", "read"),
            authorization_scope="workspace",
        ),
        "catalog.describe": OperationDescriptor(
            operation_id="catalog.describe",
            schema_version=SCHEMA_VERSION,
            kind="read",
            family="catalog",
            summary="Describe one supported Plane operation and its schemas.",
            required_input=("operation_id",),
            input_fields=("operation_id",),
            max_result_bytes=MAX_RESULT_BYTES,
            handler="catalog_describe",
            result_key="operation",
            permission="workspace",
            name="describe_plane_operation",
            input_schema=_CATALOG_DESCRIBE_INPUT,
            result_schema=_CATALOG_DESCRIBE_RESULT,
            tags=("catalog", "discovery", "read"),
            authorization_scope="workspace",
        ),
        "code_mode.spill": OperationDescriptor(
            operation_id="code_mode.spill",
            schema_version=SCHEMA_VERSION,
            kind="read",
            family="code_mode",
            summary="Accept bounded Code Mode result metadata at the audited host boundary.",
            required_input=("size_bytes", "content_digest"),
            input_fields=("size_bytes", "content_digest"),
            max_result_bytes=1024,
            handler="code_mode_spill",
            result_key="spill",
            permission="workspace",
            name="spill_plane_result",
            input_schema=_CODE_MODE_SPILL_INPUT,
            result_schema=_CODE_MODE_SPILL_RESULT,
            tags=("code-mode", "spill", "read"),
            authorization_scope="workspace",
        ),
        "agent.outcome.submit": OperationDescriptor(
            operation_id="agent.outcome.submit",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Submit one explicit Plane Agent outcome with artifacts and evidence.",
            required_input=("run_ref", "summary"),
            max_result_bytes=MAX_RESULT_BYTES,
            handler="agent_outcome_submit",
            name="submit_agent_outcome",
            result_key="outcome",
            input_schema=_AGENT_OUTCOME_SUBMIT_INPUT,
            result_schema=_AGENT_OUTCOME_SUBMIT_RESULT,
            tags=("agent", "outcome", "publication", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.outcome.publish": OperationDescriptor(
            operation_id="agent.outcome.publish",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Explicitly publish an already submitted Plane Agent outcome.",
            required_input=("run_ref", "outcome_ref", "content"),
            max_result_bytes=MAX_RESULT_BYTES,
            handler="agent_outcome_publish",
            name="publish_agent_outcome",
            result_key="outcome",
            input_schema=_AGENT_OUTCOME_PUBLISH_INPUT,
            result_schema=_AGENT_OUTCOME_PUBLISH_RESULT,
            tags=("agent", "outcome", "publication", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.assignment.delegate": OperationDescriptor(
            operation_id="agent.assignment.delegate",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Create one bounded child AssignmentContract through dynamic delegation.",
            required_input=(
                "parent_assignment_ref",
                "delegator_ref",
                "assignee_ref",
                "target_ref",
                "objective",
                "plan_rationale",
                "acceptance_criteria",
            ),
            input_fields=tuple(_AGENT_DELEGATE_INPUT["properties"]),
            max_result_bytes=8 * 1024,
            handler="agent_assignment_delegate",
            result_key="assignment",
            input_schema=_AGENT_DELEGATE_INPUT,
            result_schema={
                "type": "object",
                "required": ["assignment"],
                "properties": {"assignment": {"type": "object"}},
            },
            tags=("agent", "assignment", "delegation", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.assignment.cancel": OperationDescriptor(
            operation_id="agent.assignment.cancel",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Cancel an assignment and propagate cancellation to unfinished delegated children.",
            required_input=("assignment_ref",),
            input_fields=tuple(_AGENT_ASSIGNMENT_CANCEL_INPUT["properties"]),
            max_result_bytes=8 * 1024,
            handler="agent_assignment_cancel",
            result_key="assignment",
            input_schema=_AGENT_ASSIGNMENT_CANCEL_INPUT,
            result_schema={
                "type": "object",
                "required": ["assignment"],
                "properties": {"assignment": {"type": "object"}},
            },
            tags=("agent", "assignment", "cancellation", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.hr.propose": OperationDescriptor(
            operation_id="agent.hr.propose",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Record a human-gated HR proposal without changing Plane control state.",
            required_input=("proposer_ref", "kind", "rationale"),
            input_fields=tuple(_AGENT_HR_PROPOSE_INPUT["properties"]),
            max_result_bytes=8 * 1024,
            handler="agent_hr_propose",
            result_key="proposal",
            input_schema=_AGENT_HR_PROPOSE_INPUT,
            result_schema={"type": "object", "required": ["proposal"], "properties": {"proposal": {"type": "object"}}},
            tags=("agent", "hr", "governance", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.hr.decide": OperationDescriptor(
            operation_id="agent.hr.decide",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Approve or reject one HR proposal as a current human workspace administrator.",
            required_input=("proposal_ref", "approved"),
            input_fields=tuple(_AGENT_HR_DECIDE_INPUT["properties"]),
            max_result_bytes=8 * 1024,
            handler="agent_hr_decide",
            result_key="proposal",
            input_schema=_AGENT_HR_DECIDE_INPUT,
            result_schema={"type": "object", "required": ["proposal"], "properties": {"proposal": {"type": "object"}}},
            tags=("agent", "hr", "governance", "human", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.outcome.evaluate": OperationDescriptor(
            operation_id="agent.outcome.evaluate",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Persist evaluator evidence and recommendation before human outcome review.",
            required_input=("outcome_ref", "evaluator_ref", "verdict"),
            input_fields=tuple(_AGENT_OUTCOME_EVALUATE_INPUT["properties"]),
            max_result_bytes=8 * 1024,
            handler="agent_outcome_evaluate",
            result_key="outcome",
            input_schema=_AGENT_OUTCOME_EVALUATE_INPUT,
            result_schema={"type": "object", "required": ["outcome"], "properties": {"outcome": {"type": "object"}}},
            tags=("agent", "outcome", "evaluator", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.outcome.accept": OperationDescriptor(
            operation_id="agent.outcome.accept",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Accept an evaluator-reviewed outcome as a human reviewer.",
            required_input=("outcome_ref",),
            input_fields=tuple(_AGENT_OUTCOME_DECIDE_INPUT["properties"]),
            max_result_bytes=8 * 1024,
            handler="agent_outcome_accept",
            result_key="outcome",
            input_schema=_AGENT_OUTCOME_DECIDE_INPUT,
            result_schema={"type": "object", "required": ["outcome"], "properties": {"outcome": {"type": "object"}}},
            tags=("agent", "outcome", "human", "mutation"),
            authorization_scope="workspace",
        ),
        "agent.outcome.request_revision": OperationDescriptor(
            operation_id="agent.outcome.request_revision",
            schema_version=SCHEMA_VERSION,
            kind="mutation",
            summary="Return an evaluator-reviewed outcome for human-requested revision.",
            required_input=("outcome_ref",),
            input_fields=tuple(_AGENT_OUTCOME_DECIDE_INPUT["properties"]),
            max_result_bytes=8 * 1024,
            handler="agent_outcome_request_revision",
            result_key="outcome",
            input_schema=_AGENT_OUTCOME_DECIDE_INPUT,
            result_schema={"type": "object", "required": ["outcome"], "properties": {"outcome": {"type": "object"}}},
            tags=("agent", "outcome", "human", "revision", "mutation"),
            authorization_scope="workspace",
        ),
    }
)


def _catalog_entry(descriptor: OperationDescriptor) -> dict[str, Any]:
    return {
        "operationId": descriptor.operation_id,
        "operationRef": descriptor.operation_ref,
        "name": descriptor.name,
        "schemaVersion": descriptor.schema_version,
        "kind": descriptor.kind,
        "reconciliation": descriptor.reconciliation,
        "summary": descriptor.summary,
        "tags": list(descriptor.tags),
        "inputSchema": _thaw(descriptor.input_schema),
        "resultSchema": _thaw(descriptor.result_schema),
        "schemaDigest": descriptor.schema_digest,
        "maxResultBytes": descriptor.max_result_bytes,
        "universal": descriptor.universal,
    }


def _catalog_payload() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "codeModeCallbacks": dict(CODE_MODE_CALLBACK_NAMES),
        "operations": [_catalog_entry(OPERATION_CATALOG[key]) for key in sorted(OPERATION_CATALOG)],
    }


def _add_resource_operations(
    *,
    prefix: str,
    family: str,
    resource_label: str,
    result_key: str,
    fields: tuple[str, ...],
    retrieve_id: str,
    permission: PermissionFamily = "project",
    max_result_bytes: int = MAX_RESULT_BYTES,
    list_required_input: tuple[str, ...] | None = None,
    create_required_input: tuple[str, ...] | None = None,
    list_result_key: str | None = None,
    include_delete: bool = False,
) -> None:
    """Register one complete CRUD family with explicit typed descriptors."""

    operations = {
        f"{prefix}.list": _descriptor(
            f"{prefix}.list",
            kind="read",
            family=family,
            summary=f"List bounded {resource_label} records through a canonical Plane application adapter.",
            required_input=list_required_input
            if list_required_input is not None
            else tuple(field for field in fields if field == "project_id"),
            input_fields=fields,
            result_key=list_result_key or f"{result_key}s",
            permission=permission,
            max_result_bytes=max_result_bytes,
        ),
        f"{prefix}.create": _descriptor(
            f"{prefix}.create",
            kind="mutation",
            family=family,
            summary=f"Create one {resource_label} through a canonical Plane application adapter.",
            required_input=create_required_input
            if create_required_input is not None
            else tuple(field for field in fields if field == "project_id")
            + tuple(field for field in fields if field == "name"),
            input_fields=fields,
            result_key=result_key,
            permission=permission,
            max_result_bytes=max_result_bytes,
        ),
        f"{prefix}.retrieve": _descriptor(
            f"{prefix}.retrieve",
            kind="read",
            family=family,
            summary=f"Retrieve one {resource_label} through a canonical Plane application adapter.",
            required_input=("project_id", retrieve_id),
            input_fields=fields + (retrieve_id,),
            result_key=result_key,
            permission=permission,
            max_result_bytes=max_result_bytes,
        ),
        f"{prefix}.update": _descriptor(
            f"{prefix}.update",
            kind="mutation",
            family=family,
            summary=f"Update one {resource_label} through a canonical Plane application adapter.",
            required_input=("project_id", retrieve_id),
            input_fields=fields + (retrieve_id,),
            result_key=result_key,
            permission=permission,
            max_result_bytes=max_result_bytes,
        ),
    }
    if include_delete:
        operations[f"{prefix}.delete"] = _descriptor(
            f"{prefix}.delete",
            kind="mutation",
            family=family,
            summary=f"Delete one {resource_label} through a canonical Plane application adapter.",
            required_input=("project_id", retrieve_id),
            input_fields=fields + (retrieve_id,),
            result_key="deleted",
            permission=permission,
            max_result_bytes=2048,
        )
    OPERATION_CATALOG.update(operations)


_add_resource_operations(
    prefix="work_item",
    family="work_item",
    resource_label="work item",
    result_key="work_item",
    fields=COMMON_RESOURCE_FIELDS
    + (
        "issue_id",
        "description_stripped",
        "assignees",
        "labels",
        "type_id",
        "point",
        "priority",
        "start_date",
        "target_date",
        "sort_order",
        "is_draft",
        "parent",
        "state",
        "estimate_point",
        "type",
        "pql",
    ),
    retrieve_id="issue_id",
    list_required_input=(),
    create_required_input=("project_id", "name"),
    include_delete=True,
)
_add_resource_operations(
    prefix="cycle",
    family="cycle",
    resource_label="cycle",
    result_key="cycle",
    fields=COMMON_RESOURCE_FIELDS
    + ("cycle_id", "start_date", "end_date", "owned_by", "timezone", "archived", "status"),
    retrieve_id="cycle_id",
    create_required_input=("project_id", "name", "owned_by"),
    list_result_key="cycles",
    include_delete=True,
)
_add_resource_operations(
    prefix="module",
    family="module",
    resource_label="module",
    result_key="module",
    fields=COMMON_RESOURCE_FIELDS + ("module_id", "start_date", "target_date", "status", "lead", "members", "archived"),
    retrieve_id="module_id",
    list_result_key="modules",
    include_delete=True,
)
_add_resource_operations(
    prefix="project",
    family="project",
    resource_label="project",
    result_key="project",
    fields=(
        "project_id",
        "cursor",
        "per_page",
        "order_by",
        "fields",
        "expand",
        "name",
        "identifier",
        "description",
        "project_lead",
        "default_assignee",
        "emoji",
        "cover_image",
        "network",
        "module_view",
        "cycle_view",
        "issue_views_view",
        "page_view",
        "intake_view",
        "guest_view_all_features",
        "archive_in",
        "close_in",
        "timezone",
        "external_source",
        "external_id",
        "is_issue_type_enabled",
        "is_time_tracking_enabled",
        "default_state",
        "estimate",
    ),
    retrieve_id="project_id",
    permission="workspace",
    max_result_bytes=MAX_RESULT_BYTES,
    list_required_input=(),
    create_required_input=("name", "identifier"),
    list_result_key="projects",
    include_delete=True,
)
_add_resource_operations(
    prefix="state",
    family="state",
    resource_label="state",
    result_key="state",
    fields=COMMON_PROJECT_FIELDS
    + ("state_id", "name", "color", "description", "sequence", "group", "is_triage", "default"),
    retrieve_id="state_id",
    create_required_input=("project_id", "name", "color"),
    list_result_key="states",
    include_delete=True,
)
_add_resource_operations(
    prefix="label",
    family="label",
    resource_label="label",
    result_key="label",
    fields=COMMON_PROJECT_FIELDS
    + ("label_id", "name", "color", "description", "parent", "sort_order", "external_source", "external_id"),
    retrieve_id="label_id",
    create_required_input=("project_id", "name"),
    list_result_key="labels",
    include_delete=True,
)
_add_resource_operations(
    prefix="link",
    family="work_item_link",
    resource_label="work item link",
    result_key="link",
    fields=COMMON_PROJECT_FIELDS + ("issue_id", "link_id", "url"),
    retrieve_id="link_id",
    list_required_input=("project_id", "issue_id"),
    create_required_input=("project_id", "issue_id", "url"),
    list_result_key="links",
    include_delete=True,
)
_add_resource_operations(
    prefix="comment",
    family="work_item_comment",
    resource_label="work item comment",
    result_key="comment",
    fields=COMMON_PROJECT_FIELDS
    + (
        "issue_id",
        "comment_id",
        "comment_html",
        "comment_json",
        "access",
        "external_source",
        "external_id",
    ),
    retrieve_id="comment_id",
    list_required_input=("project_id", "issue_id"),
    create_required_input=("project_id", "issue_id"),
    list_result_key="comments",
    include_delete=True,
)
_add_resource_operations(
    prefix="intake",
    family="intake",
    resource_label="intake work item",
    result_key="intake_work_item",
    fields=COMMON_PROJECT_FIELDS
    + ("work_item_id", "data", "status", "snoozed_till", "duplicate_to", "source", "source_email"),
    retrieve_id="issue_id",
    create_required_input=("project_id", "data"),
    list_result_key="intake_work_items",
    include_delete=True,
)


for operation_id, descriptor in (
    (
        "work_item.search",
        _descriptor(
            "work_item.search",
            kind="read",
            family="work_item",
            summary="Search visible Plane work items by name, identifier, or sequence.",
            input_fields=("project_id", "query", "expand", "fields", "external_id", "external_source", "order_by"),
            result_key="issues",
            permission="workspace",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
    (
        "work_item_activity.list",
        _descriptor(
            "work_item_activity.list",
            kind="read",
            family="work_item_activity",
            summary="List visible non-comment work-item activity records.",
            required_input=("project_id", "issue_id"),
            input_fields=("project_id", "issue_id", "cursor", "per_page", "order_by", "fields", "expand", "params"),
            result_key="activities",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
    (
        "work_item_activity.retrieve",
        _descriptor(
            "work_item_activity.retrieve",
            kind="read",
            family="work_item_activity",
            summary="Retrieve one visible non-comment work-item activity record.",
            required_input=("project_id", "issue_id", "activity_id"),
            input_fields=("project_id", "issue_id", "activity_id", "fields", "expand", "params"),
            result_key="activity",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
    (
        "work_item_relation.list",
        _descriptor(
            "work_item_relation.list",
            kind="read",
            family="work_item_relation",
            summary="List visible relations grouped by Plane relation semantics.",
            required_input=("project_id", "issue_id"),
            input_fields=("project_id", "issue_id"),
            result_key="relations",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
    (
        "work_item_relation.create",
        _descriptor(
            "work_item_relation.create",
            kind="mutation",
            family="work_item_relation",
            summary="Create visible work-item relations through Plane relation validation.",
            required_input=("project_id", "issue_id", "work_item_ids"),
            input_fields=(
                "project_id",
                "issue_id",
                "work_item_ids",
                "relation_type",
                "relation_definition_id",
                "relation_definition_label",
            ),
            result_key="relations",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
    (
        "cycle.work_item.list",
        _descriptor(
            "cycle.work_item.list",
            kind="read",
            family="cycle_work_item",
            summary="List bounded work items associated with one cycle.",
            required_input=("project_id", "cycle_id"),
            input_fields=(
                "project_id",
                "cycle_id",
                "pql",
                "cursor",
                "per_page",
                "order_by",
                "fields",
                "expand",
                "params",
            ),
            result_key="work_items",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
    (
        "cycle.transfer",
        _descriptor(
            "cycle.transfer",
            kind="mutation",
            family="cycle_work_item",
            summary="Transfer cycle work items through Plane's canonical transfer helper.",
            required_input=("project_id", "cycle_id", "new_cycle_id"),
            input_fields=("project_id", "cycle_id", "new_cycle_id"),
            result_key="message",
            max_result_bytes=2048,
        ),
    ),
    (
        "module.work_item.list",
        _descriptor(
            "module.work_item.list",
            kind="read",
            family="module_work_item",
            summary="List bounded work items associated with one module.",
            required_input=("project_id", "module_id"),
            input_fields=(
                "project_id",
                "module_id",
                "pql",
                "cursor",
                "per_page",
                "order_by",
                "fields",
                "expand",
                "params",
            ),
            result_key="work_items",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
):
    OPERATION_CATALOG[operation_id] = descriptor


def _add_breadth_operation(
    operation_id: str,
    *,
    kind: OperationKind,
    family: str,
    summary: str,
    required_input: tuple[str, ...] = (),
    input_fields: tuple[str, ...] = (),
    result_key: str,
    permission: PermissionFamily = "project",
    max_result_bytes: int = MAX_RESULT_BYTES,
) -> None:
    """Register one exact breadth action without introducing a generic endpoint."""

    OPERATION_CATALOG[operation_id] = _descriptor(
        operation_id,
        kind=kind,
        family=family,
        summary=summary,
        required_input=required_input,
        input_fields=input_fields,
        result_key=result_key,
        permission=permission,
        max_result_bytes=max_result_bytes,
    )


_add_breadth_operation(
    "cycle.work_item.manage",
    kind="mutation",
    family="cycle_work_item",
    summary="Add or remove project work items from one cycle.",
    required_input=("project_id", "cycle_id"),
    input_fields=("project_id", "cycle_id", "add_ids", "remove_ids"),
    result_key="cycle_work_items",
)
_add_breadth_operation(
    "cycle.archive",
    kind="mutation",
    family="cycle",
    summary="Archive or unarchive one cycle through its native lifecycle fields.",
    required_input=("project_id", "cycle_id", "archive"),
    input_fields=("project_id", "cycle_id", "archive"),
    result_key="archived",
)
_add_breadth_operation(
    "cycle.complete",
    kind="mutation",
    family="cycle",
    summary="Complete one cycle through its native end date.",
    required_input=("project_id", "cycle_id"),
    input_fields=("project_id", "cycle_id"),
    result_key="cycle",
)
_add_breadth_operation(
    "module.work_item.manage",
    kind="mutation",
    family="module_work_item",
    summary="Add or remove project work items from one module.",
    required_input=("project_id", "module_id"),
    input_fields=("project_id", "module_id", "add_ids", "remove_ids"),
    result_key="module_work_items",
)
_add_breadth_operation(
    "module.archive",
    kind="mutation",
    family="module",
    summary="Archive or unarchive one module through its native lifecycle fields.",
    required_input=("project_id", "module_id", "archive"),
    input_fields=("project_id", "module_id", "archive"),
    result_key="module",
)
_add_breadth_operation(
    "project.archive",
    kind="mutation",
    family="project",
    summary="Archive or unarchive one project through its native lifecycle fields.",
    required_input=("project_id", "archive"),
    input_fields=("project_id", "archive"),
    result_key="project",
    permission="workspace",
)
_add_breadth_operation(
    "project.features.update",
    kind="mutation",
    family="project",
    summary="Update the native project feature flags with explicit field mapping.",
    required_input=("project_id",),
    input_fields=("project_id", "modules", "cycles", "views", "pages", "intakes", "work_item_types"),
    result_key="project",
    permission="workspace",
)
_add_breadth_operation(
    "project.estimate.retrieve",
    kind="read",
    family="project_estimate",
    summary="Read the native estimate linked to one project.",
    required_input=("project_id",),
    input_fields=("project_id",),
    result_key="estimate",
)
_add_breadth_operation(
    "project.estimate.points.list",
    kind="read",
    family="project_estimate",
    summary="List native estimate points for one project estimate.",
    required_input=("project_id", "estimate_id"),
    input_fields=("project_id", "estimate_id"),
    result_key="points",
)
_add_breadth_operation(
    "project.estimate.create",
    kind="mutation",
    family="project_estimate",
    summary="Create the native estimate for one project.",
    required_input=("project_id", "name"),
    input_fields=("project_id", "name", "type", "description", "last_used", "external_id", "external_source"),
    result_key="estimate",
)
_add_breadth_operation(
    "project.estimate.update",
    kind="mutation",
    family="project_estimate",
    summary="Update the native estimate for one project.",
    required_input=("project_id",),
    input_fields=("project_id", "name", "description", "external_id", "external_source"),
    result_key="estimate",
)
_add_breadth_operation(
    "project.estimate.delete",
    kind="mutation",
    family="project_estimate",
    summary="Delete the native estimate for one project.",
    required_input=("project_id",),
    input_fields=("project_id",),
    result_key="deleted",
    max_result_bytes=2048,
)
_add_breadth_operation(
    "project.estimate.link",
    kind="mutation",
    family="project_estimate",
    summary="Link an existing native estimate to one project.",
    required_input=("project_id", "estimate_id"),
    input_fields=("project_id", "estimate_id"),
    result_key="project",
)
_add_breadth_operation(
    "project.estimate.points.create",
    kind="mutation",
    family="project_estimate",
    summary="Create native estimate points for one project estimate.",
    required_input=("project_id", "estimate_id", "points"),
    input_fields=("project_id", "estimate_id", "points"),
    result_key="points",
)
_add_breadth_operation(
    "project.estimate.point.update",
    kind="mutation",
    family="project_estimate",
    summary="Update one native estimate point.",
    required_input=("project_id", "estimate_id", "estimate_point_id"),
    input_fields=("project_id", "estimate_id", "estimate_point_id", "value", "key", "description"),
    result_key="point",
)
_add_breadth_operation(
    "project.estimate.point.delete",
    kind="mutation",
    family="project_estimate",
    summary="Delete one native estimate point.",
    required_input=("project_id", "estimate_id", "estimate_point_id"),
    input_fields=("project_id", "estimate_id", "estimate_point_id"),
    result_key="deleted",
    max_result_bytes=2048,
)
_add_breadth_operation(
    "work_item.identifier.retrieve",
    kind="read",
    family="work_item",
    summary="Retrieve one work item by its project identifier and sequence.",
    required_input=("work_item_identifier",),
    input_fields=("work_item_identifier", "expand", "fields", "external_id", "external_source", "order_by"),
    result_key="work_item",
    permission="workspace",
)
_add_breadth_operation(
    "work_item.assignee.manage",
    kind="mutation",
    family="work_item",
    summary="Add or remove one project member as a work-item assignee.",
    required_input=("project_id", "work_item_id"),
    input_fields=("project_id", "work_item_id", "add_user_id", "remove_user_id"),
    result_key="work_item",
)
_add_breadth_operation(
    "work_item.label.manage",
    kind="mutation",
    family="work_item",
    summary="Add or remove one project label from a work item.",
    required_input=("project_id", "work_item_id"),
    input_fields=("project_id", "work_item_id", "add_label_id", "remove_label_id"),
    result_key="work_item",
)
_add_breadth_operation(
    "work_item.archive.list",
    kind="read",
    family="work_item",
    summary="List archived work items in one project with bounded pagination.",
    required_input=("project_id",),
    input_fields=("project_id", "pql", "cursor", "per_page", "order_by", "fields", "expand"),
    result_key="work_items",
)
_add_breadth_operation(
    "work_item.archive",
    kind="mutation",
    family="work_item",
    summary="Archive or unarchive one work item through its native lifecycle field.",
    required_input=("project_id", "work_item_id", "archive"),
    input_fields=("project_id", "work_item_id", "archive"),
    result_key="work_item",
)
_add_breadth_operation(
    "work_item_relation.remove",
    kind="mutation",
    family="work_item_relation",
    summary="Remove one native work-item relation in the caller's project workspace.",
    required_input=("project_id", "work_item_id", "related_work_item_id", "is_dependency"),
    input_fields=("project_id", "work_item_id", "related_work_item_id", "is_dependency"),
    result_key="removed",
    max_result_bytes=2048,
)

for operation_id, descriptor in (
    (
        "page.list",
        _descriptor(
            "page.list",
            kind="read",
            family="page",
            summary="List bounded project pages.",
            input_fields=("project_id", "params", "cursor", "per_page", "order_by", "fields", "expand"),
            result_key="pages",
        ),
    ),
    (
        "page.retrieve",
        _descriptor(
            "page.retrieve",
            kind="read",
            family="page",
            summary="Retrieve one project page.",
            required_input=("page_id",),
            input_fields=("page_id", "project_id", "track_visit"),
            result_key="page",
        ),
    ),
    (
        "page.create",
        _descriptor(
            "page.create",
            kind="mutation",
            family="page",
            summary="Create one project page.",
            required_input=("name", "description_html"),
            input_fields=(
                "name",
                "description_html",
                "project_id",
                "access",
                "color",
                "is_locked",
                "archived_at",
                "view_props",
                "logo_props",
                "external_id",
                "external_source",
            ),
            result_key="page",
        ),
    ),
    (
        "project_member.list",
        _descriptor(
            "project_member.list",
            kind="read",
            family="member",
            summary="List project members with Plane membership state.",
            required_input=("project_id",),
            input_fields=(
                "project_id",
                "first_name",
                "last_name",
                "email",
                "display_name",
                "role_slug",
                "is_active",
                "is_bot",
                "cursor",
                "per_page",
                "order_by",
            ),
            result_key="members",
        ),
    ),
    (
        "workspace_member.list",
        _descriptor(
            "workspace_member.list",
            kind="read",
            family="member",
            summary="List workspace members with Plane membership state.",
            input_fields=(
                "first_name",
                "last_name",
                "email",
                "display_name",
                "role_slug",
                "is_active",
                "is_bot",
                "cursor",
                "per_page",
                "order_by",
            ),
            result_key="members",
            permission="workspace",
            max_result_bytes=MAX_RESULT_BYTES,
        ),
    ),
):
    OPERATION_CATALOG[operation_id] = descriptor


def _validate_reconciliation_policies() -> None:
    catalog_ids = {
        descriptor.operation_id for descriptor in OPERATION_CATALOG.values() if descriptor.kind == "mutation"
    }
    policy_ids = set(MUTATION_RECONCILIATION_POLICIES)
    missing = sorted(catalog_ids - policy_ids)
    extra = sorted(policy_ids - catalog_ids)
    if missing or extra:
        raise RuntimeError(
            "Mutation reconciliation registry must exactly match the catalog "
            f"(missing={missing}, extra={extra}, version={RECONCILIATION_POLICY_VERSION})"
        )
    invalid = sorted(
        operation_id
        for operation_id in catalog_ids
        if OPERATION_CATALOG[operation_id].reconciliation != MUTATION_RECONCILIATION_POLICIES[operation_id]
    )
    if invalid:
        raise RuntimeError(f"Mutation reconciliation descriptors disagree with the registry: {invalid}")


_validate_reconciliation_policies()


# The digest is computed after the full breadth and the universal Plane core
# have been registered, so discovery and presentation share one source.
CATALOG_DIGEST = f"content:{hashlib.sha256(canonical_json(_catalog_payload()).encode('utf-8')).hexdigest()}"


# Publication intents are part of the mutation contract even though they are
# not separately callable catalog rows.  Keep this list explicit so a new
# durable publication kind cannot silently inherit replay behavior.
PUBLICATION_RECONCILIATION_MATRIX = (
    {"publicationKind": "activity", "strategy": "safe_idempotent_replay", "evidence": "deterministic_activity_id"},
    {"publicationKind": "model_activity", "strategy": "safe_idempotent_replay", "evidence": "gateway_publication_key"},
    {"publicationKind": "notification", "strategy": "safe_idempotent_replay", "evidence": "gateway_publication_key"},
    {"publicationKind": "webhook", "strategy": "outcome_unknown_escalation", "evidence": "dispatch_started_lease"},
)


# The executable seam is deliberately derived from the complete descriptor
# table.  The operation handler module asserts that every non-special row has
# one concrete registered adapter, so a descriptor cannot silently advertise
# a false operation.
IMPLEMENTED_OPERATION_IDS = frozenset(OPERATION_CATALOG)


def get_operation(operation_id: str) -> OperationDescriptor | None:
    return OPERATION_CATALOG.get(operation_id)


def code_mode_callback_names() -> dict[str, str]:
    return dict(CODE_MODE_CALLBACK_NAMES)


def operation_catalog_snapshot() -> dict[str, Any]:
    return {
        "catalogDigest": CATALOG_DIGEST,
        "reconciliationMatrix": operation_reconciliation_matrix(),
        **_catalog_payload(),
    }


_CATALOG_SEARCH_PRIORITY = (
    "user.me",
    "search_workspace",
    "work_item.read",
    "work_item.rename",
    "catalog.search",
    "catalog.describe",
    "code_mode.spill",
)
_CATALOG_SEARCH_FIELDS = (
    "operationId",
    "operationRef",
    "name",
    "kind",
    "family",
    "tags",
    "universal",
    "reconciliation",
)


def _catalog_search_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {field: entry[field] for field in _CATALOG_SEARCH_FIELDS if field in entry}


def catalog_search(query: str = "", *, limit: int | None = None, cursor: str | None = None) -> dict[str, Any]:
    if not isinstance(query, str) or (limit is not None and (not isinstance(limit, int) or isinstance(limit, bool))):
        raise ValueError("catalog search input is invalid")
    if limit is not None and not 1 <= limit <= 50:
        raise ValueError("catalog search limit is invalid")
    if limit is None and cursor is not None:
        raise ValueError("catalog search cursor is invalid")
    offset = 0
    if cursor is not None:
        if not isinstance(cursor, str) or not cursor.startswith("cursor:"):
            raise ValueError("catalog search cursor is invalid")
        try:
            offset = int(cursor.removeprefix("cursor:"))
        except ValueError as exc:
            raise ValueError("catalog search cursor is invalid") from exc
        if offset < 0:
            raise ValueError("catalog search cursor is invalid")
    needle = query.strip().casefold()
    entries = [
        entry for entry in _catalog_payload()["operations"] if not needle or needle in canonical_json(entry).casefold()
    ]
    if not needle:
        by_id = {entry["operationId"]: entry for entry in entries}
        entries = [by_id[operation_id] for operation_id in _CATALOG_SEARCH_PRIORITY if operation_id in by_id] + [
            entry for entry in entries if entry["operationId"] not in _CATALOG_SEARCH_PRIORITY
        ]
    entries = [_catalog_search_entry(entry) for entry in entries]
    if limit is None:
        return {"operations": entries, "nextCursor": None}
    page = entries[offset : offset + limit]
    next_cursor = f"cursor:{offset + limit}" if offset + limit < len(entries) else None
    return {"operations": page, "nextCursor": next_cursor}


def describe_operation(operation_id: str) -> dict[str, Any]:
    descriptor = get_operation(operation_id)
    if descriptor is None:
        raise KeyError(operation_id)
    return {"operation": _catalog_entry(descriptor)}


def all_operations() -> tuple[OperationDescriptor, ...]:
    return tuple(OPERATION_CATALOG.values())


def operation_reconciliation_matrix() -> dict[str, Any]:
    """Return the exact catalog-derived mutation and publication policy matrix."""

    mutations = sorted(
        (descriptor for descriptor in all_operations() if descriptor.kind == "mutation"),
        key=lambda item: item.operation_id,
    )
    rows = [
        {
            "operationId": descriptor.operation_id,
            "kind": descriptor.kind,
            "strategy": descriptor.reconciliation,
            "readAfterWrite": descriptor.reconciliation == "read_after_write",
            "safeReplay": descriptor.reconciliation == "safe_idempotent_replay",
            "outcomeUnknownEscalation": descriptor.reconciliation == "outcome_unknown_escalation",
        }
        for descriptor in mutations
    ]
    expected_ids = {descriptor.operation_id for descriptor in mutations}
    actual_ids = {row["operationId"] for row in rows}
    if actual_ids != expected_ids or any(not row["strategy"] for row in rows):
        raise RuntimeError("Operation reconciliation matrix is not complete")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "policyVersion": RECONCILIATION_POLICY_VERSION,
        "operations": rows,
        "publications": [dict(row) for row in PUBLICATION_RECONCILIATION_MATRIX],
    }
