import os
import random
import string
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set, Union

from rich import print
from supabase import Client

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from server.auth import init_supabase, sign_myself_in, sign_out
from server.data_model import MachineStatus, ReportKey, ViewGroup

###############################################################################
### Databse Definition and Initialization

"""
Table 1: User Table (Auth)

    id: str # primary key
    ...

Table 2: Report Keys

    id: str # primary key
    created_at: datetime
    user_id: str # foreign key
    report_key: str # Required, UNIQUE
    report_key_desc: str # Optional, used as display description
    [TODO] enabled: bool # default True

policies:
    
        - select: user can view their own report keys
        - insert: user can create their own report keys
        - update: user can update their own report keys
        - delete: user can delete their own report keys


Table 3: View Groups

    id: str # primary key
    created_at: datetime
    user_id: str # foreign key (owner of the view group)
    view_key: str # Required, UNIQUE
    view_name: str # Required, used as display title, not unique
    view_desc: str # Optional, used as display description
    view_enabled: bool # Required, default True
    view_machines: List[str] # Required, list of machine_id, can be empty
    view_timer: Optional[datetime] # Optional, used for disabling view after a certain time
    [TODO] view_public: bool # Required, default False, if True, anyone can view this view group
    [TODO] view_members: List[str] # Optional, list of user_id, can be empty

policies:

    - select: user can view their own (created) view groups
              [TODO][!important] anyone can view a specific view group given the view_key if view_public is True
              [TODO][!important] authenticated user can view a specific view group given the view_key if they are in view_members
    - insert: user can create their own (created) view groups
    - update: user can update their own (created) view groups
    - delete: user can delete their own (created) view groups


Table 4: Machine Status

    id: str # primary key
    created_at: datetime
    report_key: str # foreign key
    machine_id: str # Required, UNIQUE
    status: json # Required, json

policies:
    
    - select: user can view their own machine status based on their own report keys
    - insert: [TODO][!important] anyone can insert a new machine status given a valid report key
    - update: [TODO][!important] anyone can update a new machine status given a valid report key
    - delete: user can delete their own machine status based on their own report keys

    [NOTE] The consideration that anyone can insert/update machine status is:
            1. to allow he machine to report its status without authentication, simplifying the process;
            2. allow account owner to give out report_key to others without lending their account token to others;
            3. there is no serious security risk even when report_key are leaked to malicious users, as the 
            key owner can always delete/disable the report_key and create a new ones.
        

    
Table 5: Machine Status History [TODO]

    id: str # primary key
    created_at: datetime
    report_key: str # foreign key
    machine_id: str # Required, UNIQUE
    history_timestamps: List[datetime] # Required, list of timestamps, can be empty

"""


class Database:
    def __init__(self):
        self.STATUS_DATA: Dict[str, MachineStatus] = {
            # machine_id: MachineStatus object
            # TODO: future work: use a FIFO fixed size queue to store the last N reports
        }


DB = Database()

###############################################################################
### User


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
    view_enabled = view_group.get("view_enabled", False)
    if not view_enabled:
        raise ValueError("View is unavailable.")
    # get machine_id set
    machine_ids = view_group.get("view_machines", [])
    # get status data
    status_data = []
    for machine_id in machine_ids:
        if machine_id in DB.STATUS_DATA:
            status_data.append(DB.STATUS_DATA[machine_id])
    return status_data


def get_view_machine(view_key: str, machine_id: str) -> Union[MachineStatus, None]:
    # check view_key is valid
    if view_key not in DB.ALL_VIEW_KEYS:
        return None
    # check machine_id is valid
    if machine_id not in DB.STATUS_DATA:
        return None
    # check access permission and stuff...
    ...
    # get view_group object
    view_group = DB.ALL_VIEW_KEYS[view_key]
    # check if view is enabled
    view_enabled = view_group.get("view_enabled", False)
    if not view_enabled:
        return None
    # get machine_id set
    machine_ids = view_group.get("view_machines", [])
    # check if machine_id is in view
    if machine_id not in machine_ids:
        return None
    # get status data
    return DB.STATUS_DATA[machine_id]


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

    # if report_key in DB.ALL_REPORT_KEYS:
    #     return False
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


# def create_new_report_key(
#     user_id: str,
#     report_key: Optional[str] = "",
#     report_key_desc: Optional[str] = "",
# ):
#     # check user_id is valid
#     # if not valid_user_id(user_id):
#     #     raise ValueError(f"Invalid user_id: {user_id}")
#     # generate a new report_key if not provided
#     if not report_key:
#         report_key = random_report_key()
#     # check report_key is valid
#     if not valid_new_report_key(report_key):
#         raise ValueError(
#             "Invalid report_key: report_key is already in use or does not meet requirements"
#         )
#     # add report_key to DB
#     DB.ALL_REPORT_KEYS[report_key] = set()
#     # add to user report_key_desc map
#     DB.USER_REPORT_KEYS[user_id][report_key] = report_key_desc

#     return {
#         "report_key": report_key,
#         "report_key_desc": report_key_desc,
#     }


def create_new_report_key_supabase(
    supabase: Client,
    user_id: str,
    report_key: Optional[str] = "",
    report_key_desc: Optional[str] = "",
) -> ReportKey:
    try:
        new_key_payload = dict(
            user_id=user_id,
            report_key=report_key if report_key else random_report_key(),
            report_key_desc=report_key_desc,
        )
        response = supabase.table("report_keys").insert(new_key_payload).execute()
        data = response.data[0]
        return ReportKey(**data)
    except Exception as e:
        raise e


def get_user_report_keys_supabase(supabase: Client) -> List[ReportKey]:
    try:
        response = supabase.table("report_keys").select("*").execute()
        data = response.data
        print(f"Current user has {len(data)} report keys")
        return [ReportKey(**x) for x in data]

    except Exception as e:
        raise e


# def delete_report_key(user_id: str, report_key: str) -> None:
#     # check user_id is valid
#     # if not valid_user_id(user_id):
#     #     raise ValueError(f"Invalid user_id: {user_id}")
#     # check report_key exists
#     if report_key not in DB.USER_REPORT_KEYS[user_id]:
#         raise ValueError("report_key does not exist")  # TODO: maybe refine this
#     # remove from user report_key list
#     del DB.USER_REPORT_KEYS[user_id][report_key]
#     # remove from report_key list
#     if report_key in DB.ALL_REPORT_KEYS:
#         del DB.ALL_REPORT_KEYS[report_key]
#     else:
#         print(
#             "Unexpected Error: report_key exists in user list but not in all list, code logic might be wrong"
#         )
#     return


def delete_report_key_supabase(supabase: Client, report_key: str) -> None:
    try:
        response = (
            supabase.table("report_keys")
            .delete()
            .eq("report_key", report_key)
            .execute()
        )
        data = response.data
        if not data:
            raise ValueError("Failed to delete report key")
        assert len(data) == 1, "Unexpected error: more than one report key deleted"
    except Exception as e:
        raise e


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


# def create_new_view_group(
#     user_id: str,
#     view_group: ViewGroup,
# ):
#     # check user_id is valid
#     # if not valid_user_id(user_id):
#     #     raise ValueError(f"Invalid user_id: {user_id}")
#     # generate a new view_key if not provided
#     if not view_group.view_key:
#         view_group.view_key = random_view_key()
#     # check view_key is valid
#     if not valid_new_view_key(view_group.view_key):
#         raise ValueError(
#             "Invalid view_key: view_key is already in use or does not meet requirements. view_key should only contain letters and digits."
#         )
#     # check view_machines is valid
#     ...
#     # check view_timer is valid
#     ...
#     # add to view_key set
#     DB.ALL_VIEW_KEYS[view_group.view_key] = view_group.model_dump()
#     # add to user view_key map
#     DB.USER_VIEW_KEYS[user_id].add(view_group.view_key)
#     return view_group


def create_new_view_group_supabase(
    supabase: Client,
    user_id: str,
    view_group: ViewGroup,
) -> ViewGroup:
    try:
        new_group_payload = dict(
            user_id=user_id,
            view_key=view_group.view_key if view_group.view_key else random_view_key(),
            view_name=view_group.view_name,
            view_desc=view_group.view_desc,
            view_enabled=view_group.view_enabled,
            view_machines=view_group.view_machines,
            view_timer=view_group.view_timer,
        )
        response = supabase.table("view_groups").insert(new_group_payload).execute()
        data = response.data[0]
        return ViewGroup(**data)
    except Exception as e:
        raise e


# def check_view_group(view_key: str) -> ViewGroup:
#     """
#     Return the view_group object if view_key exists

#     Args:
#         view_key (str): view_key

#     Returns:
#         view_group (ViewGroup): view_group object

#     Raises:
#         KeyError: view_key does not exist
#     """
#     return DB.ALL_VIEW_KEYS[view_key]


def check_view_group_supabase(supabase: Client, view_key: str) -> ViewGroup:
    try:
        response = (
            supabase.table("view_groups").select("*").eq("view_key", view_key).execute()
        )
        data = response.data
        if not data:
            raise ValueError("View group not found")
        assert len(data) == 1, "Unexpected error: more than one view group found"
        return ViewGroup(**data[0])
    except Exception as e:
        raise e


def get_user_view_groups_supabase(supabase: Client, user_id: str) -> List[ViewGroup]:
    try:
        response = (
            supabase.table("view_groups").select("*").eq("user_id", user_id).execute()
        )
        data = response.data
        if not data:
            raise ValueError("No view groups found")
        return [ViewGroup(**x) for x in data]
    except Exception as e:
        raise e


# def update_machines_in_view(
#     user_id: str,
#     view_key: str,
#     add: List[str] = [],
#     remove: List[str] = [],
#     update: List[str] = [],
#     overwrite: bool = False,
# ) -> ViewGroup:
#     # check user_id is valid
#     # if not valid_user_id(user_id):
#     #     raise ValueError(f"Invalid user_id: {user_id}")
#     # check view_key is valid
#     if view_key not in DB.ALL_VIEW_KEYS:
#         raise ValueError("Invalid view_key")
#     # check view_key belongs to user
#     if view_key not in DB.USER_VIEW_KEYS[user_id]:
#         raise ValueError("Invalid view_key")
#     if not overwrite:
#         # add machines
#         for machine_id in add:
#             if machine_id not in DB.ALL_REPORT_KEYS:
#                 # do nothing
#                 # this is ok because machine_id might not be reporting yet
#                 pass
#             # todo: maybe some machine_id validation here?
#             ...
#             DB.ALL_VIEW_KEYS[view_key]["view_machines"].append(machine_id)
#         # remove machines
#         for machine_id in remove:
#             if machine_id in DB.ALL_VIEW_KEYS[view_key]["view_machines"]:
#                 DB.ALL_VIEW_KEYS[view_key]["view_machines"].remove(machine_id)
#     else:
#         # todo: maybe some machine_id validation here?
#         ...
#         # overwrite machines
#         assert isinstance(update, list), "update must be a list"
#         assert all(isinstance(x, str) for x in update), "update must be a list of str"
#         assert len(set(update)) == len(update), "duplicate machine_id in update"
#         DB.ALL_VIEW_KEYS[view_key]["view_machines"] = update

#     return DB.ALL_VIEW_KEYS[view_key]


def update_machines_in_view_supabase(
    supabase: Client,
    user_id: str,
    view_key: str,
    add: List[str] = [],
    remove: List[str] = [],
    overwrite: List[str] = [],
) -> ViewGroup:
    try:
        view_group: ViewGroup = check_view_group_supabase(supabase, view_key)
        view_machines = view_group.view_machines or []

        if not overwrite:
            # add machines
            for machine_id in add:
                if machine_id not in view_machines:
                    view_machines.append(machine_id)
            # remove machines
            for machine_id in remove:
                if machine_id in view_machines:
                    view_machines.remove(machine_id)
        else:
            view_machines = overwrite

        response = (
            supabase.table("view_groups")
            .update({"view_machines": view_machines})
            .eq("view_key", view_key)
            .execute()
        )
        data = response.data
        if not data:
            raise ValueError("Failed to update view group")
        assert len(data) == 1, "Unexpected error: more than one view group updated"
        return ViewGroup(**data[0])
    except Exception as e:
        raise e


if __name__ == "__main__":
    ...
