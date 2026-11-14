from datetime import datetime, timezone
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator

if __package__:
    from .helpers import mask_sensitive_string
else:
    from helpers import mask_sensitive_string


class StatusModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class DiskInfo(StatusModel):
    filesystem: str | None = None
    type: str | None = None
    size_str: str | None = None
    size: float | None = None  # GiB
    used_str: str | None = None
    used: float | None = None  # GiB
    avail_str: str | None = None
    avail: float | None = None  # GiB
    usage_str: str | None = None
    usage: float | None = None  # range: [0, 1]
    mounted_on: str | None = None


class GPUStatus(StatusModel):
    index: int | None = None
    gpu_name: str | None = None
    gpu_usage: float | None = None  # range: [0, 1]
    temperature: float | None = None  # Celsius
    memory_free: float | None = None  # MB
    memory_total: float | None = None  # MB
    memory_usage: float | None = None  # range: [0, 1]


class GPUComputeProcess(StatusModel):
    pid: int | None = None
    user: str | None = None
    gpu_uuid: str | None = None
    gpu_index: int | None = None
    gpu_mem_used: float | None = None  # MiB
    gpu_mem_unit: str = "MiB"
    gpu_mem_usage: float | None = None  # range: [0, 1]
    cpu_usage: float | None = None  # range: [0, 1]
    cpu_mem_usage: float | None = None  # range: [0, 1]
    proc_uptime: float | None = None  # seconds
    proc_uptime_unit: str = "seconds"
    proc_uptime_str: str | None = None  # HH:MM:SS
    command: str | None = None


class MachineStatus(StatusModel):
    created_at: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    name: str | None = None
    machine_id: str | None = None
    report_key: str | None = None
    # ip
    hostname: str | None = None
    local_ip: str | None = None
    public_ip: str | None = None
    ipv4s: list | None = None
    ipv6s: list | None = None
    # sys info
    architecture: str | None = None
    mac_address: str | None = None
    platform: str | None = None
    platform_release: str | None = None
    platform_version: str | None = None
    linux_distro: str | None = None
    processor: str | None = None
    uptime: float | None = None  # seconds
    uptime_unit: str = "seconds"
    uptime_str: str | None = None
    # sys usage
    cpu_model: str | None = None
    cpu_cores: int | None = None
    cpu_usage: float | None = None  # range: [0, 1]
    ram_free: float | None = None  # MiB
    ram_total: float | None = None  # MiB
    ram_unit: str = "MiB"
    ram_usage: float | None = None  # range: [0, 1]
    # disk info
    disk_info: List[DiskInfo] | None = None
    # gpu usage
    gpu_status: List[GPUStatus] | None = None
    gpu_compute_processes: List[GPUComputeProcess] | None = None
    users_info: Dict[str, List[str]] = Field(default_factory=dict)

    @field_validator("users_info", mode="before")
    @classmethod
    def default_users_info(cls, value):
        return {} if value is None else value

    @field_validator("users_info")
    @classmethod
    def process_users_info(cls, value):
        return {
            key: [mask_sensitive_string(user) for user in users]
            for key, users in value.items()
        }

    def __repr__(self) -> str:
        return self.model_dump_json()

    def __str__(self) -> str:
        return self.__repr__()
