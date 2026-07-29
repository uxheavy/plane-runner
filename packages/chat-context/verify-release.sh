#!/usr/bin/env bash

set -euo pipefail

cleanup() {
  docker compose -f docker-compose-test.yml down -v
}

trap cleanup EXIT

node packages/chat-context/scripts/verify-feature-docs.mjs

pnpm --filter @plane/chat-context check:types
pnpm --filter @plane/chat-context check:lint
pnpm --filter @plane/chat-context check:format
pnpm --filter @plane/chat-context test
pnpm --filter @plane/chat-context build
pnpm --filter @plane/chat-context verify:bundle

docker compose -f docker-compose-test.yml run --rm --build api-tests \
  pytest \
  plane/tests/contract/api/test_semantic_context_hydration.py \
  plane/tests/contract/api/test_semantic_context_hydration_maya_dogfood.py \
  plane/tests/contract/api/test_semantic_context_hydration_quinn_dogfood.py \
  plane/tests/contract/api/test_semantic_context_hydration_ravi_dogfood.py \
  plane/tests/contract/app/test_page_version_project_scope_app.py
