fe_dir := "src/habagou/web/frontend"
dev_image := "habagou-dev"
BASE_URL := env_var_or_default("BASE_URL", "")

_python := "python3"
_env := "eval \"$(python3 scripts/dev_env.py env)\""

# Show this checkout's derived ports and database settings
info:
    {{_python}} scripts/dev_env.py info

# Migrate, import corpus data, and seed the local database
bootstrap:
    {{_python}} scripts/dev_env.py render-keycloak-realm
    {{_env}} && uv run alembic upgrade head
    {{_env}} && uv run python scripts/import_stroke_data.py
    {{_env}} && uv run python scripts/seed.py

# Check formatting (backend + frontend)
fmt: fmt-be fmt-fe

# Check backend formatting
fmt-be:
    uv run ruff format --check .

# Check frontend formatting
fmt-fe:
    cd {{fe_dir}} && pnpm run fmt

# Fix formatting (backend + frontend)
fmt-fix: fmt-fix-be fmt-fix-fe

# Fix backend formatting
fmt-fix-be:
    uv run ruff format .

# Fix frontend formatting
fmt-fix-fe:
    cd {{fe_dir}} && pnpm run fmt-fix

# Check linting (backend + frontend)
lint: lint-be lint-fe

# Check backend linting
lint-be:
    uv run ruff check .

# Check frontend linting
lint-fe:
    cd {{fe_dir}} && pnpm run lint

# Fix linting (backend + frontend)
lint-fix: lint-fix-be lint-fix-fe

# Fix backend linting
lint-fix-be:
    uv run ruff check --fix .

# Fix frontend linting
lint-fix-fe:
    cd {{fe_dir}} && pnpm run lint-fix

# Run type checker (backend + frontend)
typecheck: typecheck-be typecheck-fe

# Run backend type checker
typecheck-be:
    uv run ty check

# Run frontend type checker
typecheck-fe:
    cd {{fe_dir}} && pnpm run typecheck

# Run all tests
test-all: test-unit test-integration test-e2e

# Run unit tests (backend + frontend)
test-unit: test-unit-be test-unit-fe

# Run backend unit tests
test-unit-be:
    uv run pytest tests/unit

# Run frontend unit tests
test-unit-fe:
    cd {{fe_dir}} && pnpm run test

# Run integration tests
test-integration:
    {{_env}} && uv run pytest -n auto tests/integration

# Run e2e tests
test-e2e: test-e2e-be test-e2e-fe

# Run backend e2e traceability anchors
test-e2e-be:
    uv run pytest tests/e2e

# Run frontend browser e2e tests
test-e2e-fe:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .artifacts/test-results
    eval "$({{_python}} scripts/dev_env.py env)"
    curl -fsS "$OIDC_ISSUER/.well-known/openid-configuration" >/dev/null
    cd {{fe_dir}} && pnpm exec playwright test

# Run the mutating browser suite against an ephemeral local instance or BASE_URL
e2e BASE_URL_ARG="":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .artifacts/test-results
    base_url="{{BASE_URL_ARG}}"
    if [[ "$base_url" == BASE_URL=* ]]; then
        base_url="${base_url#BASE_URL=}"
    fi
    if [[ -z "$base_url" ]]; then
        base_url="{{BASE_URL}}"
    fi
    if [ -n "$base_url" ]; then
        cd {{fe_dir}} && BASE_URL="$base_url" pnpm exec playwright test
    else
        eval "$({{_python}} scripts/dev_env.py env)"
        curl -fsS "$OIDC_ISSUER/.well-known/openid-configuration" >/dev/null
        cd {{fe_dir}} && pnpm exec playwright test
    fi

# Run the read-only production smoke suite against BASE_URL
smoke BASE_URL_ARG="":
    #!/usr/bin/env bash
    set -euo pipefail
    base_url="{{BASE_URL_ARG}}"
    if [[ "$base_url" == BASE_URL=* ]]; then
        base_url="${base_url#BASE_URL=}"
    fi
    if [[ -z "$base_url" ]]; then
        base_url="{{BASE_URL}}"
    fi
    if [[ -z "$base_url" ]]; then
        echo "usage: just smoke BASE_URL=http://127.0.0.1:8000" >&2
        exit 2
    fi
    cd {{fe_dir}} && BASE_URL="$base_url" pnpm exec playwright test --grep @smoke

# Run tests that hit external services
test-external:
    uv run pytest -m external

# Export the committed OpenAPI artifact
openapi-export:
    {{_env}} && uv run python scripts/export_openapi.py
    cd {{fe_dir}} && pnpm exec openapi-typescript ../../../../docs/api/openapi-v1.json -o src/lib/api-types.ts

# Check the committed OpenAPI artifact for drift
openapi-check:
    {{_env}} && uv run python scripts/export_openapi.py --check
    cd {{fe_dir}} && pnpm exec openapi-typescript ../../../../docs/api/openapi-v1.json -o src/lib/api-types.ts
    git diff --exit-code src/habagou/web/frontend/src/lib/api-types.ts

# Fast pre-push check (backend + frontend)
gate: gate-be gate-fe

# Backend gate
gate-be: fmt-be lint-be typecheck-be test-unit-be

# Frontend gate
gate-fe: fmt-fe lint-fe typecheck-fe test-unit-fe

# Full check
gate-expensive: gate test-integration test-e2e

# Everything including external
gate-external: gate-expensive test-external

# Start backend dev server
dev-be:
    {{_env}} && uv run uvicorn habagou.app:app --reload --host 127.0.0.1 --port "$HABAGOU_PORT"

# Start frontend dev server
dev-fe:
    {{_env}} && cd {{fe_dir}} && pnpm run dev -- --host 127.0.0.1 --port "$VITE_PORT"

# Start both dev servers
dev:
    #!/usr/bin/env bash
    just dev-be &
    just dev-fe &
    wait

# Start the Compose-managed database for native app development
compose-db-up:
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose up -d db
    until docker compose exec -T db pg_isready -U habagou -d habagou; do
        sleep 1
    done

# Start the production-like Compose stack
compose-up:
    {{_python}} scripts/dev_env.py render-keycloak-realm
    docker compose up --build

# Run the production-like Compose stack until it is healthy, then verify HTTP serving
compose-smoke:
    #!/usr/bin/env bash
    set -euo pipefail
    {{_python}} scripts/dev_env.py render-keycloak-realm
    export HABAGOU_DB_PORT="${HABAGOU_DB_PORT:-15432}"
    docker compose down -v --remove-orphans
    docker compose up --build -d
    cleanup() {
        docker compose down
    }
    trap cleanup EXIT
    for _ in {1..90}; do
        if curl -fsS http://127.0.0.1:8000/readyz >/dev/null; then
            break
        fi
        sleep 2
    done
    curl -fsS http://127.0.0.1:8000/readyz | grep -q '"status":"ready"'
    curl -fsS http://127.0.0.1:8000/ | grep -q '<div id="root">'
    curl -fsS http://127.0.0.1:8000/api/v1/auth/session | grep -q '"authenticated":false'
    curl -sS http://127.0.0.1:8000/api/v1/packs | grep -q '"code":"unauthenticated"'
    docker compose restart app
    for _ in {1..90}; do
        if curl -fsS http://127.0.0.1:8000/readyz >/dev/null; then
            break
        fi
        sleep 2
    done
    curl -fsS http://127.0.0.1:8000/api/v1/auth/session | grep -q '"authenticated":false'

# Stop Compose services
compose-down:
    docker compose down

# Build the Docker-based agent development image
dev-image:
    docker build -f Dockerfile.dev -t {{dev_image}} .

# Enter the Docker-based development shell
dev-shell-docker: dev-image
    #!/usr/bin/env bash
    set -euo pipefail
    eval "$({{_python}} scripts/dev_env.py env)"
    docker run --rm -it \
        -v "$PWD:/workspace" \
        -w /workspace \
        -e HABAGOU_INSTANCE \
        -e HABAGOU_PORT \
        -e VITE_PORT \
        -e DEVENV_STATE=/workspace/.devenv/state \
        -p "$HABAGOU_PORT:$HABAGOU_PORT" \
        -p "$VITE_PORT:$VITE_PORT" \
        {{dev_image}}
