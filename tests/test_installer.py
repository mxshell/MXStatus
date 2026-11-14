import os
import shutil
import subprocess
import sys
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "client" / "installer"


def test_installer_quotes_paths_and_specifiers(tmp_path):
    directory = tmp_path / 'client spaces %n $money "quoted"'
    directory.mkdir()
    script = directory / "installer"
    shutil.copyfile(INSTALLER, script)
    env = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        ["bash", str(script), "dryrun"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    exec_line = next(
        line for line in result.stdout.splitlines() if line.startswith("ExecStart=")
    )
    assert "client spaces %%n $$money" in exec_line
    assert '\\"quoted\\"' in exec_line
    assert "RestartSec=5" in result.stdout


def test_installer_stops_on_failed_privileged_command(tmp_path):
    fake_sudo = tmp_path / "sudo"
    fake_sudo.write_text("#!/bin/sh\nexit 73\n")
    fake_sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": os.pathsep.join(
            [str(tmp_path), str(Path(sys.executable).parent), os.environ["PATH"]]
        ),
    }
    result = subprocess.run(
        ["bash", str(INSTALLER), "install"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "installed successfully" not in result.stdout
