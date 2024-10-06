import os
import random
import string
import sys
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Union

from rich import print
from supabase import Client

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import postgrest.exceptions as pg_exceptions

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
    enabled: bool # default True

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


class StatusMemory:
    def __init__(self, max_length: int = 100):
        self.max_length = max_length
        self.data: Dict[str, deque[MachineStatus]] = {
            # {machine_id: deque[MachineStatus]}
        }

    def init_machine_id(self, machine_id: str) -> bool:
        if machine_id not in self.data:
            print(f"[INFO] New machine_id ({machine_id}) first time reporting.")
            self.data[machine_id] = deque(maxlen=self.max_length)
            return True
        return False

    def add_status(self, status: MachineStatus):
        first_time = self.init_machine_id(status.machine_id)
        if not first_time:
            _prev_status = self.get_last_status(status.machine_id)
            _prev_report_key = _prev_status.report_key
            if status.report_key != _prev_report_key:
                print(
                    f"[WARNING] Machine ({status.machine_id}) changed report_key from ({_prev_report_key}) to ({status.report_key})"
                )
        self.data[status.machine_id].append(status)

    def remove_machine_id(self, machine_id: str):
        if machine_id in self.data:
            del self.data[machine_id]

    def get_last_status(self, machine_id: str) -> Union[MachineStatus, None]:
        if machine_id in self.data:
            if self.data[machine_id]:
                return self.data[machine_id][-1]
        return None

    def get_status(self, machine_id: str) -> Union[MachineStatus, None]:
        return self.get_last_status(machine_id)

    def get_last_status_batch(self, machine_ids: List[str]) -> Dict[str, MachineStatus]:
        return {
            machine_id: self.get_last_status(machine_id) for machine_id in machine_ids
        }

    def get_status_batch(self, machine_ids: List[str]) -> Dict[str, MachineStatus]:
        return self.get_last_status_batch(machine_ids)


SM = StatusMemory()


class ReportKeyCache:
    def __init__(self, supabase: Client = None, cool_down: int = 5):
        """
        [Server-side] require admin authenticated supabase client
        """
        self.supabase: Optional[Client] = supabase
        self.cool_down: int = cool_down  # seconds
        if not self.supabase:
            print("[WARNING] Supabase client is not set")

        # init cache variables
        self.data: Dict[str, ReportKey] = {}
        self.last_updated: datetime = datetime.fromisoformat("1970-01-01T00:00:00")

        # init cache
        self.refresh(supabase)

    def get_key(self, report_key: str) -> Union[ReportKey, None]:
        self.refresh()
        return self.data.get(report_key)

    def refresh(self):
        if self._is_expired():
            self._fetch_all()

    def _is_expired(self) -> bool:
        return (datetime.now() - self.last_updated).seconds > self.cool_down

    def _fetch_all(self):
        if not self.supabase:
            raise ValueError("Supabase client is not set")

        response = self.supabase.table("report_keys").select("*").execute()
        data = response.data
        self.data = {x["report_key"]: ReportKey(**x) for x in data}
        self.last_updated = datetime.now()


RKC = ReportKeyCache()

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


def store_new_report_supabase(supabase: Client, status: MachineStatus) -> None:
    """
    [Server-side] Store new report status to the StatusMemory
    """
    try:
        # check if report_key is valid
        report_key = RKC.get_key(status.report_key)
        if not report_key:
            raise ValueError("Invalid report_key")
        elif not report_key.enabled:
            raise ValueError("Report key is disabled")

        # check machine_id is not empty
        if not status.machine_id:
            raise ValueError("Invalid machine_id")

        # add status to memory
        SM.add_status(status)

    except Exception as e:
        raise e


###############################################################################
### view_status


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


###############################################################################
### report_key CRUD


def create_new_report_key_supabase(
    supabase: Client,
    user_id: str,
    report_key: Optional[str] = "",
    report_key_desc: Optional[str] = "",
    enabled: Optional[bool] = True,
) -> ReportKey:
    """
    user-facing function: require user authenticated supabase client
    """
    try:
        new_key_payload = dict(
            user_id=user_id,
            report_key=report_key if report_key else random_report_key(),
            report_key_desc=report_key_desc,
            enabled=enabled,
        )
        response = supabase.table("report_keys").insert(new_key_payload).execute()
        data = response.data[0]
        return ReportKey(**data)
    except Exception as e:
        raise e


def get_user_report_keys_supabase(supabase: Client) -> List[ReportKey]:
    """
    user-facing function: require user authenticated supabase client
    """
    try:
        response = supabase.table("report_keys").select("*").execute()
        data = response.data
        print(f"Current user has {len(data)} report keys")
        return [ReportKey(**x) for x in data]

    except Exception as e:
        raise e


def update_report_key_supabase(
    supabase: Client,
    report_key: str,
    report_key_desc: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> ReportKey:
    """
    user-facing function: require user authenticated supabase client
    """
    try:
        update_payload = dict()
        if isinstance(report_key_desc, str):
            update_payload["report_key_desc"] = report_key_desc
        if isinstance(enabled, bool):
            update_payload["enabled"] = enabled
        if not update_payload:
            raise ValueError("Nothing to update")

        response = (
            supabase.table("report_keys")
            .update(update_payload)
            .eq("report_key", report_key)
            .execute()
        )
        data = response.data
        if not data:
            raise ValueError("Failed to update report key")
        assert len(data) == 1, "Unexpected error: more than one report key updated"
        return ReportKey(**data[0])
    except Exception as e:
        raise e


def delete_report_key_supabase(supabase: Client, report_key: str) -> None:
    """
    user-facing function: require user authenticated supabase client
    """
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
