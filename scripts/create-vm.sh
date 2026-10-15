#!/usr/bin/env bash
# ==============================================================================
# scripts/create-vm.sh
# Create an Ubuntu 24.04 LTS Linux VM in VirtualBox using VBoxManage CLI tools.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATE_DIR="${ROOT_DIR}/.state"

VM_NAME="${VM_NAME:-gitlab-server}"
VM_CPUS="${VM_CPUS:-4}"
VM_MEMORY_MB="${VM_MEMORY_MB:-8192}"
VM_DISK_GB="${VM_DISK_GB:-40}"
SSH_USER="${SSH_USER:-ubuntu}"
VM_HOSTNAME="${VM_HOSTNAME:-gitlab.local}"
SSH_HOST_PORT="${SSH_HOST_PORT:-2222}"
HTTP_HOST_PORT="${HTTP_HOST_PORT:-8080}"
HTTPS_HOST_PORT="${HTTPS_HOST_PORT:-8443}"
GIT_SSH_HOST_PORT="${GIT_SSH_HOST_PORT:-2224}"
DRY_RUN="${DRY_RUN:-false}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Create and boot a Linux VM in VirtualBox using VBoxManage CLI tools.

Options:
  --name <name>         VM name (default: ${VM_NAME})
  --cpus <count>        vCPU count (default: ${VM_CPUS})
  --memory <mb>         RAM in MB (default: ${VM_MEMORY_MB})
  --disk <gb>           Disk size in GB (default: ${VM_DISK_GB})
  --http-port <port>    Host HTTP port forwarded to GitLab (default: ${HTTP_HOST_PORT})
  --ssh-port <port>     Host SSH port forwarded to VM port 22 (default: ${SSH_HOST_PORT})
  --dry-run             Print VBoxManage commands without executing
  -h, --help            Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) VM_NAME="$2"; shift 2 ;;
    --cpus) VM_CPUS="$2"; shift 2 ;;
    --memory) VM_MEMORY_MB="$2"; shift 2 ;;
    --disk) VM_DISK_GB="$2"; shift 2 ;;
    --http-port) HTTP_HOST_PORT="$2"; shift 2 ;;
    --ssh-port) SSH_HOST_PORT="$2"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

run_cmd() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "  [dry-run] $*"
  else
    "$@"
  fi
}

# Detect host architecture for VirtualBox 7.x and Ubuntu Cloud Image
HOST_ARCH="$(uname -m)"
if [[ "${HOST_ARCH}" == "arm64" || "${HOST_ARCH}" == "aarch64" ]]; then
  UBUNTU_ARCH="arm64"
  VBOX_OSTYPE="Ubuntu24_LTS_arm64"
else
  UBUNTU_ARCH="amd64"
  VBOX_OSTYPE="Ubuntu24_LTS_64"
fi

command -v VBoxManage >/dev/null 2>&1 || { echo "Error: VBoxManage not found in PATH." >&2; exit 1; }
command -v qemu-img >/dev/null 2>&1 || { echo "Error: qemu-img not found in PATH (brew install qemu / apt install qemu-utils)." >&2; exit 1; }

IMAGES_DIR="${STATE_DIR}/images"
VM_DIR="${STATE_DIR}/vms/${VM_NAME}"
CIDATA_DIR="${STATE_DIR}/cloud-init/${VM_NAME}"
SSH_KEY_PATH="${STATE_DIR}/ssh/id_ed25519"

mkdir -p "${IMAGES_DIR}" "${VM_DIR}" "${CIDATA_DIR}" "$(dirname "${SSH_KEY_PATH}")"

# 1. Generate SSH keypair if not present
if [[ ! -f "${SSH_KEY_PATH}" ]]; then
  echo "[INFO] Generating SSH keypair at ${SSH_KEY_PATH} ..."
  run_cmd ssh-keygen -t ed25519 -N "" -C "gitlab-vbox-iac" -f "${SSH_KEY_PATH}"
fi
if [[ -f "${SSH_KEY_PATH}.pub" ]]; then
  SSH_PUBLIC_KEY="$(cat "${SSH_KEY_PATH}.pub")"
else
  SSH_PUBLIC_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDryRunKey gitlab-vbox-iac"
fi

# 2. Check if VM already exists
if [[ "${DRY_RUN}" != "true" ]] && VBoxManage list vms | grep -q "^\"${VM_NAME}\" "; then
  echo "[INFO] VirtualBox VM '${VM_NAME}' already exists."
  if ! VBoxManage list runningvms | grep -q "^\"${VM_NAME}\" "; then
    echo "[INFO] Starting existing VM '${VM_NAME}' in headless mode..."
    run_cmd VBoxManage startvm "${VM_NAME}" --type headless
  fi
  exit 0
fi

# 3. Download Ubuntu 24.04 LTS Cloud Image
IMG_NAME="noble-server-cloudimg-${UBUNTU_ARCH}.img"
IMG_URL="https://cloud-images.ubuntu.com/noble/current/${IMG_NAME}"
CACHED_IMG="${IMAGES_DIR}/${IMG_NAME}"

if [[ ! -f "${CACHED_IMG}" ]]; then
  echo "[INFO] Downloading Ubuntu 24.04 cloud image (${UBUNTU_ARCH})..."
  run_cmd curl -fL --progress-bar -o "${CACHED_IMG}" "${IMG_URL}"
else
  echo "[INFO] Using cached cloud image: ${CACHED_IMG}"
fi

# 4. Convert cloud image to VirtualBox VDI and resize
RAW_DISK="${VM_DIR}/${VM_NAME}.raw"
VDI_DISK="${VM_DIR}/${VM_NAME}.vdi"
rm -f "${RAW_DISK}" "${VDI_DISK}"

echo "[INFO] Converting cloud image to VDI and resizing to ${VM_DISK_GB} GB..."
run_cmd qemu-img convert -f qcow2 -O raw "${CACHED_IMG}" "${RAW_DISK}"
run_cmd VBoxManage convertfromraw "${RAW_DISK}" "${VDI_DISK}" --format VDI
rm -f "${RAW_DISK}"
run_cmd VBoxManage modifymedium disk "${VDI_DISK}" --resize "$((VM_DISK_GB * 1024))"

# 5. Render Cloud-Init NoCloud seed ISO
cat > "${CIDATA_DIR}/meta-data" <<EOF
instance-id: ${VM_NAME}-01
local-hostname: ${VM_HOSTNAME}
EOF

cat > "${CIDATA_DIR}/user-data" <<EOF
#cloud-config
hostname: ${VM_HOSTNAME}
fqdn: ${VM_HOSTNAME}
manage_etc_hosts: true
users:
  - name: ${SSH_USER}
    groups: [adm, sudo, docker]
    lock_passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - ${SSH_PUBLIC_KEY}
package_update: true
packages:
  - curl
  - ca-certificates
  - openssh-server
  - apt-transport-https
  - gnupg
  - jq
  - tzdata
  - perl
swap:
  filename: /swapfile
  size: 4294967296
  maxsize: 4294967296
runcmd:
  - systemctl enable --now ssh
EOF

SEED_ISO="${VM_DIR}/seed.iso"
rm -f "${SEED_ISO}"
echo "[INFO] Creating cloud-init seed ISO at ${SEED_ISO} ..."
if command -v hdiutil >/dev/null 2>&1; then
  run_cmd hdiutil makehybrid -o "${SEED_ISO}" "${CIDATA_DIR}" -iso -joliet -default-volume-name cidata
elif command -v genisoimage >/dev/null 2>&1; then
  run_cmd genisoimage -output "${SEED_ISO}" -volid cidata -joliet -rock "${CIDATA_DIR}"
elif command -v mkisofs >/dev/null 2>&1; then
  run_cmd mkisofs -output "${SEED_ISO}" -volid cidata -joliet -rock "${CIDATA_DIR}"
elif command -v xorriso >/dev/null 2>&1; then
  run_cmd xorriso -as mkisofs -output "${SEED_ISO}" -volid cidata -joliet -rock "${CIDATA_DIR}"
else
  echo "Error: No ISO creation tool found (hdiutil, genisoimage, mkisofs, xorriso)." >&2
  exit 1
fi

# 6. Create and configure the VM in VirtualBox
echo "[INFO] Creating VirtualBox VM '${VM_NAME}' (${VBOX_OSTYPE})..."
run_cmd VBoxManage createvm \
  --name "${VM_NAME}" \
  --ostype "${VBOX_OSTYPE}" \
  --register \
  --basefolder "${STATE_DIR}/vms"

run_cmd VBoxManage modifyvm "${VM_NAME}" \
  --cpus "${VM_CPUS}" \
  --memory "${VM_MEMORY_MB}" \
  --vram 33 \
  --firmware efi \
  --rtcuseutc on \
  --graphicscontroller vmsvga \
  --audio-enabled off \
  --nic1 nat \
  --nictype1 virtio \
  --natpf1 "ssh,tcp,127.0.0.1,${SSH_HOST_PORT},,22" \
  --natpf1 "http,tcp,0.0.0.0,${HTTP_HOST_PORT},,${HTTP_HOST_PORT}" \
  --natpf1 "https,tcp,0.0.0.0,${HTTPS_HOST_PORT},,${HTTPS_HOST_PORT}" \
  --natpf1 "git_ssh,tcp,0.0.0.0,${GIT_SSH_HOST_PORT},,22"

run_cmd VBoxManage storagectl "${VM_NAME}" \
  --name "VirtIO" \
  --add virtio \
  --controller VirtIO \
  --portcount 4 \
  --bootable on

run_cmd VBoxManage storageattach "${VM_NAME}" \
  --storagectl "VirtIO" \
  --port 0 \
  --device 0 \
  --type hdd \
  --medium "${VDI_DISK}"

run_cmd VBoxManage storageattach "${VM_NAME}" \
  --storagectl "VirtIO" \
  --port 1 \
  --device 0 \
  --type dvddrive \
  --medium "${SEED_ISO}"

echo "[INFO] Starting VM '${VM_NAME}' in headless mode..."
run_cmd VBoxManage startvm "${VM_NAME}" --type headless
echo "[OK] VM '${VM_NAME}' created and started."
