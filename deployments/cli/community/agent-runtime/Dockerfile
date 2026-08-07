# Dedicated Plane Agent runtime image.  The Hermes source is staged by
# tools/build-agent-runtime-image.py from a clean uxheavy checkout at the
# exact commit below; no application source is mounted at runtime.
ARG HERMES_COMMIT
ARG PLANE_REVISION
FROM company-runner-upstream-runtime:a8e53b6ac7b8@sha256:4c0d9f4dee14a4b2f59bc997baf557066f4394c4adcb285905aaa5838ed5ad39 AS runtime_base

FROM scratch
ARG HERMES_COMMIT
ARG PLANE_REVISION
COPY --from=runtime_base / /
WORKDIR /opt/hermes
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONPATH=/opt:/opt/hermes

# The build context contains a git archive of Hermes and the Plane-owned
# runtime transport package only.  The runtime service has no Plane source
# checkout, host credentials, or source bind mount at execution time.
COPY hermes/ /opt/hermes/
COPY plane_runtime_service/ /opt/plane/agent/runtime/
# The pinned Hermes G1 image intentionally uses this canonical no-op module
# instead of python-dotenv so the real run_agent source remains importable
# without ambient environment credential loading.
COPY hermes/plane_runtime/g1_runtime_image/dotenv/ /opt/hermes/dotenv/

LABEL org.opencontainers.image.title="Plane Agent runtime" \
      org.opencontainers.image.source="https://github.com/uxheavy/hermes-agent" \
      org.opencontainers.image.revision="$HERMES_COMMIT" \
      org.uxheavy.plane.hermes.commit="$HERMES_COMMIT" \
      org.uxheavy.plane.hermes.remote="https://github.com/uxheavy/hermes-agent.git" \
      org.uxheavy.plane.runtime.revision="$PLANE_REVISION" \
      org.uxheavy.plane.runtime.contract="plane.agent-runtime/v1"

ENTRYPOINT ["python3", "-m", "plane_runtime.g1_runtime_image.bootstrap", "--once", "--g1-production"]
