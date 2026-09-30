ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424
ARG PYTHON_IMAGE=python:3.13.15-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26

FROM ${UV_IMAGE} AS uv-bin

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv-bin /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM builder AS test
RUN uv sync --locked --no-install-project
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/tests ./tests
COPY backend/alembic.ini ./alembic.ini
RUN mkdir -p /app/.pytest_cache \
    && chown -R 10001:10001 /app/.pytest_cache \
    && install -d -o 10001 -g 10001 -m 0700 /var/lib/clientops/private
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
ENTRYPOINT []
CMD ["pytest"]

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --gid 10001 clientops \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin clientops \
    && install -d -o 10001 -g 10001 -m 0700 /var/lib/clientops/private
WORKDIR /app
COPY --from=builder --chown=10001:10001 /app/.venv ./.venv
COPY --chown=10001:10001 backend/app ./app
COPY --chown=10001:10001 backend/migrations ./migrations
COPY --chown=10001:10001 backend/alembic.ini ./alembic.ini
USER 10001:10001
EXPOSE 8000
ENTRYPOINT []
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
