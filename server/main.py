import os
import sys
from datetime import datetime
from logging import DEBUG, INFO

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
## ENDPOINTS


@app.get("/")
async def read_root():
    return {"msg": "Hello World. This is MXSHELL API."}


@app.get("/get")
async def get_status():
    """Temporary endpoint for testing, will deprecated soon"""
    return db.DB.STATUS_DATA


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


@app.post("/view", status_code=200)
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
## Web ENDPOINTS


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
