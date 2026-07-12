#!/usr/bin/env bash
#
# Cloud Agent `install` step. Runs once per environment build and is snapshotted.
#
# Warms the devenv shell (materialises Python, Node, pnpm, Postgres, Keycloak,
# uv, just into the Nix store), installs language dependencies, Playwright
# browsers, and vendors agent skills. Idempotent.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
export PATH="/nix/var/nix/profiles/default/bin:${PATH}"

bash .cursor/ensure-nix-daemon.sh

# Build the devenv shell and install dependencies inside it.
devenv shell -- bash -lc '
  set -euo pipefail
  uv sync --dev --frozen
  cd src/habagou/web/frontend
  pnpm install --frozen-lockfile
  pnpm exec playwright install --with-deps chromium
'

# Vendor agent skills into ~/.cursor/skills.
bash .cursor/install-skills.sh
