FROM python:3.13-slim

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app/ ./app/
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir .
COPY backend/ ./
COPY algorithm/ /app/algorithm/
ENV PYTHONPATH=/app
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
