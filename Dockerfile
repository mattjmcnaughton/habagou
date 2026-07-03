FROM node:22-bookworm-slim AS frontend-deps

WORKDIR /app/src/habagou/web/frontend
RUN corepack enable && corepack prepare pnpm@11.0.4 --activate
COPY src/habagou/web/frontend/package.json \
  src/habagou/web/frontend/pnpm-lock.yaml \
  src/habagou/web/frontend/pnpm-workspace.yaml \
  src/habagou/web/frontend/.npmrc ./
RUN pnpm install --frozen-lockfile

FROM frontend-deps AS frontend-build

COPY src/habagou/web/frontend ./
RUN pnpm run build

FROM python:3.12-slim AS backend-build

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY src ./src
COPY --from=frontend-build /app/src/habagou/web/frontend/dist ./src/habagou/web/frontend/dist
RUN uv sync --no-dev --frozen

FROM python:3.12-slim AS production

LABEL org.opencontainers.image.title="habagou"
LABEL org.opencontainers.image.description="Learn to write Chinese characters by tracing them, stroke by stroke."

RUN groupadd --gid 1000 app \
  && useradd --uid 1000 --gid 1000 --create-home app \
  && mkdir -p /home/app/.cache/habagou \
  && chown -R app:app /home/app/.cache

WORKDIR /app
COPY --from=backend-build --chown=app:app /app /app
COPY --chown=app:app docker/entrypoint.sh /app/docker/entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}" \
  XDG_CACHE_HOME="/home/app/.cache" \
  HOST="0.0.0.0" \
  PORT="8000"

USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "habagou.app:app", "--host", "0.0.0.0", "--port", "8000"]
