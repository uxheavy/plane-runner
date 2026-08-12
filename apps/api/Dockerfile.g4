ARG BASE_API_IMAGE=plane-g3-external-client-api-tests:prepared
FROM ${BASE_API_IMAGE}

WORKDIR /workspace/apps/api
COPY . /workspace/apps/api

RUN mkdir -p /workspace/apps/api/plane/logs /workspace/apps/api/plane/static-assets/collected-static

ARG PLANE_API_SOURCE_REVISION
ARG PLANE_API_IMAGE_TAG
LABEL org.uxheavy.plane.api.artifact="plane-agent-api-g4" \
      org.uxheavy.plane.api.contract="plane.operation/v1" \
      org.uxheavy.plane.api.source.revision="${PLANE_API_SOURCE_REVISION}" \
      org.uxheavy.plane.api.image.tag="${PLANE_API_IMAGE_TAG}"

# The prepared base image installs dependencies in its development entrypoint.
# The bound artifact is already prepared; verifier and live invocations must
# execute its copied source without a runtime install or source replacement.
ENTRYPOINT ["/bin/sh", "-c", "exec \"$@\"", "--"]
