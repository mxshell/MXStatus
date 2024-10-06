from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, validator

from .helpers import mask_sensitive_string


class GPUStatus(BaseModel):
    index: Union[int, None] = None
    gpu_name: Union[str, None] = None
    gpu_usage: Union[float, None] = None  # range: [0, 1]
    temperature: Union[float, None] = None  # Celsius
    memory_free: Union[float, None] = None  # MB
    memory_total: Union[float, None] = None  # MB
    memory_usage: Union[float, None] = None  # range: [0, 1]


class GPUComputeProcess(BaseModel):
    pid: Union[int, None] = None
    user: Union[str, None] = None
    gpu_uuid: Union[str, None] = None
    gpu_index: Union[int, None] = None
    gpu_mem_used: Union[float, None] = None  # MiB
    gpu_mem_unit: Union[str, None] = None
    gpu_mem_usage: Union[float, None] = None  # range: [0, 1]
    cpu_usage: Union[float, None] = None  # range: [0, 1]
    cpu_mem_usage: Union[float, None] = None  # range: [0, 1]
    proc_uptime: Union[float, None] = None  # seconds
    proc_uptime_unit: Union[str, None] = None
    proc_uptime_str: Union[str, None] = None  # HH:MM:SS
    command: Union[str, None] = None


class MachineStatus(BaseModel):
    created_at: Union[datetime, None] = None
    name: Union[str, None] = None
    machine_id: Union[str, None] = None
    report_key: Union[str, None] = None
    # ip
    hostname: Union[str, None] = None
    local_ip: Union[str, None] = None
    public_ip: Union[str, None] = None
    ipv4s: Union[list, None] = None
    ipv6s: Union[list, None] = None
    # sys info
    architecture: Union[str, None] = None
    mac_address: Union[str, None] = None
    platform: Union[str, None] = None
    platform_release: Union[str, None] = None
    platform_version: Union[str, None] = None
    linux_distro: Union[str, None] = None
    processor: Union[str, None] = None
    uptime: Union[float, None] = None  # seconds
    uptime_unit: Union[str, None] = None
    uptime_str: Union[str, None] = None
    # sys usage
    cpu_model: Union[str, None] = None
    cpu_cores: Union[int, None] = None
    cpu_usage: Union[float, None] = None  # range: [0, 1]
    ram_free: Union[float, None] = None  # MB
    ram_total: Union[float, None] = None  # MB
    ram_unit: Union[str, None] = None
    ram_usage: Union[float, None] = None  # range: [0, 1]
    # gpu usage
    gpu_status: Union[List[GPUStatus], None] = None
    gpu_compute_processes: Union[List[GPUComputeProcess], None] = None
    # users info
    users_info: Union[dict, None] = None

    @validator("created_at", pre=True, always=True)
    def default_created_at(cls, v):
        return v or datetime.now()

    @validator("users_info", pre=True, always=True)
    def process_users_info(cls, v):
        if isinstance(v, dict):
            for keys in v.keys():
                v[keys] = [mask_sensitive_string(user) for user in v[keys]]
            return v
        else:
            return {}

    def __repr__(self) -> str:
        return self.model_dump_json()

    def __str__(self) -> str:
        return self.__repr__()

    @staticmethod
    def dummy() -> "MachineStatus":
        return MachineStatus(
            name="My Dummy Machine",
            machine_id="DUMMY-MACHINE-UUID",
            report_key="DUMMY-REPORT-KEY",
            hostname="my-dummy-machine",
            local_ip="100.100.100.100",
            public_ip="200.200.200.200",
            ipv4s=["100.100.100.100"],
            ipv6s=[],
            architecture="x86_64",
            mac_address="00:11:22:33:44:55",
            platform="Linux",
            platform_release="5.11.0-37-generic",
            platform_version="#41~20.04.2-Ubuntu SMP Fri Oct 8 06:57:59 UTC 2021",
            linux_distro="Ubuntu",
            processor="Intel(R) Core(TM) i5-1035G1 CPU @ 1.00GHz",
            uptime=123456,
            uptime_unit="seconds",
            uptime_str="1d 10h 17m 36s",
            cpu_model="Intel(R) Core(TM) i5-1035G1 CPU @ 1.00GHz",
            cpu_cores=4,
            cpu_usage=0.3,
            ram_free=123456,
            ram_total=123456,
            ram_unit="MB",
            ram_usage=0.5,
            gpu_status=[
                GPUStatus(
                    index=0,
                    gpu_name="NVIDIA GeForce MX330",
                    gpu_usage=0.3,
                    temperature=60.0,
                    memory_free=123456,
                    memory_total=123456,
                    memory_usage=0.5,
                )
            ],
            gpu_compute_processes=[
                GPUComputeProcess(
                    pid=12345,
                    user="user",
                    gpu_uuid="GPU-123456",
                    gpu_index=0,
                    gpu_mem_used=123456,
                    gpu_mem_unit="MB",
                    gpu_mem_usage=0.5,
                    cpu_usage=0.3,
                    cpu_mem_usage=0.5,
                    proc_uptime=123456,
                    proc_uptime_unit="seconds",
                    proc_uptime_str="1d 10h 17m 36s",
                    command="python3 -m http.server",
                )
            ],
            users_info=None,
        )


##################################################################
### Web


class ViewGroup(BaseModel):
    view_key: Union[str, None] = ""
    view_name: Union[str, None] = ""
    view_desc: Union[str, None] = ""
    view_enabled: bool = True
    view_machines: Union[List[str], None] = []
    view_timer: Union[datetime, None] = None
    view_public: bool = False
    view_members: Union[List[str], None] = []

    def __repr__(self) -> str:
        return self.model_dump_json()

    def __str__(self) -> str:
        return self.__repr__()


class ReportKey(BaseModel):
    report_key: Union[str, None] = ""
    report_desc: Union[str, None] = ""
    enabled: bool = True

    def __repr__(self) -> str:
        return self.model_dump_json()

    def __str__(self) -> str:
        return self.__repr__()
