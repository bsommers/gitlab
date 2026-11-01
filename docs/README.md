# GitLab on VirtualBox (`gitlab`) — Documentation Hub

[← Back to Project README](../README.md)

Welcome to the documentation suite for **`gitlab`** — the standalone Infrastructure-as-Code (IaC) and CLI automation toolkit for provisioning an Ubuntu 24.04 LTS VirtualBox VM and deploying a self-hosted GitLab Community Edition (CE) server.

---

## Documentation Navigation

```text
docs/
├── README.md                                   # Central navigational index (you are here)
├── PURPOSE.md                                  # Problem statement, goals, non-goals, trade-offs
├── ARCHITECTURE.md                             # Subsystems, clean boundaries, data flows, state machine, ADRs
├── HOWTO.md                                    # Task-oriented operational recipes & debugging
├── brochure.md                                 # Executive product showcase & visual architecture
└── user-guide/                                 # Comprehensive 4-chapter User Manual
    ├── README.md                               # User Guide entry point & quick navigation
    ├── 01-getting-started.md                   # Prerequisites, multi-scope install, init -> doctor -> up
    ├── 02-examples-and-recipes.md              # End-to-end Omnibus, Docker, port mapping & Bridged LAN recipes
    ├── 03-cli-and-config-reference.md          # Complete CLI flags, vm-spec.yaml schema, env vars & exit codes
    └── 04-troubleshooting-and-faq.md           # Diagnostics, error remedies, password recovery & FAQ
```

---

## Recommended Reading Order

1. **New Users & Quick Onboarding:** Start with the [Project README](../README.md) or [User Guide — Chapter 01: Getting Started](user-guide/01-getting-started.md) to run `install.sh → init → doctor → up`.
2. **Executive Overview:** View the [Product Brochure](brochure.md) for the before/after comparison and visual Mermaid architecture diagrams.
3. **Why This Exists:** Read [Purpose & Motivation](PURPOSE.md) for the problem statement, goals, non-goals, and hypervisor trade-offs.
4. **Hands-On Operational Tasks:** Follow the [How-To Guide](HOWTO.md) and [User Guide — Chapter 02: Examples & Recipes](user-guide/02-examples-and-recipes.md).
5. **CLI & Schema Reference:** Consult [User Guide — Chapter 03: CLI & Config Reference](user-guide/03-cli-and-config-reference.md) for every flag, YAML key, environment variable, and exit code.
6. **System Internals & Architecture:** Study [Architecture](ARCHITECTURE.md) for component boundaries, dependency graphs, sequence diagrams, and Architecture Decision Records (ADRs).
