# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.2.0] - 2026-11-01

### Added
- Multi-target CLI installer (`scripts/install.sh`) supporting `--local` (`~/.local/bin`), `--global` (`/usr/local/bin`), and `--prefix DIR` scopes, `--copy` mode, `--dry-run`, `--force`, and marker-verified `--uninstall`.
- Onboarding subcommands in `gitlab_vm.py`:
  - `init` (`--force`, `--non-interactive`) to bootstrap starter `iac/vm-spec.yaml` specifications.
  - `doctor` (`--json`) to preflight `VBoxManage`, `qemu-img`, ISO builders (`hdiutil`/`genisoimage`/`mkisofs`/`xorriso`), `curl`, `ssh`, `ssh-keygen`, and `ansible-playbook` with actionable one-line remedies.
  - `guide` subcommand and `--help` workflow epilog for offline CLI lifecycle reference.
- Progressive `Next steps:` breadcrumbs emitted to `stderr` (via `print_next_steps()`) and suppressed under `--quiet`, `--json`, and `--raw` modes.
- Comprehensive 4-chapter User Guide under `docs/user-guide/`:
  - `docs/user-guide/README.md` — User Guide entry point and navigation table.
  - `docs/user-guide/01-getting-started.md` — Prerequisites, multi-scope installation, and `init → doctor → up` bootstrap workflow.
  - `docs/user-guide/02-examples-and-recipes.md` — Copy-pasteable recipes for Omnibus, Docker Compose, custom ports/RAM, Bridged LAN networking, and CI scripting.
  - `docs/user-guide/03-cli-and-config-reference.md` — Complete CLI flags, `iac/vm-spec.yaml` schema, environment variables, and exit codes.
  - `docs/user-guide/04-troubleshooting-and-faq.md` — Error diagnostics, remedies, root password recovery, and FAQ.
- Central Documentation Hub (`docs/README.md`) and AI agent context files (`AGENTS.md`, `CLAUDE.md`).

### Changed
- Updated `docs/ARCHITECTURE.md` with clean boundary principles, onboarding state machine transitions, and ADR-05 (`stderr` onboarding breadcrumbs).
- Synchronized root `README.md`, `docs/HOWTO.md`, `docs/PURPOSE.md`, and `docs/brochure.md` with the `install.sh → init → doctor → up` workflow and bidirectional links to `docs/user-guide/`.

## [v0.1.0] - 2026-10-15

### Added
- Initial standalone Infrastructure-as-Code (`iac/vm-spec.yaml`, `iac/cloud-init/*.tmpl`, `iac/ansible/*`, `iac/docker/docker-compose.yml.tmpl`) for deploying GitLab CE inside an Ubuntu 24.04 LTS VirtualBox VM.
- Python CLI orchestrator (`gitlab_vm.py`) supporting `up`, `create-vm`, `provision`, `url` (`--raw`, `--json`), `ssh`, `start`, `stop`, `destroy`, and `--dry-run`.
- Standalone Bash scripts (`scripts/create-vm.sh`, `scripts/install-gitlab.sh`, `scripts/show-url.sh`, `scripts/deploy-all.sh`) with automatic `arm64` (Apple Silicon) and `x86_64` architecture detection.
- Initial documentation suite (`README.md`, `docs/ARCHITECTURE.md`, `docs/PURPOSE.md`, `docs/HOWTO.md`, `docs/brochure.md`).
