#!/usr/bin/env bash
# ==============================================================================
# scripts/deploy-all.sh
# End-to-end launcher: creates the VirtualBox Linux VM, installs GitLab, and
# prints the GitLab connection URL.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

exec python3 "${ROOT_DIR}/gitlab_vm.py" up "$@"
