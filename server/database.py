"""Single-process telemetry with durable management settings and credentials."""

import os
import secrets
import string
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps

from server.admin_models import ClientSettings, ServerSettings
from server.data_model import MachineStatus, ViewGroup
from server.persistence import StateStore


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
    def __init__(self, storage_path: str | None = None):
        self.store = StateStore(
            storage_path
            or os.environ.get("MXSTATUS_DATA_PATH", "data/mxstatus.sqlite3")
        )
        self.SETTINGS = ServerSettings()
        self.CLIENT_SETTINGS: dict[str, ClientSettings] = {}
        self._transaction_depth = 0
        self.STATUS_DATA: dict[str, dict] = {}
        user_id = os.environ.get("MXSTATUS_ADMIN_USER_ID", "1000")
        self.UID_USERS = {user_id: "admin"}
        self.USER_REPORT_KEYS: dict[str, dict[str, str]] = {user_id: {}}
        self.ALL_REPORT_KEYS: dict[str, set[str]] = {}
        self.ALL_VIEW_KEYS: dict[str, dict] = {}
        self.USER_VIEW_KEYS: dict[str, set[str]] = {user_id: set()}

        saved = self.store.load()
        if saved is not None:
            self._restore(saved)
            return

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

        self.store.save(self._snapshot())

    def _snapshot(self) -> dict:
        return {
            "version": 1,
            "users": self.UID_USERS,
            "user_report_keys": self.USER_REPORT_KEYS,
            "report_keys": {
                key: sorted(machines) for key, machines in self.ALL_REPORT_KEYS.items()
            },
            "views": {
                key: ViewGroup.model_validate(group).model_dump(mode="json")
                for key, group in self.ALL_VIEW_KEYS.items()
            },
            "user_views": {
                uid: sorted(keys) for uid, keys in self.USER_VIEW_KEYS.items()
            },
            "settings": self.SETTINGS.model_dump(),
            "clients": {
                mid: settings.model_dump()
                for mid, settings in self.CLIENT_SETTINGS.items()
            },
        }

    def _restore(self, state: dict) -> None:
        if state.get("version") != 1:
            raise RuntimeError("Unsupported management database version")
        self.UID_USERS = state["users"]
        self.USER_REPORT_KEYS = state["user_report_keys"]
        self.ALL_REPORT_KEYS = {
            key: set(machines) for key, machines in state["report_keys"].items()
        }
        self.ALL_VIEW_KEYS = {
            key: ViewGroup.model_validate(group).model_dump()
            for key, group in state["views"].items()
        }
        self.USER_VIEW_KEYS = {
            uid: set(keys) for uid, keys in state["user_views"].items()
        }
        self.SETTINGS = ServerSettings.model_validate(state["settings"])
        self.CLIENT_SETTINGS = {
            mid: ClientSettings.model_validate(settings)
            for mid, settings in state["clients"].items()
        }

    @contextmanager
    def transaction(self):
        # API handlers do not yield during a mutation. Keep a single server worker.
        if self._transaction_depth:
            yield
            return
        snapshot = deepcopy(self._snapshot())
        # Management operations replace entire report entries, so a shallow copy suffices.
        reports = dict(self.STATUS_DATA)
        self._transaction_depth += 1
        try:
            yield
            self.store.save(self._snapshot())
        except Exception:
            self._restore(snapshot)
            self.STATUS_DATA = reports
            raise
        finally:
            self._transaction_depth -= 1


def persistent_mutation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with DB.transaction():
            return function(*args, **kwargs)

    return wrapped


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
    known_machines = {
        mid for machines in DB.ALL_REPORT_KEYS.values() for mid in machines
    }
    if status.machine_id not in known_machines and not DB.SETTINGS.accept_new_clients:
        raise DatabaseError("New client enrollment is disabled")
    metadata = DB.CLIENT_SETTINGS.get(status.machine_id, ClientSettings())
    if not metadata.enabled:
        raise DatabaseError("Reports from this client are blocked")
    if status.machine_id not in known_machines and len(known_machines) >= min(
        MAX_MACHINES, DB.SETTINGS.max_machines
    ):
        raise DatabaseError("Machine capacity reached")
    # Do not trust client clocks, including future dates that would bypass expiry.
    report = status.model_dump(exclude={"report_key"})
    report["created_at"] = datetime.now(timezone.utc)
    if status.machine_id not in DB.ALL_REPORT_KEYS[key]:
        with DB.transaction():
            DB.ALL_REPORT_KEYS[key].add(status.machine_id)
            DB.STATUS_DATA[status.machine_id] = report
    else:
        DB.STATUS_DATA[status.machine_id] = report


def get_report(machine_id: str) -> dict | None:
    report = DB.STATUS_DATA.get(machine_id)
    settings = DB.CLIENT_SETTINGS.get(machine_id)
    if report and settings and settings.display_name:
        return {**report, "name": settings.display_name}
    return report


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
    return [get_report(mid) for mid in group["view_machines"] if mid in DB.STATUS_DATA]


def get_view_machine(view_key: str, machine_id: str) -> dict | None:
    group = _active_view(view_key)
    if group is None or machine_id not in group["view_machines"]:
        return None
    return get_report(machine_id)


def valid_new_report_key(report_key: str) -> bool:
    return valid_key(report_key) and normalize_key(report_key) not in DB.ALL_REPORT_KEYS


def random_report_key() -> str:
    while True:
        key = random_key_gen()
        if valid_new_report_key(key):
            return key


@persistent_mutation
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


@persistent_mutation
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
        DB.CLIENT_SETTINGS.pop(machine, None)
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


@persistent_mutation
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


@persistent_mutation
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


def _require_client(machine_id: str) -> None:
    if not any(machine_id in machines for machines in DB.ALL_REPORT_KEYS.values()):
        raise DatabaseError("Unknown client")


@persistent_mutation
def update_client(machine_id: str, settings: ClientSettings) -> None:
    _require_client(machine_id)
    DB.CLIENT_SETTINGS[machine_id] = settings.model_copy(deep=True)


@persistent_mutation
def forget_client(machine_id: str) -> None:
    _require_client(machine_id)
    for machines in DB.ALL_REPORT_KEYS.values():
        machines.discard(machine_id)
    for group in DB.ALL_VIEW_KEYS.values():
        group["view_machines"] = [
            mid for mid in group["view_machines"] if mid != machine_id
        ]
    DB.STATUS_DATA.pop(machine_id, None)
    DB.CLIENT_SETTINGS.pop(machine_id, None)


@persistent_mutation
def update_settings(settings: ServerSettings) -> ServerSettings:
    count = len({mid for machines in DB.ALL_REPORT_KEYS.values() for mid in machines})
    if settings.max_machines < count:
        raise DatabaseError(
            "Capacity cannot be lower than the number of registered clients"
        )
    DB.SETTINGS = settings.model_copy(deep=True)
    return settings


@persistent_mutation
def update_report_key(report_key: str, description: str) -> None:
    key = normalize_key(report_key)
    owner = _report_owner(key)
    if owner is None:
        raise DatabaseError("Unknown report key")
    DB.USER_REPORT_KEYS[owner][key] = description


def view_owner(view_key: str) -> str:
    key = normalize_key(view_key)
    owner = next((uid for uid, keys in DB.USER_VIEW_KEYS.items() if key in keys), None)
    if owner is None:
        raise DatabaseError("Unknown view group")
    return owner


@persistent_mutation
def edit_view_group(group: ViewGroup) -> ViewGroup:
    key = normalize_key(group.view_key or "")
    owner = view_owner(key)
    machines = _validate_machines(owner, group.view_machines)
    updated = group.model_copy(update={"view_key": key, "view_machines": machines})
    DB.ALL_VIEW_KEYS[key] = updated.model_dump()
    return updated


@persistent_mutation
def delete_view_group(view_key: str) -> None:
    key = normalize_key(view_key)
    owner = view_owner(key)
    DB.USER_VIEW_KEYS[owner].remove(key)
    del DB.ALL_VIEW_KEYS[key]
