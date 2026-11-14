from pydantic import BaseModel, ConfigDict, Field


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_name: str = Field(default="MXStatus", min_length=1, max_length=80)
    offline_after_seconds: int = Field(default=300, ge=10, le=86400, strict=True)
    default_report_interval: int = Field(default=10, ge=1, le=86400, strict=True)
    refresh_interval: int = Field(default=15, ge=5, le=300, strict=True)
    max_machines: int = Field(default=10000, ge=1, le=10000, strict=True)
    accept_new_clients: bool = True


class ClientSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)
    enabled: bool = True
    report_interval: int | None = Field(default=None, ge=1, le=86400, strict=True)


class ClientUpdate(ClientSettings):
    machine_id: str = Field(min_length=1, max_length=256)


class ClientDelete(BaseModel):
    machine_id: str = Field(min_length=1, max_length=256)


class ReportKeyCreate(BaseModel):
    report_key: str = Field(default="", max_length=64)
    report_key_desc: str = Field(default="", max_length=200)
    user_id: str | None = None


class ReportKeyUpdate(BaseModel):
    report_key: str = Field(min_length=1, max_length=64)
    report_key_desc: str = Field(default="", max_length=200)


class ReportKeyDelete(BaseModel):
    report_key: str = Field(min_length=1, max_length=64)


class ViewDelete(BaseModel):
    view_key: str = Field(min_length=1, max_length=64)
