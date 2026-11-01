# Chapter 03 — CLI & Configuration Reference

[← Examples & Recipes](02-examples-and-recipes.md) | [User Guide Index](README.md) | [Next: Troubleshooting & FAQ →](04-troubleshooting-and-faq.md)

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
usage: gitlab_vm.py [-h] [--version] [-c CONFIG] [--dry-run] [-v] [-q]
                    {init,doctor,guide,up,create-vm,provision,url,status,info,ssh,start,stop,destroy} ...
```

### Global Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--version` | — | Print `gitlab_vm.py` version (`0.2.0`) and exit |
| `-c, --config <path>` | `iac/vm-spec.yaml` | Path to declarative VM and GitLab YAML specification |
| `--dry-run` | `false` | Print all `VBoxManage`, `qemu-img`, and provisioning commands without executing them |
| `-v, --verbose` | `false` | Echo every executed subprocess command to stdout |
| `-q, --quiet` | `false` | Suppress informational logs and `Next steps:` onboarding breadcrumbs |
| `-h, --help` | — | Show help message and workflow quickstart epilog |

### Subcommands

| Subcommand | Options | Description |
|------------|---------|-------------|
| `init` | `--force`, `--non-interactive` (`--yes`) | Initialize a starter `iac/vm-spec.yaml` configuration file |
| `doctor` | `--json` | Validate required host tools (`VBoxManage`, `qemu-img`, ISO builder, `curl`, `ssh`, `ssh-keygen`) and spec file |
| `guide` | — | Print the built-in step-by-step lifecycle workflow and reference guide |
| `up` | `--provisioner {auto,ansible,ssh}` | Create the VirtualBox Linux VM, provision GitLab CE, and display the connection URL |
| `create-vm` | `--no-start` | Download the Ubuntu 24.04 cloud image, convert to `.vdi`, build `seed.iso`, and register/boot the VM |
| `provision` | `--provisioner {auto,ansible,ssh}` | Wait for SSH readiness and provision GitLab CE inside the running VM via Ansible or SSH script |
| `url` (`status`, `info`) | `--json`, `--raw` | Inspect live VirtualBox NAT rules, probe GitLab HTTP readiness, and output connection details |
| `ssh` | — | Open an interactive SSH session into the VirtualBox Linux VM |
| `start` | — | Start an existing VirtualBox VM in headless mode (`VBoxManage startvm --type headless`) |
| `stop` | — | Send an ACPI power button shutdown signal (`VBoxManage controlvm acpipowerbutton`) |
| `destroy` | — | Power off and completely delete the VirtualBox VM and its attached disk/ISO media |

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
| `vm.name` | `string` | `"gitlab-server"` | VirtualBox VM name |
| `vm.ostype` | `string` | `"auto"` | `auto` resolves to `Ubuntu24_LTS_arm64` or `Ubuntu24_LTS_64` |
| `vm.cpus` | `int` | `4` | Virtual CPU cores |
| `vm.memory_mb` | `int` | `8192` | Guest RAM in MiB |
| `vm.disk_size_gb` | `int` | `40` | Resized VDI disk capacity in GiB |
| `vm.vram_mb` | `int` | `33` | Video RAM in MiB |
| `vm.firmware` | `string` | `"efi"` | Firmware type (`efi` or `bios`) |
| `vm.rtc_use_utc` | `bool` | `true` | Set hardware clock to UTC |
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
