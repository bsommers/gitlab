#!/usr/bin/env python3
"""
Standalone Infrastructure-as-Code & VirtualBox CLI Orchestrator for GitLab.

Reads declarative configuration from iac/vm-spec.yaml and uses VirtualBox CLI
(VBoxManage), Cloud-Init (NoCloud ISO), and Ansible / SSH provisioning to:
  1. Create a Linux VM in VirtualBox using CLI tools
  2. Install and configure a GitLab server inside the VM
  3. Display the connection URL(s) and credentials for GitLab
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import socket
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SPEC_PATH = ROOT_DIR / "iac" / "vm-spec.yaml"
STATE_DIR = ROOT_DIR / ".state"


# ---------------------------------------------------------------------------
# Minimal fallback YAML parser in case PyYAML is not installed
# ---------------------------------------------------------------------------
def load_yaml_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return _simple_yaml_parse(text)


def _simple_yaml_parse(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, val = stripped.split(":", 1)
        key = key.strip()
        val = val.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if val == "":
            new_dict: Dict[str, Any] = {}
            current[key] = new_dict
            stack.append((indent, new_dict))
        else:
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                parsed_val: Any = val[1:-1]
            elif val.lower() in ("true", "false"):
                parsed_val = val.lower() == "true"
            elif val.isdigit():
                parsed_val = int(val)
            else:
                parsed_val = val
            current[key] = parsed_val
    return root


# ---------------------------------------------------------------------------
# Helpers for logging and command execution
# ---------------------------------------------------------------------------
class Runner:
    def __init__(self, dry_run: bool = False, verbose: bool = False) -> None:
        self.dry_run = dry_run
        self.verbose = verbose

    def info(self, msg: str) -> None:
        print(f"\033[1;34m[INFO]\033[0m {msg}")

    def success(self, msg: str) -> None:
        print(f"\033[1;32m[OK]\033[0m   {msg}")

    def warn(self, msg: str) -> None:
        print(f"\033[1;33m[WARN]\033[0m {msg}")

    def error(self, msg: str) -> None:
        print(f"\033[1;31m[ERR]\033[0m  {msg}", file=sys.stderr)

    def run(
        self,
        cmd: List[str],
        *,
        check: bool = True,
        capture: bool = False,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[str]:
        cmd_str = " ".join(shlex.quote(str(c)) for c in cmd)
        if self.dry_run or self.verbose:
            print(f"\033[0;36m  $ {cmd_str}\033[0m")
        if self.dry_run:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.run(
            cmd,
            check=check,
            text=True,
            capture_output=capture,
            cwd=str(cwd) if cwd else None,
            env=env,
        )


# ---------------------------------------------------------------------------
# Architecture & Spec Resolution
# ---------------------------------------------------------------------------
def resolve_arch(spec_arch: str) -> Tuple[str, str]:
    """Return (ubuntu_arch, vbox_ostype_default) based on host or spec."""
    machine = platform.machine().lower()
    if spec_arch and spec_arch != "auto":
        arch = spec_arch.lower()
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "amd64"

    if arch in ("arm64", "aarch64"):
        return "arm64", "Ubuntu24_LTS_arm64"
    return "amd64", "Ubuntu24_LTS_64"


def render_template(template_path: Path, variables: Dict[str, Any]) -> str:
    content = template_path.read_text(encoding="utf-8")
    str_vars = {k: str(v) for k, v in variables.items()}
    return string.Template(content).safe_substitute(str_vars)


def ensure_ssh_keypair(runner: Runner, key_path: Path) -> Tuple[Path, str]:
    pub_path = key_path.with_suffix(".pub")
    if key_path.exists() and pub_path.exists():
        return key_path, pub_path.read_text(encoding="utf-8").strip()

    key_path.parent.mkdir(parents=True, exist_ok=True)
    runner.info(f"Generating dedicated SSH keypair at {key_path} ...")
    runner.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            "gitlab-vbox-iac",
            "-f",
            str(key_path),
        ]
    )
    if runner.dry_run:
        return key_path, "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDryRunKey gitlab-vbox-iac"
    os.chmod(key_path, 0o600)
    return key_path, pub_path.read_text(encoding="utf-8").strip()


def build_cidata_iso(runner: Runner, cidata_dir: Path, output_iso: Path) -> None:
    """Create a NoCloud cidata ISO image using available OS CLI tools."""
    if output_iso.exists() and not runner.dry_run:
        output_iso.unlink()

    if shutil.which("hdiutil"):
        runner.run(
            [
                "hdiutil",
                "makehybrid",
                "-o",
                str(output_iso),
                str(cidata_dir),
                "-iso",
                "-joliet",
                "-default-volume-name",
                "cidata",
            ]
        )
    elif shutil.which("genisoimage"):
        runner.run(
            [
                "genisoimage",
                "-output",
                str(output_iso),
                "-volid",
                "cidata",
                "-joliet",
                "-rock",
                str(cidata_dir),
            ]
        )
    elif shutil.which("mkisofs"):
        runner.run(
            [
                "mkisofs",
                "-output",
                str(output_iso),
                "-volid",
                "cidata",
                "-joliet",
                "-rock",
                str(cidata_dir),
            ]
        )
    elif shutil.which("xorriso"):
        runner.run(
            [
                "xorriso",
                "-as",
                "mkisofs",
                "-output",
                str(output_iso),
                "-volid",
                "cidata",
                "-joliet",
                "-rock",
                str(cidata_dir),
            ]
        )
    else:
        raise RuntimeError(
            "No ISO creation utility found (checked hdiutil, genisoimage, mkisofs, xorriso)."
        )


# ---------------------------------------------------------------------------
# VirtualBox CLI Operations
# ---------------------------------------------------------------------------
def vm_exists(vm_name: str) -> bool:
    res = subprocess.run(
        ["VBoxManage", " list", "vms"],
        capture_output=True,
        text=True,
        check=False,
    )
    # Call without leading space:
    res = subprocess.run(
        ["VBoxManage", "list", "vms"],
        capture_output=True,
        text=True,
        check=False,
    )
    pattern = re.compile(rf'^"{re.escape(vm_name)}"\s+\{{')
    return any(pattern.search(line) for line in res.stdout.splitlines())


def get_vm_info(vm_name: str) -> Dict[str, str]:
    res = subprocess.run(
        ["VBoxManage", "showvminfo", vm_name, "--machinereadable"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return {}
    info: Dict[str, str] = {}
    for line in res.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip().strip('"')] = v.strip().strip('"')
    return info


def get_vm_state(vm_name: str) -> str:
    info = get_vm_info(vm_name)
    return info.get("VMState", "not_found")


def create_vm(runner: Runner, spec: Dict[str, Any], start: bool = True) -> None:
    if not shutil.which("VBoxManage"):
        raise RuntimeError("VBoxManage CLI not found in PATH. Please install VirtualBox.")
    if not shutil.which("qemu-img"):
        raise RuntimeError("qemu-img not found in PATH (install via `brew install qemu` or `apt install qemu-utils`).")

    vm_cfg = spec.get("vm", {})
    img_cfg = spec.get("image", {})
    net_cfg = spec.get("network", {})
    auth_cfg = spec.get("auth", {})

    vm_name = str(vm_cfg.get("name", "gitlab-server"))
    cpus = int(vm_cfg.get("cpus", 4))
    memory_mb = int(vm_cfg.get("memory_mb", 8192))
    disk_size_gb = int(vm_cfg.get("disk_size_gb", 40))
    vram_mb = int(vm_cfg.get("vram_mb", 33))

    ubuntu_arch, default_ostype = resolve_arch(str(img_cfg.get("arch", "auto")))
    ostype = str(vm_cfg.get("ostype", "auto"))
    if ostype == "auto":
        ostype = default_ostype

    codename = str(img_cfg.get("codename", "noble"))
    base_url = str(
        img_cfg.get("base_url", f"https://cloud-images.ubuntu.com/{codename}/current")
    ).rstrip("/")
    img_filename = f"{codename}-server-cloudimg-{ubuntu_arch}.img"
    img_url = f"{base_url}/{img_filename}"

    images_dir = STATE_DIR / "images"
    vm_dir = STATE_DIR / "vms" / vm_name
    cidata_dir = STATE_DIR / "cloud-init" / vm_name
    for d in (images_dir, vm_dir, cidata_dir):
        d.mkdir(parents=True, exist_ok=True)

    ssh_key_rel = str(auth_cfg.get("ssh_key_path", ".state/ssh/id_ed25519"))
    ssh_key_path = (ROOT_DIR / ssh_key_rel).resolve()
    _, ssh_pub_key = ensure_ssh_keypair(runner, ssh_key_path)

    # 1. Check if VM already exists
    if not runner.dry_run and vm_exists(vm_name):
        state = get_vm_state(vm_name)
        runner.info(f"VM '{vm_name}' already exists in VirtualBox (state: {state}).")
        if start and state != "running":
            runner.info(f"Starting existing VM '{vm_name}' in headless mode...")
            runner.run(["VBoxManage", "startvm", vm_name, "--type", "headless"])
        return

    # 2. Download Ubuntu cloud image if not cached
    cached_img = images_dir / img_filename
    if not cached_img.exists():
        runner.info(f"Downloading Ubuntu cloud image ({ubuntu_arch}) from {img_url} ...")
        runner.run(["curl", "-fL", "--progress-bar", "-o", str(cached_img), img_url])
    else:
        runner.info(f"Using cached Ubuntu cloud image: {cached_img}")

    # 3. Convert cloud image (.img / qcow2) -> raw -> VDI and resize
    raw_disk = vm_dir / f"{vm_name}.raw"
    vdi_disk = vm_dir / f"{vm_name}.vdi"
    if vdi_disk.exists() and not runner.dry_run:
        vdi_disk.unlink()

    runner.info(f"Converting cloud image to VirtualBox VDI ({disk_size_gb} GB)...")
    runner.run(["qemu-img", "convert", "-f", "qcow2", "-O", "raw", str(cached_img), str(raw_disk)])
    disk_bytes = disk_size_gb * 1024 * 1024 * 1024
    runner.run(["VBoxManage", "convertfromraw", str(raw_disk), str(vdi_disk), "--format", "VDI"])
    if raw_disk.exists() and not runner.dry_run:
        raw_disk.unlink()
    runner.run(["VBoxManage", "modifymedium", "disk", str(vdi_disk), "--resize", str(disk_size_gb * 1024)])

    # 4. Render cloud-init templates and build cidata seed ISO
    hostname = str(auth_cfg.get("hostname", "gitlab.local"))
    ssh_user = str(auth_cfg.get("ssh_user", "ubuntu"))
    tmpl_vars = {
        "INSTANCE_ID": f"{vm_name}-01",
        "HOSTNAME": hostname,
        "SSH_USER": ssh_user,
        "SSH_PUBLIC_KEY": ssh_pub_key,
    }
    meta_tmpl = ROOT_DIR / "iac" / "cloud-init" / "meta-data.yaml.tmpl"
    user_tmpl = ROOT_DIR / "iac" / "cloud-init" / "user-data.yaml.tmpl"
    (cidata_dir / "meta-data").write_text(render_template(meta_tmpl, tmpl_vars), encoding="utf-8")
    (cidata_dir / "user-data").write_text(render_template(user_tmpl, tmpl_vars), encoding="utf-8")

    seed_iso = vm_dir / "seed.iso"
    runner.info(f"Building Cloud-Init NoCloud seed ISO at {seed_iso} ...")
    build_cidata_iso(runner, cidata_dir, seed_iso)

    # 5. Create and register VM in VirtualBox
    runner.info(f"Creating VirtualBox VM '{vm_name}' (ostype={ostype}, cpus={cpus}, memory={memory_mb}MB)...")
    runner.run(
        [
            "VBoxManage",
            "createvm",
            "--name",
            vm_name,
            "--ostype",
            ostype,
            "--register",
            "--basefolder",
            str(STATE_DIR / "vms"),
        ]
    )

    modify_cmd = [
        "VBoxManage",
        "modifyvm",
        vm_name,
        "--cpus",
        str(cpus),
        "--memory",
        str(memory_mb),
        "--vram",
        str(vram_mb),
        "--firmware",
        str(vm_cfg.get("firmware", "efi")),
        "--rtcuseutc",
        "on" if vm_cfg.get("rtc_use_utc", True) else "off",
        "--graphicscontroller",
        "vmsvga",
        "--audio-enabled",
        "off",
    ]
    runner.run(modify_cmd)

    # 6. Configure networking and NAT port forwarding
    adapter1 = net_cfg.get("adapter1", {})
    nic_type = str(adapter1.get("nic_type", "virtio"))
    runner.run(
        [
            "VBoxManage",
            "modifyvm",
            vm_name,
            "--nic1",
            str(adapter1.get("type", "nat")),
            "--nictype1",
            nic_type,
        ]
    )

    port_forwards = adapter1.get("port_forwards", {})
    for rule_name, rule in port_forwards.items():
        proto = str(rule.get("protocol", "tcp"))
        host_ip = str(rule.get("host_ip", "127.0.0.1"))
        host_port = int(rule.get("host_port", 0))
        guest_port = int(rule.get("guest_port", 0))
        pf_spec = f"{rule_name},{proto},{host_ip},{host_port},,{guest_port}"
        runner.run(["VBoxManage", "modifyvm", vm_name, "--natpf1", pf_spec])

    adapter2 = net_cfg.get("adapter2", {})
    adapter2_type = str(adapter2.get("type", "none")).lower()
    if adapter2_type in ("bridged", "hostonly"):
        iface = str(adapter2.get("interface", ""))
        flag = "--bridgeadapter2" if adapter2_type == "bridged" else "--hostonlyadapter2"
        cmd_nic2 = ["VBoxManage", "modifyvm", vm_name, "--nic2", adapter2_type, "--nictype2", nic_type]
        if iface:
            cmd_nic2.extend([flag, iface])
        runner.run(cmd_nic2)

    # 7. Configure storage controller & attach disks
    # VirtIO works cleanly on both ARM64 (Apple Silicon) and x86_64 in VirtualBox 7.x
    storage_ctl = "VirtIO"
    runner.run(
        [
            "VBoxManage",
            "storagectl",
            vm_name,
            "--name",
            storage_ctl,
            "--add",
            "virtio",
            "--controller",
            "VirtIO",
            "--portcount",
            "4",
            "--bootable",
            "on",
        ]
    )
    runner.run(
        [
            "VBoxManage",
            "storageattach",
            vm_name,
            "--storagectl",
            storage_ctl,
            "--port",
            "0",
            "--device",
            "0",
            "--type",
            "hdd",
            "--medium",
            str(vdi_disk),
        ]
    )
    runner.run(
        [
            "VBoxManage",
            "storageattach",
            vm_name,
            "--storagectl",
            storage_ctl,
            "--port",
            "1",
            "--device",
            "0",
            "--type",
            "dvddrive",
            "--medium",
            str(seed_iso),
        ]
    )

    if start:
        runner.info(f"Starting VM '{vm_name}' in headless mode...")
        runner.run(["VBoxManage", "startvm", vm_name, "--type", "headless"])
        runner.success(f"VM '{vm_name}' is now booting.")


# ---------------------------------------------------------------------------
# SSH & Provisioning Operations
# ---------------------------------------------------------------------------
def get_ssh_connection_params(spec: Dict[str, Any]) -> Tuple[str, int, str, Path]:
    net_cfg = spec.get("network", {})
    auth_cfg = spec.get("auth", {})
    pf = net_cfg.get("adapter1", {}).get("port_forwards", {}).get("ssh", {})
    host = str(pf.get("host_ip", "127.0.0.1"))
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    port = int(pf.get("host_port", 2222))
    user = str(auth_cfg.get("ssh_user", "ubuntu"))
    key_path = (ROOT_DIR / str(auth_cfg.get("ssh_key_path", ".state/ssh/id_ed25519"))).resolve()
    return host, port, user, key_path


def wait_for_ssh(runner: Runner, host: str, port: int, user: str, key_path: Path, timeout_sec: int = 300) -> None:
    if runner.dry_run:
        runner.info(f"[dry-run] Would wait up to {timeout_sec}s for SSH on {user}@{host}:{port}")
        return

    runner.info(f"Waiting for SSH readiness at {user}@{host}:{port} (timeout: {timeout_sec}s)...")
    deadline = time.time() + timeout_sec
    ssh_cmd = [
        "ssh",
        "-i",
        str(key_path),
        "-p",
        str(port),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "BatchMode=yes",
        f"{user}@{host}",
        "cloud-init status --wait >/dev/null 2>&1 || true; echo ready",
    ]
    while time.time() < deadline:
        res = subprocess.run(ssh_cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and "ready" in res.stdout:
            runner.success(f"SSH connection established and cloud-init finished on {host}:{port}.")
            return
        time.sleep(5)
    raise TimeoutError(f"Timed out waiting for SSH on {user}@{host}:{port}")


def provision_gitlab(runner: Runner, spec: Dict[str, Any], provisioner: str = "auto") -> None:
    vm_name = str(spec.get("vm", {}).get("name", "gitlab-server"))
    host, port, user, key_path = get_ssh_connection_params(spec)
    wait_for_ssh(runner, host, port, user, key_path)

    gitlab_cfg = spec.get("gitlab", {})
    install_method = str(gitlab_cfg.get("install_method", "omnibus"))
    edition = str(gitlab_cfg.get("edition", "gitlab-ce"))
    ext_proto = str(gitlab_cfg.get("external_protocol", "http"))
    ext_host = str(gitlab_cfg.get("external_host", "localhost"))
    ext_port = int(gitlab_cfg.get("external_port", 8080))
    ssh_port = int(gitlab_cfg.get("ssh_port", port))
    root_pw = str(gitlab_cfg.get("initial_root_password", "GitLabRoot!2026"))
    puma_workers = int(gitlab_cfg.get("puma_workers", 2))
    sidekiq_concurrency = int(gitlab_cfg.get("sidekiq_concurrency", 10))
    prometheus_enable = bool(gitlab_cfg.get("prometheus_monitoring_enable", False))

    if (ext_proto == "http" and ext_port == 80) or (ext_proto == "https" and ext_port == 443):
        external_url = f"{ext_proto}://{ext_host}"
    else:
        external_url = f"{ext_proto}://{ext_host}:{ext_port}"

    # Render Ansible inventory file
    ans_state_dir = STATE_DIR / "ansible"
    ans_state_dir.mkdir(parents=True, exist_ok=True)
    inv_tmpl = ROOT_DIR / "iac" / "ansible" / "inventory.ini.tmpl"
    inv_file = ans_state_dir / "inventory.ini"
    inv_content = render_template(
        inv_tmpl,
        {
            "VM_NAME": vm_name,
            "ANSIBLE_HOST": host,
            "ANSIBLE_PORT": port,
            "SSH_USER": user,
            "SSH_PRIVATE_KEY": str(key_path),
            "GITLAB_INSTALL_METHOD": install_method,
            "GITLAB_EDITION": edition,
            "GITLAB_EXTERNAL_URL": external_url,
            "GITLAB_EXTERNAL_PORT": ext_port,
            "GITLAB_SSH_PORT": ssh_port,
            "GITLAB_INITIAL_ROOT_PASSWORD": root_pw,
            "GITLAB_PUMA_WORKERS": puma_workers,
            "GITLAB_SIDEKIQ_CONCURRENCY": sidekiq_concurrency,
            "GITLAB_PROMETHEUS_ENABLE": str(prometheus_enable).lower(),
        },
    )
    inv_file.write_text(inv_content, encoding="utf-8")

    use_ansible = provisioner == "ansible" or (
        provisioner == "auto" and shutil.which("ansible-playbook") is not None
    )

    if use_ansible:
        runner.info(f"Provisioning GitLab ({install_method}) via Ansible IaC playbook...")
        playbook_path = ROOT_DIR / "iac" / "ansible" / "playbook.yml"
        env = os.environ.copy()
        env["ANSIBLE_CONFIG"] = str(ROOT_DIR / "iac" / "ansible" / "ansible.cfg")
        runner.run(
            ["ansible-playbook", "-i", str(inv_file), str(playbook_path)],
            env=env,
        )
    else:
        runner.info(f"Provisioning GitLab ({install_method}) via SSH script (scripts/install-gitlab.sh)...")
        install_script = ROOT_DIR / "scripts" / "install-gitlab.sh"
        remote_script = "/tmp/install-gitlab.sh"
        scp_cmd = [
            "scp",
            "-i",
            str(key_path),
            "-P",
            str(port),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            str(install_script),
            f"{user}@{host}:{remote_script}",
        ]
        runner.run(scp_cmd)
        ssh_exec = [
            "ssh",
            "-i",
            str(key_path),
            "-p",
            str(port),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"{user}@{host}",
            (
                f"sudo env "
                f"GITLAB_INSTALL_METHOD={shlex.quote(install_method)} "
                f"GITLAB_EDITION={shlex.quote(edition)} "
                f"GITLAB_EXTERNAL_URL={shlex.quote(external_url)} "
                f"GITLAB_EXTERNAL_PORT={shlex.quote(str(ext_port))} "
                f"GITLAB_SSH_PORT={shlex.quote(str(ssh_port))} "
                f"GITLAB_INITIAL_ROOT_PASSWORD={shlex.quote(root_pw)} "
                f"GITLAB_PUMA_WORKERS={shlex.quote(str(puma_workers))} "
                f"GITLAB_SIDEKIQ_CONCURRENCY={shlex.quote(str(sidekiq_concurrency))} "
                f"GITLAB_PROMETHEUS_ENABLE={shlex.quote(str(prometheus_enable).lower())} "
                f"bash {remote_script} --local"
            ),
        ]
        runner.run(ssh_exec)

    runner.success("GitLab provisioning complete.")


# ---------------------------------------------------------------------------
# Connection URL Discovery & Health Check
# ---------------------------------------------------------------------------
def discover_connection_details(spec: Dict[str, Any]) -> Dict[str, Any]:
    vm_name = str(spec.get("vm", {}).get("name", "gitlab-server"))
    gitlab_cfg = spec.get("gitlab", {})
    ext_proto = str(gitlab_cfg.get("external_protocol", "http"))
    ext_host = str(gitlab_cfg.get("external_host", "localhost"))
    ext_port = int(gitlab_cfg.get("external_port", 8080))
    ssh_port = int(gitlab_cfg.get("ssh_port", 2222))
    root_pw = str(gitlab_cfg.get("initial_root_password", "GitLabRoot!2026"))

    vm_info = get_vm_info(vm_name)
    vm_state = vm_info.get("VMState", "not_created")

    # Inspect live NAT port-forwarding rules on the VM if it exists in VirtualBox
    for k, v in vm_info.items():
        if k.startswith("Forwarding("):
            # Format: name,proto,hostip,hostport,guestip,guestport
            parts = v.split(",")
            if len(parts) >= 6:
                rule_name, _, _, hport, _, _ = parts[:6]
                if rule_name == "http" and hport.isdigit():
                    ext_port = int(hport)
                elif rule_name == "ssh" and hport.isdigit():
                    ssh_port = int(hport)

    if (ext_proto == "http" and ext_port == 80) or (ext_proto == "https" and ext_port == 443):
        web_url = f"{ext_proto}://{ext_host}"
    else:
        web_url = f"{ext_proto}://{ext_host}:{ext_port}"

    git_ssh_url = f"ssh://git@{ext_host}:{ssh_port}/<namespace>/<project>.git"

    # Probe HTTP health
    http_status: Optional[int] = None
    http_ready = False
    probe_url = f"{web_url}/users/sign_in"
    try:
        req = urllib.request.Request(probe_url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            http_status = resp.status
            http_ready = resp.status in (200, 302)
    except urllib.error.HTTPError as e:
        http_status = e.code
        http_ready = e.code in (200, 302)
    except Exception:
        http_ready = False

    return {
        "vm_name": vm_name,
        "vm_state": vm_state,
        "gitlab_web_url": web_url,
        "gitlab_sign_in_url": f"{web_url}/users/sign_in",
        "gitlab_git_ssh_url": git_ssh_url,
        "vm_ssh_command": f"ssh -i {ROOT_DIR / str(spec.get('auth', {}).get('ssh_key_path', '.state/ssh/id_ed25519'))} -p {ssh_port} {spec.get('auth', {}).get('ssh_user', 'ubuntu')}@127.0.0.1",
        "username": "root",
        "initial_root_password": root_pw,
        "http_ready": http_ready,
        "http_status": http_status,
    }


def show_connection_url(spec: Dict[str, Any], as_json: bool = False, url_only: bool = False) -> None:
    details = discover_connection_details(spec)
    if as_json:
        print(json.dumps(details, indent=2))
        return
    if url_only:
        print(details["gitlab_web_url"])
        return

    status_badge = (
        "\033[1;32mONLINE (HTTP Ready)\033[0m"
        if details["http_ready"]
        else f"\033[1;33m{details['vm_state'].upper()} (HTTP status: {details['http_status'] or 'unreachable'})\033[0m"
    )
    print("\n" + "=" * 68)
    print("  GITLAB VIRTUALBOX SERVER - CONNECTION DETAILS")
    print("=" * 68)
    print(f"  VM Name          : {details['vm_name']}")
    print(f"  Status           : {status_badge}")
    print(f"  GitLab Web URL   : \033[1;36m{details['gitlab_web_url']}\033[0m")
    print(f"  Sign-In URL      : {details['gitlab_sign_in_url']}")
    print(f"  Git SSH Clone    : {details['gitlab_git_ssh_url']}")
    print("-" * 68)
    print(f"  Admin Username   : {details['username']}")
    print(f"  Initial Password : {details['initial_root_password']}")
    print(f"  Retrieve in VM   : sudo cat /etc/gitlab/initial_root_password")
    print("-" * 68)
    print(f"  VM SSH Access    : {details['vm_ssh_command']}")
    print("=" * 68 + "\n")


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitlab_vm.py",
        description="Standalone IaC & VirtualBox CLI Manager for GitLab Server",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_SPEC_PATH,
        help=f"Path to declarative VM spec YAML (default: {DEFAULT_SPEC_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print VBoxManage/provisioning commands without executing them",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print executed shell commands",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # up
    p_up = sub.add_parser("up", help="Create Linux VM, provision GitLab, and show connection URL")
    p_up.add_argument(
        "--provisioner",
        choices=["auto", "ansible", "ssh"],
        default="auto",
        help="Provisioning engine to use inside the VM (default: auto)",
    )

    # create-vm
    p_create = sub.add_parser("create-vm", help="Create and boot the Linux VM in VirtualBox via CLI")
    p_create.add_argument("--no-start", action="store_true", help="Create VM without starting it")

    # provision
    p_prov = sub.add_parser("provision", help="Provision GitLab server inside the running VirtualBox VM")
    p_prov.add_argument(
        "--provisioner",
        choices=["auto", "ansible", "ssh"],
        default="auto",
        help="Provisioning engine to use (default: auto)",
    )

    # url / status
    p_url = sub.add_parser("url", aliases=["status", "info"], help="Show GitLab connection URL and status")
    p_url.add_argument("--json", action="store_true", help="Output connection details as JSON")
    p_url.add_argument("--raw", action="store_true", help="Print only the GitLab HTTP URL")

    # ssh
    sub.add_parser("ssh", help="Open an interactive SSH shell into the VirtualBox Linux VM")

    # start / stop / destroy
    sub.add_parser("start", help="Start the VirtualBox Linux VM in headless mode")
    sub.add_parser("stop", help="Gracefully shut down the VirtualBox Linux VM")
    sub.add_parser("destroy", help="Power off and completely delete the VirtualBox VM and its disks")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.config.exists():
        print(f"Error: Spec file not found at {args.config}", file=sys.stderr)
        return 1

    spec = load_yaml_file(args.config)
    runner = Runner(dry_run=args.dry_run, verbose=args.verbose)
    vm_name = str(spec.get("vm", {}).get("name", "gitlab-server"))

    try:
        if args.command == "create-vm":
            create_vm(runner, spec, start=not args.no_start)
        elif args.command == "provision":
            provision_gitlab(runner, spec, provisioner=args.provisioner)
        elif args.command in ("url", "status", "info"):
            show_connection_url(spec, as_json=args.json, url_only=args.raw)
        elif args.command == "up":
            create_vm(runner, spec, start=True)
            provision_gitlab(runner, spec, provisioner=args.provisioner)
            show_connection_url(spec)
        elif args.command == "ssh":
            host, port, user, key_path = get_ssh_connection_params(spec)
            ssh_cmd = [
                "ssh",
                "-i",
                str(key_path),
                "-p",
                str(port),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                f"{user}@{host}",
            ]
            if runner.dry_run:
                runner.run(ssh_cmd)
                return 0
            return subprocess.call(ssh_cmd)
        elif args.command == "start":
            runner.run(["VBoxManage", "startvm", vm_name, "--type", "headless"])
        elif args.command == "stop":
            runner.run(["VBoxManage", "controlvm", vm_name, "acpipowerbutton"])
        elif args.command == "destroy":
            if runner.dry_run or vm_exists(vm_name):
                state = get_vm_state(vm_name) if not runner.dry_run else "running"
                if state == "running":
                    runner.run(["VBoxManage", "controlvm", vm_name, "poweroff"], check=False)
                    time.sleep(2)
                runner.run(["VBoxManage", "unregistervm", vm_name, "--delete-all"])
                runner.success(f"VM '{vm_name}' destroyed.")
            else:
                runner.info(f"VM '{vm_name}' does not exist.")
    except Exception as exc:
        runner.error(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
