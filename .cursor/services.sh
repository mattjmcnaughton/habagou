#!/usr/bin/env bash
#
# Cloud Agent `services` terminal. Boots the devenv-managed backing services
# (Postgres + Keycloak) as native processes — no Docker required.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
export PATH="/nix/var/nix/profiles/default/bin:${PATH}"

bash .cursor/ensure-nix-daemon.sh
exec devenv up
