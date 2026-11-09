# AGENTS.md — Agent Context & Engineering Guidelines

## Repository Overview

`gitlab` (`github.com/bsommers/gitlab`) is a standalone Infrastructure-as-Code (IaC) and CLI automation toolkit that manages an Ubuntu 24.04 LTS Linux VM in Proxmox VE (via REST API) or Oracle VirtualBox (via `VBoxManage` CLI tools), provisions a GitLab CE server inside the VM (via Ansible or SSH/Bash), and displays the connection URL and credentials.

## Key Entry Points & Files

- `gitlab_vm.py` — Primary Python 3 CLI orchestrator (`init`, `doctor`, `guide`, `up`, `create-vm`, `provision`, `url`, `ssh`, `start`, `stop`, `destroy`, with `--provider {auto,proxmox,virtualbox}`).
- `iac/vm-spec.yaml` — Declarative single source of truth for VM hardware, Proxmox VE / VirtualBox settings, NAT/Bridged networking, SSH auth, and GitLab Omnibus/Docker settings.
- `iac/cloud-init/` — `NoCloud` seed ISO templates (`meta-data.yaml.tmpl`, `user-data.yaml.tmpl`).
- `iac/ansible/` — Idempotent Ansible configuration (`ansible.cfg`, `inventory.ini.tmpl`, `playbook.yml`).
- `iac/docker/docker-compose.yml.tmpl` — Reference Docker Compose stack for `install_method: docker`.
- `scripts/install.sh` — Multi-target CLI installer (`--local`, `--global`, `--prefix DIR`, `--copy`, `--uninstall`).
- `scripts/create-vm.sh` — Standalone Bash VM builder using `VBoxManage` (or delegating `--provider proxmox` to `gitlab_vm.py`).
- `scripts/install-gitlab.sh` — Standalone Bash GitLab installer (remote SSH or `--local` inside guest).
- `scripts/show-url.sh` & `scripts/deploy-all.sh` — CLI convenience wrappers.

## Non-Negotiable Invariants

1. **Standalone Portability:** Zero dependencies on external sibling repositories or Vagrant. `gitlab_vm.py` must work with Python 3.9+ stdlib even when `PyYAML` or `ansible-playbook` are absent (using `_simple_yaml_parse()` and automatic fallback to `scripts/install-gitlab.sh`).
2. **Proxmox Non-Overwrite Protection:** Never overwrite, re-clone, reconfigure, or destroy an existing VM on Proxmox VE (`proxmox_find_existing_vm()` checks both `vm.name` and `proxmox.vmid`; `proxmox.protect_existing: true` is enforced on `create-vm`, `up`, and `destroy`).
3. **Cross-Architecture Support (`arm64` & `x86_64`):** Always preserve `resolve_arch()` auto-detection (`Ubuntu24_LTS_arm64` on Apple Silicon, `Ubuntu24_LTS_64` on `x86_64`) and `VirtIO` storage/network controllers (`--controller VirtIO`, `--nictype1 virtio`).
4. **Clean Stdout for Piped Commands:** Onboarding `Next steps:` breadcrumbs must always print to `sys.stderr` (via `print_next_steps()`) and be suppressed when `--quiet`, `--json`, or `--raw` is passed.
5. **Documentation Synchronization (`keeping-docs-in-sync`):** Any change to CLI subcommands, flags, or `iac/vm-spec.yaml` keys must update `README.md`, `docs/ARCHITECTURE.md`, `docs/HOWTO.md`, and `docs/user-guide/` in the same commit.

## Verification Gate (Run Before Every Commit / Release)

```bash
python3 -m py_compile gitlab_vm.py
bash -n scripts/install.sh scripts/create-vm.sh scripts/install-gitlab.sh scripts/show-url.sh scripts/deploy-all.sh
ansible-playbook --syntax-check -i "localhost," iac/ansible/playbook.yml
./gitlab_vm.py doctor
./gitlab_vm.py --dry-run up
./scripts/create-vm.sh --dry-run
./scripts/install-gitlab.sh --dry-run
```
