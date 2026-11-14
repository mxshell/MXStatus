import csv
import datetime
import ipaddress
import json
import math
import os
import platform
import re
import shlex
import socket
import subprocess
import sys
import time
import uuid
from logging import DEBUG, INFO
from pathlib import Path
from time import sleep
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit

import psutil
import requests
from puts import get_logger

if __package__:
    from .data_model import GPUComputeProcess, GPUStatus, MachineStatus
    from .helpers import guid
else:
    from data_model import GPUComputeProcess, GPUStatus, MachineStatus
    from helpers import guid

curr_dir = Path(__file__).resolve().parent
CONFIG_PATH = curr_dir / "config.json"

# we get a customised logger from puts with max file size of 10MB
logger = get_logger(max_file_size=10 * 1024 * 1024)  # 10MB
# keep the next line fixed, only configure the logger level from config.json
logger.setLevel(INFO)

REQUEST_TIMEOUT = (5, 15)
COMMAND_TIMEOUT = 10
MAX_RECOVERY_DELAY = 300
configs = {}
REPORT_KEY = ""
INTERVAL = 10
POST_URL = ""
HEADERS = {"Content-type": "application/json", "Accept": "application/json"}
PUBLIC_IP = ""
MACHINE_ID = None
_PROCESS_SAMPLES: dict[int, tuple[float, float, float]] = {}


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config, dict):
        raise ValueError("Config must be a JSON object")
    server = config.get("server_address")
    key = config.get("report_key")
    interval = config.get("report_interval", 10)
    if not isinstance(server, str) or not server.strip():
        raise ValueError("server_address must be a nonempty string")
    server = server.strip().rstrip("/")
    if "://" not in server:
        server = "https://" + server
    parsed = urlsplit(server)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "server_address must be an HTTP(S) URL without credentials, query, or fragment"
        )
    # Accessing port also validates malformed or out-of-range ports.
    parsed.port
    if (
        not isinstance(key, str)
        or not 16 <= len(key) <= 64
        or not key.isascii()
        or not key.isalnum()
    ):
        raise ValueError("report_key must contain 16–64 ASCII letters or digits")
    if (
        isinstance(interval, bool)
        or not isinstance(interval, int)
        or not 1 <= interval <= 86400
    ):
        raise ValueError(
            "report_interval must be an integer between 1 and 86400 seconds"
        )
    return {
        **config,
        "server_address": server,
        "report_key": key,
        "report_interval": interval,
    }


def configure(path: Path = CONFIG_PATH) -> None:
    global configs, REPORT_KEY, INTERVAL, POST_URL, MACHINE_ID
    configs = load_config(path)
    REPORT_KEY = configs["report_key"]
    INTERVAL = configs["report_interval"]
    POST_URL = configs["server_address"] + "/report"
    MACHINE_ID = guid()
    if not MACHINE_ID:
        raise ValueError("Could not determine a stable machine ID")
    logger.setLevel(
        DEBUG if str(configs.get("logger_level", "INFO")).upper() == "DEBUG" else INFO
    )


###############################################################################
## Networks


def google_is_reachable():
    try:
        sock = socket.create_connection(("www.google.com", 80), timeout=5)
        if sock is not None:
            sock.close()
        return True
    except OSError:
        pass
    return False


def is_connected() -> bool:
    # Ref: https://stackoverflow.com/a/40283805
    try:
        sock = socket.create_connection(("1.1.1.1", 53), timeout=5)
        if sock is not None:
            sock.close()
        return True
    except OSError:
        pass
    return False


def get_ip_addresses(family):
    # Ref: https://stackoverflow.com/a/43478599
    for interface, snics in psutil.net_if_addrs().items():
        for snic in snics:
            if snic.family == family:
                yield (interface, snic.address)


def get_ip() -> dict:
    info = {}
    try:
        hostname = socket.gethostname()
        info["hostname"] = hostname
        try:
            info["local_ip"] = socket.gethostbyname(hostname)
        except OSError:
            info["local_ip"] = ""
        info["ipv4s"] = list(get_ip_addresses(socket.AF_INET))
        info["ipv6s"] = list(get_ip_addresses(socket.AF_INET6))
        info["public_ip"] = get_public_ip()
    except Exception as e:
        logger.error(e)
        info["error"] = str(e)
    return info


def get_public_ip() -> str:
    """
    Get the public IP address of the current machine

    To minimize the number of requests, we cache the public IP address once obtained.
    The cache is stored in the global variable `PUBLIC_IP`.
    When the cache is empty, we make a request to ipify.org to get the public IP address.
    The correctness of the IP address is not guaranteed.

    Returns:
        str: public IP address

    Raises:
        Strictly no exception is raised.
    """
    global PUBLIC_IP
    if not PUBLIC_IP:
        try:
            # https://www.ipify.org/
            response = requests.get("https://api64.ipify.org", timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            PUBLIC_IP = str(ipaddress.ip_address(response.text.strip()))
        except Exception as e:
            logger.error(e)

    return PUBLIC_IP


###############################################################################
## TODO


def get_temp_status():
    # linux only
    # TODO
    try:
        temp = psutil.sensors_temperatures()
        return temp
    except Exception as e:
        logger.error(e)


def get_fans_status():
    # linux only
    # TODO
    try:
        fans = psutil.sensors_fans()
        return fans
    except Exception as e:
        logger.error(e)


###############################################################################
## System


def run_command(command: str) -> Tuple[bool, str]:
    """
    Run a shell command and return the output as a string.
    This function wraps `subprocess.run` and handles the exceptions.
    Some commands may not work due to `subprocess.run` is not running in shell mode.

    Args:
        command (str): shell command to run

    Returns:
        success (bool): whether the command is executed successfully
        output (str): output of the command
    """
    try:
        completed_proc = subprocess.run(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=COMMAND_TIMEOUT,
            env={**os.environ, "LC_ALL": "C"},
        )
        if completed_proc.returncode != 0:
            success = False
        else:
            success = True
        output = completed_proc.stdout.decode("utf-8", errors="replace").strip()
    except Exception as e:
        logger.error(e)
        success = False
        output = str(e)

    return success, output


def run_shell_command(command: str) -> Tuple[bool, str]:
    """
    Run a shell command and return the output as a string.
    This function wraps `subprocess.run` and handles the exceptions.
    This function runs `subprocess.run` with `shell=True` to fully emulate shell execution.

    Args:
        command (str): shell command to run

    Returns:
        success (bool): whether the command is executed successfully
        output (str): output of the command
    """
    try:
        completed_proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=COMMAND_TIMEOUT,
            env={**os.environ, "LC_ALL": "C"},
            shell=True,
        )
        output = completed_proc.stdout.decode("utf-8", errors="replace").strip()
        success = completed_proc.returncode == 0
    except Exception as e:
        logger.error(e)
        output = str(e)
        success = False

    return success, output


def _get_sys_uptime() -> Tuple[float, str]:
    """Get the system uptime.
    Compatibility: All mainstream Linux distributions

    Returns:
        float: system uptime in seconds
        str: system uptime in human readable format

    Raises:
        None
    """
    cmd = "cat /proc/uptime"
    success, output = run_command(cmd)
    if not success:
        return -1, "NA"

    try:
        uptime = float(output.split()[0])
    except (ValueError, IndexError):
        return -1, "NA"
    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)

    if days > 0:
        uptime_str = f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        uptime_str = f"{hours}h {minutes}m"
    else:
        uptime_str = f"{minutes}m"

    return uptime, uptime_str


def _get_distro() -> str:
    """Get the name of the Linux distribution.

    Compatibility: All mainstream Linux distributions

    Returns:
        str: name of the Linux distribution

    Raises:
        None
    """
    cmd = "cat /etc/os-release | grep PRETTY_NAME | cut -d '=' -f 2 | tr -d '\"'"
    success, output = run_shell_command(cmd)
    if not success:
        logger.error(f"Error encountered: {output}")
    return output if success else "NA"


def _get_cpu_model() -> str:
    """Get the CPU model name.
    Compatibility: All mainstream Linux distributions

    Returns:
        str: CPU model name

    Raises:
        None
    """
    cmd = "awk -F: '/model name/ {name=$2} END {print name}' /proc/cpuinfo"
    success, output = run_command(cmd)
    return output if success else "NA"


def _get_cpu_cores() -> int:
    """Get the number of CPU cores.
    Compatibility: All mainstream Linux distributions

    Returns:
        int: number of CPU cores

    Raises:
        None
    """
    cmd = "awk -F: '/processor/ {core++} END {print core}' /proc/cpuinfo"
    success, output = run_command(cmd)
    try:
        return int(output) if success else 0
    except ValueError:
        return psutil.cpu_count() or 0


def _get_mac_address() -> str:
    return ":".join(re.findall("..", "%012x" % uuid.getnode()))


def get_sys_info() -> Dict[str, str]:
    info = {}
    try:
        uptime, uptime_str = _get_sys_uptime()
        info = dict(
            uptime=uptime,
            uptime_str=uptime_str,
            platform=platform.system(),
            linux_distro=_get_distro(),
            platform_release=platform.release(),
            platform_version=platform.version(),
            architecture=platform.machine(),
            processor=platform.processor(),
            mac_address=_get_mac_address(),
            cpu_model=_get_cpu_model(),
            cpu_cores=_get_cpu_cores(),
        )
    except Exception as e:
        logger.error(e)
        info["error"] = str(e)
    return info


###############################################################################
## Disk / Storage


def _convert_size_str_to_GiB(size_str: str) -> float:
    """
    Convert the human readable storage size string to a float number in Gigabytes (GiB).
    """
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGTPE]?)", size_str.strip())
    if not match:
        return -1
    powers = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}
    return float(match[1]) * 1024 ** (powers[match[2]] - 3)


def get_disk_info() -> List[Dict[str, Any]]:
    """
    Get the disk information by using
    df -h -x tmpfs -x squashfs -x devtmpfs -x vfat -x efivarfs
    and parse the output.

    Example output from the command:
    ➜ df -x tmpfs -x squashfs -x devtmpfs -x vfat -x efivarfs -hT
    Filesystem     Type  Size  Used Avail Use% Mounted on
    /dev/nvme1n1p3 ext4  3.2T  2.6T  475G  85% /
    /dev/nvme1n1p2 ext4   20G  212M   19G   2% /boot
    /dev/nvme1n1p4 ext4   98G   11M   93G   1% /tmp
    /dev/nvme1n1p6 ext4   32G  3.5G   27G  12% /var/log
    /dev/nvme1n1p5 ext4   49G  6.7M   47G   1% /var/tmp
    /dev/nvme0n1p1 ext4  3.5T  3.2T  151G  96% /home
    /dev/nvme1n1p7 ext4   46G  9.6G   34G  23% /var/log/audit
    /dev/sda1      ext4   33T   17T   15T  53% /mnt/data

    Returned dictionary should be like:
    {
        "filesystem": "/dev/nvme1n1p3",
        "type": "ext4",
        "size_str": "3.2T",
        "size": _convert_size_str_to_GiB("3.2T"),
        "used_str": "2.6T",
        "used": _convert_size_str_to_GiB("2.6T"),
        "avail_str": "475G",
        "avail": _convert_size_str_to_GiB("475G"),
        "usage_str": "85%",
        "usage": 0.85, # range: [0, 1]
        "mounted_on": "/",
    }

    Returns:
        List[Dict[str, Any]]: List of disk information dictionaries.
                             Returns empty list on error or if no disks found.
                             Malformed lines are skipped with debug logging.
    """
    disk_info: List[Dict[str, Any]] = []
    cmd = "df -x tmpfs -x squashfs -x devtmpfs -x vfat -x efivarfs -hPT"
    success, output = run_command(cmd)
    if not success:
        logger.warning(f"Failed to execute df command: {output}")
        return []

    lines = output.split("\n")
    if len(lines) <= 1:
        logger.warning("df command returned no data lines")
        return []

    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        # Handle mount points with spaces by splitting carefully
        # df -hT output format: filesystem type size used avail use% mounted_on
        # The first 6 fields are fixed, but mounted_on can contain spaces
        fields = line.split()
        if len(fields) < 7:
            logger.debug(
                f"Skipping malformed line (expected 7+ fields, got {len(fields)}): {line}"
            )
            continue

        try:
            filesystem = fields[0]
            fs_type = fields[1]
            size_str = fields[2]
            used_str = fields[3]
            avail_str = fields[4]
            usage_str = fields[5]
            # Mount point is everything after the 6th field (handles spaces)
            mounted_on = " ".join(fields[6:])

            # Convert size strings to GiB
            size = _convert_size_str_to_GiB(size_str)
            used = _convert_size_str_to_GiB(used_str)
            avail = _convert_size_str_to_GiB(avail_str)

            # Validate conversions
            if size < 0 or used < 0 or avail < 0:
                logger.debug(f"Skipping disk with invalid size conversion: {line}")
                continue

            # Parse usage percentage
            usage_str_clean = usage_str.strip("% ")
            try:
                usage = float(usage_str_clean) / 100.0
                # Clamp usage to [0, 1] range
                usage = max(0.0, min(1.0, usage))
            except (ValueError, TypeError):
                logger.debug(
                    f"Skipping disk with invalid usage percentage '{usage_str}': {line}"
                )
                continue

            disk_info.append(
                dict(
                    filesystem=filesystem,
                    type=fs_type,
                    size_str=size_str,
                    size=size,
                    used_str=used_str,
                    used=used,
                    avail_str=avail_str,
                    avail=avail,
                    usage_str=usage_str,
                    usage=usage,
                    mounted_on=mounted_on,
                )
            )
        except (ValueError, IndexError, TypeError) as e:
            logger.debug(f"Error parsing disk info line '{line}': {e}")
            continue
        except Exception as e:
            logger.warning(f"Unexpected error parsing disk info line '{line}': {e}")
            continue

    return disk_info


###############################################################################
## Processes


def _get_proc_info(pid: int) -> dict:
    try:
        proc = psutil.Process(pid)
        user = proc.username()
        _create_time = proc.create_time()
        # A new psutil.Process.cpu_percent() always returns zero on its first call.
        # Retain cumulative CPU samples between reports, checking for PID reuse.
        cpu_times = proc.cpu_times()
        cpu_total = cpu_times.user + cpu_times.system
        sampled_at = time.monotonic()
        previous = _PROCESS_SAMPLES.get(pid)
        cpu_usage = None
        if previous and previous[0] == _create_time and sampled_at > previous[1]:
            cpu_usage = round(
                max(0.0, (cpu_total - previous[2]) / (sampled_at - previous[1])), 5
            )
        _PROCESS_SAMPLES[pid] = (_create_time, sampled_at, cpu_total)
        cpu_mem_usage = round(proc.memory_percent() / 100, 5)
        _time_now = time.time()
        proc_uptime: float = _time_now - _create_time  # seconds
        proc_uptime_str = str(datetime.timedelta(seconds=int(proc_uptime)))
        # Process arguments frequently contain credentials; report only the executable name.
        command = proc.name()

        return dict(
            pid=pid,
            user=user,
            cpu_usage=cpu_usage,
            cpu_mem_usage=cpu_mem_usage,
            proc_uptime=proc_uptime,
            proc_uptime_str=proc_uptime_str,
            command=command,
        )
    except Exception as e:
        logger.error(e)

    return None


###############################################################################
## CPU & RAM


def get_sys_usage() -> Dict[str, float]:
    info = {}
    try:
        info["cpu_usage"] = psutil.cpu_percent() / 100  # 0 ~ 1
        mem = psutil.virtual_memory()
        info["ram_total"] = mem.total / (1024.0**2)  # MiB
        info["ram_free"] = mem.available / (1024.0**2)  # MiB
        info["ram_usage"] = round(mem.percent / 100, 5)  # 0 ~ 1
    except Exception as e:
        logger.error(e)
        info["error"] = str(e)
    return info


###############################################################################
## Users


def _get_sudo_users() -> List[str]:
    """
    Get a list of users who have sudo privileges.
    """
    cmd = "awk -F: '/^sudo/ {print $4}' /etc/group"
    success, output = run_command(cmd)
    return list(set(output.split(","))) if success else []


def _get_online_users() -> List[str]:
    """
    Get a list of users who are currently logged in.

    Returns:
        List[str]: a list of usernames

    Raises:
        None, all errors should be handled internally.
    """
    success, output = run_command("users")
    if success:
        return list(set(output.split()))
    else:
        return []


def _get_all_users() -> List[str]:
    """
    Get a list of all users on the system.

    Returns:
        List[str]: a list of usernames

    Raises:
        None, all errors should be handled internally.
    """
    passwd_file = Path("/etc/passwd")
    all_users: List[str] = []

    if not passwd_file.exists():
        return []

    try:
        with passwd_file.open(mode="r") as f:
            lines = f.readlines()

        for line in lines:
            line = str(line).strip()
            if line:
                """
                Ref: https://askubuntu.com/a/725122

                /etc/passwd contains one line for each user account, with seven fields
                delimited by colons (“:”). These fields are:

                0 - login name
                1 - optional encrypted password
                2 - numerical user ID
                3 - numerical group ID
                4 - user name or comment field
                5 - user home directory
                6 - optional user command interpreter
                """
                if line.startswith("#"):
                    continue
                user_data = line.split(":")
                username = user_data[0]
                user_id = user_data[2]
                if 1000 <= int(user_id) <= 60000:
                    all_users.append(username)

        all_users = list(set(all_users))
    except Exception as e:
        logger.error(e)
        all_users = []

    return all_users


def get_users_info() -> Dict[str, List[str]]:
    """
    Get a dictionary containing all users, online users and offline users.

    Returns:
        Dict[str, List[str]]: a dictionary containing all users, online users and offline users.
                              The keys are "all_users", "online_users" and "offline_users".
                              The values are lists of usernames.

    Raises:
        None, all errors should be handled internally.
    """
    online_users = _get_online_users()
    all_users = _get_all_users()
    sudo_users = _get_sudo_users()

    # SECURITY: protect the sudo users from being exposed
    for _sudo_user in sudo_users:
        if _sudo_user in all_users:
            all_users.remove(_sudo_user)
        if _sudo_user in online_users:
            online_users.remove(_sudo_user)

    # make a shallow copy of all_users
    offline_users = all_users[:]
    # get offline users by removing online users
    for u in online_users:
        if u in offline_users:
            offline_users.remove(u)

    return dict(
        all_users=all_users,
        online_users=online_users,
        offline_users=offline_users,
    )


###############################################################################
## GPU


def _nvidia_exist() -> bool:
    """
    Check if nvidia-smi command exists and GPU is detected.

    Returns:
        bool: True if nvidia-smi command exists and GPU is detected.
              False otherwise.
    """
    success, _ = run_command("nvidia-smi")
    return success


def _gpu_number(value: str) -> float | None:
    """Unavailable NVIDIA sensors are reported as N/A or [Not Supported]."""
    try:
        number = float(value.strip().split()[0].rstrip("%"))
        return number if math.isfinite(number) else None
    except (ValueError, IndexError):
        return None


def get_gpu_status() -> List[GPUStatus]:
    """
    Get GPU utilization info via nvidia-smi command call
    """
    cmd = "nvidia-smi --query-gpu=index,gpu_name,utilization.gpu,temperature.gpu,memory.total,memory.used,memory.free --format=csv"
    success, output = run_command(cmd)
    if not success:
        return []

    gpu_status_list: List[GPUStatus] = []
    lines = output.split("\n")
    if len(lines) <= 1:
        return []
    for row in csv.reader(lines[1:]):
        if len(row) != 7:
            continue
        try:
            index = int(row[0].strip())
        except ValueError:
            continue
        utilization, temperature, total, used, free = map(_gpu_number, row[2:])
        gpu_status_list.append(
            GPUStatus(
                index=index,
                gpu_name=row[1].strip(),
                gpu_usage=utilization / 100 if utilization is not None else None,
                temperature=temperature,
                memory_total=total,
                memory_free=free,
                memory_usage=round(used / total, 5)
                if total and total > 0 and used is not None
                else None,
            )
        )

    return gpu_status_list


def _get_gpu_uuid_index_map():
    """
    Get GPU uuid to index map
    """

    cmd = "nvidia-smi --query-gpu=index,uuid --format=csv"
    success, output = run_command(cmd)
    if not success:
        return {}

    gpu_uuid_index_map: Dict[str, int] = {}
    lines = output.split("\n")
    if len(lines) <= 1:
        return {}
    for row in lines[1:]:
        row = row.split(",")
        if len(row) != 2:
            continue
        try:
            gpu_uuid_index_map[row[1].strip()] = int(row[0].strip())
        except ValueError:
            continue

    return gpu_uuid_index_map


def get_gpu_compute_processes() -> List[GPUComputeProcess]:
    cmd = "nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv"
    success, output = run_command(cmd)
    if not success:
        return []

    gpu_compute_processes: List[GPUComputeProcess] = []
    lines = output.split("\n")
    if len(lines) <= 1:
        return []

    gpu_uuid_index_map = _get_gpu_uuid_index_map()

    for row in lines[1:]:
        row = row.split(",")
        if len(row) != 3:
            continue
        gpu_proc = GPUComputeProcess()
        try:
            gpu_proc.pid = int(row[0].strip())
        except ValueError:
            continue
        gpu_proc.gpu_uuid = row[1].strip()
        gpu_proc.gpu_index = gpu_uuid_index_map.get(gpu_proc.gpu_uuid, -1)
        gpu_proc.gpu_mem_used = _gpu_number(row[2])
        # TODO: compute gpu memory usage percentage
        ...

        # get more details of the process from ps
        proc_info: dict = _get_proc_info(gpu_proc.pid)
        if not proc_info:
            # NOTE: if no process info found, likely it is a zombie process
            proc_info = dict()
            # TODO: maybe a way to handle zombie process or notify the user

        gpu_proc.user = proc_info.get("user", "[zombie]")
        gpu_proc.cpu_usage = proc_info.get("cpu_usage", 0)
        gpu_proc.cpu_mem_usage = proc_info.get("cpu_mem_usage", 0)
        gpu_proc.proc_uptime = proc_info.get("proc_uptime", 0)
        gpu_proc.proc_uptime_str = proc_info.get("proc_uptime_str", "NA")
        gpu_proc.command = proc_info.get("command", "NA")

        gpu_compute_processes.append(gpu_proc)

    active_pids = {process.pid for process in gpu_compute_processes}
    for pid in set(_PROCESS_SAMPLES) - active_pids:
        del _PROCESS_SAMPLES[pid]
    return gpu_compute_processes


###############################################################################
## get status


def get_status() -> MachineStatus:
    ip = get_ip()
    sys_info = get_sys_info()
    sys_usage = get_sys_usage()
    disk_info = get_disk_info()

    display_name = str(configs.get("display_name", "")).strip()

    status: MachineStatus = MachineStatus()
    # Custom Machine Name
    status.name = display_name if display_name else ip.get("hostname", "")
    status.machine_id = MACHINE_ID
    status.report_key = REPORT_KEY

    # TODO FIXME: need to update the data model to support display_note and display_warning
    # consider to use a flexible payload dictionary to store flexible fields
    # status.display_note = display_note
    # status.display_warning = display_warning
    # Networks
    status.hostname = ip.get("hostname", "")
    status.local_ip = ip.get("local_ip", "")
    status.public_ip = ip.get("public_ip", "")
    status.ipv4s = ip.get("ipv4s", [])
    status.ipv6s = ip.get("ipv6s", [])
    # System
    status.architecture = sys_info.get("architecture", "")
    status.mac_address = sys_info.get("mac_address", "")
    status.platform = sys_info.get("platform", "")
    status.platform_release = sys_info.get("platform_release", "")
    status.platform_version = sys_info.get("platform_version", "")
    status.linux_distro = sys_info.get("linux_distro", "")
    status.processor = sys_info.get("processor", "")
    status.uptime = sys_info.get("uptime", 0.0)
    status.uptime_str = sys_info.get("uptime_str", "")
    # CPU
    status.cpu_model = sys_info.get("cpu_model", "")
    status.cpu_cores = sys_info.get("cpu_cores", 0)
    status.cpu_usage = sys_usage.get("cpu_usage")
    # RAM
    status.ram_free = sys_usage.get("ram_free")
    status.ram_total = sys_usage.get("ram_total")
    status.ram_usage = sys_usage.get("ram_usage")
    # Disk
    status.disk_info = disk_info
    # GPU
    if _nvidia_exist():
        status.gpu_status = get_gpu_status()
        status.gpu_compute_processes = get_gpu_compute_processes()
    # USER
    status.users_info = get_users_info()

    return MachineStatus.model_validate(status.__dict__)


###############################################################################
## Main


def report_to_server(status: MachineStatus) -> bool:
    payload = status.model_dump(mode="json", exclude={"created_at"})
    try:
        response = requests.post(
            POST_URL,
            json=payload,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        logger.warning("Could not send status report; will retry")
        return False
    if response.status_code != 201:
        logger.error(f"status_code: {response.status_code}")
        return False
    try:
        remote = response.json().get("config")
        if isinstance(remote, dict) and "report_interval" in remote:
            interval = remote["report_interval"]
            if interval is None:
                interval = configs.get("report_interval", 10)
            if type(interval) is int and 1 <= interval <= 86400:
                global INTERVAL
                INTERVAL = interval
    except (ValueError, AttributeError):
        # Older servers may return a non-JSON acknowledgement.
        pass
    return True


def main(debug_mode: bool = False) -> int:
    try:
        configure()
    except (OSError, ValueError) as exc:
        logger.error(f"Invalid client configuration: {exc}")
        return 1
    recovery_delay = 0  # seconds
    if debug_mode:
        from pprint import pprint

    first_time = True

    while True:
        #######################################################################
        # 1. Report status to server immediately after the script starts
        # 2. On subsequent runs, report status to server after every INTERVAL seconds
        # 3. If any error occurs, wait for (INTERVAL + recovery_delay) seconds before trying again
        if first_time:
            first_time = False
        else:
            # sleep for a while
            logger.info(f"Next status report in {INTERVAL + recovery_delay} seconds...")
            sleep(INTERVAL + recovery_delay)

        #######################################################################
        # Catch all exceptions to prevent the script from crashing
        try:
            ###################################################################
            # Acquire the current status of the machine
            status: MachineStatus = get_status()

            # Debug mode: print the status to the console once and exit
            if debug_mode:
                pprint(status.model_dump(exclude={"report_key"}))
                return 0

            # Post the status to the server
            successful = report_to_server(status)
            if successful:
                logger.info("201 OK. Machine Status posted to server.")
                # Reset the recovery delay to zero
                recovery_delay = 0
            else:
                # Additive recovery delay
                recovery_delay = min(recovery_delay + 5, MAX_RECOVERY_DELAY)

        except Exception as e:
            logger.error(e)
            recovery_delay = min(recovery_delay + 5, MAX_RECOVERY_DELAY)
            if debug_mode:
                logger.exception(e)
                return 1


if __name__ == "__main__":
    sys.exit(main(debug_mode=False))
