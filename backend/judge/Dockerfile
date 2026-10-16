FROM python:3.13-slim

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY}
RUN apt-get update \
    && apt-get install --no-install-recommends -y g++ time \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin runner
USER runner
WORKDIR /workspace
