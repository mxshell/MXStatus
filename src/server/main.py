import os
import sys
from datetime import datetime
from logging import DEBUG, INFO

import api.server.database as db
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from puts import get_logger

from .data_model import MachineStatus

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


DATA_CACHE = dict()

###############################################################################
## ENDPOINTS


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/get")
async def get_status():
    return DATA_CACHE


@app.post("/reset")
async def reset_status():
    global DATA_CACHE

    for key in DATA_CACHE.keys():
        DATA_CACHE[key] = {}

    return {"msg": "OK"}


@app.post("/post", status_code=201)
async def post_status(status: MachineStatus):
    global DATA_CACHE

    report_key = status.report_key
    if report_key in db.ALL_REPORTKEYS:
        if report_key not in DATA_CACHE:
            DATA_CACHE[report_key] = dict()

        machine_id = status.machine_id
        if not machine_id:
            raise HTTPException(status_code=400, detail="Empty machine_id")

        # store update
        DATA_CACHE[report_key][machine_id] = status.model_dump()

        logger.debug(
            f"Received status report from: {status.name} ({status.report_key})"
        )
        return {"msg": "OK"}
    else:
        raise HTTPException(status_code=401, detail="Invalid report_key")
