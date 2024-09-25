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


##################################################################
### Web


class ViewGroup(BaseModel):
    view_key: Union[str, None] = ""
    view_name: Union[str, None] = ""
    view_desc: Union[str, None] = ""
    view_enabled: bool = True
    view_machines: Union[List[str], None] = []
    view_timer: Union[datetime, None] = None

    def __repr__(self) -> str:
        return self.model_dump_json()

    def __str__(self) -> str:
        return self.__repr__()


class ReportKey(BaseModel):
    report_key: Union[str, None] = ""
    report_desc: Union[str, None] = ""

    def __repr__(self) -> str:
        return self.model_dump_json()

    def __str__(self) -> str:
        return self.__repr__()
