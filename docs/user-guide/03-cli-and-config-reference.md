# Chapter 03 — CLI & Configuration Reference

[← Back to Project README](../../README.md) | [← Examples & Recipes](02-examples-and-recipes.md) | [User Guide Index](README.md) | [Next: Troubleshooting & FAQ →](04-troubleshooting-and-faq.md)

## Table of Contents

- [1. Python CLI Orchestrator (`gitlab_vm.py`)](#1-python-cli-orchestrator-gitlab_vmpy)
- [2. Multi-Target Installer (`scripts/install.sh`)](#2-multi-target-installer-scriptsinstallsh)
- [3. Standalone Bash Scripts](#3-standalone-bash-scripts)
- [4. Declarative Specification Schema (`iac/vm-spec.yaml`)](#4-declarative-specification-schema-iacvm-specyaml)
- [5. Environment Variables](#5-environment-variables)
- [6. Exit Codes](#6-exit-codes)

---

## 1. Python CLI Orchestrator (`gitlab_vm.py`)

```text
usage: gitlab_vm.py [-h] [--version] [-c CONFIG] [--provider {auto,proxmox,virtualbox}]
                    [--dry-run] [-v] [-q]
                    {init,doctor,guide,up,create-vm,provision,url,status,info,ssh,start,stop,destroy} ...
```

### Global Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--version` | — | Print `gitlab_vm.py` version (`0.2.0`) and exit |
| `-c, --config <path>` | `iac/vm-spec.yaml` | Path to declarative VM and GitLab YAML specification |
| `--provider {auto,proxmox,virtualbox}` | `vm.provider` (`proxmox`) | Override hypervisor provider (`proxmox` REST API or `virtualbox` CLI) |
| `--dry-run` | `false` | Print all Proxmox/VirtualBox and provisioning commands without executing them |
| `-v, --verbose` | `false` | Echo every executed subprocess command to stdout |
| `-q, --quiet` | `false` | Suppress informational logs and `Next steps:` onboarding breadcrumbs |
| `-h, --help` | — | Show help message and workflow quickstart epilog |

### Subcommands

| Subcommand | Options | Description |
|------------|---------|-------------|
| `init` | `--force`, `--non-interactive` (`--yes`) | Initialize a starter `iac/vm-spec.yaml` configuration file |
| `doctor` | `--json` | Validate required host tools, Proxmox API reachability, existing VM protection, and spec file |
| `guide` | — | Print the built-in step-by-step lifecycle workflow and reference guide |
| `up` | `--provisioner {auto,ansible,ssh}`, `--force-provision` | Ensure VM exists (never overwriting existing Proxmox VMs), provision GitLab CE if needed, and display URL |
| `create-vm` | `--no-start` | Create and boot the Linux VM in Proxmox VE or VirtualBox (never overwrites an existing VM) |
| `provision` | `--provisioner {auto,ansible,ssh}` | Wait for SSH readiness and provision GitLab CE inside the running VM via Ansible or SSH script |
| `url` (`status`, `info`) | `--json`, `--raw` | Inspect live Proxmox QEMU Guest Agent IP or VirtualBox NAT rules, probe HTTP readiness, and output connection details |
| `ssh` | — | Open an interactive SSH session into the Linux VM |
| `start` | — | Start an existing Proxmox VE or VirtualBox VM in headless mode |
| `stop` | — | Send an ACPI power button shutdown signal to the VM |
| `destroy` | `--force` | Power off and delete the VM (refuses if `proxmox.protect_existing: true` unless `--force` is passed) |

---

## 2. Multi-Target Installer (`scripts/install.sh`)

```text
Usage: install.sh [scope] [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--local` | Default scope | Install `gitlab-vm` into `${XDG_BIN_HOME:-$HOME/.local/bin}` and `${XDG_DATA_HOME:-$HOME/.local/share}/gitlab-vm` |
| `--global` | — | Install system-wide into `/usr/local/bin/gitlab-vm` and `/usr/local/share/gitlab-vm` (defaults to `--copy`) |
| `--prefix <DIR>` | — | Install into `<DIR>/bin/gitlab-vm` and `<DIR>/share/gitlab-vm` |
| `--copy` | `link` (`copy` for `--global`) | Copy files into the target data directory instead of symlinking |
| `--dry-run` | `false` | Print installation actions without modifying the filesystem |
| `--force` | `false` | Overwrite an existing unmanaged binary at the target path |
| `--uninstall` | `false` | Remove installed binary and data directory for the selected scope |
| `-h, --help` | — | Show usage instructions and examples |

---

## 3. Standalone Bash Scripts

### `scripts/create-vm.sh`

| Flag | Default | Description |
|------|---------|-------------|
| `--name <name>` | `gitlab-server` | VirtualBox VM name |
| `--cpus <count>` | `4` | Number of vCPUs |
| `--memory <mb>` | `8192` | RAM in MiB |
| `--disk <gb>` | `40` | Virtual disk capacity in GiB |
| `--http-port <port>` | `8080` | Host TCP port forwarded to GitLab HTTP |
| `--ssh-port <port>` | `2222` | Host TCP port forwarded to VM SSH port `22` |
| `--dry-run` | `false` | Print commands without executing |
| `-h, --help` | — | Show help message |

### `scripts/install-gitlab.sh`

| Flag | Default | Description |
|------|---------|-------------|
| `--local` | Remote SSH mode | Run directly inside the target Ubuntu VM rather than connecting from the host via SSH |
| `--method <omnibus\|docker>` | `omnibus` | Provisioning backend (`omnibus` APT package or `docker` Compose) |
| `--external-url <url>` | `http://localhost:8080` | External URL configured in `/etc/gitlab/gitlab.rb` |
| `--port <port>` | `8080` | GitLab HTTP listen port (`nginx['listen_port']`) |
| `--ssh-port <port>` | `2222` | Host SSH port forwarded to VM port `22` |
| `--root-password <pw>` | `GitLabRoot!2026` | Initial `root` password (must be at least 8 characters) |
| `--dry-run` | `false` | Print commands without executing |
| `-h, --help` | — | Show help message |

### `scripts/show-url.sh` & `scripts/deploy-all.sh`

- `scripts/show-url.sh [flags]` — Forwards all flags (`--raw`, `--json`, `-c <config>`) to `gitlab_vm.py url`.
- `scripts/deploy-all.sh [flags]` — Forwards all flags (`--dry-run`, `--provisioner`, `-c <config>`) to `gitlab_vm.py up`.

---

## 4. Declarative Specification Schema (`iac/vm-spec.yaml`)

| Key Path | Type | Default | Description |
|----------|------|---------|-------------|
| `vm.name` | `string` | `"gitlab-server"` | VM name on Proxmox VE or VirtualBox |
| `vm.provider` | `string` | `"proxmox"` | Hypervisor provider (`proxmox`, `virtualbox`, or `auto`) |
| `vm.ostype` | `string` | `"auto"` | `auto` resolves to `Ubuntu24_LTS_arm64` or `Ubuntu24_LTS_64` |
| `vm.cpus` | `int` | `4` | Virtual CPU cores |
| `vm.memory_mb` | `int` | `8192` | Guest RAM in MiB |
| `vm.disk_size_gb` | `int` | `40` | Resized disk capacity in GiB |
| `vm.vram_mb` | `int` | `33` | Video RAM in MiB |
| `vm.firmware` | `string` | `"efi"` | Firmware type (`efi` or `bios`) |
| `vm.rtc_use_utc` | `bool` | `true` | Set hardware clock to UTC |
| `proxmox.api_url` | `string` | `"https://192.168.1.62:8006"` | Proxmox VE REST API endpoint |
| `proxmox.node` | `string` | `"pve"` | Target Proxmox VE node name |
| `proxmox.vmid` | `int` | `112` | Target Proxmox VMID |
| `proxmox.template_vmid` | `int` | `9000` | Ubuntu 24.04 Cloud-Init template VMID for new clones |
| `proxmox.storage` | `string` | `"stor3"` | Proxmox storage pool for VM disks |
| `proxmox.bridge` | `string` | `"vmbr0"` | Proxmox network bridge |
| `proxmox.insecure_tls` | `bool` | `true` | Allow self-signed Proxmox VE TLS certificates |
| `proxmox.api_token_env` | `string` | `"PROXMOX_API_TOKEN"` | Environment variable holding `USER@REALM!TOKENID=UUID` |
| `proxmox.api_token_file` | `string` | `".state/proxmox/api_token"` | Local gitignored file holding Proxmox API token |
| `proxmox.protect_existing` | `bool` | `true` | Never overwrite, re-clone, reconfigure, or destroy an existing Proxmox VM |
| `image.release` | `string` | `"24.04"` | Ubuntu release version |
| `image.codename` | `string` | `"noble"` | Ubuntu release codename |
| `image.arch` | `string` | `"auto"` | `auto` resolves to `arm64` or `amd64` |
| `image.base_url` | `string` | `"https://cloud-images.ubuntu.com/noble/current"` | Upstream cloud image mirror URL |
| `network.adapter1.type` | `string` | `"nat"` | Primary network mode |
| `network.adapter1.nic_type` | `string` | `"virtio"` | Paravirtualized VirtIO network adapter |
| `network.adapter1.port_forwards.<rule>` | `object` | `ssh` (`2222->22`), `http` (`8080->8080`), `https` (`8443->8443`), `git_ssh` (`2224->22`) | Host-to-guest NAT port forwarding rules |
| `network.adapter2.type` | `string` | `"none"` | Optional secondary adapter (`none`, `bridged`, or `hostonly`) |
| `network.adapter2.interface` | `string` | `""` | Host network interface name when `adapter2.type` is `bridged` or `hostonly` |
| `auth.ssh_user` | `string` | `"ubuntu"` | Default cloud-init sudo user |
| `auth.ssh_key_path` | `string` | `".state/ssh/id_ed25519"` | Relative path to Ed25519 SSH private key |
| `auth.hostname` | `string` | `"gitlab.local"` | Guest VM hostname and FQDN |
| `gitlab.install_method` | `string` | `"omnibus"` | `omnibus` or `docker` |
| `gitlab.edition` | `string` | `"gitlab-ce"` | `gitlab-ce` or `gitlab-ee` |
| `gitlab.external_host` | `string` | `"localhost"` | Hostname in `external_url` |
| `gitlab.external_protocol` | `string` | `"http"` | Protocol in `external_url` (`http` or `https`) |
| `gitlab.external_port` | `int` | `8080` | Port in `external_url` and `nginx['listen_port']` |
| `gitlab.ssh_port` | `int` | `2222` | Port set in `gitlab_rails['gitlab_shell_ssh_port']` |
| `gitlab.initial_root_password` | `string` | `"GitLabRoot!2026"` | Initial password for `root` user |
| `gitlab.tune_for_vm` | `bool` | `true` | Enable single-VM memory tuning |
| `gitlab.puma_workers` | `int` | `2` | `puma['worker_processes']` in `/etc/gitlab/gitlab.rb` |
| `gitlab.sidekiq_concurrency` | `int` | `10` | `sidekiq['concurrency']` in `/etc/gitlab/gitlab.rb` |
| `gitlab.prometheus_monitoring_enable` | `bool` | `false` | `prometheus_monitoring['enable']` in `/etc/gitlab/gitlab.rb` |

---

## 5. Environment Variables

| Variable | Consumed By | Default | Description |
|----------|-------------|---------|-------------|
| `PROXMOX_API_TOKEN` / `CVM_PROXMOX_TOKEN` | `gitlab_vm.py` | `.state/proxmox/api_token` | Proxmox VE REST API token (`USER@REALM!TOKENID=UUID`) |
| `GITLAB_VM_PROVIDER` / `VM_PROVIDER` | `gitlab_vm.py`, `scripts/create-vm.sh` | `vm.provider` (`proxmox`) | Hypervisor provider override (`proxmox` or `virtualbox`) |
| `PREFIX` | `scripts/install.sh` | — | Custom installation prefix directory |
| `XDG_BIN_HOME` | `scripts/install.sh` | `$HOME/.local/bin` | User binary directory for `--local` scope |
| `XDG_DATA_HOME` | `scripts/install.sh` | `$HOME/.local/share` | User data directory for `--local` scope |
| `VM_NAME` | `scripts/create-vm.sh` | `gitlab-server` | Target VirtualBox VM name |
| `VM_CPUS` | `scripts/create-vm.sh` | `4` | Virtual CPU count |
| `VM_MEMORY_MB` | `scripts/create-vm.sh` | `8192` | VM RAM in MiB |
| `VM_DISK_GB` | `scripts/create-vm.sh` | `40` | VM disk size in GiB |
| `SSH_HOST_PORT` / `SSH_PORT` | `scripts/*.sh` | `2222` | Host port forwarded to guest SSH |
| `HTTP_HOST_PORT` / `GITLAB_EXTERNAL_PORT` | `scripts/*.sh` | `8080` | Host and guest HTTP port for GitLab |
| `HTTPS_HOST_PORT` | `scripts/create-vm.sh` | `8443` | Host port forwarded to guest HTTPS |
| `GIT_SSH_HOST_PORT` | `scripts/create-vm.sh` | `2224` | Host port forwarded to Git SSH |
| `GITLAB_INSTALL_METHOD` | `scripts/install-gitlab.sh` | `omnibus` | `omnibus` or `docker` |
| `GITLAB_EDITION` | `scripts/install-gitlab.sh` | `gitlab-ce` | `gitlab-ce` or `gitlab-ee` |
| `GITLAB_EXTERNAL_URL` | `scripts/install-gitlab.sh` | `http://localhost:8080` | GitLab `external_url` |
| `GITLAB_INITIAL_ROOT_PASSWORD` | `scripts/install-gitlab.sh` | `GitLabRoot!2026` | Initial `root` password |
| `DRY_RUN` | `scripts/*.sh` | `false` | Set to `true` to preview commands without executing |

---

## 6. Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| `0` | Success (command completed, dry-run succeeded, or `doctor` verified all required tools) |
| `1` | Runtime error, missing configuration file, missing required dependency in `doctor`, or subprocess failure |
| `2` | Invalid CLI argument or unknown option |
