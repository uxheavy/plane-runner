# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Gateway-owned attachment semantics shared by all five MCP attachment tools.

The external MCP server owns the public tool wrappers.  This module owns the
Plane-side semantic seam: object scope, existing attachment serialization and
storage signing, bounded public-source fetches, and safe content-read metadata.
It deliberately returns JSON-safe data so the normal gateway idempotency and
append-only audit path remains the only mutation boundary.
"""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import uuid4

import requests
from django.conf import settings
from django.utils import timezone
from plane.api.serializers import IssueAttachmentSerializer
from plane.app.permissions import ROLE
from plane.db.models import FileAsset, Issue, ProjectMember, Workspace
from plane.settings.storage import S3Storage
from plane.utils.path_validator import sanitize_filename

from .attachment_policy import (
    MAX_UPLOAD_BYTES,
    AttachmentFailure,
    assert_public_url,
    read_limit,
)

HTTP_TIMEOUT = (10, 60)


@dataclass(frozen=True)
class AttachmentReadAuthorization:
    """The bounded metadata needed by the outer SDK read adapter."""

    attachment_id: str
    name: str
    content_type: str
    download_url: str
    max_bytes: int

    def as_result(self) -> dict[str, object]:
        return {
            "attachment_id": self.attachment_id,
            "name": self.name,
            "content_type": self.content_type,
            "download_url": self.download_url,
            "max_bytes": self.max_bytes,
        }


def _asset_projection(asset: FileAsset) -> dict[str, object]:
    """Preserve the SDK model shape plus the donor's convenience fields."""

    data = dict(IssueAttachmentSerializer(asset).data)
    attributes = data.get("attributes") or {}
    if isinstance(attributes, dict):
        data["name"] = attributes.get("name")
        data["size"] = attributes.get("size") or data.get("size")
        data["content_type"] = attributes.get("type")
    return data


def _attachment_queryset(workspace: Workspace, project_id: str, issue_id: str):
    return FileAsset.objects.filter(
        workspace_id=workspace.id,
        project_id=project_id,
        issue_id=issue_id,
        entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
        is_uploaded=True,
        is_deleted=False,
    )


def _find_attachment(
    workspace: Workspace,
    project_id: str,
    issue_id: str,
    attachment_id: str,
) -> FileAsset:
    asset = _attachment_queryset(workspace, project_id, issue_id).filter(pk=attachment_id).first()
    if asset is None:
        raise AttachmentFailure("ATTACHMENT_NOT_FOUND", 404)
    return asset


def _user_has_issue_permission(user_id, project_id, issue=None, allowed_roles=None, allow_creator=True):
    """Apply Plane's issue membership rule without importing an endpoint module."""

    if allow_creator and issue is not None and user_id == issue.created_by_id:
        return True
    queryset = ProjectMember.objects.filter(project_id=project_id, member_id=user_id, is_active=True)
    if allowed_roles is not None:
        queryset = queryset.filter(role__in=allowed_roles)
    return queryset.exists()


def _assert_issue_permission(request, workspace: Workspace, project_id: str, issue_id: str, *, mutation: bool) -> None:
    issue = Issue.objects.filter(workspace_id=workspace.id, project_id=project_id, pk=issue_id).first()
    if issue is None:
        raise AttachmentFailure("OPERATION_REJECTED", 400)
    allowed = _user_has_issue_permission(
        request.user.id,
        project_id=project_id,
        issue=issue if mutation else None,
        allowed_roles=[ROLE.ADMIN.value, ROLE.MEMBER.value, ROLE.GUEST.value],
        allow_creator=mutation,
    )
    if not allowed:
        raise AttachmentFailure("NOT_AUTHORIZED", 403)


def _fetch_public_source(url: str) -> tuple[bytes, str]:
    """Fetch one public URL without following an unvalidated redirect."""

    assert_public_url(url)
    response = None
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT, stream=True, allow_redirects=False)
        if 300 <= response.status_code < 400:
            raise AttachmentFailure("EXTERNAL_SOURCE_REJECTED", 400)
        response.raise_for_status()
        declared_size = response.headers.get("Content-Length")
        if declared_size and int(declared_size) > MAX_UPLOAD_BYTES:
            raise AttachmentFailure("ATTACHMENT_TOO_LARGE", 400)
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise AttachmentFailure("ATTACHMENT_TOO_LARGE", 400)
            chunks.append(chunk)
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
    except AttachmentFailure:
        raise
    except (TypeError, ValueError, requests.RequestException):
        raise AttachmentFailure("EXTERNAL_SOURCE_REJECTED", 400) from None
    finally:
        if response is not None:
            response.close()
    return b"".join(chunks), content_type


class WorkItemAttachmentService:
    """Use Plane's existing file asset and storage services behind the gateway."""

    def list(self, *, request, workspace: Workspace, project_id: str, issue_id: str) -> dict[str, object]:
        _assert_issue_permission(request, workspace, project_id, issue_id, mutation=False)
        return {
            "attachments": [_asset_projection(asset) for asset in _attachment_queryset(workspace, project_id, issue_id)]
        }

    def download_url(
        self, *, request, workspace: Workspace, project_id: str, issue_id: str, attachment_id: str
    ) -> dict[str, object]:
        _assert_issue_permission(request, workspace, project_id, issue_id, mutation=False)
        asset = _find_attachment(workspace, project_id, issue_id, attachment_id)
        name = (asset.attributes or {}).get("name") or attachment_id
        storage = S3Storage(request=request)
        url = storage.generate_presigned_url(
            object_name=asset.asset.name,
            disposition="attachment",
            filename=name,
        )
        if not url:
            raise AttachmentFailure("UPSTREAM_FAILURE", 503, True)
        return {"download_url": url, "attachment_id": str(asset.id), "name": name}

    def upload_from_url(
        self,
        *,
        request,
        workspace: Workspace,
        project_id: str,
        issue_id: str,
        url: str,
        name: str | None,
    ) -> dict[str, object]:
        _assert_issue_permission(request, workspace, project_id, issue_id, mutation=True)
        content, content_type = _fetch_public_source(url)
        if not content:
            raise AttachmentFailure("VALIDATION_ERROR", 400)
        filename = sanitize_filename(name) if name else None
        if not filename:
            filename = sanitize_filename(os.path.basename(urlparse(url).path.rstrip("/"))) or "attachment"
        if not content_type or content_type == "application/octet-stream":
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if content_type not in settings.ATTACHMENT_MIME_TYPES:
            raise AttachmentFailure("VALIDATION_ERROR", 400)

        asset_key = f"{workspace.id}/{uuid4().hex}-{filename}"
        asset = FileAsset.objects.create(
            attributes={"name": filename, "type": content_type, "size": len(content)},
            asset=asset_key,
            size=len(content),
            workspace_id=workspace.id,
            created_by=request.user,
            issue_id=issue_id,
            project_id=project_id,
            entity_type=FileAsset.EntityTypeContext.ISSUE_ATTACHMENT,
        )
        storage = S3Storage(request=request)
        upload_data = storage.generate_presigned_post(
            object_name=asset_key,
            file_type=content_type,
            file_size=len(content),
        )
        if not upload_data:
            raise AttachmentFailure("UPSTREAM_FAILURE", 503, True)
        try:
            upload_response = requests.post(
                upload_data["url"],
                data=upload_data.get("fields", {}),
                files={"file": (filename, content, content_type)},
                timeout=HTTP_TIMEOUT,
            )
            upload_response.raise_for_status()
        except requests.RequestException:
            try:
                storage.delete_files([asset_key])
            finally:
                raise AttachmentFailure("UPSTREAM_FAILURE", 503, True) from None
        asset.is_uploaded = True
        asset.save(update_fields=["is_uploaded", "updated_at"])
        return {"attachment": _asset_projection(asset)}

    def delete(
        self, *, request, workspace: Workspace, project_id: str, issue_id: str, attachment_id: str
    ) -> dict[str, object]:
        _assert_issue_permission(request, workspace, project_id, issue_id, mutation=True)
        asset = _find_attachment(workspace, project_id, issue_id, attachment_id)
        asset.is_deleted = True
        asset.deleted_at = timezone.now()
        asset.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        return {"deleted": True}

    def authorize_read(
        self, *, request, workspace: Workspace, project_id: str, issue_id: str, attachment_id: str
    ) -> dict[str, object]:
        _assert_issue_permission(request, workspace, project_id, issue_id, mutation=False)
        asset = _find_attachment(workspace, project_id, issue_id, attachment_id)
        attributes = asset.attributes or {}
        content_type = attributes.get("type") or "application/octet-stream"
        name = attributes.get("name") or attachment_id
        maximum = read_limit(content_type)
        storage = S3Storage(request=request)
        url = storage.generate_presigned_url(
            object_name=asset.asset.name,
            disposition="inline",
            filename=name,
        )
        if not url:
            raise AttachmentFailure("UPSTREAM_FAILURE", 503, True)
        return AttachmentReadAuthorization(
            attachment_id=str(asset.id),
            name=name,
            content_type=content_type,
            download_url=url,
            max_bytes=maximum,
        ).as_result()
