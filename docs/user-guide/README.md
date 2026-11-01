# GitLab on VirtualBox (`gitlab`) — User Guide

[← Back to Project README](../../README.md) | [Documentation Hub](../README.md)

Welcome to the comprehensive User Guide for **GitLab on VirtualBox (`gitlab`)** — the standalone Infrastructure-as-Code (IaC) and CLI toolkit for provisioning an Ubuntu 24.04 LTS VirtualBox VM and deploying a self-hosted GitLab Community Edition (CE) server.

---

## Table of Contents

- [Chapters Overview](#chapters-overview)
- [Getting Started & Bootstrap Workflow](#getting-started--bootstrap-workflow)
- [Examples](#examples)
- [Reference](#reference)
- [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Chapters Overview

| Chapter | File | Topics Covered |
|---------|------|----------------|
| **01. Getting Started** | [01-getting-started.md](01-getting-started.md) | Host prerequisites, multi-scope installation (`--local`, `--global`, `--prefix`), `init → doctor → up` bootstrap workflow |
| **02. Examples & Recipes** | [02-examples-and-recipes.md](02-examples-and-recipes.md) | End-to-end Omnibus & Docker workflows, custom ports/RAM, Bridged LAN networking, extending Ansible |
| **03. CLI & Config Reference** | [03-cli-and-config-reference.md](03-cli-and-config-reference.md) | All CLI subcommands & flags, `iac/vm-spec.yaml` schema, environment variables, and exit codes |
| **04. Troubleshooting & FAQ** | [04-troubleshooting-and-faq.md](04-troubleshooting-and-faq.md) | Diagnostic steps, common error remedies, password recovery, and frequently asked questions |

---

## Getting Started & Bootstrap Workflow

Follow the four-step bootstrap lifecycle (`install → init → doctor → up`):

```bash
# 1. Install the CLI into your user home (~/.local/bin/gitlab-vm)
./scripts/install.sh --local

# 2. Initialize or verify the declarative VM specification (iac/vm-spec.yaml)
./gitlab_vm.py init

# 3. Run the environment preflight check (verifies VBoxManage, qemu-img, ISO tools, SSH)
./gitlab_vm.py doctor

# 4. Preview the execution plan, then deploy the VM and GitLab server
./gitlab_vm.py --dry-run up
./gitlab_vm.py up
```

See [Chapter 01: Getting Started](01-getting-started.md) for `--global` and `--prefix DIR` installation scopes and platform-specific prerequisite installation commands.

---

## Examples

### Basic Usage: Check Connection URL & Readiness

```bash
./gitlab_vm.py url
```

Expected output:

```text
====================================================================
  GITLAB VIRTUALBOX SERVER - CONNECTION DETAILS
====================================================================
  VM Name          : gitlab-server
  Status           : ONLINE (HTTP Ready)
  GitLab Web URL   : http://localhost:8080
  Sign-In URL      : http://localhost:8080/users/sign_in
  Git SSH Clone    : ssh://git@localhost:2222/<namespace>/<project>.git
--------------------------------------------------------------------
  Admin Username   : root
  Initial Password : GitLabRoot!2026
  Retrieve in VM   : sudo cat /etc/gitlab/initial_root_password
--------------------------------------------------------------------
  VM SSH Access    : ssh -i .state/ssh/id_ed25519 -p 2222 ubuntu@127.0.0.1
====================================================================
```

### Scripted URL Extraction

```bash
# Print only the raw HTTP URL for use in scripts or curl
./gitlab_vm.py url --raw
# Output: http://localhost:8080

# Emit structured JSON for CI pipelines
./gitlab_vm.py url --json
```

See [Chapter 02: Examples & Recipes](02-examples-and-recipes.md) for complete recipes including Docker Compose mode, custom port mappings, and secondary network adapters.

---

## Reference

| Tool / File | Purpose | Reference Link |
|-------------|---------|----------------|
| `gitlab_vm.py` | Primary Python CLI orchestrator (`init`, `doctor`, `guide`, `up`, `create-vm`, `provision`, `url`, `ssh`, `start`, `stop`, `destroy`) | [CLI & Config Reference](03-cli-and-config-reference.md#1-python-cli-orchestrator-gitlab_vmpy) |
| `scripts/install.sh` | Multi-scope CLI installer (`--local`, `--global`, `--prefix`, `--copy`, `--uninstall`) | [CLI & Config Reference](03-cli-and-config-reference.md#2-multi-target-installer-scriptsinstallsh) |
| `scripts/create-vm.sh` | Standalone Bash VM builder using `VBoxManage` | [CLI & Config Reference](03-cli-and-config-reference.md#3-standalone-bash-scripts) |
| `scripts/install-gitlab.sh` | Standalone Bash GitLab CE provisioner (SSH or `--local`) | [CLI & Config Reference](03-cli-and-config-reference.md#3-standalone-bash-scripts) |
| `iac/vm-spec.yaml` | Declarative VM hardware, networking, and GitLab configuration | [CLI & Config Reference](03-cli-and-config-reference.md#4-declarative-specification-schema-iacvm-specyaml) |

---

## Troubleshooting & FAQ

If a preflight check fails or the VM cannot be reached:

1. Run `./gitlab_vm.py doctor` to inspect every required binary and its installation remedy.
2. Check VM hypervisor state with `VBoxManage showvminfo gitlab-server --machinereadable | grep -E "VMState|Forwarding"`.
3. Consult [Chapter 04: Troubleshooting & FAQ](04-troubleshooting-and-faq.md) for step-by-step solutions.
