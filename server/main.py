import os
import sys
from datetime import datetime
from logging import DEBUG, INFO
from typing import List, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from puts import get_logger

import server.database as db
from server.data_model import MachineStatus, ViewGroup

logger = get_logger()
logger.setLevel(INFO)

###############################################################################
# Constants

app = FastAPI()
origins = [
    "http://localhost",
    "http://localhost:8080",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# print timezone and current time
print()
logger.info(f"Environ 'TZ'    : {os.environ.get('TZ', 'N.A.')}")
logger.info(f"Current Time    : {datetime.now()}")
logger.info(f"Current UTC Time: {datetime.utcnow()}")
logger.info(f"Python Version  : {sys.version}")
print()


###############################################################################
## ENDPOINTS for DEBUGGING


@app.get("/")
async def hello():
    return {"msg": "Hello, this is MXShell."}


@app.get("/get", response_model=List[MachineStatus])
async def get_status():
    """Temporary endpoint for testing, will deprecated soon"""
    return list(db.DB.STATUS_DATA.values())


###############################################################################
## ENDPOINTS


@app.post("/report", status_code=201)
async def report_status(status: MachineStatus):
    """
    POST Endpoint for receiving status report from client (machines under monitoring).
    Incoming status report needs to have a valid report_key.
    Invalid report_key will be rejected.
    """
    try:
        db.store_new_report(status)
        logger.debug(
            f"Received status report from: {status.name} (report_key: {status.report_key})"
        )
        return {"msg": "OK"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


###############################################################################
## Web ENDPOINTS


@app.get("/view", status_code=200, response_model=List[MachineStatus])
async def view_status(view_key: str):
    """
    GET Endpoint for receiving view request from web (users).
    Incoming view request needs to have a valid view_key.
    """
    try:
        return db.get_view(view_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/view_machine", status_code=200, response_model=MachineStatus)
async def view_machine(view_key: str, machine_id: str, seconds_to_expire: int = 60 * 5):
    """
    GET Endpoint for receiving view_machine request from web (users).
    This endpoint is used to view status of a specific machine and will return
    the status of the machine with the given machine_id.
    The main motivation for this endpoint is for monitoring tools to probe each machine individually.

    Args:
        view_key (str): a valid view_key is required
        machine_id (str): the machine_id of the machine to view, this machine_id
            must be in the view group associated with the view_key
        seconds_to_expire (int): the number of seconds to consider a status report as expired (default: 300 seconds)

    Returns:
        MachineStatus: the status of the machine with the given machine_id

    Status Codes:
        200: OK - Target machine is online and status is returned
        404: Not Found - Invalid view_key or machine_id
        417: Expectation Failed - Target machine is offline or status is expired
        418: I'm a teapot - Target machine's GPU is not available
    """
    try:
        _now = datetime.now()
        status = db.get_view_machine(view_key, machine_id)
        if not status:
            raise HTTPException(status_code=404, detail="Machine Not Found")
        _created_at = status.created_at
        _delta = (_now - _created_at).total_seconds()
        if _delta > seconds_to_expire:
            raise HTTPException(
                status_code=417, detail="Status Expired; Machine Offline"
            )
        _gpu_status = status.gpu_status
        if not _gpu_status:
            raise HTTPException(status_code=418, detail="GPU Not Available")
        return status
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/check_view_group", status_code=200, response_model=ViewGroup)
async def check_view_group(view_key: str):
    try:
        view_group = db.check_view_group(view_key)
        return view_group
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Invalid view key")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


###############################################################################
## Web Admin ENDPOINTS


@app.post("/create_report_key", status_code=201)
async def create_report_key(
    user_id: str,
    report_key: str = "",
    report_key_desc: str = "",
):
    try:
        key_dict = db.create_new_report_key(user_id, report_key, report_key_desc)
        report_key = key_dict.get("report_key", report_key)
        logger.debug(f"New report key ({report_key}) created for user {user_id}")
        return key_dict
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/delete_report_key", status_code=200)
async def delete_report_key(user_id: str, report_key: str):
    try:
        db.delete_report_key(user_id, report_key)
        logger.debug(f"Report key ({report_key}) deleted for {user_id}")
        return {"msg": "OK"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/create_view_group", status_code=201, response_model=ViewGroup)
async def create_view_group(user_id: str, view_group: ViewGroup):
    try:
        view_group = db.create_new_view_group(user_id, view_group)
        logger.debug(f"Created view group: {view_group.view_key} for user {user_id}")
        return view_group
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/add_machines_to_view_group", status_code=200, response_model=ViewGroup)
async def add_machines_to_view_group(user_id: str, view_key: str, machines: List[str]):
    """
    Add machines to a view group.

    Args:
        user_id (str): user id
        view_key (str): view key of the view group
        machines (List[str]): a list of machine_id
    """
    try:
        view_group = db.update_machines_in_view(
            user_id=user_id, view_key=view_key, add=machines
        )
        logger.debug(f"Added machines to view group: {view_key} for {user_id}")
        return view_group
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/remove_machines_from_view_group", status_code=200, response_model=ViewGroup)
async def remove_machines_from_view_group(
    user_id: str, view_key: str, machines: List[str]
):
    """
    Remove machines from a view group.

    Args:
        user_id (str): user id
        view_key (str): view key of the view group
        machines (List[str]): a list of machine_id
    """
    try:
        view_group = db.update_machines_in_view(
            user_id=user_id, view_key=view_key, remove=machines
        )
        logger.debug(f"Removed machines from view group: {view_key} for {user_id}")
        return view_group
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/set_machines_in_view_group", status_code=200, response_model=ViewGroup)
async def set_machines_in_view_group(user_id: str, view_key: str, machines: List[str]):
    """
    Set machines in a view group.

    Args:
        user_id (str): user id
        view_key (str): view key of the view group
        machines (List[str]): a list of machine_id
    """
    try:
        view_group = db.update_machines_in_view(
            user_id=user_id,
            view_key=view_key,
            update=machines,
            overwrite=True,
        )
        logger.debug(f"Set machines in view group: {view_key} for {user_id}")
        return view_group
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
