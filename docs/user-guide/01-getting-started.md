# Chapter 01 — Getting Started & Bootstrap Workflow

[← Back to Project README](../../README.md) | [← User Guide Index](README.md) | [Next: Examples & Recipes →](02-examples-and-recipes.md)

## Table of Contents

- [1. Host Prerequisites](#1-host-prerequisites)
- [2. Multi-Scope Installation (`scripts/install.sh`)](#2-multi-scope-installation-scriptsinstallsh)
- [3. Workspace Initialization (`init`)](#3-workspace-initialization-init)
- [4. Environment Preflight (`doctor`)](#4-environment-preflight-doctor)
- [5. First Run (`--dry-run up` → `up` → `url`)](#5-first-run---dry-run-up--up--url)

---

## 1. Host Prerequisites

Before creating a VirtualBox VM, ensure the following tools are installed on your macOS (`arm64` / `x86_64`) or Linux (`x86_64` / `arm64`) workstation:

| Requirement | Required | Purpose | Installation Command |
|-------------|----------|---------|----------------------|
| **VirtualBox 7.0+** (`VBoxManage`) | Yes | Hypervisor CLI for VM creation, VirtIO storage, and NAT port forwarding | macOS: `brew install --cask virtualbox`<br>Ubuntu: `sudo apt-get install -y virtualbox` |
| **`qemu-img`** | Yes | Converts the Ubuntu 24.04 QCOW2 cloud image (`.img`) to raw format prior to `.vdi` creation | macOS: `brew install qemu`<br>Ubuntu: `sudo apt-get install -y qemu-utils` |
| **ISO Builder** (`hdiutil`, `genisoimage`, `mkisofs`, or `xorriso`) | Yes | Packages `cloud-init` metadata and user-data into `seed.iso` (`cidata`) | macOS: Built-in (`hdiutil`)<br>Ubuntu: `sudo apt-get install -y genisoimage xorriso` |
| **Python 3.9+** | Yes | Runs `gitlab_vm.py` orchestrator | macOS: `brew install python`<br>Ubuntu: `sudo apt-get install -y python3` |
| **OpenSSH & `curl`** | Yes | Downloads cloud images, generates Ed25519 keys, and connects to the VM | Pre-installed on macOS and most Linux distributions |
| **Ansible (`ansible-playbook`)** | Optional | Runs `iac/ansible/playbook.yml` (automatically falls back to `scripts/install-gitlab.sh` if absent) | `pip install ansible-core` |

---

## 2. Multi-Scope Installation (`scripts/install.sh`)

You can run `./gitlab_vm.py` directly from a git checkout or install `gitlab-vm` onto your `PATH` using `scripts/install.sh`. Three installation scopes are supported:

| Scope | Flag | Target Binary Path | Data Directory | Privilege |
|-------|------|--------------------|----------------|-----------|
| **User Home (Default)** | `--local` | `${XDG_BIN_HOME:-$HOME/.local/bin}/gitlab-vm` | `${XDG_DATA_HOME:-$HOME/.local/share}/gitlab-vm` | Unprivileged |
| **System Global** | `--global` | `/usr/local/bin/gitlab-vm` | `/usr/local/share/gitlab-vm` | Requires write access / `sudo` |
| **Custom Prefix** | `--prefix DIR` | `DIR/bin/gitlab-vm` | `DIR/share/gitlab-vm` | User-defined (CI, sandboxes) |

```bash
# Option A: Install into user home (~/.local/bin/gitlab-vm)
./scripts/install.sh --local

# Option B: Install into a custom directory prefix
./scripts/install.sh --prefix "$HOME/opt/gitlab-vm"

# Option C: Install system-wide (automatically uses --copy mode)
sudo ./scripts/install.sh --global

# Uninstall cleanly from any scope
./scripts/install.sh --local --uninstall
```

---

## 3. Workspace Initialization (`init`)

Run `init` to ensure a valid declarative VM specification exists at `iac/vm-spec.yaml` (or pass `-c path/to/custom-spec.yaml` to generate a separate configuration file):

```bash
./gitlab_vm.py init
```

Expected output (on `stderr`):

```text
Configuration already exists at iac/vm-spec.yaml (use --force to overwrite).

Next steps:
  1. ./gitlab_vm.py doctor        # verify VirtualBox, qemu-img, and host dependencies
  2. ./gitlab_vm.py --dry-run up  # preview VM creation and GitLab provisioning commands
  3. ./gitlab_vm.py up            # create the Linux VM, provision GitLab, and show URL
```

To generate a fresh custom spec file:

```bash
./gitlab_vm.py -c iac/dev-spec.yaml init
```

---

## 4. Environment Preflight (`doctor`)

Run `doctor` to validate every required host binary and specification file before downloading images or creating VMs:

```bash
./gitlab_vm.py doctor
```

Expected output:

```text
GitLab VirtualBox IaC — Environment Preflight (doctor)
================================================================
  [OK]   VBoxManage: /usr/local/bin/VBoxManage
  [OK]   qemu-img: /opt/homebrew/bin/qemu-img
  [OK]   iso-builder (hdiutil/genisoimage/mkisofs/xorriso): /usr/bin/hdiutil
  [OK]   curl: /usr/bin/curl
  [OK]   ssh: /usr/bin/ssh
  [OK]   ssh-keygen: /usr/bin/ssh-keygen
  [OK]   ansible-playbook (optional; falls back to SSH script): ~/.local/bin/ansible-playbook
  [OK]   spec (iac/vm-spec.yaml): iac/vm-spec.yaml
================================================================
Environment verified: all required tools and specifications are ready.
```

For automated CI pipelines, pass `--json`:

```bash
./gitlab_vm.py doctor --json
```

---

## 5. First Run (`--dry-run up` → `up` → `url`)

1. **Preview all hypervisor and provisioning commands (`--dry-run`)**:
   ```bash
   ./gitlab_vm.py --dry-run up
   ```
2. **Execute the full deployment**:
   ```bash
   ./gitlab_vm.py up
   ```
3. **Verify the connection URL and credentials**:
   ```bash
   ./gitlab_vm.py url
   ```
4. **Sign in to GitLab**:
   Open `http://localhost:8080/users/sign_in` in your browser and log in with username `root` and password `GitLabRoot!2026` (or the password configured in `iac/vm-spec.yaml`).
