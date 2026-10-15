# GitLab on VirtualBox — Standalone IaC & CLI Automation

Standalone Infrastructure-as-Code (IaC) templates, Python CLI orchestrator, and Bash scripts to:
1. **Create an Ubuntu 24.04 LTS Linux VM in VirtualBox** using `VBoxManage` CLI and Cloud-Init (`NoCloud` seed ISO).
2. **Provision a GitLab CE Server inside the VM** via Ansible IaC (`iac/ansible/playbook.yml`) or standalone SSH/Bash (`scripts/install-gitlab.sh`), supporting both **Omnibus** (`gitlab-ce`) and **Docker Compose** deployments across `arm64` (Apple Silicon) and `x86_64`.
3. **Display the GitLab connection URL**, SSH Git clone endpoint, and initial `root` credentials.

---

## Repository Structure

```text
.
├── gitlab_vm.py                        # Python CLI orchestrator (reads iac/vm-spec.yaml)
├── iac/
│   ├── vm-spec.yaml                    # Declarative VM & GitLab specification
│   ├── cloud-init/
│   │   ├── meta-data.yaml.tmpl         # Cloud-Init instance metadata template
│   │   └── user-data.yaml.tmpl         # Cloud-Init user-data (SSH keys, swap, packages)
│   ├── ansible/
│   │   ├── ansible.cfg                 # Ansible configuration
│   │   ├── inventory.ini.tmpl          # Dynamic inventory template
│   │   └── playbook.yml                # Idempotent Ansible playbook for GitLab CE
│   └── docker/
│       └── docker-compose.yml.tmpl     # Docker Compose template (when install_method: docker)
└── scripts/
    ├── deploy-all.sh                   # End-to-end: create VM + install GitLab + show URL
    ├── create-vm.sh                    # Step 1: Create Linux VM in VirtualBox via VBoxManage
    ├── install-gitlab.sh               # Step 2: Provision GitLab CE inside the VM
    └── show-url.sh                     # Step 3: Show GitLab connection URL & credentials
```

---

## Prerequisites

- **VirtualBox 7.x+** (`VBoxManage` in `PATH`)
- **`qemu-img`** (`brew install qemu` on macOS or `apt install qemu-utils` on Linux) for cloud image conversion
- **ISO creation tool**: `hdiutil` (macOS built-in), `genisoimage`, `mkisofs`, or `xorriso`
- **Python 3.9+** (optional: `ansible-playbook` for Ansible provisioning; automatically falls back to SSH script if Ansible is not used)

---

## Quick Start

### Option A: Python Orchestrator (`gitlab_vm.py`)

```bash
# Full end-to-end deployment (create VM -> provision GitLab -> show URL)
./gitlab_vm.py up

# Or run each step individually:
./gitlab_vm.py create-vm
./gitlab_vm.py provision
./gitlab_vm.py url
```

Preview all commands without executing (`--dry-run`):
```bash
./gitlab_vm.py --dry-run up
```

### Option B: Standalone Bash Scripts (`scripts/`)

```bash
# 1. Create the Linux VM in VirtualBox using VBoxManage CLI
./scripts/create-vm.sh

# 2. Install and configure GitLab server inside the VM
./scripts/install-gitlab.sh

# 3. Display the GitLab connection URL and login details
./scripts/show-url.sh
```

Or run everything in one command:
```bash
./scripts/deploy-all.sh
```

---

## Configuration (`iac/vm-spec.yaml`)

Edit [`iac/vm-spec.yaml`](iac/vm-spec.yaml) to customize:
- **VM hardware**: `vm.name`, `vm.cpus` (default `4`), `vm.memory_mb` (default `8192`), `vm.disk_size_gb` (default `40`)
- **Networking / Ports**: Host port `8080` -> Guest HTTP `8080`, Host port `2222` -> Guest SSH `22`
- **GitLab settings**: `gitlab.install_method` (`omnibus` or `docker`), `gitlab.external_port`, `gitlab.initial_root_password`

---

## Useful Lifecycle Commands

```bash
./gitlab_vm.py url            # Show formatted connection banner and HTTP readiness
./gitlab_vm.py url --raw      # Print only the GitLab URL (e.g., http://localhost:8080)
./gitlab_vm.py url --json     # Print machine-readable JSON connection info
./gitlab_vm.py ssh            # Open an interactive SSH session into the VM
./gitlab_vm.py stop           # Gracefully stop the VM
./gitlab_vm.py start          # Start the VM headless
./gitlab_vm.py destroy        # Power off and delete the VM and its disk images
```
