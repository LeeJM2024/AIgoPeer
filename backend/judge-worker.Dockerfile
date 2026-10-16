FROM python:3.13-slim

ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY}
WORKDIR /app
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .
COPY backend/ ./
ENV PYTHONPATH=/app
CMD ["python", "-m", "app.workers.judge_worker"]
