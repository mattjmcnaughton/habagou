#!/usr/bin/env bash
#
# Ensure the (Determinate) Nix daemon is running.
#
# Dockerfile.dev installs Nix with `--init none`, so no service manager starts
# the daemon. Every entrypoint that shells into Nix/devenv sources this first.
# Idempotent: a no-op when the daemon is already up.
set -euo pipefail

export PATH="/nix/var/nix/profiles/default/bin:${PATH}"
socket="/nix/var/nix/daemon-socket/socket"

if [ -S "$socket" ] && nix store ping >/dev/null 2>&1; then
  exit 0
fi

as_root="sh -c"
if [ "$(id -u)" -ne 0 ]; then
  as_root="sudo sh -c"
fi

$as_root 'nohup /nix/var/nix/profiles/default/bin/nix-daemon >/tmp/nix-daemon.log 2>&1 &'

for _ in $(seq 1 30); do
  if [ -S "$socket" ] && nix store ping >/dev/null 2>&1; then
    exit 0
  fi
  sleep 1
done

echo "nix daemon failed to start; see /tmp/nix-daemon.log" >&2
exit 1
