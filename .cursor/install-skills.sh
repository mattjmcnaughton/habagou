#!/usr/bin/env bash
#
# Vendors the skills declared in .cursor/skillvendor/skills.yaml into the
# directories listed under `targets:` (currently ~/.cursor/skills) using
# skillvendor (https://github.com/mattjmcnaughton/skillvendor).
#
# Designed to run as the `install` step of a Cursor Cloud Agent environment so
# every remote agent boots with the same set of skills. Safe to run repeatedly.
set -euo pipefail

SKILLVENDOR_VERSION="${SKILLVENDOR_VERSION:-v1.1.0}"

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest_src="$repo_dir/.cursor/skillvendor/skills.yaml"
lock_src="$repo_dir/.cursor/skillvendor/skillvendor.lock"

config_dir="${SKILLVENDOR_HOME:-$HOME}/.config/skillvendor"
bin_dir="$HOME/.local/bin"
mkdir -p "$config_dir" "$bin_dir"

# 1. Ensure the skillvendor binary is available (prefer prebuilt release asset;
#    fall back to `go install` when a matching binary is unavailable).
if ! command -v skillvendor >/dev/null 2>&1; then
  os_tag="" arch_tag=""
  case "$(uname -s)" in
    Linux) os_tag="linux" ;;
    Darwin) os_tag="macos" ;;
  esac
  case "$(uname -m)" in
    x86_64 | amd64) arch_tag="x86_64" ;;
    arm64 | aarch64) arch_tag="arm64" ;;
  esac

  if [ -n "$os_tag" ] && [ -n "$arch_tag" ]; then
    asset="skillvendor-${os_tag}-${arch_tag}"
    url="https://github.com/mattjmcnaughton/skillvendor/releases/download/${SKILLVENDOR_VERSION}/${asset}"
    echo "Installing skillvendor ${SKILLVENDOR_VERSION} from ${url}"
    curl -fsSL "$url" -o "$bin_dir/skillvendor"
    chmod +x "$bin_dir/skillvendor"
  elif command -v go >/dev/null 2>&1; then
    echo "No prebuilt asset for this platform; building with go install"
    GOBIN="$bin_dir" go install "github.com/mattjmcnaughton/skillvendor/cmd/skillvendor@${SKILLVENDOR_VERSION}"
  else
    echo "Cannot install skillvendor: no prebuilt asset and no Go toolchain" >&2
    exit 1
  fi
  export PATH="$bin_dir:$PATH"
fi

# 2. Place the committed manifest + lockfile where skillvendor reads them.
cp "$manifest_src" "$config_dir/skills.yaml"
[ -f "$lock_src" ] && cp "$lock_src" "$config_dir/skillvendor.lock"

# 3. Vendor the skills. Without --update this honours the committed lockfile,
#    so installs are reproducible across machines.
skillvendor sync

echo "skillvendor sync complete — skills linked into the configured targets."
