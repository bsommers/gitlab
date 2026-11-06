# Chapter 02 — Examples & Operational Recipes

[← Back to Project README](../../README.md) | [← Getting Started](01-getting-started.md) | [User Guide Index](README.md) | [Next: CLI & Config Reference →](03-cli-and-config-reference.md)

## Table of Contents

- [Recipe 1: Standard Omnibus GitLab Deployment (`gitlab_vm.py`)](#recipe-1-standard-omnibus-gitlab-deployment-gitlab_vmpy)
- [Recipe 2: Pure Bash Workflow Without Ansible (`scripts/*.sh`)](#recipe-2-pure-bash-workflow-without-ansible-scriptssh)
- [Recipe 3: Deploy Containerized GitLab via Docker Compose](#recipe-3-deploy-containerized-gitlab-via-docker-compose)
- [Recipe 4: Customize vCPUs, RAM, Disk Size, and Host Ports](#recipe-4-customize-vcpus-ram-disk-size-and-host-ports)
- [Recipe 5: Expose GitLab on a LAN IP via Bridged Networking](#recipe-5-expose-gitlab-on-a-lan-ip-via-bridged-networking)
- [Recipe 6: Scripted URL & Readiness Polling in CI](#recipe-6-scripted-url--readiness-polling-in-ci)

---

## Recipe 1: Standard Omnibus GitLab Deployment (`gitlab_vm.py`)

Create the Ubuntu 24.04 LTS VM, install the official `gitlab-ce` Omnibus package, and print the connection banner:

```bash
# Run end-to-end
./gitlab_vm.py up

# Or run each phase separately
./gitlab_vm.py create-vm
./gitlab_vm.py provision --provisioner ansible
./gitlab_vm.py url
```

---

## Recipe 2: Pure Bash Workflow Without Ansible (`scripts/*.sh`)

If you prefer standalone shell scripts or do not have Ansible installed on your workstation:

```bash
# 1. Create and boot the Linux VM in VirtualBox
./scripts/create-vm.sh \
  --name gitlab-server \
  --cpus 4 \
  --memory 8192 \
  --disk 40 \
  --http-port 8080 \
  --ssh-port 2222

# 2. Provision GitLab CE inside the VM over SSH
./scripts/install-gitlab.sh \
  --method omnibus \
  --port 8080 \
  --ssh-port 2222 \
  --external-url "http://localhost:8080"

# 3. Show connection details
./scripts/show-url.sh
```

Or invoke the Python orchestrator with `--provisioner ssh`:

```bash
./gitlab_vm.py up --provisioner ssh
```

---

## Recipe 3: Deploy Containerized GitLab via Docker Compose

To run GitLab inside a Docker container (`/opt/gitlab/docker-compose.yml`) inside the Ubuntu VM rather than installing the Omnibus `.deb` package directly onto the guest OS:

**Option A — Via `iac/vm-spec.yaml`:**

```yaml
gitlab:
  install_method: "docker"
  edition: "gitlab-ce"
```

Then run:

```bash
./gitlab_vm.py provision
```

**Option B — Via `scripts/install-gitlab.sh`:**

```bash
./scripts/install-gitlab.sh --method docker
```

---

## Recipe 4: Customize vCPUs, RAM, Disk Size, and Host Ports

If port `8080` is already in use on your host machine, create a custom specification file and map GitLab to port `9080`:

```bash
# 1. Initialize a custom spec file
./gitlab_vm.py -c iac/custom-spec.yaml init

# 2. Update host_port and external_port to 9080 in iac/custom-spec.yaml
python3 -c '
from pathlib import Path
p = Path("iac/custom-spec.yaml")
text = p.read_text().replace("8080", "9080").replace("cpus: 4", "cpus: 6").replace("memory_mb: 8192", "memory_mb: 12288")
p.write_text(text)
'

# 3. Preview and deploy using the custom spec
./gitlab_vm.py -c iac/custom-spec.yaml --dry-run up
./gitlab_vm.py -c iac/custom-spec.yaml up
```

---

## Recipe 5: Expose GitLab on a LAN IP via Bridged Networking

By default, `adapter1` uses VirtualBox NAT port forwarding (`localhost:8080`). To attach a secondary Bridged network adapter so other machines on your LAN can reach the VM:

1. List available host network interfaces in VirtualBox:
   ```bash
   VBoxManage list bridgedifs | grep -E "^Name:"
   ```
2. Configure `network.adapter2` in `iac/vm-spec.yaml`:
   ```yaml
   network:
     adapter2:
       type: "bridged"
       interface: "en0"
   ```
3. Recreate or update the VM and set `gitlab.external_host` to the VM's LAN IP or hostname.

---

## Recipe 6: Scripted URL & Readiness Polling in CI

Use `--json` and `--raw` output modes to integrate with automated test suites (notice that `stdout` contains only pure JSON or the URL, never onboarding hints):

```bash
# Extract the Web URL and HTTP readiness state
GITLAB_URL="$(./gitlab_vm.py url --raw)"
IS_READY="$(./gitlab_vm.py url --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["http_ready"])')"

echo "URL=${GITLAB_URL} READY=${IS_READY}"
```
