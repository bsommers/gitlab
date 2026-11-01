#!/usr/bin/env bash
# ==============================================================================
# scripts/install.sh
# Multi-target installer for gitlab-vm:
#   --local (default: ~/.local/bin), --global (/usr/local/bin), or --prefix DIR
# Supports symlink (default for --local/--prefix) and --copy (default for --global),
# plus --dry-run, --force, and safe marker-verified --uninstall.
# ==============================================================================
set -euo pipefail

TOOL_NAME="gitlab-vm"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MARKER_FILE=".installed-by-${TOOL_NAME}"

SCOPE="local"
PREFIX="${PREFIX:-}"
MODE=""
DRY_RUN=0
FORCE=0
UNINSTALL=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [scope] [options]

Install scopes (pick one; default is --local):
  --local           Install in user home (\${XDG_BIN_HOME:-\$HOME/.local/bin})
  --global          Install system-wide (/usr/local/bin, defaults to --copy)
  --prefix DIR      Install into custom prefix (DIR/bin, DIR/share/${TOOL_NAME})

Options:
  --copy            Copy files instead of symlinking (default for --global)
  --dry-run         Print actions without modifying the filesystem
  --force           Overwrite existing unmanaged installation
  --uninstall       Remove installed files for the selected scope
  -h, --help        Show this help message

Examples:
  ./scripts/install.sh --local
  ./scripts/install.sh --prefix "\$HOME/opt/${TOOL_NAME}"
  sudo ./scripts/install.sh --global
  ./scripts/install.sh --local --uninstall
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --local) SCOPE="local" ;;
    --global) SCOPE="global" ;;
    --prefix)
      SCOPE="custom"
      PREFIX="${2:?error: --prefix requires a directory argument}"
      shift
      ;;
    --copy) MODE="copy" ;;
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option '$1' (run with --help)" >&2; exit 2 ;;
  esac
  shift
done

[ -n "${PREFIX}" ] && [ "${SCOPE}" = "local" ] && SCOPE="custom"
if [ -z "${MODE}" ]; then
  if [ "${SCOPE}" = "global" ]; then MODE="copy"; else MODE="link"; fi
fi

resolve_abs_dir() {
  local p="$1"
  case "${p}" in
    /*) printf '%s\n' "${p%/}" ;;
    *)  printf '%s/%s\n' "$(pwd)" "${p#./}" | sed 's:/$::' ;;
  esac
}

case "${SCOPE}" in
  local)
    BIN_DIR="$(resolve_abs_dir "${XDG_BIN_HOME:-${HOME}/.local/bin}")"
    SHARE_DIR="$(resolve_abs_dir "${XDG_DATA_HOME:-${HOME}/.local/share}/${TOOL_NAME}")"
    ;;
  global)
    BIN_DIR="/usr/local/bin"
    SHARE_DIR="/usr/local/share/${TOOL_NAME}"
    ;;
  custom)
    ABS_PREFIX="$(resolve_abs_dir "${PREFIX}")"
    BIN_DIR="${ABS_PREFIX}/bin"
    SHARE_DIR="${ABS_PREFIX}/share/${TOOL_NAME}"
    ;;
esac

run() {
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

check_writable() {
  local target_parent="$1"
  while [ ! -e "${target_parent}" ] && [ "${target_parent}" != "/" ]; do
    target_parent="$(dirname "${target_parent}")"
  done
  if [ "${DRY_RUN}" -eq 0 ] && [ ! -w "${target_parent}" ]; then
    echo "error: cannot write to ${target_parent} (use --local, --prefix DIR, or run with sudo for --global)" >&2
    exit 1
  fi
}

TARGET_BIN="${BIN_DIR}/${TOOL_NAME}"

is_managed_target() {
  if [ -L "${TARGET_BIN}" ]; then
    local link_dest
    link_dest="$(readlink "${TARGET_BIN}")"
    if [ "${link_dest}" = "${SHARE_DIR}/gitlab_vm.py" ] || [ "${link_dest}" = "${REPO_ROOT}/gitlab_vm.py" ]; then
      return 0
    fi
  fi
  if [ -f "${SHARE_DIR}/${MARKER_FILE}" ]; then
    return 0
  fi
  return 1
}

if [ "${UNINSTALL}" -eq 1 ]; then
  check_writable "${BIN_DIR}"
  if [ -e "${TARGET_BIN}" ] || [ -L "${TARGET_BIN}" ]; then
    if is_managed_target || [ "${FORCE}" -eq 1 ]; then
      run rm -f "${TARGET_BIN}"
    else
      echo "error: ${TARGET_BIN} was not installed by this script (use --force to remove anyway)" >&2
      exit 1
    fi
  fi
  if [ -d "${SHARE_DIR}" ]; then
    run rm -rf "${SHARE_DIR}"
  fi
  echo "Uninstalled ${TOOL_NAME} from ${BIN_DIR}"
  exit 0
fi

check_writable "${BIN_DIR}"
if { [ -e "${TARGET_BIN}" ] || [ -L "${TARGET_BIN}" ]; } && ! is_managed_target && [ "${FORCE}" -eq 0 ]; then
  echo "error: ${TARGET_BIN} already exists and is unmanaged (re-run with --force to overwrite)" >&2
  exit 1
fi

run mkdir -p "${BIN_DIR}" "${SHARE_DIR}"
if [ "${MODE}" = "copy" ]; then
  run install -m 0755 "${REPO_ROOT}/gitlab_vm.py" "${SHARE_DIR}/gitlab_vm.py"
  run cp -R "${REPO_ROOT}/iac" "${SHARE_DIR}/"
  run cp -R "${REPO_ROOT}/scripts" "${SHARE_DIR}/"
  run ln -sf "${SHARE_DIR}/gitlab_vm.py" "${TARGET_BIN}"
else
  run ln -sf "${REPO_ROOT}/gitlab_vm.py" "${TARGET_BIN}"
fi

if [ "${DRY_RUN}" -eq 0 ]; then
  printf 'scope=%s\nmode=%s\n' "${SCOPE}" "${MODE}" > "${SHARE_DIR}/${MARKER_FILE}"
fi

cat <<EOF
Installed ${TOOL_NAME} (${SCOPE} scope, ${MODE} mode):
  binary: ${TARGET_BIN}
  data:   ${SHARE_DIR}
EOF

case ":${PATH:-}:" in
  *":${BIN_DIR}:"*) ;;
  *)
    cat <<EOF

Note: ${BIN_DIR} is not on your PATH. Add it to your shell profile:
  export PATH="${BIN_DIR}:\$PATH"
EOF
    ;;
esac

cat >&2 <<EOF

Next steps:
  1. ${TOOL_NAME} init          # initialize starter iac/vm-spec.yaml config
  2. ${TOOL_NAME} doctor        # verify VirtualBox, qemu-img, and host dependencies
  3. ${TOOL_NAME} --dry-run up  # preview VM creation and GitLab provisioning commands
  4. ${TOOL_NAME} guide         # view the complete workflow guide
EOF
