# Chapter 04 — Troubleshooting & FAQ

[← Back to Project README](../../README.md) | [← CLI & Config Reference](03-cli-and-config-reference.md) | [User Guide Index](README.md)

## Table of Contents

- [1. Preflight & Dependency Errors](#1-preflight--dependency-errors)
- [2. VM Boot & SSH Connectivity Issues](#2-vm-boot--ssh-connectivity-issues)
- [3. GitLab Provisioning & HTTP 502 Issues](#3-gitlab-provisioning--http-502-issues)
- [4. Frequently Asked Questions (FAQ)](#4-frequently-asked-questions-faq)

---

## 1. Preflight & Dependency Errors

### Symptom: `error: specification file not found at ...`

**Cause**: `-c / --config` points to a YAML file that does not exist yet.
**Remedy**:
```bash
./gitlab_vm.py init
# Or for a custom path:
./gitlab_vm.py -c iac/custom-spec.yaml init
```

### Symptom: `qemu-img not found in PATH` or `VBoxManage CLI not found in PATH`

**Cause**: Required host virtualization or disk conversion binaries are not installed.
**Remedy**: Run `./gitlab_vm.py doctor` to view the exact missing binary and platform-specific install command:
```bash
./gitlab_vm.py doctor
```

---

## 2. VM Boot & SSH Connectivity Issues

### Symptom: `Timed out waiting for SSH on ubuntu@127.0.0.1:2222`

**Causes**:
1. Another VM or local daemon is already listening on host TCP port `2222`.
2. The VM failed to start or is paused in VirtualBox.
3. First-boot `cloud-init` package metadata refresh is still running over a slow internet connection.

**Diagnostics & Remedy**:
```bash
# 1. Verify VM state and active port-forwarding rules
VBoxManage showvminfo gitlab-server --machinereadable | grep -E "VMState|Forwarding"

# 2. Check for port conflicts on host port 2222
lsof -iTCP:2222 -sTCP:LISTEN

# 3. Re-run provisioning once the VM finishes booting
./gitlab_vm.py provision
```

---

## 3. GitLab Provisioning & HTTP 502 Issues

### Symptom: `http://localhost:8080` returns `502 Bad Gateway` or `unreachable` immediately after install

**Cause**: GitLab's Puma web server and PostgreSQL migrations take 60–120 seconds to finish warming up after `gitlab-ctl reconfigure` exits.
**Diagnostics & Remedy**:
```bash
# 1. Open an SSH session into the VM and inspect GitLab service health
./gitlab_vm.py ssh
sudo gitlab-ctl status
sudo gitlab-ctl tail puma

# 2. Poll readiness from the host
./gitlab_vm.py url
```

### Symptom: Cannot log in with `root` password

**Cause**: GitLab enforces a minimum password length of 8 characters and complexity rules. If `initial_root_password` was omitted or rejected, GitLab generates a random password in `/etc/gitlab/initial_root_password`.
**Remedy**:
```bash
# Read the generated password inside the VM
./gitlab_vm.py ssh
sudo cat /etc/gitlab/initial_root_password

# Or reset the root password via gitlab-rake
sudo gitlab-rake "gitlab:password:reset[root]"
```

---

## 4. Frequently Asked Questions (FAQ)

### Q: Does this work on Apple Silicon (`M1` / `M2` / `M3` / `M4`) Macs?
**Yes.** `gitlab_vm.py` and `scripts/create-vm.sh` automatically detect `arm64`, download `noble-server-cloudimg-arm64.img`, select the `Ubuntu24_LTS_arm64` VirtualBox OS type (`armv8virtual` chipset + EFI firmware), and attach disks and network interfaces via `VirtIO`.

### Q: Do I need Vagrant or Terraform installed?
**No.** All hypervisor interactions use VirtualBox's native `VBoxManage` CLI directly, and guest bootstrapping uses standard `NoCloud` `cloud-init` ISOs.

### Q: What happens if `ansible-playbook` is not installed on my host?
When `--provisioner auto` (the default) is used, `gitlab_vm.py` checks if `ansible-playbook` is on `PATH`. If not found, it automatically falls back to uploading and executing `scripts/install-gitlab.sh` over SSH.

### Q: Does `./gitlab_vm.py destroy` delete the downloaded Ubuntu 24.04 cloud image?
**No.** `destroy` unregisters the VM and deletes `.state/vms/<vm_name>/` (the `.vdi` disk and `seed.iso`), but preserves `.state/images/noble-server-cloudimg-*.img` so subsequent `create-vm` or `up` runs do not re-download the ~600 MB base image.
