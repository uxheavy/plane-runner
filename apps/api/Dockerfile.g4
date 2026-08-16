ARG BASE_API_IMAGE=plane-g3-external-client-api-tests:prepared
FROM ${BASE_API_IMAGE}

WORKDIR /workspace/apps/api
COPY . /workspace/apps/api
COPY --chown=root:root ./bin/plane-agent-runtime-credential-resolver /usr/local/bin/plane-agent-runtime-credential-resolver
RUN chmod 755 /usr/local/bin/plane-agent-runtime-credential-resolver

# The prepared base keeps its development source under /code. Make the
# copied candidate source authoritative for every Python command in this
# artifact, including processes that do not inherit a working directory.
ENV PYTHONPATH=/workspace/apps/api

ARG PLANE_API_SOURCE_REVISION
ARG PLANE_API_IMAGE_TAG
ARG PLANE_API_CONTRACT=plane.operation/v1
ARG PLANE_TYPESCRIPT_VERSION=5.4.5
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
RUN DJANGO_SETTINGS_MODULE="plane.settings.test" \
    REDIS_URL="redis://127.0.0.1:6379/" \
    PLANE_API_SOURCE_REVISION="${PLANE_API_SOURCE_REVISION}" \
    PLANE_API_IMAGE_TAG="${PLANE_API_IMAGE_TAG}" \
    PLANE_API_CONTRACT="${PLANE_API_CONTRACT}" \
    PLANE_API_MANAGE_SHA256="${PLANE_API_MANAGE_SHA256}" \
    PLANE_API_READBACK_SHA256="${PLANE_API_READBACK_SHA256}" \
    PLANE_API_ADMIN_SHA256="${PLANE_API_ADMIN_SHA256}" \
    PLANE_API_CORRUPTION_TEST_SHA256="${PLANE_API_CORRUPTION_TEST_SHA256}" \
    PLANE_API_PROVIDER_CONFIG_SHA256="${PLANE_API_PROVIDER_CONFIG_SHA256}" \
    python - <<'PY'
import hashlib
import importlib
import os
import re
import stat
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

resolver_source = root / "bin/plane-agent-runtime-credential-resolver"
installed_resolver = Path("/usr/local/bin/plane-agent-runtime-credential-resolver")
if not resolver_source.is_file():
    raise SystemExit("candidate credential resolver source is missing")
try:
    resolver_source_stat = resolver_source.lstat()
    installed_resolver_stat = installed_resolver.lstat()
except FileNotFoundError as exc:
    raise SystemExit("installed credential resolver is missing") from exc
if not stat.S_ISREG(installed_resolver_stat.st_mode):
    raise SystemExit("installed credential resolver is not a regular file")
if stat.S_IMODE(installed_resolver_stat.st_mode) != 0o755:
    raise SystemExit("installed credential resolver mode is not 0755")
if installed_resolver_stat.st_uid != 0 or installed_resolver_stat.st_gid != 0:
    raise SystemExit("installed credential resolver is not owned by root:root")
if not stat.S_ISREG(resolver_source_stat.st_mode):
    raise SystemExit("candidate credential resolver source is not a regular file")
source_sha256 = hashlib.sha256(resolver_source.read_bytes()).hexdigest()
installed_sha256 = hashlib.sha256(installed_resolver.read_bytes()).hexdigest()
if installed_sha256 != source_sha256:
    raise SystemExit("installed credential resolver does not match candidate source")

plane_module = importlib.import_module("plane")
plane_path = Path(plane_module.__file__).resolve()
expected_plane_path = (root / "plane/__init__.py").resolve()
if plane_path != expected_plane_path:
    raise SystemExit(f"Plane API imported from unexpected path: {plane_path}")

credentials_module = importlib.import_module("plane.agent.runtime.credentials")
credentials_path = Path(credentials_module.__file__).resolve()
expected_credentials_path = (root / "plane/agent/runtime/credentials.py").resolve()
if credentials_path != expected_credentials_path:
    raise SystemExit(f"runtime credentials imported from unexpected path: {credentials_path}")

config_module = importlib.import_module("plane.agent.runtime.config")
config_path = Path(config_module.__file__).resolve()
expected_config_path = (root / "plane/agent/runtime/config.py").resolve()
if config_path != expected_config_path:
    raise SystemExit(f"runtime config imported from unexpected path: {config_path}")
if config_module.RUNTIME_PROTOCOL != "plane.agent-runtime/v1":
    raise SystemExit("runtime source sentinel is invalid")
PY
RUN PLANE_TYPESCRIPT_VERSION="${PLANE_TYPESCRIPT_VERSION}" \
    node -e 'const expected = process.env.PLANE_TYPESCRIPT_VERSION; const actual = require("/usr/share/node_modules/typescript/lib/typescript.js").version; if (actual !== expected) { throw new Error(`TypeScript compiler ${actual} does not match ${expected}`); }'
RUN command -v python >/dev/null \
    && command -v pytest >/dev/null \
    && command -v ruff >/dev/null \
    && python -c "import django, psycopg, pytest" \
    && mkdir -p /workspace/apps/api/plane/logs /workspace/apps/api/plane/static-assets/collected-static

LABEL org.uxheavy.plane.api.artifact="plane-agent-api-g4" \
      org.uxheavy.plane.api.contract="${PLANE_API_CONTRACT}" \
      org.uxheavy.plane.api.code-mode.typescript.version="${PLANE_TYPESCRIPT_VERSION}" \
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
