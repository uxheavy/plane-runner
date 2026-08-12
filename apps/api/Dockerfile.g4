ARG BASE_API_IMAGE=plane-g3-external-client-api-tests:prepared
FROM ${BASE_API_IMAGE}

WORKDIR /workspace/apps/api
COPY . /workspace/apps/api

ARG PLANE_API_SOURCE_REVISION
ARG PLANE_API_IMAGE_TAG
ARG PLANE_API_CONTRACT=plane.operation/v1
ARG PLANE_API_MANAGE_SHA256
ARG PLANE_API_READBACK_SHA256
ARG PLANE_API_ADMIN_SHA256
ARG PLANE_API_CORRUPTION_TEST_SHA256
ARG PLANE_API_PROVIDER_CONFIG_SHA256

# This Dockerfile's canonical context is apps/api. A repository-root context
# would copy the tree below /workspace/apps/api/apps/api and leave the base
# image's stale executable tree in place; reject that shape before exporting an
# artifact. The source hashes are supplied by the same exact checkout used for
# the build and become immutable labels for independent inspection.
RUN PLANE_API_SOURCE_REVISION="${PLANE_API_SOURCE_REVISION}" \
    PLANE_API_IMAGE_TAG="${PLANE_API_IMAGE_TAG}" \
    PLANE_API_CONTRACT="${PLANE_API_CONTRACT}" \
    PLANE_API_MANAGE_SHA256="${PLANE_API_MANAGE_SHA256}" \
    PLANE_API_READBACK_SHA256="${PLANE_API_READBACK_SHA256}" \
    PLANE_API_ADMIN_SHA256="${PLANE_API_ADMIN_SHA256}" \
    PLANE_API_CORRUPTION_TEST_SHA256="${PLANE_API_CORRUPTION_TEST_SHA256}" \
    PLANE_API_PROVIDER_CONFIG_SHA256="${PLANE_API_PROVIDER_CONFIG_SHA256}" \
    python - <<'PY'
import hashlib
import os
import re
from pathlib import Path

root = Path("/workspace/apps/api")
required = {
    "manage.py": os.environ["PLANE_API_MANAGE_SHA256"],
    "plane/agent/readback.py": os.environ["PLANE_API_READBACK_SHA256"],
    "plane/api/views/agent_admin.py": os.environ["PLANE_API_ADMIN_SHA256"],
    "plane/tests/contract/api/test_agent_admin.py": os.environ["PLANE_API_CORRUPTION_TEST_SHA256"],
    "plane/agent/runtime/config.py": os.environ["PLANE_API_PROVIDER_CONFIG_SHA256"],
}
if not (root / "manage.py").is_file() or not (root / "plane").is_dir():
    raise SystemExit("apps/api build context must contain manage.py and plane/")
if (root / "apps/api").exists():
    raise SystemExit("repository-root build context is not accepted")
if not re.fullmatch(r"[0-9a-f]{40}", os.environ["PLANE_API_SOURCE_REVISION"]):
    raise SystemExit("PLANE_API_SOURCE_REVISION must be a full git SHA")
if not os.environ["PLANE_API_IMAGE_TAG"] or os.environ["PLANE_API_CONTRACT"] != "plane.operation/v1":
    raise SystemExit("API artifact tag/contract binding is invalid")
for relative, expected in required.items():
    path = root / relative
    if not path.is_file():
        raise SystemExit(f"required executable source is missing: {relative}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
        raise SystemExit(f"source hash mismatch: {relative}")
PY
RUN command -v python >/dev/null \
    && command -v pytest >/dev/null \
    && command -v ruff >/dev/null \
    && python -c "import django, psycopg, pytest" \
    && mkdir -p /workspace/apps/api/plane/logs /workspace/apps/api/plane/static-assets/collected-static

LABEL org.uxheavy.plane.api.artifact="plane-agent-api-g4" \
      org.uxheavy.plane.api.contract="${PLANE_API_CONTRACT}" \
      org.uxheavy.plane.api.source.revision="${PLANE_API_SOURCE_REVISION}" \
      org.uxheavy.plane.api.image.tag="${PLANE_API_IMAGE_TAG}" \
      org.uxheavy.plane.api.source.manage.sha256="${PLANE_API_MANAGE_SHA256}" \
      org.uxheavy.plane.api.source.readback.sha256="${PLANE_API_READBACK_SHA256}" \
      org.uxheavy.plane.api.source.agent-admin.sha256="${PLANE_API_ADMIN_SHA256}" \
      org.uxheavy.plane.api.source.corruption-test.sha256="${PLANE_API_CORRUPTION_TEST_SHA256}" \
      org.uxheavy.plane.api.source.provider-config.sha256="${PLANE_API_PROVIDER_CONFIG_SHA256}"

# The prepared base image installs dependencies in its development entrypoint.
# The bound artifact is already prepared; verifier and live invocations must
# execute its copied source without a runtime install or source replacement.
ENTRYPOINT ["/bin/sh", "-c", "exec \"$@\"", "--"]
