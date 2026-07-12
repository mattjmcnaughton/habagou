#!/usr/bin/env bash
#
# Cloud Agent `dev` terminal. Waits for the backing services from services.sh,
# bootstraps the database, then runs the backend + frontend dev servers.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
export PATH="/nix/var/nix/profiles/default/bin:${PATH}"

bash .cursor/ensure-nix-daemon.sh

# Wait for Keycloak (Postgres comes up first in `devenv up`) before bootstrapping.
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:12345/realms/habagou/.well-known/openid-configuration >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

exec devenv shell -- bash -lc 'just bootstrap && just dev'
