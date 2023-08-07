import argparse
import datetime
import json
import platform
import re
import shlex
import socket
import subprocess
import sys
import time
import uuid
from logging import INFO
from pathlib import Path
from time import sleep
from typing import Dict, List, Tuple

import psutil
import requests
from puts import get_logger, json_serial

from data_model import GPUComputeProcess, GPUStatus, MachineStatus

logger = get_logger()
logger.setLevel(INFO)

###############################################################################
## Get Argument Parser

parser = argparse.ArgumentParser()
parser.add_argument(
    "-i",
    "--interval",
    dest="interval",
    default=5,
    help="Interval in number of seconds",
)
parser.add_argument(
    "-n",
    "--name",
    dest="name",
    default="Default",
    help="Name of current machine",
)
parser.add_argument(
    "-s",
    "--server",
    dest="server",
    default="http://127.0.0.1:5000",
    help="Server address",
)

args = parser.parse_args()

# get value from parser
INTERVAL = int(args.interval)
MACHINE_NAME = str(args.name)
SERVER = str(args.server)

###############################################################################
## Constants

if SERVER.endswith("/"):
    SERVER = SERVER[:-1]
POST_URL = SERVER + "/post"
HEADERS = {"Content-type": "application/json", "Accept": "application/json"}
PUBLIC_IP: str = ""


###############################################################################
## Networks


def is_connected() -> bool:
    # https://stackoverflow.com/a/40283805
    try:
        # connect to the host -- tells us if the host is actually reachable
        socket.create_connection(("1.1.1.1", 53))
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


def get_ip() -> str:
    info = {}
    try:
        hostname = socket.gethostname()
        info["hostname"] = hostname
        info["local_ip"] = socket.gethostbyname(hostname)
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
            PUBLIC_IP = requests.get("https://api64.ipify.org").content.decode("utf-8")
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
        )
        if completed_proc.returncode != 0:
            success = False
        else:
            output = completed_proc.stdout.decode("utf-8").strip()
            success = True
    except Exception as e:
        logger.error(e)
        success = False
        output = str(e)

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

    uptime = float(output.split()[0])
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
    return int(output) if success else 0


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
## Processes


def _get_proc_info(pid: int) -> dict:
    try:
        proc = psutil.Process(pid)
        user = proc.username()
        cpu_usage = round(proc.cpu_percent() / 100, 5)  # 0 ~ 1
        cpu_mem_usage = round(proc.memory_percent() / 100, 5)  # 0 ~ 1
        _create_time = proc.create_time()
        _time_now = time.time()
        proc_uptime: float = _time_now - _create_time  # seconds
        proc_uptime_str = str(datetime.timedelta(seconds=int(proc_uptime)))
        command = " ".join(proc.cmdline())

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
    completed_proc = subprocess.run(
        "nvidia-smi",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=True,
    )
    return completed_proc.returncode == 0


def get_gpu_status() -> List[GPUStatus]:
    """
    Get GPU utilization info via nvidia-smi command call
    """

    cmd = "nvidia-smi --query-gpu=index,gpu_name,utilization.gpu,temperature.gpu,memory.total,memory.used,memory.free --format=csv"
    completed_proc = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed_proc.returncode != 0:
        return []

    output = completed_proc.stdout.decode("utf-8").strip()
    gpu_status_list: List[GPUStatus] = []
    lines = output.split("\n")
    if len(lines) <= 1:
        return []
    for row in lines[1:]:
        gpu_status = GPUStatus()
        row = row.split(",")
        if len(row) != 7:
            continue
        gpu_status.index = row[0].strip()
        gpu_status.gpu_name = row[1].strip()
        gpu_status.gpu_usage = float(row[2].strip("% ")) / 100
        gpu_status.temperature = float(row[3].strip())
        gpu_status.memory_total = float(row[4].strip(" MiB"))
        gpu_mem_used = float(row[5].strip(" MiB"))
        gpu_status.memory_free = float(row[6].strip(" MiB"))
        # compute used memory percentage
        # value returned by utilization.memory is not accurate
        gpu_status.memory_usage = round(gpu_mem_used / gpu_status.memory_total, 5)
        gpu_status_list.append(gpu_status)

    return gpu_status_list


def _get_gpu_uuid_index_map():
    """
    Get GPU uuid to index map
    """

    cmd = "nvidia-smi --query-gpu=index,uuid --format=csv"
    completed_proc = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed_proc.returncode != 0:
        return {}

    output = completed_proc.stdout.decode("utf-8").strip()
    gpu_uuid_index_map: Dict[str, int] = {}
    lines = output.split("\n")
    if len(lines) <= 1:
        return {}
    for row in lines[1:]:
        row = row.split(",")
        if len(row) != 2:
            continue
        gpu_uuid_index_map[row[1].strip()] = int(row[0].strip())

    return gpu_uuid_index_map


def get_gpu_compute_processes() -> List[GPUComputeProcess]:
    cmd = "nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv"
    completed_proc = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed_proc.returncode != 0:
        return []

    output = completed_proc.stdout.decode("utf-8").strip()
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
        gpu_proc.pid = int(row[0].strip())
        gpu_proc.gpu_uuid = row[1].strip()
        gpu_proc.gpu_index = gpu_uuid_index_map.get(gpu_proc.gpu_uuid, -1)
        gpu_proc.gpu_mem_used = float(row[2].strip(" MiB"))
        # get more details of the process from ps
        proc_info: dict = _get_proc_info(gpu_proc.pid)
        gpu_proc.user = proc_info.get("user", "")
        gpu_proc.cpu_usage = proc_info.get("cpu_usage", "")
        gpu_proc.cpu_mem_usage = proc_info.get("cpu_mem_usage", "")
        gpu_proc.proc_uptime = proc_info.get("proc_uptime", 0)
        gpu_proc.proc_uptime_str = proc_info.get("proc_uptime_str", "")
        gpu_proc.command = proc_info.get("command", "")

        gpu_compute_processes.append(gpu_proc)

    return gpu_compute_processes


###############################################################################
## get status


def get_status() -> MachineStatus:

    ip = get_ip()
    sys_info = get_sys_info()
    sys_usage = get_sys_usage()

    status: MachineStatus = MachineStatus()
    # Custom Machine Name
    status.name = MACHINE_NAME
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
    status.processor = sys_info.get("processor", "")
    status.uptime = sys_info.get("uptime", 0)
    status.uptime_str = sys_info.get("uptime_str", "")
    # CPU
    status.cpu_model = sys_info.get("cpu_model", "")
    status.cpu_cores = sys_info.get("cpu_cores", 0)
    status.cpu_usage = sys_usage.get("cpu_usage", "")
    # RAM
    status.ram_free = sys_usage.get("ram_free", "")
    status.ram_total = sys_usage.get("ram_total", "")
    status.ram_usage = sys_usage.get("ram_usage", "")
    # GPU
    if _nvidia_exist():
        status.gpu_status = get_gpu_status()
        status.gpu_compute_processes = get_gpu_compute_processes()
    # USER
    status.users_info = get_users_info()

    return status


###############################################################################
## Main


def report_to_server(status: MachineStatus) -> bool:
    # remove machine time
    status.created_at = None
    status: dict = dict(status.dict())
    data: str = json.dumps(status, default=json_serial)
    r = requests.post(POST_URL, data=data, headers=HEADERS)
    if r.status_code != 201:
        logger.error(f"status_code: {r.status_code}")
        return False
    else:
        return True


def main(debug_mode: bool = False) -> None:
    retry = 0

    while True:
        sleep(INTERVAL)
        sleep(retry)

        try:
            if not is_connected():
                logger.warning("Not Connected to Internet.")
                retry += 5
                continue

            status: MachineStatus = get_status()
            if debug_mode:
                logger.info(status)
                return

            successful = report_to_server(status)
            if successful:
                retry = 0
                print("201 OK")
            else:
                retry += 5

        except Exception as e:
            logger.error(e)
            # logger.exception(e)
            retry += 5


if __name__ == "__main__":
    main(debug_mode=True)
