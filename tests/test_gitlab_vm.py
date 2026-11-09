#!/usr/bin/env python3
"""
Unit & contract test suite for gitlab_vm.py.

Covers:
  1. Standalone YAML parser (_simple_yaml_parse) vs PyYAML equivalence
  2. Cross-architecture resolution (arm64 vs amd64) & template rendering
  3. Provider resolution & Proxmox API token loading (.state, env vars, prefix stripping)
  4. Proxmox VE strict non-overwrite protection (by VM name, by VMID, VMID collision,
     up idempotency when HTTP ready, and destroy refusal when protect_existing=True)
  5. Proxmox QEMU Guest Agent IPv4 discovery & static ipconfig0 fallback
  6. VirtualBox CLI lifecycle, NAT port-forwarding discovery, and dry-run execution
  7. Onboarding CLI subcommands (init, doctor, guide) and clean stdout invariants
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gitlab_vm  # noqa: E402


class TestYamlAndTemplates(unittest.TestCase):
    def test_simple_yaml_parse_matches_starter_spec(self) -> None:
        parsed = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        self.assertEqual(parsed["vm"]["name"], "gitlab-server")
        self.assertEqual(parsed["vm"]["provider"], "proxmox")
        self.assertEqual(parsed["vm"]["cpus"], 4)
        self.assertEqual(parsed["vm"]["memory_mb"], 8192)
        self.assertIs(parsed["vm"]["rtc_use_utc"], True)
        self.assertEqual(parsed["proxmox"]["vmid"], 112)
        self.assertEqual(parsed["proxmox"]["node"], "pve")
        self.assertIs(parsed["proxmox"]["protect_existing"], True)
        self.assertEqual(
            parsed["network"]["adapter1"]["port_forwards"]["http"]["host_port"],
            8080,
        )
        self.assertEqual(parsed["gitlab"]["install_method"], "omnibus")
        self.assertIs(parsed["gitlab"]["prometheus_monitoring_enable"], False)

    def test_load_yaml_file_fallback_without_pyyaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "vm-spec.yaml"
            spec_path.write_text(gitlab_vm.STARTER_SPEC_YAML, encoding="utf-8")
            with mock.patch.object(gitlab_vm, "yaml", None):
                data = gitlab_vm.load_yaml_file(spec_path)
            self.assertEqual(data["proxmox"]["vmid"], 112)
            self.assertEqual(data["vm"]["name"], "gitlab-server")

    def test_render_template_substitutes_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpl = Path(tmp) / "meta.tmpl"
            tmpl.write_text("instance-id: ${INSTANCE_ID}\nhostname: ${HOSTNAME}\n", encoding="utf-8")
            rendered = gitlab_vm.render_template(
                tmpl,
                {"INSTANCE_ID": "gitlab-server-01", "HOSTNAME": "gitlab.local"},
            )
            self.assertEqual(rendered, "instance-id: gitlab-server-01\nhostname: gitlab.local\n")


class TestArchAndProviderResolution(unittest.TestCase):
    def test_resolve_arch_auto_arm64_and_amd64(self) -> None:
        with mock.patch("platform.machine", return_value="arm64"):
            self.assertEqual(gitlab_vm.resolve_arch("auto"), ("arm64", "Ubuntu24_LTS_arm64"))
        with mock.patch("platform.machine", return_value="aarch64"):
            self.assertEqual(gitlab_vm.resolve_arch("auto"), ("arm64", "Ubuntu24_LTS_arm64"))
        with mock.patch("platform.machine", return_value="x86_64"):
            self.assertEqual(gitlab_vm.resolve_arch("auto"), ("amd64", "Ubuntu24_LTS_64"))

    def test_resolve_arch_explicit_override(self) -> None:
        with mock.patch("platform.machine", return_value="arm64"):
            self.assertEqual(gitlab_vm.resolve_arch("amd64"), ("amd64", "Ubuntu24_LTS_64"))
        with mock.patch("platform.machine", return_value="x86_64"):
            self.assertEqual(gitlab_vm.resolve_arch("arm64"), ("arm64", "Ubuntu24_LTS_arm64"))

    def test_get_proxmox_token_strips_prefix_and_reads_env_or_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "api_token"
            token_file.write_text("PVEAPIToken=root@pam!tok=1234-5678\n", encoding="utf-8")
            spec = {
                "proxmox": {
                    "api_token_env": "CUSTOM_PVE_TOKEN",
                    "api_token_file": str(token_file),
                }
            }
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(gitlab_vm.get_proxmox_token(spec), "root@pam!tok=1234-5678")

            with mock.patch.dict(
                os.environ,
                {"CUSTOM_PVE_TOKEN": "PVEAPIToken=user@pve!envtok=abcd"},
                clear=True,
            ):
                self.assertEqual(gitlab_vm.get_proxmox_token(spec), "user@pve!envtok=abcd")

    def test_resolve_provider_precedence(self) -> None:
        spec_pve = {"vm": {"provider": "proxmox"}, "proxmox": {"vmid": 112}}
        spec_vbox = {"vm": {"provider": "virtualbox"}}
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(gitlab_vm.resolve_provider(spec_pve), "proxmox")
            self.assertEqual(gitlab_vm.resolve_provider(spec_vbox), "virtualbox")
            self.assertEqual(gitlab_vm.resolve_provider(spec_pve, "virtualbox"), "virtualbox")
        with mock.patch.dict(os.environ, {"GITLAB_VM_PROVIDER": "virtualbox"}, clear=True):
            self.assertEqual(gitlab_vm.resolve_provider(spec_pve), "virtualbox")


class TestProxmoxNonOverwriteProtection(unittest.TestCase):
    def setUp(self) -> None:
        self.spec: Dict[str, Any] = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        self.spec["proxmox"]["api_token"] = "root@pam!test=0000"

    def test_proxmox_find_existing_vm_matches_by_name_and_vmid(self) -> None:
        fake_vms = [
            {"vmid": 110, "name": "Home-Assistant", "status": "running"},
            {"vmid": 112, "name": "gitlab-server", "status": "running"},
        ]
        with mock.patch.object(gitlab_vm, "proxmox_api_request", return_value=fake_vms):
            found = gitlab_vm.proxmox_find_existing_vm(self.spec)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["vmid"], 112)
        self.assertEqual(found["name"], "gitlab-server")
        self.assertEqual(found["status"], "running")
        self.assertEqual(found["match"], "name_and_vmid")

    def test_proxmox_find_existing_vm_matches_by_name_even_if_vmid_differs(self) -> None:
        fake_vms = [
            {"vmid": 112, "name": "gitlab-server", "status": "running"},
        ]
        spec_diff_id = json.loads(json.dumps(self.spec))
        spec_diff_id["proxmox"]["vmid"] = 250
        with mock.patch.object(gitlab_vm, "proxmox_api_request", return_value=fake_vms):
            found = gitlab_vm.proxmox_find_existing_vm(spec_diff_id)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["vmid"], 112)
        self.assertEqual(found["name"], "gitlab-server")
        self.assertEqual(found["match"], "name")

    def test_create_vm_proxmox_never_overwrites_existing_running_vm(self) -> None:
        existing_vm = {
            "vmid": 112,
            "name": "gitlab-server",
            "status": "running",
            "node": "pve",
            "match": "name_and_vmid",
        }
        runner = gitlab_vm.Runner(dry_run=False, quiet=True)
        with mock.patch.object(
            gitlab_vm, "proxmox_find_existing_vm", return_value=existing_vm
        ), mock.patch.object(gitlab_vm, "proxmox_api_request") as mock_api:
            gitlab_vm.create_vm_proxmox(runner, self.spec, start=True)
            mock_api.assert_not_called()

    def test_create_vm_proxmox_starts_stopped_existing_vm_without_cloning_or_reconfiguring(self) -> None:
        existing_vm = {
            "vmid": 112,
            "name": "gitlab-server",
            "status": "stopped",
            "node": "pve",
            "match": "name_and_vmid",
        }
        runner = gitlab_vm.Runner(dry_run=False, quiet=True)
        with mock.patch.object(
            gitlab_vm, "proxmox_find_existing_vm", return_value=existing_vm
        ), mock.patch.object(gitlab_vm, "proxmox_api_request") as mock_api:
            gitlab_vm.create_vm_proxmox(runner, self.spec, start=True)
            mock_api.assert_called_once_with(
                self.spec,
                "nodes/pve/qemu/112/status/start",
                method="POST",
            )

    def test_create_vm_proxmox_refuses_vmid_collision_with_different_vm_name(self) -> None:
        colliding_vm = {
            "vmid": 112,
            "name": "production-db",
            "status": "running",
            "node": "pve",
            "match": "vmid",
        }
        runner = gitlab_vm.Runner(dry_run=False, quiet=True)
        with mock.patch.object(
            gitlab_vm, "proxmox_find_existing_vm", return_value=colliding_vm
        ), mock.patch.object(gitlab_vm, "proxmox_api_request") as mock_api:
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite existing Proxmox VMID 112"):
                gitlab_vm.create_vm_proxmox(runner, self.spec, start=True)
            mock_api.assert_not_called()

    def test_up_skips_provisioning_when_existing_proxmox_vm_is_http_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_file = Path(tmp) / "vm-spec.yaml"
            spec_file.write_text(gitlab_vm.STARTER_SPEC_YAML, encoding="utf-8")
            fake_details = {
                "provider": "proxmox",
                "vm_name": "gitlab-server",
                "vm_state": "running",
                "proxmox_node": "pve",
                "proxmox_vmid": 112,
                "guest_ip": "192.168.1.250",
                "gitlab_web_url": "http://192.168.1.250:8080",
                "gitlab_sign_in_url": "http://192.168.1.250:8080/users/sign_in",
                "gitlab_git_ssh_url": "git@192.168.1.250:<namespace>/<project>.git",
                "vm_ssh_command": "ssh -i key -p 22 ubuntu@192.168.1.250",
                "username": "root",
                "initial_root_password": "GitLabRoot!2026",
                "http_ready": True,
                "http_status": 200,
            }
            with mock.patch.object(gitlab_vm, "create_vm") as mock_create, mock.patch.object(
                gitlab_vm, "discover_connection_details", return_value=fake_details
            ), mock.patch.object(gitlab_vm, "provision_gitlab") as mock_prov, redirect_stdout(
                io.StringIO()
            ), redirect_stderr(io.StringIO()):
                rc = gitlab_vm.main(["-c", str(spec_file), "-q", "up"])
            self.assertEqual(rc, 0)
            mock_create.assert_called_once()
            mock_prov.assert_not_called()

    def test_destroy_refuses_when_proxmox_protect_existing_is_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_file = Path(tmp) / "vm-spec.yaml"
            spec_file.write_text(gitlab_vm.STARTER_SPEC_YAML, encoding="utf-8")
            existing_vm = {
                "vmid": 112,
                "name": "gitlab-server",
                "status": "running",
                "node": "pve",
                "match": "name_and_vmid",
            }
            err_buf = io.StringIO()
            with mock.patch.object(
                gitlab_vm, "proxmox_find_existing_vm", return_value=existing_vm
            ), mock.patch.object(gitlab_vm, "proxmox_api_request") as mock_api, redirect_stderr(err_buf):
                rc = gitlab_vm.main(["-c", str(spec_file), "destroy"])
            self.assertEqual(rc, 1)
            self.assertIn("Refusing to destroy protected Proxmox VM", err_buf.getvalue())
            mock_api.assert_not_called()


class TestProxmoxGuestIpAndDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.spec: Dict[str, Any] = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        self.spec["proxmox"]["api_token"] = "root@pam!test=0000"

    def test_proxmox_get_guest_ip_from_qemu_agent(self) -> None:
        agent_payload = {
            "result": [
                {
                    "name": "lo",
                    "ip-addresses": [{"ip-address-type": "ipv4", "ip-address": "127.0.0.1"}],
                },
                {
                    "name": "eth0",
                    "ip-addresses": [
                        {"ip-address-type": "ipv6", "ip-address": "fe80::1"},
                        {"ip-address-type": "ipv4", "ip-address": "192.168.1.250"},
                    ],
                },
            ]
        }
        with mock.patch.object(gitlab_vm, "proxmox_api_request", return_value=agent_payload):
            ip = gitlab_vm.proxmox_get_guest_ip(self.spec, 112)
        self.assertEqual(ip, "192.168.1.250")

    def test_proxmox_get_guest_ip_falls_back_to_ipconfig0(self) -> None:
        def fake_api(spec: Dict[str, Any], path: str, **kwargs: Any) -> Any:
            if "agent/network-get-interfaces" in path:
                raise RuntimeError("QEMU guest agent not running")
            if path.endswith("/config"):
                return {"ipconfig0": "ip=192.168.1.250/24,gw=192.168.1.1"}
            return {}

        with mock.patch.object(gitlab_vm, "proxmox_api_request", side_effect=fake_api):
            ip = gitlab_vm.proxmox_get_guest_ip(self.spec, 112)
        self.assertEqual(ip, "192.168.1.250")

    def test_url_raw_and_json_keep_stdout_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_file = Path(tmp) / "vm-spec.yaml"
            spec_file.write_text(gitlab_vm.STARTER_SPEC_YAML, encoding="utf-8")
            fake_details = {
                "provider": "proxmox",
                "vm_name": "gitlab-server",
                "vm_state": "running",
                "proxmox_node": "pve",
                "proxmox_vmid": 112,
                "guest_ip": "192.168.1.250",
                "gitlab_web_url": "http://192.168.1.250:8080",
                "gitlab_sign_in_url": "http://192.168.1.250:8080/users/sign_in",
                "gitlab_git_ssh_url": "git@192.168.1.250:<namespace>/<project>.git",
                "vm_ssh_command": "ssh -i key -p 22 ubuntu@192.168.1.250",
                "username": "root",
                "initial_root_password": "GitLabRoot!2026",
                "http_ready": True,
                "http_status": 200,
            }
            out_raw = io.StringIO()
            with mock.patch.object(
                gitlab_vm, "discover_connection_details", return_value=fake_details
            ), redirect_stdout(out_raw):
                rc = gitlab_vm.main(["-c", str(spec_file), "url", "--raw"])
            self.assertEqual(rc, 0)
            self.assertEqual(out_raw.getvalue().strip(), "http://192.168.1.250:8080")

            out_json = io.StringIO()
            with mock.patch.object(
                gitlab_vm, "discover_connection_details", return_value=fake_details
            ), redirect_stdout(out_json):
                rc = gitlab_vm.main(["-c", str(spec_file), "url", "--json"])
            self.assertEqual(rc, 0)
            parsed = json.loads(out_json.getvalue())
            self.assertEqual(parsed["guest_ip"], "192.168.1.250")
            self.assertTrue(parsed["http_ready"])


class TestOnboardingAndVirtualBoxLifecycle(unittest.TestCase):
    def test_cmd_init_creates_and_protects_existing_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_file = Path(tmp) / "vm-spec.yaml"
            err = io.StringIO()
            with redirect_stderr(err):
                rc1 = gitlab_vm.cmd_init(spec_file)
            self.assertEqual(rc1, 0)
            self.assertTrue(spec_file.exists())

            spec_file.write_text("# custom\n", encoding="utf-8")
            with redirect_stderr(err):
                rc2 = gitlab_vm.cmd_init(spec_file, force=False)
            self.assertEqual(rc2, 0)
            self.assertEqual(spec_file.read_text(encoding="utf-8"), "# custom\n")

            with redirect_stderr(err):
                rc3 = gitlab_vm.cmd_init(spec_file, force=True)
            self.assertEqual(rc3, 0)
            self.assertIn("gitlab-server", spec_file.read_text(encoding="utf-8"))

    def test_print_next_steps_writes_only_to_stderr_and_respects_quiet(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            gitlab_vm.print_next_steps("Done.", [("./gitlab_vm.py url", "check url")])
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Next steps:", err.getvalue())

        err_quiet = io.StringIO()
        with redirect_stderr(err_quiet):
            gitlab_vm.print_next_steps("Done.", [("./gitlab_vm.py url", "check url")], quiet=True)
        self.assertEqual(err_quiet.getvalue(), "")

    def test_virtualbox_discover_connection_details_parses_nat_forwarding(self) -> None:
        spec = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        spec["vm"]["provider"] = "virtualbox"
        fake_vminfo = {
            "VMState": "running",
            "Forwarding(0)": "http,tcp,0.0.0.0,9080,,8080",
            "Forwarding(1)": "ssh,tcp,127.0.0.1,2229,,22",
        }
        with mock.patch.object(gitlab_vm, "get_vm_info", return_value=fake_vminfo), mock.patch(
            "urllib.request.urlopen", side_effect=OSError("offline")
        ):
            details = gitlab_vm.discover_connection_details(spec, provider="virtualbox")
        self.assertEqual(details["provider"], "virtualbox")
        self.assertEqual(details["vm_state"], "running")
        self.assertEqual(details["gitlab_web_url"], "http://localhost:9080")
        self.assertEqual(details["gitlab_git_ssh_url"], "ssh://git@localhost:2229/<namespace>/<project>.git")
        self.assertFalse(details["http_ready"])

    def test_wait_for_ssh_timeout_raises(self) -> None:
        runner = gitlab_vm.Runner(dry_run=False, quiet=True)
        failed_proc = subprocess.CompletedProcess(["ssh"], 255, stdout="", stderr="Connection refused")
        with mock.patch("subprocess.run", return_value=failed_proc), mock.patch(
            "time.time", side_effect=[0.0, 1.0, 10.0]
        ), mock.patch("time.sleep"):
            with self.assertRaises(TimeoutError):
                gitlab_vm.wait_for_ssh(runner, "127.0.0.1", 2222, "ubuntu", Path("/tmp/key"), timeout_sec=5)

    def test_wait_for_ssh_dry_run_and_success(self) -> None:
        runner_dry = gitlab_vm.Runner(dry_run=True, quiet=True)
        gitlab_vm.wait_for_ssh(runner_dry, "127.0.0.1", 2222, "ubuntu", Path("/tmp/key"))

        runner = gitlab_vm.Runner(dry_run=False, quiet=True)
        ok_proc = subprocess.CompletedProcess(["ssh"], 0, stdout="ready\n", stderr="")
        with mock.patch("subprocess.run", return_value=ok_proc):
            gitlab_vm.wait_for_ssh(runner, "127.0.0.1", 2222, "ubuntu", Path("/tmp/key"), timeout_sec=5)

    def test_runner_logging_and_execution(self) -> None:
        runner = gitlab_vm.Runner(dry_run=False, verbose=True, quiet=False)
        out = io.StringIO()
        err = io.StringIO()
        ok_proc = subprocess.CompletedProcess(["echo", "hi"], 0, stdout="hi\n", stderr="")
        with redirect_stdout(out), redirect_stderr(err), mock.patch("subprocess.run", return_value=ok_proc):
            runner.info("info msg")
            runner.success("ok msg")
            runner.warn("warn msg")
            runner.error("err msg")
            res = runner.run(["echo", "hi"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("info msg", out.getvalue())
        self.assertIn("ok msg", out.getvalue())
        self.assertIn("warn msg", err.getvalue())
        self.assertIn("err msg", err.getvalue())

    def test_cmd_doctor_json_and_human_for_proxmox_and_virtualbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_file = Path(tmp) / "vm-spec.yaml"
            spec_file.write_text(gitlab_vm.STARTER_SPEC_YAML, encoding="utf-8")

            out_json = io.StringIO()
            with mock.patch.object(gitlab_vm, "get_proxmox_token", return_value="tok"), mock.patch.object(
                gitlab_vm, "proxmox_api_request", return_value={"version": "9.2.3"}
            ), mock.patch.object(
                gitlab_vm,
                "proxmox_find_existing_vm",
                return_value={"name": "gitlab-server", "vmid": 112, "status": "running", "node": "pve"},
            ), redirect_stdout(out_json):
                rc = gitlab_vm.cmd_doctor(spec_file, as_json=True, cli_provider="proxmox")
            self.assertEqual(rc, 0)
            report = json.loads(out_json.getvalue())
            self.assertTrue(report["ok"])
            self.assertEqual(report["provider"], "proxmox")

            out_human = io.StringIO()
            err_human = io.StringIO()
            with mock.patch.object(gitlab_vm, "get_proxmox_token", return_value=""), redirect_stdout(
                out_human
            ), redirect_stderr(err_human):
                rc_fail = gitlab_vm.cmd_doctor(spec_file, as_json=False, cli_provider="proxmox")
            self.assertEqual(rc_fail, 1)
            self.assertIn("[MISS]", out_human.getvalue())

    def test_cmd_guide_and_missing_spec_error(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(gitlab_vm.main(["guide"]), 0)
        self.assertIn("WORKFLOW & LIFECYCLE GUIDE", out.getvalue())

        err = io.StringIO()
        with redirect_stderr(err):
            rc = gitlab_vm.main(["-c", "/nonexistent/spec.yaml", "url"])
        self.assertEqual(rc, 1)
        self.assertIn("specification file not found", err.getvalue())

    def test_build_cidata_iso_all_tool_branches(self) -> None:
        runner = gitlab_vm.Runner(dry_run=True, quiet=True)
        with tempfile.TemporaryDirectory() as tmp:
            cidata = Path(tmp) / "cidata"
            cidata.mkdir()
            iso = Path(tmp) / "seed.iso"
            for tool in ("hdiutil", "genisoimage", "mkisofs", "xorriso"):
                with mock.patch("shutil.which", side_effect=lambda name, t=tool: f"/usr/bin/{t}" if name == t else None):
                    gitlab_vm.build_cidata_iso(runner, cidata, iso)
            with mock.patch("shutil.which", return_value=None):
                with self.assertRaises(RuntimeError):
                    gitlab_vm.build_cidata_iso(runner, cidata, iso)

    def test_proxmox_api_request_and_wait_task(self) -> None:
        spec = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        with mock.patch.object(gitlab_vm, "get_proxmox_token", return_value=""):
            with self.assertRaises(RuntimeError):
                gitlab_vm.proxmox_api_request(spec, "version")

        class FakeResp:
            def __init__(self, payload: Dict[str, Any]) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self) -> "FakeResp":
                return self

            def __exit__(self, *args: Any) -> None:
                pass

        with mock.patch.object(gitlab_vm, "get_proxmox_token", return_value="tok"), mock.patch(
            "urllib.request.urlopen", return_value=FakeResp({"data": {"version": "9.2"}})
        ):
            data = gitlab_vm.proxmox_api_request(spec, "version", method="POST", data={"k": "v"})
            self.assertEqual(data, {"version": "9.2"})

        with mock.patch.object(
            gitlab_vm,
            "proxmox_api_request",
            return_value={"status": "stopped", "exitstatus": "OK"},
        ):
            gitlab_vm.proxmox_wait_task(spec, "pve", "UPID:pve:1")

        with mock.patch.object(
            gitlab_vm,
            "proxmox_api_request",
            return_value={"status": "stopped", "exitstatus": "ERR"},
        ):
            with self.assertRaises(RuntimeError):
                gitlab_vm.proxmox_wait_task(spec, "pve", "UPID:pve:1")

    def test_create_vm_proxmox_new_vm_clone_flow_and_dry_run(self) -> None:
        spec = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        spec["proxmox"]["api_token"] = "tok"
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "id_ed25519"
            key_path.write_text("priv", encoding="utf-8")
            key_path.with_suffix(".pub").write_text("ssh-ed25519 AAAATest test", encoding="utf-8")
            spec["auth"]["ssh_key_path"] = str(key_path)

            runner_dry = gitlab_vm.Runner(dry_run=True, quiet=True)
            with mock.patch.object(gitlab_vm, "proxmox_find_existing_vm", return_value=None):
                gitlab_vm.create_vm_proxmox(runner_dry, spec, start=True)

            runner_live = gitlab_vm.Runner(dry_run=False, quiet=True)
            api_calls: List[Tuple[str, str]] = []

            def fake_api(s: Dict[str, Any], path: str, *, method: str = "GET", **kw: Any) -> Any:
                api_calls.append((method, path))
                if path.endswith("/clone") or path.endswith("/resize"):
                    return "UPID:pve:task"
                return {}

            with mock.patch.object(gitlab_vm, "proxmox_find_existing_vm", return_value=None), mock.patch.object(
                gitlab_vm, "proxmox_api_request", side_effect=fake_api
            ), mock.patch.object(gitlab_vm, "proxmox_wait_task"):
                gitlab_vm.create_vm_proxmox(runner_live, spec, start=True)

            self.assertEqual(
                api_calls,
                [
                    ("POST", "nodes/pve/qemu/9000/clone"),
                    ("PUT", "nodes/pve/qemu/112/resize"),
                    ("POST", "nodes/pve/qemu/112/config"),
                    ("POST", "nodes/pve/qemu/112/status/start"),
                ],
            )

    def test_virtualbox_create_vm_and_provision_ansible_and_ssh(self) -> None:
        spec = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        spec["vm"]["provider"] = "virtualbox"
        spec["network"]["adapter2"] = {"type": "bridged", "interface": "en0"}
        runner_dry = gitlab_vm.Runner(dry_run=True, quiet=True)
        with mock.patch("shutil.which", return_value="/usr/bin/mock"):
            gitlab_vm.create_vm(runner_dry, spec, start=True, provider="virtualbox")

        # Existing VirtualBox VM branch
        runner_live = gitlab_vm.Runner(dry_run=False, quiet=True)
        with mock.patch("shutil.which", return_value="/usr/bin/mock"), mock.patch.object(
            gitlab_vm, "ensure_ssh_keypair", return_value=(Path("/tmp/id"), "ssh-ed25519 AAAA")
        ), mock.patch.object(gitlab_vm, "vm_exists", return_value=True), mock.patch.object(
            gitlab_vm, "get_vm_state", return_value="poweroff"
        ), mock.patch.object(runner_live, "run") as mock_run:
            gitlab_vm.create_vm(runner_live, spec, start=True, provider="virtualbox")
            mock_run.assert_called_once_with(["VBoxManage", "startvm", "gitlab-server", "--type", "headless"])

        # Provisioning via ansible and ssh
        with mock.patch.object(gitlab_vm, "wait_for_ssh"):
            gitlab_vm.provision_gitlab(runner_dry, spec, provisioner="ansible", provider="virtualbox")
            gitlab_vm.provision_gitlab(runner_dry, spec, provisioner="ssh", provider="proxmox")

    def test_cli_subcommands_start_stop_ssh_destroy_and_url_banner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_file = Path(tmp) / "vm-spec.yaml"
            spec_file.write_text(gitlab_vm.STARTER_SPEC_YAML, encoding="utf-8")
            existing = {"vmid": 112, "name": "gitlab-server", "status": "running", "node": "pve"}
            fake_details = {
                "provider": "proxmox",
                "vm_name": "gitlab-server",
                "vm_state": "running",
                "proxmox_node": "pve",
                "proxmox_vmid": 112,
                "guest_ip": "192.168.1.250",
                "gitlab_web_url": "http://192.168.1.250:8080",
                "gitlab_sign_in_url": "http://192.168.1.250:8080/users/sign_in",
                "gitlab_git_ssh_url": "git@192.168.1.250:<namespace>/<project>.git",
                "vm_ssh_command": "ssh -i key -p 22 ubuntu@192.168.1.250",
                "username": "root",
                "initial_root_password": "GitLabRoot!2026",
                "http_ready": True,
                "http_status": 200,
            }
            out = io.StringIO()
            with mock.patch.object(gitlab_vm, "proxmox_find_existing_vm", return_value=existing), mock.patch.object(
                gitlab_vm, "proxmox_get_guest_ip", return_value="192.168.1.250"
            ), mock.patch.object(
                gitlab_vm, "discover_connection_details", return_value=fake_details
            ), mock.patch.object(gitlab_vm, "proxmox_api_request"), redirect_stdout(out), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "url"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "-q", "start"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "-q", "stop"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "--dry-run", "-q", "ssh"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "--dry-run", "-q", "start"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "--dry-run", "-q", "stop"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "--dry-run", "-q", "destroy", "--force"]), 0)
                with mock.patch("time.sleep"):
                    self.assertEqual(gitlab_vm.main(["-c", str(spec_file), "destroy", "--force"]), 0)
            self.assertIn("GITLAB PROXMOX VE SERVER - CONNECTION DETAILS", out.getvalue())

    def test_vbox_helpers_and_proxmox_discovery_live_branches(self) -> None:
        list_proc = subprocess.CompletedProcess(
            ["VBoxManage"], 0, stdout='"gitlab-server" {1111-2222}\n', stderr=""
        )
        info_proc = subprocess.CompletedProcess(
            ["VBoxManage"], 0, stdout='VMState="running"\n"Forwarding(0)"="http,tcp,0.0.0.0,8080,,8080"\n', stderr=""
        )
        with mock.patch("subprocess.run", return_value=list_proc):
            self.assertTrue(gitlab_vm.vm_exists("gitlab-server"))
            self.assertFalse(gitlab_vm.vm_exists("other-vm"))
        with mock.patch("subprocess.run", return_value=info_proc):
            self.assertEqual(gitlab_vm.get_vm_state("gitlab-server"), "running")

        # Missing VBoxManage / qemu-img errors
        spec_vbox = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        spec_vbox["vm"]["provider"] = "virtualbox"
        runner = gitlab_vm.Runner(dry_run=True, quiet=True)
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "VBoxManage CLI not found"):
                gitlab_vm.create_vm(runner, spec_vbox, provider="virtualbox")
        with mock.patch("shutil.which", side_effect=lambda b: "/bin/vbox" if b == "VBoxManage" else None):
            with self.assertRaisesRegex(RuntimeError, "qemu-img not found"):
                gitlab_vm.create_vm(runner, spec_vbox, provider="virtualbox")

        # Proxmox discover_connection_details with HTTP 200 and fallback status/current
        spec_pve = gitlab_vm._simple_yaml_parse(gitlab_vm.STARTER_SPEC_YAML)
        spec_pve["proxmox"]["api_token"] = "tok"

        def fallback_api(s: Dict[str, Any], path: str, **kw: Any) -> Any:
            if path == "nodes/pve/qemu":
                raise RuntimeError("list restricted")
            if path == "nodes/pve/qemu/112/status/current":
                return {"status": "running", "name": "gitlab-server"}
            return {}

        with mock.patch.object(gitlab_vm, "proxmox_api_request", side_effect=fallback_api):
            found = gitlab_vm.proxmox_find_existing_vm(spec_pve)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found["status"], "running")

        class FakeHttpResp:
            status = 200

            def __enter__(self) -> "FakeHttpResp":
                return self

            def __exit__(self, *args: Any) -> None:
                pass

        with mock.patch.object(gitlab_vm, "proxmox_find_existing_vm", return_value=found), mock.patch.object(
            gitlab_vm, "proxmox_get_guest_ip", return_value="192.168.1.250"
        ), mock.patch("urllib.request.urlopen", return_value=FakeHttpResp()):
            details = gitlab_vm.discover_connection_details(spec_pve, provider="proxmox")
            self.assertTrue(details["http_ready"])
            self.assertEqual(details["gitlab_web_url"], "http://192.168.1.250:8080")

        # VirtualBox main subcommands (create-vm, provision, start, stop, destroy)
        with tempfile.TemporaryDirectory() as tmp:
            vbox_spec_file = Path(tmp) / "vbox-spec.yaml"
            vbox_spec_file.write_text(
                gitlab_vm.STARTER_SPEC_YAML.replace('provider: "proxmox"', 'provider: "virtualbox"'),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), mock.patch.object(
                gitlab_vm, "create_vm"
            ), mock.patch.object(gitlab_vm, "provision_gitlab"):
                self.assertEqual(gitlab_vm.main(["-c", str(vbox_spec_file), "-q", "create-vm"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(vbox_spec_file), "-q", "provision"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(vbox_spec_file), "--dry-run", "-q", "start"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(vbox_spec_file), "--dry-run", "-q", "stop"]), 0)
                self.assertEqual(gitlab_vm.main(["-c", str(vbox_spec_file), "--dry-run", "-q", "destroy"]), 0)


if __name__ == "__main__":
    unittest.main()
