# Purpose

## Problem Statement

Standing up a disposable or local self-hosted GitLab server in VirtualBox traditionally requires downloading a multi-gigabyte Ubuntu installer ISO, clicking through VirtualBox GUI wizards, waiting 20+ minutes for OS installation, manually configuring NAT port-forwarding rules, setting up SSH keys, and troubleshooting GitLab Omnibus memory exhaustion (`gitlab-ctl reconfigure` OOM failures) inside constrained VMs. On Apple Silicon (`arm64`) Macs running VirtualBox 7.1, default x86 storage and NIC settings also fail unless `VirtIO` and `armv8virtual` parameters are explicitly configured.

---

## Solution

`gitlab` provides a self-contained Infrastructure-as-Code (IaC) and CLI automation suite that reduces VirtualBox VM creation, GitLab CE installation, and URL discovery to a single command (`./gitlab_vm.py up` or `./scripts/deploy-all.sh`). By combining official Ubuntu 24.04 cloud images, `NoCloud` cloud-init ISO generation, architecture-aware `VBoxManage` CLI automation, and VM-tuned Ansible/Bash provisioning, it delivers a ready-to-use GitLab instance at `http://localhost:8080` with zero GUI interaction.

---

## Goals

1. **Zero-GUI Reproducibility** — Every hypervisor setting, disk resize, cloud-init user-data script, NAT port-forwarding rule, and `/etc/gitlab/gitlab.rb` directive is defined in code (`iac/vm-spec.yaml`) and executed via CLI tools (`VBoxManage`, `ansible-playbook`, `ssh`).
2. **Cross-Architecture Portability (`arm64` & `x86_64`)** — Automatically detect whether the host is Apple Silicon (`arm64` -> `Ubuntu24_LTS_arm64`) or Intel/AMD (`amd64` -> `Ubuntu24_LTS_64`) and select matching cloud images and VirtualBox `VirtIO` controllers.
3. **Standalone Execution (No External Repo or Vagrant Lock-In)** — Operate directly against `VBoxManage` and standard system utilities (`qemu-img`, `hdiutil`/`mkisofs`, `ssh`) with an automatic fallback from Ansible to pure SSH/Bash (`scripts/install-gitlab.sh`) and a built-in Python YAML parser fallback.
4. **Immediate Connection Visibility** — Provide a dedicated command (`./gitlab_vm.py url` / `./scripts/show-url.sh`) that inspects the live VM state, verifies HTTP readiness, and prints the Web URL, Git SSH clone URL, and initial `root` credentials in human-readable, raw, or JSON format.

## Non-Goals

- **Not a Multi-Node High-Availability Cluster Installer** — This project targets a single VirtualBox VM for local development, CI/CD testing, and evaluation; it does not provision external RDS/PostgreSQL clusters, Redis Sentinel, or Gitaly Praefect nodes.
- **Not a Public Cloud Provisioner** — It does not manage AWS EC2, GCP Compute Engine, or Azure VMs; its hypervisor boundary is strictly local Oracle VirtualBox via `VBoxManage`.
- **Not Dependent on Vagrant** — While Vagrant wraps VirtualBox, Vagrant boxes for `arm64` VirtualBox 7.1 are scarce and frequently break with guest additions mismatches; `gitlab` uses official Ubuntu cloud images directly.

---

## Users and Stakeholders

| Audience | How they interact | What they need from this |
|----------|------------------|--------------------------|
| **DevOps & Infrastructure Engineers** | Edit `iac/vm-spec.yaml` and `iac/ansible/playbook.yml`; run `./gitlab_vm.py up` | A fast, repeatable sandbox to test GitLab upgrades, Omnibus configurations, runners, and webhooks before applying changes to production |
| **Software Developers** | Run `./scripts/deploy-all.sh` and `./scripts/show-url.sh` | A local GitLab server on `http://localhost:8080` to test Git workflows, API integrations, and CI pipelines offline |
| **Platform / Automation Scripts** | Invoke `./gitlab_vm.py url --json` or `./gitlab_vm.py url --raw` | Deterministic exit codes and structured JSON output for automated test harnesses |

---

## Success Criteria

- [x] Creating a Linux VM in VirtualBox succeeds solely via CLI tools (`./gitlab_vm.py create-vm` or `./scripts/create-vm.sh`) on both `arm64` and `x86_64`.
- [x] Provisioning GitLab CE inside the VM succeeds idempotently via Ansible (`iac/ansible/playbook.yml`) or standalone Bash (`scripts/install-gitlab.sh`) using either `omnibus` or `docker`.
- [x] Running `./gitlab_vm.py url` or `./scripts/show-url.sh` outputs the live GitLab Web URL, Git SSH endpoint, VM SSH command, and initial `root` credentials.
- [x] `--dry-run` mode previews all `VBoxManage`, `qemu-img`, ISO creation, and provisioning commands without mutating host state.

---

## Context and History

Built as a standalone repository (`github.com/bsommers/gitlab`) to provide clean, dependency-free VirtualBox + GitLab automation. The implementation specifically addresses VirtualBox 7.1's `armv8virtual` EFI chipset requirements on Apple Silicon alongside traditional `x86_64` hosts by standardizing on `VirtIO` storage controllers and paravirtualized networking.

---

## Relationship to Other Systems

```text
  ╔══════════════════════════════╗      ╔══════════════════════════════╗
  ║ Ubuntu Cloud Images (Noble)  ║      ║ GitLab Package / Docker Repo ║
  ║ cloud-images.ubuntu.com      ║      ║ packages.gitlab.com / Hub    ║
  ╚══════════════╤═══════════════╝      ╚══════════════╤═══════════════╝
                 │                                     │
                 │ 1. QCOW2 .img download              │ 2. gitlab-ce deb / image
                 ▼                                     ▼
          ┌───────────────────────────────────────────────────┐
          │          gitlab (IaC + CLI Orchestrator)          │
          │   iac/vm-spec.yaml + gitlab_vm.py + scripts/*.sh  │
          └─────────────────────────┬─────────────────────────┘
                                    │
                                    │ 3. HTTP :8080 / Git SSH :2222
                                    ▼
                 ╔═════════════════════════════════════╗
                 ║  Developer Browser / Git CLI / CI   ║
                 ╚═════════════════════════════════════╝
```

- **Upstream Artifacts**: Pulls the official Ubuntu 24.04 cloud image (`noble-server-cloudimg-{arm64,amd64}.img`) and official GitLab CE packages (`https://packages.gitlab.com/install/repositories/gitlab/gitlab-ce/script.deb.sh`) or Docker images (`gitlab/gitlab-ce:latest`).
- **Host Hypervisor**: Drives Oracle VirtualBox 7.x through `VBoxManage` subprocess calls.
- **Downstream Consumers**: Exposes GitLab HTTP (`http://localhost:8080`) and SSH (`ssh://git@localhost:2222/...`) to browsers, `git` clients, and local automation tools.

---

## Trade-offs Made

- **Cloud Image + `NoCloud` ISO vs. Standard Installer ISO**: Chose Ubuntu Cloud Images + `qemu-img` conversion over raw installer ISOs because cloud images boot to SSH in under 90 seconds instead of 20+ minutes. Cost: requires `qemu-img` (`brew install qemu` / `apt install qemu-utils`) on the host.
- **NAT Port Forwarding vs. Bridged Networking by Default**: Chose `nat` on `adapter1` with explicit host port forwards (`8080`, `8443`, `2222`, `2224`) over `bridged` networking because bridged mode frequently fails on corporate Wi-Fi interfaces that block promiscuous/multiple MAC addresses. Cost: GitLab is accessed via `localhost:8080` by default unless `adapter2` is enabled.
- **Omnibus vs. Docker Default**: Chose `install_method: omnibus` as the default in `iac/vm-spec.yaml` because official `gitlab-ce` `.deb` packages are published natively for both `amd64` and `arm64` on Ubuntu 24.04, whereas official `gitlab/gitlab-ce` Docker Hub images have historically focused on `amd64`. Cost: Omnibus installs directly into the guest OS filesystem rather than a container, though `install_method: docker` remains selectable via a single YAML line.
