import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Set, Union

from server.data_model import MachineStatus, ViewGroup

###############################################################################
### Databse Definition and Initialization


class Database:
    def __init__(self):
        self.STATUS_DATA: Dict[str, MachineStatus] = {
            # machine_id: MachineStatus object
            # TODO: future work: use a FIFO fixed size queue to store the last N reports
        }
        # user_id to user_email
        self.UID_USERS: Dict[str, str] = {
            # UID: User Email
            "1000": "dev@markhh.com",
        }
        # user_id to report_key to report_key_desc
        self.USER_REPORT_KEYS: Dict[str, Dict[str, str]] = {
            # user_id: {}
            "1000": {
                # report_key: desc string
                "dev@markhh.com": "default",
            },
        }
        # All report_key
        self.ALL_REPORT_KEYS: Dict[str, Set[str]] = {
            # report_key: set of machine_id
            "dev@markhh.com": set(),
        }
        # All view_key
        self.ALL_VIEW_KEYS: Dict[str, dict] = {
            # view_key: view_group object
            "markhuang": {
                "view_key": "markhuang",
                "view_name": "Default",
                "view_desc": "Default",
                "view_enabled": True,
                "view_machines": [],
                "view_timer": None,
            },
        }
        # user_id to view_key to view_group
        self.USER_VIEW_KEYS: Dict[str, Set[str]] = {
            # user_id: set of view_key
            "1000": ("markhuang",)
        }


DB = Database()

###############################################################################
### User


def valid_user_id(user_id: str) -> bool:
    """
    Check if the user_id is valid
    """
    if not isinstance(user_id, str):
        return False
    if user_id not in DB.UID_USERS:
        return False

    if user_id not in DB.USER_REPORT_KEYS:
        DB.USER_REPORT_KEYS[user_id] = {}

    if user_id not in DB.USER_VIEW_KEYS:
        DB.USER_VIEW_KEYS[user_id] = {}

    return True


def random_key_gen(length: int = 8, digits: bool = True) -> str:
    """
    Generate a random key of the given length
    """
    tmp = string.ascii_letters + string.digits if digits else string.ascii_letters
    return "".join(random.choices(tmp, k=length)).upper()


###############################################################################
### report_status


def store_new_report(status: MachineStatus) -> None:
    # check report_key is valid
    # report_key has to be pre-existing
    if status.report_key not in DB.ALL_REPORT_KEYS:
        raise ValueError("Invalid report_key")

    # check machine_id is not empty
    if not status.machine_id:
        raise ValueError("Invalid machine_id")

    # check first time reporting
    if status.machine_id not in DB.ALL_REPORT_KEYS[status.report_key]:
        # new machine_id reporting to this report_key
        DB.ALL_REPORT_KEYS[status.report_key].add(status.machine_id)
        print(
            f"New machine_id ({status.machine_id}) reporting using report_key ({status.report_key})"
        )

    # store update
    DB.STATUS_DATA[status.machine_id] = status.model_dump()

    return


###############################################################################
### view_status


def get_view(view_key: str) -> Dict[str, Dict[str, MachineStatus]]:
    # check view_key is valid
    if view_key not in DB.ALL_VIEW_KEYS:
        raise ValueError("Invalid view_key.")
    # TODO: check access permission and stuff...
    ...
    # get view_group object
    view_group = DB.ALL_VIEW_KEYS[view_key]
    # TODO: maybe check timer here?
    ...
    # check if view is enabled
    if not view_group.view_enabled:
        raise ValueError("View is unavailable.")
    # get machine_id set
    machine_ids = view_group.get("view_machines", [])
    # get status data
    status_data = []
    for machine_id in machine_ids:
        if machine_id in DB.STATUS_DATA:
            status_data.append(DB.STATUS_DATA[machine_id])
    return status_data


###############################################################################
### report_key related helpers


def valid_new_report_key(report_key: str) -> bool:
    """
    Check if the report_key is valid and not in use
    report_key needs to be universally unique across users

    Requirements:
        - report_key is a string
        - report_key is not in use by any user
        - report_key is no less than 8 characters
        - report_key is no more than 64 characters
        - report_key contains only letters and digits
        - report_key is case insensitive
    """
    if not isinstance(report_key, str):
        return False

    # case insensitive
    report_key = report_key.upper()

    if report_key in DB.ALL_REPORT_KEYS:
        return False
    if len(report_key) < 8 or len(report_key) > 64:
        return False
    if not report_key.isalnum():
        return False

    return True


def random_report_key() -> str:
    """
    Generate a new random report_key that is not in use
    """
    while True:
        code = random_key_gen()
        if valid_new_report_key(code):
            return code


def create_new_report_key(
    user_id: str,
    report_key: Optional[str] = "",
    report_key_desc: Optional[str] = "",
):
    # check user_id is valid
    if not valid_user_id(user_id):
        raise ValueError(f"Invalid user_id: {user_id}")
    # generate a new report_key if not provided
    if not report_key:
        report_key = random_report_key()
    # check report_key is valid
    if not valid_new_report_key(report_key):
        raise ValueError(
            "Invalid report_key: report_key is already in use or does not meet requirements"
        )
    # add report_key to DB
    DB.ALL_REPORT_KEYS[report_key] = set()
    # add to user report_key_desc map
    DB.USER_REPORT_KEYS[user_id][report_key] = report_key_desc

    return {
        "report_key": report_key,
        "report_key_desc": report_key_desc,
    }


def delete_report_key(user_id: str, report_key: str) -> None:
    # check user_id is valid
    if not valid_user_id(user_id):
        raise ValueError(f"Invalid user_id: {user_id}")
    # check report_key exists
    if report_key not in DB.USER_REPORT_KEYS[user_id]:
        raise ValueError("report_key does not exist")  # TODO: maybe refine this
    # remove from user report_key list
    del DB.USER_REPORT_KEYS[user_id][report_key]
    # remove from report_key list
    if report_key in DB.ALL_REPORT_KEYS:
        del DB.ALL_REPORT_KEYS[report_key]
    else:
        print(
            "Unexpected Error: report_key exists in user list but not in all list, code logic might be wrong"
        )
    return


###############################################################################
### view_group related helpers


def valid_new_view_key(view_key: str) -> bool:
    """
    Check if the view_key is valid and not in use
    view_key needs to be universally unique across users

    Requirements:
        - view_key is a string
        - view_key is not in use by any user
        - view_key contains only letters and digits
        - view_key is case insensitive
    """
    if not isinstance(view_key, str):
        return False

    # case insensitive
    view_key = view_key.upper()

    if view_key in DB.ALL_VIEW_KEYS:
        return False
    if not view_key.isalnum():
        return False

    return True


def random_view_key() -> str:
    """
    Generate a random view_key that is not in use
    """
    while True:
        code = random_key_gen(length=6, digits=False)
        if valid_new_view_key(code):
            return code


def store_view_group(
    user_id: str,
    view_group: ViewGroup,
):
    # check user_id is valid
    if not valid_user_id(user_id):
        raise ValueError(f"Invalid user_id: {user_id}")
    # generate a new view_key if not provided
    if not view_group.view_key:
        view_group.view_key = random_view_key()
    # check view_key is valid
    if not valid_new_view_key(view_group.view_key):
        raise ValueError(
            "Invalid view_key: view_key is already in use or does not meet requirements"
        )
    # check view_machines is valid
    ...
    # check view_timer is valid
    ...
    # add to view_key set
    DB.ALL_VIEW_KEYS[view_group.view_key] = view_group.model_dump()
    # add to user view_key map
    DB.USER_VIEW_KEYS[user_id].add(view_group.view_key)
    return view_group


def update_machines_in_view(
    user_id: str,
    view_key: str,
    add: List[str] = [],
    remove: List[str] = [],
    update: List[str] = [],
    overwrite: bool = False,
) -> None:
    # check user_id is valid
    if not valid_user_id(user_id):
        raise ValueError(f"Invalid user_id: {user_id}")
    # check view_key is valid
    if view_key not in DB.ALL_VIEW_KEYS:
        raise ValueError("Invalid view_key")
    # check view_key belongs to user
    if view_key not in DB.USER_VIEW_KEYS[user_id]:
        raise ValueError("Invalid view_key")
    if not overwrite:
        # add machines
        for machine_id in add:
            if machine_id not in DB.ALL_REPORT_KEYS:
                # do nothing
                # this is ok because machine_id might not be reporting yet
                pass
            # TODO: maybe some machine_id validation here?
            ...
            DB.ALL_VIEW_KEYS[view_key]["view_machines"].append(machine_id)
        # remove machines
        for machine_id in remove:
            if machine_id in DB.ALL_VIEW_KEYS[view_key]["view_machines"]:
                DB.ALL_VIEW_KEYS[view_key]["view_machines"].remove(machine_id)
    else:
        # TODO: maybe some machine_id validation here?
        ...
        # overwrite machines
        DB.ALL_VIEW_KEYS[view_key]["view_machines"] = list(set(update))

    return


if __name__ == "__main__":
    ...
