import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import server.database as db
from server.data_model import MachineStatus, ViewGroup
from server.middleware import RequestSizeLimit

logger = logging.getLogger(__name__)
app = FastAPI()
app.add_middleware(RequestSizeLimit, max_bytes=1024 * 1024)
origins = [
    origin.strip()
    for origin in os.environ.get("MXSTATUS_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.exception_handler(db.DatabaseError)
async def invalid_value(request: Request, exc: db.DatabaseError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(db.ViewNotFoundError)
async def missing_key(request: Request, exc: db.ViewNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "Invalid view key"})


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Pydantic error inputs may contain reporting credentials or private telemetry.
    errors = [
        {key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception):
    logger.error("Unhandled API error", exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


bearer = HTTPBearer(auto_error=False)


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    token = os.environ.get("MXSTATUS_ADMIN_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), token.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


admin = APIRouter(dependencies=[Depends(require_admin)])


@app.get("/")
async def hello():
    return {"msg": "Hello, this is MXShell."}


@admin.get("/get", response_model=list[MachineStatus])
async def get_status():
    return list(db.DB.STATUS_DATA.values())


@app.post("/report", status_code=201)
async def report_status(status: MachineStatus):
    db.store_new_report(status)
    return {"msg": "OK"}


@app.get("/view", response_model=list[MachineStatus])
async def view_status(view_key: str):
    return db.get_view(view_key)


@app.get("/view_machine", response_model=MachineStatus)
async def view_machine(
    view_key: str, machine_id: str, seconds_to_expire: Annotated[int, Query(gt=0)] = 300
):
    """Return 404 for unavailable machines, 417 for stale reports, 418 for missing GPUs."""
    status = db.get_view_machine(view_key, machine_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Machine Not Found")
    if (
        datetime.now(timezone.utc) - status["created_at"]
    ).total_seconds() > seconds_to_expire:
        raise HTTPException(status_code=417, detail="Status Expired; Machine Offline")
    if not status.get("gpu_status"):
        raise HTTPException(status_code=418, detail="GPU Not Available")
    return status


@app.get("/check_view_group", response_model=ViewGroup)
async def check_view_group(view_key: str):
    return db.check_view_group(view_key)


@admin.post("/create_report_key", status_code=201)
async def create_report_key(
    user_id: str, report_key: str = "", report_key_desc: str = ""
):
    return db.create_new_report_key(user_id, report_key, report_key_desc)


@admin.post("/delete_report_key")
async def delete_report_key(user_id: str, report_key: str):
    db.delete_report_key(user_id, report_key)
    return {"msg": "OK"}


@admin.post("/create_view_group", status_code=201, response_model=ViewGroup)
async def create_view_group(user_id: str, view_group: ViewGroup):
    return db.create_new_view_group(user_id, view_group)


@admin.post("/add_machines_to_view_group", response_model=ViewGroup)
async def add_machines_to_view_group(user_id: str, view_key: str, machines: list[str]):
    return db.update_machines_in_view(user_id, view_key, add=machines)


@admin.post("/remove_machines_from_view_group", response_model=ViewGroup)
async def remove_machines_from_view_group(
    user_id: str, view_key: str, machines: list[str]
):
    return db.update_machines_in_view(user_id, view_key, remove=machines)


@admin.post("/set_machines_in_view_group", response_model=ViewGroup)
async def set_machines_in_view_group(user_id: str, view_key: str, machines: list[str]):
    return db.update_machines_in_view(
        user_id, view_key, update=machines, overwrite=True
    )


app.include_router(admin)
