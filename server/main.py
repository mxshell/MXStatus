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
logger.setLevel(DEBUG)

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
async def read_root():
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


@app.post("/view", status_code=200, response_model=List[MachineStatus])
async def view_status(view_key: str):
    """
    POST Endpoint for receiving view request from web (users).
    Incoming view request needs to have a valid view_key.
    """
    try:
        return db.get_view(view_key)
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
        logger.debug(f"New report key ({report_key}) created for {user_id}")
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


@app.post("/create_view_group", status_code=201)
async def create_view_group(user_id: str, view_group: ViewGroup):
    try:
        db.store_view_group(user_id, view_group)
        logger.debug(f"Created view group: {view_group.view_key} for {user_id}")
        return {"msg": "OK"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/add_machines_to_view_group", status_code=200)
async def add_machines_to_view_group(user_id: str, view_key: str, machines: List[str]):
    """
    Add machines to a view group.

    Args:
        user_id (str): user id
        view_key (str): view key of the view group
        machines (List[str]): a list of machine_id
    """
    try:
        db.update_machines_in_view(user_id=user_id, view_key=view_key, add=machines)
        logger.debug(f"Added machines to view group: {view_key} for {user_id}")
        return {"msg": "OK"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/remove_machines_from_view_group", status_code=200)
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
        db.update_machines_in_view(user_id=user_id, view_key=view_key, remove=machines)
        logger.debug(f"Removed machines from view group: {view_key} for {user_id}")
        return {"msg": "OK"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/set_machines_in_view_group", status_code=200)
async def set_machines_in_view_group(user_id: str, view_key: str, machines: List[str]):
    """
    Set machines in a view group.

    Args:
        user_id (str): user id
        view_key (str): view key of the view group
        machines (List[str]): a list of machine_id
    """
    try:
        db.update_machines_in_view(
            user_id=user_id,
            view_key=view_key,
            update=machines,
            overwrite=True,
        )
        logger.debug(f"Set machines in view group: {view_key} for {user_id}")
        return {"msg": "OK"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
