#!/usr/bin/env bash
# ==============================================================================
# scripts/install-gitlab.sh
# Install and configure GitLab Server inside the VirtualBox Linux VM.
# Can be executed from the host (connects via SSH) or inside the VM (--local).
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATE_DIR="${ROOT_DIR}/.state"

RUN_MODE="remote"
GITLAB_INSTALL_METHOD="${GITLAB_INSTALL_METHOD:-omnibus}"
GITLAB_EDITION="${GITLAB_EDITION:-gitlab-ce}"
GITLAB_EXTERNAL_PORT="${GITLAB_EXTERNAL_PORT:-8080}"
GITLAB_EXTERNAL_URL="${GITLAB_EXTERNAL_URL:-http://localhost:${GITLAB_EXTERNAL_PORT}}"
GITLAB_SSH_PORT="${GITLAB_SSH_PORT:-2222}"
GITLAB_INITIAL_ROOT_PASSWORD="${GITLAB_INITIAL_ROOT_PASSWORD:-GitLabRoot!2026}"
GITLAB_PUMA_WORKERS="${GITLAB_PUMA_WORKERS:-2}"
GITLAB_SIDEKIQ_CONCURRENCY="${GITLAB_SIDEKIQ_CONCURRENCY:-10}"
GITLAB_PROMETHEUS_ENABLE="${GITLAB_PROMETHEUS_ENABLE:-false}"

SSH_HOST="${SSH_HOST:-127.0.0.1}"
SSH_PORT="${SSH_PORT:-2222}"
SSH_USER="${SSH_USER:-ubuntu}"
SSH_KEY_PATH="${SSH_KEY_PATH:-${STATE_DIR}/ssh/id_ed25519}"
DRY_RUN="${DRY_RUN:-false}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install and configure GitLab CE inside the VirtualBox Linux VM.

Options:
  --local                  Run directly inside the target Linux VM
  --method <omnibus|docker> Installation method (default: ${GITLAB_INSTALL_METHOD})
  --external-url <url>     GitLab external URL (default: ${GITLAB_EXTERNAL_URL})
  --port <port>            GitLab HTTP listen port (default: ${GITLAB_EXTERNAL_PORT})
  --ssh-port <port>        Host SSH port for VM connection (default: ${SSH_PORT})
  --root-password <pw>     Initial root password (default: ${GITLAB_INITIAL_ROOT_PASSWORD})
  --dry-run                Print commands without executing
  -h, --help               Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local) RUN_MODE="local"; shift ;;
    --method) GITLAB_INSTALL_METHOD="$2"; shift 2 ;;
    --external-url) GITLAB_EXTERNAL_URL="$2"; shift 2 ;;
    --port) GITLAB_EXTERNAL_PORT="$2"; shift 2 ;;
    --ssh-port) SSH_PORT="$2"; GITLAB_SSH_PORT="$2"; shift 2 ;;
    --root-password) GITLAB_INITIAL_ROOT_PASSWORD="$2"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

install_gitlab_local() {
  export DEBIAN_FRONTEND=noninteractive
  echo "[INFO] Waiting for cloud-init to finish..."
  cloud-init status --wait >/dev/null 2>&1 || true

  echo "[INFO] Installing prerequisite packages..."
  apt-get update -qq
  apt-get install -y -qq curl openssh-server ca-certificates tzdata perl jq gnupg apt-transport-https

  if [[ "${GITLAB_INSTALL_METHOD}" == "omnibus" ]]; then
    echo "[INFO] Configuring official GitLab (${GITLAB_EDITION}) APT repository..."
    if [[ ! -f "/etc/apt/sources.list.d/gitlab_${GITLAB_EDITION}.list" ]]; then
      curl -fsSL "https://packages.gitlab.com/install/repositories/gitlab/${GITLAB_EDITION}/script.deb.sh" | bash
    fi

    echo "[INFO] Installing ${GITLAB_EDITION} Omnibus package..."
    EXTERNAL_URL="${GITLAB_EXTERNAL_URL}" \
    GITLAB_ROOT_PASSWORD="${GITLAB_INITIAL_ROOT_PASSWORD}" \
      apt-get install -y "${GITLAB_EDITION}"

    echo "[INFO] Tuning /etc/gitlab/gitlab.rb for VirtualBox VM..."
    sed -i "/# BEGIN GITLAB VM IAC/,/# END GITLAB VM IAC/d" /etc/gitlab/gitlab.rb
    cat >> /etc/gitlab/gitlab.rb <<EOF
# BEGIN GITLAB VM IAC
external_url '${GITLAB_EXTERNAL_URL}'
nginx['listen_port'] = ${GITLAB_EXTERNAL_PORT}
nginx['listen_https'] = false
gitlab_rails['gitlab_shell_ssh_port'] = ${GITLAB_SSH_PORT}
puma['worker_processes'] = ${GITLAB_PUMA_WORKERS}
sidekiq['concurrency'] = ${GITLAB_SIDEKIQ_CONCURRENCY}
prometheus_monitoring['enable'] = ${GITLAB_PROMETHEUS_ENABLE}
# END GITLAB VM IAC
EOF

    echo "[INFO] Running gitlab-ctl reconfigure..."
    gitlab-ctl reconfigure

  elif [[ "${GITLAB_INSTALL_METHOD}" == "docker" ]]; then
    echo "[INFO] Installing Docker and Docker Compose..."
    apt-get install -y -qq docker.io docker-compose-v2
    systemctl enable --now docker
    mkdir -p /opt/gitlab/{config,logs,data}

    cat > /opt/gitlab/docker-compose.yml <<EOF
services:
  gitlab:
    image: gitlab/${GITLAB_EDITION}:latest
    container_name: gitlab
    restart: always
    hostname: '$(hostname -f 2>/dev/null || hostname)'
    environment:
      GITLAB_OMNIBUS_CONFIG: |
        external_url '${GITLAB_EXTERNAL_URL}'
        nginx['listen_port'] = ${GITLAB_EXTERNAL_PORT}
        nginx['listen_https'] = false
        gitlab_rails['gitlab_shell_ssh_port'] = ${GITLAB_SSH_PORT}
        gitlab_rails['initial_root_password'] = '${GITLAB_INITIAL_ROOT_PASSWORD}'
        puma['worker_processes'] = ${GITLAB_PUMA_WORKERS}
        sidekiq['concurrency'] = ${GITLAB_SIDEKIQ_CONCURRENCY}
        prometheus_monitoring['enable'] = ${GITLAB_PROMETHEUS_ENABLE}
    ports:
      - "${GITLAB_EXTERNAL_PORT}:${GITLAB_EXTERNAL_PORT}"
      - "2224:22"
    volumes:
      - /opt/gitlab/config:/etc/gitlab
      - /opt/gitlab/logs:/var/log/gitlab
      - /opt/gitlab/data:/var/opt/gitlab
    shm_size: '256m'
EOF
    (cd /opt/gitlab && docker compose up -d)
  else
    echo "Error: Unsupported GITLAB_INSTALL_METHOD '${GITLAB_INSTALL_METHOD}'" >&2
    exit 1
  fi

  echo "[INFO] Waiting for GitLab HTTP service on port ${GITLAB_EXTERNAL_PORT}..."
  for _ in $(seq 1 60); do
    code="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${GITLAB_EXTERNAL_PORT}/users/sign_in" || true)"
    if [[ "${code}" == "200" || "${code}" == "302" ]]; then
      echo "[OK] GitLab is up and responding (HTTP ${code})."
      return 0
    fi
    sleep 10
  done
  echo "[WARN] GitLab is still initializing; check status with 'sudo gitlab-ctl status'."
}

if [[ "${RUN_MODE}" == "local" ]]; then
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[dry-run] Would install GitLab (${GITLAB_INSTALL_METHOD}) locally inside VM."
    exit 0
  fi
  install_gitlab_local
  exit 0
fi

# Remote execution from Host over SSH
if [[ "${DRY_RUN}" == "true" ]]; then
  echo "  [dry-run] scp -i ${SSH_KEY_PATH} -P ${SSH_PORT} ${BASH_SOURCE[0]} ${SSH_USER}@${SSH_HOST}:/tmp/install-gitlab.sh"
  echo "  [dry-run] ssh -i ${SSH_KEY_PATH} -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} sudo bash /tmp/install-gitlab.sh --local"
  exit 0
fi

echo "[INFO] Waiting for VM SSH on ${SSH_USER}@${SSH_HOST}:${SSH_PORT} ..."
for _ in $(seq 1 60); do
  if ssh -i "${SSH_KEY_PATH}" -p "${SSH_PORT}" \
       -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
       -o ConnectTimeout=5 -o BatchMode=yes \
       "${SSH_USER}@${SSH_HOST}" "echo ready" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo "[INFO] Uploading and executing GitLab installer inside VM..."
scp -i "${SSH_KEY_PATH}" -P "${SSH_PORT}" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "${BASH_SOURCE[0]}" "${SSH_USER}@${SSH_HOST}:/tmp/install-gitlab.sh"

ssh -i "${SSH_KEY_PATH}" -p "${SSH_PORT}" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "${SSH_USER}@${SSH_HOST}" \
  "sudo env \
    GITLAB_INSTALL_METHOD='${GITLAB_INSTALL_METHOD}' \
    GITLAB_EDITION='${GITLAB_EDITION}' \
    GITLAB_EXTERNAL_URL='${GITLAB_EXTERNAL_URL}' \
    GITLAB_EXTERNAL_PORT='${GITLAB_EXTERNAL_PORT}' \
    GITLAB_SSH_PORT='${GITLAB_SSH_PORT}' \
    GITLAB_INITIAL_ROOT_PASSWORD='${GITLAB_INITIAL_ROOT_PASSWORD}' \
    GITLAB_PUMA_WORKERS='${GITLAB_PUMA_WORKERS}' \
    GITLAB_SIDEKIQ_CONCURRENCY='${GITLAB_SIDEKIQ_CONCURRENCY}' \
    GITLAB_PROMETHEUS_ENABLE='${GITLAB_PROMETHEUS_ENABLE}' \
    bash /tmp/install-gitlab.sh --local"
