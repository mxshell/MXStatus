import json
import subprocess
from types import SimpleNamespace

import pytest
import requests

from client import helpers
from client import main as client
from client.data_model import MachineStatus


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", 0),
        ("512", 512 / 1024**3),
        ("1K", 1 / 1024**2),
        ("2M", 2 / 1024),
        ("3G", 3),
        ("1T", 1024),
        ("1P", 1024**2),
        ("bad", -1),
    ],
)
def test_disk_size_conversion(value, expected):
    assert client._convert_size_str_to_GiB(value) == expected


def test_disk_full_and_mountpoint_spaces(monkeypatch):
    monkeypatch.setattr(
        client,
        "run_command",
        lambda cmd: (
            True,
            "Filesystem Type Size Used Avail Use% Mounted on\n/dev/sda1 ext4 1T 1T 0 100% /mnt/full disk\nbad line",
        ),
    )
    result = client.get_disk_info()
    assert len(result) == 1
    assert result[0]["avail"] == 0
    assert result[0]["usage"] == 1
    assert result[0]["mounted_on"] == "/mnt/full disk"


def test_gpu_unsupported_sensors_do_not_abort_report(monkeypatch):
    output = """index,name,usage,temp,total,used,free
0,"GPU, Model",N/A,[Not Supported],0 MiB,0 MiB,0 MiB
1,Working,50 %,70,1024 MiB,512 MiB,512 MiB
bad,row
2,Partial,NaN,inf,N/A,N/A,N/A"""
    monkeypatch.setattr(client, "run_command", lambda cmd: (True, output))
    result = client.get_gpu_status()
    assert len(result) == 3
    assert result[0].gpu_name == "GPU, Model"
    assert result[0].gpu_usage is None
    assert result[0].memory_usage is None
    assert result[1].memory_usage == 0.5
    assert result[2].temperature is None


def test_gpu_process_unavailable_memory_and_exited_process(monkeypatch):
    monkeypatch.setattr(
        client,
        "run_command",
        lambda cmd: (True, "pid,uuid,memory\n123,GPU-123,[N/A]\ninvalid,GPU-123,1 MiB"),
    )
    monkeypatch.setattr(client, "_get_gpu_uuid_index_map", lambda: {})
    monkeypatch.setattr(client, "_get_proc_info", lambda pid: None)
    result = client.get_gpu_compute_processes()
    assert len(result) == 1
    assert result[0].gpu_mem_used is None
    assert result[0].gpu_index == -1


@pytest.mark.parametrize("runner", [client.run_command, client.run_shell_command])
def test_commands_have_timeout_and_report_nonzero_exit(monkeypatch, runner):
    calls = []

    def run(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=1, stdout=b"failed\xff")

    monkeypatch.setattr(client.subprocess, "run", run)
    assert runner("false")[0] is False
    assert calls[0]["timeout"] == client.COMMAND_TIMEOUT
    assert calls[0]["env"]["LC_ALL"] == "C"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test", 10)

    monkeypatch.setattr(client.subprocess, "run", timeout)
    assert runner("false")[0] is False


def test_reporting_has_timeout_disables_redirects_and_keeps_input(monkeypatch):
    status = MachineStatus(machine_id="m", report_key="secret")
    created = status.created_at

    def post(url, **kwargs):
        assert kwargs["timeout"] == client.REQUEST_TIMEOUT
        assert kwargs["allow_redirects"] is False
        assert "created_at" not in kwargs["json"]
        assert kwargs["json"]["report_key"] == "secret"
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr(client.requests, "post", post)
    assert client.report_to_server(status)
    assert status.created_at == created

    def timeout(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr(client.requests, "post", timeout)
    assert not client.report_to_server(status)


def test_public_ip_only_caches_successful_ip_values(monkeypatch):
    monkeypatch.setattr(client, "PUBLIC_IP", "")
    monkeypatch.setattr(
        client.requests,
        "get",
        lambda *a, **kw: SimpleNamespace(
            raise_for_status=lambda: None, text="not an IP"
        ),
    )
    assert client.get_public_ip() == ""
    monkeypatch.setattr(
        client.requests,
        "get",
        lambda *a, **kw: SimpleNamespace(
            raise_for_status=lambda: None, text="203.0.113.1\n"
        ),
    )
    assert client.get_public_ip() == "203.0.113.1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"report_interval": 0},
        {"report_interval": -1},
        {"report_interval": True},
        {"report_interval": "10"},
        {"report_key": None},
        {"server_address": None},
        {"server_address": "ftp://host"},
        {"server_address": "https://user:pass@host"},
        {"server_address": "https://host:99999"},
    ],
)
def test_bad_configuration_is_rejected(tmp_path, overrides):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"server_address": "example.com", "report_key": "A" * 32, **overrides}
        )
    )
    with pytest.raises(ValueError):
        client.load_config(path)


def test_config_normalizes_server(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"server_address": "example.com/", "report_key": "A" * 32})
    )
    assert client.load_config(path)["server_address"] == "https://example.com"


def test_missing_machine_id_fails_startup(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"server_address": "example.com", "report_key": "A" * 32})
    )
    monkeypatch.setattr(client, "guid", lambda: None)
    with pytest.raises(ValueError, match="machine ID"):
        client.configure(path)


def test_windows_guid_handles_command_failure(monkeypatch):
    monkeypatch.setattr(helpers.sys, "platform", "win32")
    monkeypatch.setattr(helpers, "_run", lambda cmd: None)
    assert helpers.guid() is None
    monkeypatch.setattr(helpers, "_run", lambda cmd: "UUID\n\n123456\n")
    assert helpers.guid() == "123456"


def test_reporting_does_not_depend_on_google_and_backoff_is_bounded(monkeypatch):
    monkeypatch.setattr(client, "configure", lambda: None)
    monkeypatch.setattr(client, "INTERVAL", 1)
    monkeypatch.setattr(client, "MAX_RECOVERY_DELAY", 10)
    monkeypatch.setattr(client, "get_status", lambda: MachineStatus())
    monkeypatch.setattr(
        client,
        "google_is_reachable",
        lambda: pytest.fail("Should only depend on configured server"),
    )
    outcomes = iter([False, False, False, True])
    monkeypatch.setattr(client, "report_to_server", lambda status: next(outcomes))
    delays = []

    def sleep(seconds):
        delays.append(seconds)
        if len(delays) == 4:
            raise KeyboardInterrupt()

    monkeypatch.setattr(client, "sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        client.main()
    assert delays == [6, 11, 11, 1]


def test_process_cpu_samples_and_pid_reuse(monkeypatch):
    monkeypatch.setattr(client, "_PROCESS_SAMPLES", {})
    sample = {"created": 10, "cpu": 1, "now": 100}
    proc = SimpleNamespace(
        username=lambda: "user",
        name=lambda: "worker",
        create_time=lambda: sample["created"],
        memory_percent=lambda: 5,
        cpu_times=lambda: SimpleNamespace(user=sample["cpu"], system=0),
    )
    monkeypatch.setattr(client.psutil, "Process", lambda pid: proc)
    monkeypatch.setattr(client.time, "monotonic", lambda: sample["now"])
    assert client._get_proc_info(12)["cpu_usage"] is None
    sample.update(cpu=2, now=102)
    info = client._get_proc_info(12)
    assert info["cpu_usage"] == 0.5
    assert info["command"] == "worker"
    sample.update(created=20, cpu=0, now=103)
    assert client._get_proc_info(12)["cpu_usage"] is None


def test_client_payload_roundtrip_with_partial_metrics(api, registered, monkeypatch):
    key, view = registered
    monkeypatch.setattr(client, "REPORT_KEY", key)
    monkeypatch.setattr(client, "MACHINE_ID", "machine-1")
    monkeypatch.setattr(client, "get_ip", lambda: {"ipv4s": [("eth0", "10.0.0.1")]})
    monkeypatch.setattr(client, "get_sys_info", lambda: {})
    monkeypatch.setattr(client, "get_sys_usage", lambda: {})
    monkeypatch.setattr(client, "get_disk_info", lambda: [{"avail": 0, "usage": 1}])
    monkeypatch.setattr(client, "_nvidia_exist", lambda: False)
    monkeypatch.setattr(client, "get_users_info", lambda: {"all_users": ["alice"]})
    status = client.get_status()
    response = api.post("/report", json=status.model_dump(mode="json"))
    assert response.status_code == 201, response.text
    report = api.get("/view", params={"view_key": view}).json()[0]
    assert report["ram_usage"] is None
    assert report["disk_info"][0]["avail"] == 0
    assert report["users_info"]["all_users"] == ["al**e"]
