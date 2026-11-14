import os
import platform
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from server import database as db
from server.admin_models import (
    ClientDelete,
    ClientSettings,
    ClientUpdate,
    ReportKeyCreate,
    ReportKeyDelete,
    ReportKeyUpdate,
    ServerSettings,
    ViewDelete,
)
from server.data_model import MachineStatus, ViewGroup
from server.security import require_admin

router = APIRouter(
    prefix="/admin/api", dependencies=[Depends(require_admin)], tags=["Administration"]
)
STARTED_AT = time.monotonic()


def default_user() -> str:
    configured = os.environ.get("MXSTATUS_ADMIN_USER_ID", "1000")
    return configured if configured in db.DB.UID_USERS else next(iter(db.DB.UID_USERS))


@router.get("/state")
async def state():
    now = datetime.now(timezone.utc)
    keys = []
    machine_keys: dict[str, list[str]] = {}
    owners: dict[str, str] = {}
    for uid, report_keys in db.DB.USER_REPORT_KEYS.items():
        for key, description in report_keys.items():
            machines = sorted(db.DB.ALL_REPORT_KEYS.get(key, set()))
            keys.append(
                {
                    "report_key": key,
                    "report_key_desc": description,
                    "user_id": uid,
                    "machines": machines,
                }
            )
            for machine in machines:
                machine_keys.setdefault(machine, []).append(key)
                owners[machine] = uid
    clients = []
    for machine_id in sorted(machine_keys):
        report = db.get_report(machine_id)
        settings = db.DB.CLIENT_SETTINGS.get(machine_id, ClientSettings())
        age = max(0, (now - report["created_at"]).total_seconds()) if report else None
        status = (
            "blocked"
            if not settings.enabled
            else "waiting"
            if age is None
            else "online"
            if age <= db.DB.SETTINGS.offline_after_seconds
            else "offline"
        )
        clients.append(
            {
                "machine_id": machine_id,
                "user_id": owners[machine_id],
                "report_keys": machine_keys[machine_id],
                "settings": settings.model_dump(),
                "status": status,
                "age_seconds": age,
                "report": MachineStatus.model_validate(report).model_dump(mode="json")
                if report
                else None,
            }
        )
    return {
        "server_time": now.isoformat(),
        "user_id": default_user(),
        "users": sorted(db.DB.UID_USERS),
        "settings": db.DB.SETTINGS.model_dump(),
        "clients": clients,
        "report_keys": keys,
        "view_groups": [
            {
                **ViewGroup.model_validate(group).model_dump(mode="json"),
                "user_id": db.view_owner(key),
            }
            for key, group in db.DB.ALL_VIEW_KEYS.items()
        ],
        "runtime": {
            "persistent": db.DB.store.persistent,
            "python": platform.python_version(),
            "uptime_seconds": int(time.monotonic() - STARTED_AT),
            "cors_origins": [
                origin.strip()
                for origin in os.environ.get("MXSTATUS_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ],
            "version": "0.1.0",
            "workers": 1,
        },
    }


@router.post("/settings")
async def save_settings(settings: ServerSettings):
    return db.update_settings(settings)


@router.post("/clients/update")
async def update_client(settings: ClientUpdate):
    db.update_client(
        settings.machine_id,
        ClientSettings.model_validate(settings.model_dump(exclude={"machine_id"})),
    )
    return {"msg": "Client settings saved"}


@router.post("/clients/delete")
async def delete_client(client: ClientDelete):
    db.forget_client(client.machine_id)
    return {"msg": "Client forgotten"}


@router.post("/keys", status_code=201)
async def create_key(key: ReportKeyCreate):
    return db.create_new_report_key(
        key.user_id or default_user(), key.report_key, key.report_key_desc
    )


@router.post("/keys/update")
async def update_key(key: ReportKeyUpdate):
    db.update_report_key(key.report_key, key.report_key_desc)
    return {"msg": "Key updated"}


@router.post("/keys/delete")
async def delete_key(key: ReportKeyDelete):
    owner = db._report_owner(db.normalize_key(key.report_key))
    if owner is None:
        raise db.DatabaseError("Unknown report key")
    db.delete_report_key(owner, key.report_key)
    return {"msg": "Key revoked"}


@router.post("/views", status_code=201)
async def create_view(group: ViewGroup, user_id: str | None = None):
    return db.create_new_view_group(user_id or default_user(), group)


@router.post("/views/update")
async def update_view(group: ViewGroup):
    return db.edit_view_group(group)


@router.post("/views/delete")
async def delete_view(group: ViewDelete):
    db.delete_view_group(group.view_key)
    return {"msg": "View group deleted"}
