import subprocess
import sys


def mask_sensitive_string(value: str) -> str:
    """
    Mask sensitive string
    """
    if value is None:
        return None

    assert isinstance(value, str)

    if len(value) == 0:
        return ""
    elif len(value) <= 2:
        return value[0] + "***"
    elif len(value) <= 4:
        return value[0] + "*" * (len(value) - 2) + value[-1]
    else:
        return value[0:2] + "*" * (len(value) - 3) + value[-1]


def _run(cmd):
    try:
        return subprocess.run(
            cmd, shell=True, capture_output=True, check=True, encoding="utf-8"
        ).stdout.strip()
    except:
        return None


def guid():
    """
    Get the machine's globally unique identifier
    """
    if sys.platform == "darwin":
        return _run(
            "ioreg -d2 -c IOPlatformExpertDevice | awk -F\\\" '/IOPlatformUUID/{print $(NF-1)}'",
        )

    if sys.platform == "win32" or sys.platform == "cygwin" or sys.platform == "msys":
        return _run("wmic csproduct get uuid").split("\n")[2].strip()

    if sys.platform.startswith("linux"):
        return _run("cat /var/lib/dbus/machine-id") or _run("cat /etc/machine-id")

    if sys.platform.startswith("openbsd") or sys.platform.startswith("freebsd"):
        return _run("cat /etc/hostid") or _run("kenv -q smbios.system.uuid")
