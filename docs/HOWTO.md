# How-To Guide

## Contents

- [Set up development environment](#set-up-development-environment)
- [Run the application](#run-the-application)
- [Run tests and dry-run verification](#run-tests-and-dry-run-verification)
- [Configure VM hardware, ports, and GitLab settings](#configure-vm-hardware-ports-and-gitlab-settings)
- [Switch between Omnibus and Docker Compose installation](#switch-between-omnibus-and-docker-compose-installation)
- [Enable a secondary Bridged or Host-Only network adapter](#enable-a-secondary-bridged-or-host-only-network-adapter)
- [Add a custom Ansible task or post-install hook](#add-a-custom-ansible-task-or-post-install-hook)
- [Debug common problems](#debug-common-problems)
- [Manage VM lifecycle (SSH, stop, start, destroy)](#manage-vm-lifecycle-ssh-stop-start-destroy)

---

## Set up development environment

**Prerequisites**:
- Oracle VirtualBox 7.0+ (`VBoxManage` in `PATH`)
- `qemu-img` (`brew install qemu` on macOS, or `sudo apt-get install qemu-utils` on Ubuntu/Debian)
- Python 3.9+ (optional: `pip install pyyaml ansible-core`)
- ISO builder: `hdiutil` (pre-installed on macOS) or `genisoimage` / `mkisofs` / `xorriso` on Linux

```bash
# Clone repository
git clone git@github.com:bsommers/gitlab.git
cd gitlab

# Verify required host binaries are available
which VBoxManage qemu-img python3 curl ssh-keygen

# Verify configuration and preview generated VBoxManage commands
./gitlab_vm.py --dry-run up
# Expected output: Prints ssh-keygen, curl, qemu-img, VBoxManage, and ansible-playbook commands with [OK] status
```

---

## Run the application

### Option 1: End-to-End via Python CLI Orchestrator

```bash
# Create the VirtualBox VM, provision GitLab CE, and display connection URL
./gitlab_vm.py up

# Or execute each stage step-by-step:
./gitlab_vm.py create-vm
./gitlab_vm.py provision
./gitlab_vm.py url
```

### Option 2: Step-by-Step via Standalone Bash Scripts

```bash
# 1. Create and boot the Ubuntu 24.04 VM in VirtualBox
./scripts/create-vm.sh

# 2. Install and configure GitLab CE inside the VM over SSH
./scripts/install-gitlab.sh

# 3. Display the connection URL and root credentials
./scripts/show-url.sh
```

### Confirm GitLab is running

```bash
# Query formatted status banner
./gitlab_vm.py url

# Query raw URL only (for scripts)
./gitlab_vm.py url --raw
# Output: http://localhost:8080

# Query machine-readable JSON status
./gitlab_vm.py url --json
```

Open `http://localhost:8080/users/sign_in` in your browser and sign in with username `root` and password `GitLabRoot!2026` (or the password configured in `iac/vm-spec.yaml`).

---

## Run tests and dry-run verification

```bash
# 1. Compile and syntax-check the Python CLI orchestrator
python3 -m py_compile gitlab_vm.py

# 2. Syntax-check all Bash scripts
bash -n scripts/create-vm.sh scripts/install-gitlab.sh scripts/show-url.sh scripts/deploy-all.sh

# 3. Syntax-check the Ansible IaC playbook
ansible-playbook --syntax-check -i "localhost," iac/ansible/playbook.yml

# 4. Dry-run VM creation and provisioning (zero side effects)
./gitlab_vm.py --dry-run up
./scripts/create-vm.sh --dry-run
./scripts/install-gitlab.sh --dry-run
```

---

## Configure VM hardware, ports, and GitLab settings

Edit `iac/vm-spec.yaml` to adjust CPU cores, RAM, disk size, host ports, or initial root password:

```yaml
# In iac/vm-spec.yaml:
vm:
  name: "gitlab-server"
  cpus: 6                 # Increase vCPUs to 6
  memory_mb: 12288        # Increase RAM to 12 GB
  disk_size_gb: 60        # Increase disk size to 60 GB

network:
  adapter1:
    type: "nat"
    nic_type: "virtio"
    port_forwards:
      ssh:
        protocol: "tcp"
        host_ip: "127.0.0.1"
        host_port: 2222
        guest_port: 22
      http:
        protocol: "tcp"
        host_ip: "0.0.0.0"
        host_port: 9080   # Expose GitLab on host port 9080
        guest_port: 9080

gitlab:
  install_method: "omnibus"
  external_host: "localhost"
  external_protocol: "http"
  external_port: 9080     # Match host_port above
  initial_root_password: "MyCustomRootPassword!2026"
```

When using the standalone Bash scripts directly without `iac/vm-spec.yaml`, pass CLI flags or environment variables:

```bash
./scripts/create-vm.sh --name gitlab-dev --cpus 6 --memory 12288 --disk 60 --http-port 9080
./scripts/install-gitlab.sh --port 9080 --external-url "http://localhost:9080"
```

---

## Switch between Omnibus and Docker Compose installation

Both `gitlab_vm.py` (via Ansible) and `scripts/install-gitlab.sh` support two installation methods:

### Method A: Official Omnibus Package (`omnibus`, default)

Installs `gitlab-ce` directly inside the Ubuntu 24.04 VM via `packages.gitlab.com`:

```yaml
# In iac/vm-spec.yaml:
gitlab:
  install_method: "omnibus"
  edition: "gitlab-ce"
```

### Method B: Docker Compose (`docker`)

Installs `docker.io` and `docker-compose-v2` inside the VM and deploys `/opt/gitlab/docker-compose.yml`:

```yaml
# In iac/vm-spec.yaml:
gitlab:
  install_method: "docker"
  edition: "gitlab-ce"
```

Or via the standalone Bash script:

```bash
./scripts/install-gitlab.sh --method docker
```

---

## Enable a secondary Bridged or Host-Only network adapter

To make the VM directly reachable on a LAN IP in addition to NAT port forwarding, configure `network.adapter2` in `iac/vm-spec.yaml`:

```yaml
# In iac/vm-spec.yaml:
network:
  adapter2:
    type: "bridged"       # or "hostonly"
    interface: "en0"      # Host interface name (check via `VBoxManage list bridgedifs`)
```

---

## Add a custom Ansible task or post-install hook

To extend the guest VM configuration (for example, installing `gitlab-runner` or configuring SMTP settings):

**1. Add a variable to `iac/vm-spec.yaml` and `iac/ansible/inventory.ini.tmpl`**

```ini
# In iac/ansible/inventory.ini.tmpl:
gitlab_smtp_enabled=false
```

**2. Add the task block to `iac/ansible/playbook.yml`**

```yaml
# In iac/ansible/playbook.yml:
    - name: Ensure custom packages are installed
      ansible.builtin.apt:
        name:
          - git
          - htop
        state: present
```

**3. Re-run provisioning against the running VM**

```bash
./gitlab_vm.py provision --provisioner ansible
```

Expected result: Ansible connects over `127.0.0.1:2222`, applies the new task idempotently, and reports `ok` / `changed`.

---

## Debug common problems

### `qemu-img not found in PATH`

**Cause**: `qemu-img` is required to convert the upstream Ubuntu QCOW2 `.img` cloud image into a raw image before `VBoxManage convertfromraw` creates the `.vdi` disk.
**Fix**:
```bash
# macOS
brew install qemu

# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y qemu-utils
```

### `Timed out waiting for SSH on ubuntu@127.0.0.1:2222`

**Cause**: The VM either failed to start, port `2222` is already bound by another process on the host, or `cloud-init` is still running initial package updates.
**Fix**:
```bash
# 1. Check VM state in VirtualBox
VBoxManage showvminfo gitlab-server --machinereadable | grep -E "VMState|Forwarding"

# 2. Check if another process is listening on port 2222
lsof -iTCP:2222 -sTCP:LISTEN

# 3. Inspect guest console or serial log via VirtualBox GUI if stuck in EFI shell
VBoxManage startvm gitlab-server --type separate
```

### GitLab returns `502 Bad Gateway` right after provisioning

**Cause**: Puma and PostgreSQL migrations take 60–120 seconds to warm up after `gitlab-ctl reconfigure` completes.
**Fix**:
```bash
# Check service status inside the VM
./gitlab_vm.py ssh
sudo gitlab-ctl status
sudo gitlab-ctl tail puma

# Re-check readiness from the host
./gitlab_vm.py url
```

### Forgot or need to retrieve the auto-generated `root` password

**Cause**: If `initial_root_password` was left empty or rotated during initial setup, GitLab writes the temporary password to `/etc/gitlab/initial_root_password` (retained for 24 hours).
**Fix**:
```bash
./gitlab_vm.py ssh
sudo cat /etc/gitlab/initial_root_password
```

---

## Manage VM lifecycle (SSH, stop, start, destroy)

```bash
# Open an interactive shell inside the Ubuntu VM
./gitlab_vm.py ssh

# Gracefully stop the VM (sends ACPI power button signal)
./gitlab_vm.py stop

# Start the stopped VM in headless mode
./gitlab_vm.py start

# Completely power off and delete the VM and its VDI/ISO media (keeps cached Ubuntu .img)
./gitlab_vm.py destroy
```
