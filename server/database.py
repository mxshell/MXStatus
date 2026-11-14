"""Single-process, in-memory state. Configure bootstrap credentials via the environment."""

import os
import secrets
import string
from datetime import datetime, timezone

from server.data_model import MachineStatus, ViewGroup


def normalize_key(key: str) -> str:
    return key.upper()


def valid_key(key: str) -> bool:
    return (
        isinstance(key, str)
        and 16 <= len(key) <= 64
        and key.isascii()
        and key.isalnum()
    )


class DatabaseError(ValueError):
    """An expected client error that is safe to include in an API response."""


class ViewNotFoundError(LookupError):
    """The requested view is missing, disabled, or expired."""


MAX_MACHINES = 10000


class Database:
    def __init__(self):
        self.STATUS_DATA: dict[str, dict] = {}
        user_id = os.environ.get("MXSTATUS_ADMIN_USER_ID", "1000")
        self.UID_USERS = {user_id: "admin"}
        self.USER_REPORT_KEYS: dict[str, dict[str, str]] = {user_id: {}}
        self.ALL_REPORT_KEYS: dict[str, set[str]] = {}
        self.ALL_VIEW_KEYS: dict[str, dict] = {}
        self.USER_VIEW_KEYS: dict[str, set[str]] = {user_id: set()}

        report_key = os.environ.get("MXSTATUS_REPORT_KEY", "")
        view_key = os.environ.get("MXSTATUS_VIEW_KEY", "")
        machines = list(
            dict.fromkeys(
                value.strip()
                for value in os.environ.get("MXSTATUS_MACHINE_IDS", "").split(",")
                if value.strip()
            )
        )
        if (view_key or machines) and not report_key:
            raise DatabaseError(
                "MXSTATUS_REPORT_KEY is required to bootstrap a view or machines"
            )
        for key in (report_key, view_key):
            if key and not valid_key(key):
                raise DatabaseError(
                    "Bootstrap keys must contain 16–64 ASCII letters or digits"
                )
        if report_key:
            report_key = normalize_key(report_key)
            self.ALL_REPORT_KEYS[report_key] = set(machines)
            self.USER_REPORT_KEYS[user_id][report_key] = "bootstrap"
        if view_key:
            view_key = normalize_key(view_key)
            self.ALL_VIEW_KEYS[view_key] = ViewGroup(
                view_key=view_key, view_name="Default", view_machines=machines
            ).model_dump()
            self.USER_VIEW_KEYS[user_id].add(view_key)


DB = Database()


def valid_user_id(user_id: str) -> bool:
    if not isinstance(user_id, str) or user_id not in DB.UID_USERS:
        return False
    DB.USER_REPORT_KEYS.setdefault(user_id, {})
    DB.USER_VIEW_KEYS.setdefault(user_id, set())
    return True


def random_key_gen(length: int = 32, digits: bool = True) -> str:
    alphabet = string.ascii_uppercase + (string.digits if digits else "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _report_owner(report_key: str) -> str | None:
    return next(
        (uid for uid, keys in DB.USER_REPORT_KEYS.items() if report_key in keys), None
    )


def _owned_machines(user_id: str) -> set[str]:
    return {
        machine
        for key in DB.USER_REPORT_KEYS[user_id]
        for machine in DB.ALL_REPORT_KEYS.get(key, set())
    }


def _validate_machines(user_id: str, machines: list[str]) -> list[str]:
    if not isinstance(machines, list) or any(
        not isinstance(machine, str) or not machine.strip() for machine in machines
    ):
        raise DatabaseError("machines must be a list of nonempty machine IDs")
    if not set(machines) <= _owned_machines(user_id):
        raise DatabaseError(
            "Machines must report under one of this user's report keys first"
        )
    return list(dict.fromkeys(machines))


def store_new_report(status: MachineStatus) -> None:
    key = normalize_key(status.report_key or "")
    owner = _report_owner(key)
    if key not in DB.ALL_REPORT_KEYS or owner is None:
        raise DatabaseError("Invalid report_key")
    if not status.machine_id or not status.machine_id.strip():
        raise DatabaseError("Invalid machine_id")
    for other_key, machines in DB.ALL_REPORT_KEYS.items():
        if status.machine_id in machines and _report_owner(other_key) != owner:
            raise DatabaseError("Machine is registered to another user")
    if status.machine_id not in DB.STATUS_DATA and len(DB.STATUS_DATA) >= MAX_MACHINES:
        raise DatabaseError("Machine capacity reached")
    # Do not trust client clocks, including future dates that would bypass expiry.
    report = status.model_dump(exclude={"report_key"})
    report["created_at"] = datetime.now(timezone.utc)
    DB.ALL_REPORT_KEYS[key].add(status.machine_id)
    DB.STATUS_DATA[status.machine_id] = report


def _active_view(view_key: str) -> dict | None:
    group = DB.ALL_VIEW_KEYS.get(normalize_key(view_key))
    if not group or not group["view_enabled"]:
        return None
    timer = group.get("view_timer")
    if timer is not None and timer <= datetime.now(timezone.utc):
        return None
    return group


def get_view(view_key: str) -> list[dict]:
    group = _active_view(view_key)
    if group is None:
        raise DatabaseError("View is unavailable")
    return [
        DB.STATUS_DATA[mid] for mid in group["view_machines"] if mid in DB.STATUS_DATA
    ]


def get_view_machine(view_key: str, machine_id: str) -> dict | None:
    group = _active_view(view_key)
    if group is None or machine_id not in group["view_machines"]:
        return None
    return DB.STATUS_DATA.get(machine_id)


def valid_new_report_key(report_key: str) -> bool:
    return valid_key(report_key) and normalize_key(report_key) not in DB.ALL_REPORT_KEYS


def random_report_key() -> str:
    while True:
        key = random_key_gen()
        if valid_new_report_key(key):
            return key


def create_new_report_key(
    user_id: str, report_key: str = "", report_key_desc: str = ""
):
    if not valid_user_id(user_id):
        raise DatabaseError("Invalid user_id")
    report_key = normalize_key(report_key) if report_key else random_report_key()
    if not valid_new_report_key(report_key):
        raise DatabaseError(
            "report_key is already in use or is not 16–64 ASCII letters or digits"
        )
    DB.ALL_REPORT_KEYS[report_key] = set()
    DB.USER_REPORT_KEYS[user_id][report_key] = report_key_desc
    return {"report_key": report_key, "report_key_desc": report_key_desc}


def delete_report_key(user_id: str, report_key: str) -> None:
    report_key = normalize_key(report_key)
    if not valid_user_id(user_id) or report_key not in DB.USER_REPORT_KEYS[user_id]:
        raise DatabaseError("report_key does not exist")
    machines = DB.ALL_REPORT_KEYS.pop(report_key, set())
    del DB.USER_REPORT_KEYS[user_id][report_key]
    # Revoke stale reports and view memberships unless another key still owns them.
    removed = machines - _owned_machines(user_id)
    for machine in removed:
        DB.STATUS_DATA.pop(machine, None)
    for group in DB.ALL_VIEW_KEYS.values():
        group["view_machines"] = [
            mid for mid in group["view_machines"] if mid not in removed
        ]


def valid_new_view_key(view_key: str) -> bool:
    return valid_key(view_key) and normalize_key(view_key) not in DB.ALL_VIEW_KEYS


def random_view_key() -> str:
    while True:
        key = random_key_gen()
        if valid_new_view_key(key):
            return key


def create_new_view_group(user_id: str, view_group: ViewGroup) -> ViewGroup:
    if not valid_user_id(user_id):
        raise DatabaseError("Invalid user_id")
    key = (
        normalize_key(view_group.view_key) if view_group.view_key else random_view_key()
    )
    if not valid_new_view_key(key):
        raise DatabaseError(
            "view_key is already in use or is not 16–64 ASCII letters or digits"
        )
    machines = _validate_machines(user_id, view_group.view_machines)
    view_group = view_group.model_copy(
        update={"view_key": key, "view_machines": machines}
    )
    DB.ALL_VIEW_KEYS[key] = view_group.model_dump()
    DB.USER_VIEW_KEYS[user_id].add(key)
    return view_group


def check_view_group(view_key: str) -> dict:
    group = _active_view(view_key)
    if group is None:
        raise ViewNotFoundError("Invalid view key")
    return group


def update_machines_in_view(
    user_id: str,
    view_key: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    update: list[str] | None = None,
    overwrite: bool = False,
) -> dict:
    view_key = normalize_key(view_key)
    if not valid_user_id(user_id):
        raise DatabaseError("Invalid user_id")
    if view_key not in DB.USER_VIEW_KEYS[user_id] or view_key not in DB.ALL_VIEW_KEYS:
        raise DatabaseError("Invalid view_key")
    current = DB.ALL_VIEW_KEYS[view_key]["view_machines"]
    if overwrite:
        machines = _validate_machines(user_id, update if update is not None else [])
    else:
        additions = _validate_machines(user_id, add if add is not None else [])
        machines = [
            mid
            for mid in dict.fromkeys(current + additions)
            if mid not in (remove or [])
        ]
    DB.ALL_VIEW_KEYS[view_key]["view_machines"] = machines
    return DB.ALL_VIEW_KEYS[view_key]
