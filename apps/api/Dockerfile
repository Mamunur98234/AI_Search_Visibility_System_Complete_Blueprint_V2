FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv
RUN useradd --system --uid 10001 --home /srv app
COPY pyproject.toml ./
COPY app ./app
RUN pip install .
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
USER app
EXPOSE 8000
# --proxy-headers: trust X-Forwarded-For only because this container is reachable solely from the web
# container on an internal network, and the edge proxy (Caddy) overwrites X-Forwarded-For with the peer IP.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
