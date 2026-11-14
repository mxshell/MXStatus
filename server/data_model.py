from datetime import datetime, timezone
from typing import List, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .helpers import mask_sensitive_string


class StatusModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class DiskInfo(StatusModel):
    filesystem: Union[str, None] = None
    type: Union[str, None] = None
    size_str: Union[str, None] = None
    size: Union[float, None] = None  # GiB
    used_str: Union[str, None] = None
    used: Union[float, None] = None  # GiB
    avail_str: Union[str, None] = None
    avail: Union[float, None] = None  # GiB
    usage_str: Union[str, None] = None
    usage: Union[float, None] = None  # range: [0, 1]
    mounted_on: Union[str, None] = None


class GPUStatus(StatusModel):
    index: Union[int, None] = None
    gpu_name: Union[str, None] = None
    gpu_usage: Union[float, None] = None  # range: [0, 1]
    temperature: Union[float, None] = None  # Celsius
    memory_free: Union[float, None] = None  # MB
    memory_total: Union[float, None] = None  # MB
    memory_usage: Union[float, None] = None  # range: [0, 1]


class GPUComputeProcess(StatusModel):
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


class MachineStatus(StatusModel):
    created_at: Union[datetime, None] = None
    name: Union[str, None] = None
    machine_id: Union[str, None] = Field(default=None, max_length=256)
    report_key: Union[str, None] = Field(
        default=None, exclude=True, repr=False, max_length=64
    )
    # ip
    hostname: Union[str, None] = None
    local_ip: Union[str, None] = None
    public_ip: Union[str, None] = None
    ipv4s: Union[list[tuple[str, str]], None] = None
    ipv6s: Union[list[tuple[str, str]], None] = None
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
    # disk info
    disk_info: Union[List[DiskInfo], None] = None
    # gpu usage
    gpu_status: Union[List[GPUStatus], None] = None
    gpu_compute_processes: Union[List[GPUComputeProcess], None] = None
    # Validate the collection before masking, without mutating the input mapping.
    users_info: dict[str, list[str]] = Field(default_factory=dict)

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


##################################################################
### Web


class ViewGroup(BaseModel):
    view_key: Union[str, None] = None
    view_name: Union[str, None] = None
    view_desc: Union[str, None] = None
    view_enabled: bool = True
    view_machines: List[str] = Field(default_factory=list)
    view_timer: Union[datetime, None] = None

    @field_validator("view_machines", mode="before")
    @classmethod
    def default_view_machines(cls, value):
        return [] if value is None else value

    @field_validator("view_timer")
    @classmethod
    def normalize_timer(cls, value):
        if value is not None:
            # Legacy timestamps without an offset are interpreted as UTC.
            return (
                value.replace(tzinfo=timezone.utc)
                if value.tzinfo is None
                else value.astimezone(timezone.utc)
            )
        return value

    def __repr__(self) -> str:
        return self.model_dump_json()

    def __str__(self) -> str:
        return self.__repr__()
