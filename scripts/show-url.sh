#!/usr/bin/env bash
# ==============================================================================
# scripts/show-url.sh
# Inspect the VirtualBox VM and display the GitLab Server connection URL & info.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

exec python3 "${ROOT_DIR}/gitlab_vm.py" url "$@"
