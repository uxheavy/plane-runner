#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

assert_line() {
    local file="$1"
    local expected="$2"

    if ! grep -Fqx "$expected" "$file"; then
        echo "Local development contract mismatch in $file" >&2
        echo "Expected: $expected" >&2
        exit 1
    fi
}

assert_line "apps/api/.env.example" 'AWS_S3_ENDPOINT_URL="http://plane-minio:9000"'
assert_line "apps/api/.env.example" 'USE_MINIO=1'
assert_line "apps/api/.env.example" 'WEB_URL="http://localhost:8080"'
assert_line "apps/api/.env.example" 'APP_BASE_URL="http://localhost:3000"'
assert_line "apps/api/.env.example" 'DJANGO_SETTINGS_MODULE=plane.settings.local'
assert_line "apps/api/.env.example" 'PLANE_AGENT_RUNTIME_ENABLED=0'
assert_line ".env.example" 'PLANE_AGENT_RUNTIME_ENABLED=0'
assert_line ".env.example" 'PLANE_AGENT_RUNTIME_URL="http://agent-runtime:8080"'
assert_line ".env.example" 'PLANE_AGENT_RUNTIME_IMAGE="uxheavy/plane-agent-runtime:hermes-e573a466-g4-ff8cd9c5"'
if [ ! -s ".plane-agent-runtime.secret" ]; then
    echo "Missing generated .plane-agent-runtime.secret; run ./setup.sh first." >&2
    exit 1
fi
assert_line "apps/web/.env.example" 'VITE_API_BASE_URL="http://localhost:8080"'
assert_line "apps/admin/.env.example" 'VITE_API_BASE_URL="http://localhost:8080"'
assert_line "apps/space/.env.example" 'VITE_API_BASE_URL="http://localhost:8080"'
assert_line "apps/live/.env.example" 'API_BASE_URL="http://localhost:8080"'

if [ -f ".env" ]; then
    assert_line ".env" 'AWS_S3_ENDPOINT_URL="http://plane-minio:9000"'
    assert_line ".env" 'USE_MINIO=1'
fi

if [ -f "apps/api/.env" ]; then
    assert_line "apps/api/.env" 'AWS_S3_ENDPOINT_URL="http://plane-minio:9000"'
    assert_line "apps/api/.env" 'USE_MINIO=1'
    assert_line "apps/api/.env" 'WEB_URL="http://localhost:8080"'
    assert_line "apps/api/.env" 'DJANGO_SETTINGS_MODULE=plane.settings.local'
fi

for app in web admin space; do
    if [ -f "apps/$app/.env" ]; then
        assert_line "apps/$app/.env" 'VITE_API_BASE_URL="http://localhost:8080"'
    fi

    if [ -f "apps/$app/.env.local" ] && grep -q '^VITE_API_BASE_URL=' "apps/$app/.env.local"; then
        echo "Remove VITE_API_BASE_URL from apps/$app/.env.local; it overrides the validated .env value." >&2
        exit 1
    fi
done

if [ -f "apps/live/.env" ]; then
    assert_line "apps/live/.env" 'API_BASE_URL="http://localhost:8080"'
fi

assert_line "apps/proxy/Caddyfile.ce" $'\treverse_proxy /api/* api:8000'
assert_line "apps/proxy/Caddyfile.ce" $'\treverse_proxy /{$BUCKET_NAME}/* plane-minio:9000'

docker compose -f docker-compose-local.yml config --quiet
docker compose -f docker-compose-local.yml config --format json | python3 tools/check-local-dev-topology.py --mode ordinary
PLANE_AGENT_RUNTIME_ENABLED=1 docker compose --profile agent -f docker-compose-local.yml config --format json | \
    python3 tools/check-local-dev-topology.py --mode agent

if [ "${1:-}" = "--runtime" ]; then
    curl --fail --silent --show-error --output /dev/null http://127.0.0.1:8080/api/instances/

    docker compose -f docker-compose-local.yml exec -T api python -c '
from uuid import uuid4

import requests

from plane.settings.storage import S3Storage


Request = type("Request", (), {"scheme": "http", "get_host": lambda self: "localhost:8080"})
key = f"local-dev-contract-{uuid4().hex}.txt"
public_storage = S3Storage(request=Request())
internal_storage = S3Storage()

try:
    post = public_storage.generate_presigned_post(key, "text/plain", 4)
    assert post["url"].startswith("http://localhost:8080/uploads")
    internal_proxy_url = post["url"].replace("http://localhost:8080", "http://proxy", 1)
    response = requests.post(
        internal_proxy_url,
        data=post["fields"],
        files={"file": (key, b"test", "text/plain")},
        timeout=10,
    )
    response.raise_for_status()
    metadata = internal_storage.get_object_metadata(key)
    assert metadata and metadata["ContentLength"] == 4
finally:
    internal_storage.s3_client.delete_object(
        Bucket=internal_storage.aws_storage_bucket_name,
        Key=key,
    )
'

    echo "Local proxy upload and worker storage access are valid."
elif [ "$#" -ne 0 ]; then
    echo "Usage: $0 [--runtime]" >&2
    exit 2
fi

echo "Local development environment contract is valid."
