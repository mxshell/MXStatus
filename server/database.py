import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Set, Union

from server.data_model import MachineStatus, ViewGroup

###############################################################################
### Databse Definition and Initialization


class Database:
    def __init__(self):
        self.STATUS_DATA: Dict[str, Dict[str, MachineStatus]] = {}
        # user_id to user_email
        self.UID_USERS: Dict[str, str] = {
            # UID: User Email
            "1000": "dev@markhh.com",
        }
        # user_id to report_key to report_key_desc
        self.USER_REPORT_KEYS: Dict[str, Dict[str, str]] = {
            # user_id: {}
            "1000": {
                # report_key: desc
                "dev@markhh.com": "default",
            },
        }
        # All report_key
        self.ALL_REPORT_KEYS: Set[str] = set(["dev@markhh.com"])
        # All view_key
        self.ALL_VIEW_KEYS: Set[str] = set(["markhuang"])
        # user_id to view_key to view_group
        self.USER_VIEW_KEYS: Dict[str, Dict[str, str]] = {
            # user_id: {}
            "1000": {
                # view_key: view_group
                "markhuang": {
                    "view_key": "markhuang",
                    "view_name": "Default",
                    "view_desc": "Default",
                }
            },
        }


database = Database()

###############################################################################
### User


def valid_user_id(user_id: str) -> bool:
    """
    Check if the user_id is valid
    """
    if not isinstance(user_id, str):
        return False
    if user_id not in database.UID_USERS:
        return False

    if user_id not in database.USER_REPORT_KEYS:
        database.USER_REPORT_KEYS[user_id] = {}

    if user_id not in database.USER_VIEW_KEYS:
        database.USER_VIEW_KEYS[user_id] = {}

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
    if status.report_key not in database.ALL_REPORT_KEYS:
        raise ValueError("Invalid report_key")
    # check machine_id is valid
    if not status.machine_id:
        raise ValueError("Invalid machine_id")
    # store update
    if status.report_key not in database.STATUS_DATA:
        database.STATUS_DATA[status.report_key] = {}
    database.STATUS_DATA[status.report_key][status.machine_id] = status.model_dump()
    return


###############################################################################
### view_status

###############################################################################
### report_key related helpers


def valid_new_report_key(report_key: str) -> bool:
    """
    Check if the report_key is valid and not in use

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

    if report_key in database.ALL_REPORT_KEYS:
        return False
    if len(report_key) < 8 or len(report_key) > 64:
        return False
    if not report_key.isalnum():
        return False

    return True


def random_report_key() -> str:
    """
    Generate a random report_key that is not in use
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
    # add to report_key set
    database.ALL_REPORT_KEYS.add(report_key)
    # add to user report_key_desc map
    database.USER_REPORT_KEYS[user_id][report_key] = report_key_desc
    return {
        "report_key": report_key,
        "report_key_desc": report_key_desc,
    }


def delete_report_key(user_id: str, report_key: str) -> None:
    # check user_id is valid
    if not valid_user_id(user_id):
        raise ValueError(f"Invalid user_id: {user_id}")
    # check report_key exists
    if report_key not in database.USER_REPORT_KEYS[user_id]:
        raise ValueError("report_key does not exist")  # TODO: maybe refine this
    # remove from user report_key list
    del database.USER_REPORT_KEYS[user_id][report_key]
    # remove from report_key list
    if report_key in database.ALL_REPORT_KEYS:
        database.ALL_REPORT_KEYS.remove(report_key)
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

    if view_key in database.ALL_VIEW_KEYS:
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
    database.ALL_VIEW_KEYS.add(view_group.view_key)
    # add to user view_key map
    database.USER_VIEW_KEYS[user_id][view_group.view_key] = view_group.model_dump()
    return view_group


if __name__ == "__main__":
    ...
