import os
from datetime import datetime, timedelta, timezone

import pytest

from server import database as db
from server.admin_models import ClientSettings, ServerSettings
from server.data_model import MachineStatus, ViewGroup


@pytest.mark.parametrize(
    "path,body",
    [
        ("state", None),
        ("settings", {}),
        ("clients/update", {"machine_id": "m"}),
        ("clients/delete", {"machine_id": "m"}),
        ("keys", {}),
        ("keys/update", {"report_key": "x"}),
        ("keys/delete", {"report_key": "x"}),
        ("views", {}),
        ("views/update", {}),
        ("views/delete", {"view_key": "x"}),
    ],
)
def test_every_admin_api_requires_token(api, path, body):
    method = "GET" if body is None else "POST"
    response = api.request(method, "/admin/api/" + path, json=body)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_panel_shell_and_assets_are_served_without_private_data(api):
    response = api.get("/admin/")
    assert response.status_code == 200
    assert "MXStatus" in response.text
    assert "mxstatus-local-preview" not in response.text
    assert "admin-token-for-tests" not in response.text
    assert response.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    for file, content_type in [
        ("app.js", "javascript"),
        ("styles.css", "text/css"),
        ("favicon.svg", "image/svg+xml"),
    ]:
        asset = api.get("/admin/" + file)
        assert asset.status_code == 200
        assert content_type in asset.headers["content-type"]
    assert api.get("/admin/%2e%2e/database.py").status_code == 404


def test_admin_state_contains_ownership_and_redacted_reports(
    api, registered, admin_headers
):
    key, view = registered
    response = api.get("/admin/api/state", headers=admin_headers)
    assert response.status_code == 200
    state = response.json()
    assert state["report_keys"][0]["report_key"] == key
    assert state["view_groups"][0]["view_key"] == view
    assert state["clients"][0]["status"] == "online"
    assert state["clients"][0]["user_id"] == "1000"
    assert "report_key" not in state["clients"][0]["report"]
    assert os.environ["MXSTATUS_ADMIN_TOKEN"] not in response.text
    assert not state["runtime"]["persistent"]


def test_settings_control_expiry_enrollment_and_capacity(
    api, registered, admin_headers
):
    key, view = registered
    settings = ServerSettings(
        offline_after_seconds=30,
        accept_new_clients=False,
        max_machines=1,
        server_name="Research lab",
    )
    response = api.post(
        "/admin/api/settings", json=settings.model_dump(), headers=admin_headers
    )
    assert response.status_code == 200
    db.DB.STATUS_DATA["machine-1"]["created_at"] = datetime.now(
        timezone.utc
    ) - timedelta(seconds=60)
    assert (
        api.get(
            "/view_machine", params={"view_key": view, "machine_id": "machine-1"}
        ).status_code
        == 417
    )
    assert (
        api.get("/admin/api/state", headers=admin_headers).json()["clients"][0][
            "status"
        ]
        == "offline"
    )
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "machine-2"}
        ).status_code
        == 400
    )
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "machine-1"}
        ).status_code
        == 201
    )
    settings.accept_new_clients = True
    assert (
        api.post(
            "/admin/api/settings", json=settings.model_dump(), headers=admin_headers
        ).status_code
        == 200
    )
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "machine-2"}
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("refresh_interval", 0),
        ("refresh_interval", True),
        ("offline_after_seconds", -1),
        ("max_machines", 10001),
        ("default_report_interval", 0),
        ("server_name", ""),
    ],
)
def test_invalid_settings_do_not_change_existing_values(
    api, admin_headers, field, value
):
    before = db.DB.SETTINGS.model_dump()
    response = api.post(
        "/admin/api/settings", json={**before, field: value}, headers=admin_headers
    )
    assert response.status_code == 422
    assert db.DB.SETTINGS.model_dump() == before


def test_client_settings_override_interval_block_and_forget(
    api, registered, admin_headers
):
    key, view = registered
    settings = {
        "machine_id": "machine-1",
        "display_name": "Lab GPU",
        "notes": "Rack 2",
        "report_interval": 45,
        "enabled": True,
    }
    assert (
        api.post(
            "/admin/api/clients/update", json=settings, headers=admin_headers
        ).status_code
        == 200
    )
    response = api.post(
        "/report",
        json={"machine_id": "machine-1", "report_key": key, "name": "old name"},
    )
    assert response.status_code == 201
    assert response.json()["config"]["report_interval"] == 45
    assert api.get("/view", params={"view_key": view}).json()[0]["name"] == "Lab GPU"
    settings["enabled"] = False
    assert (
        api.post(
            "/admin/api/clients/update", json=settings, headers=admin_headers
        ).status_code
        == 200
    )
    assert (
        api.post(
            "/report", json={"machine_id": "machine-1", "report_key": key}
        ).status_code
        == 400
    )
    state = api.get("/admin/api/state", headers=admin_headers).json()
    assert state["clients"][0]["status"] == "blocked"
    assert state["clients"][0]["settings"]["notes"] == "Rack 2"
    assert (
        api.post(
            "/admin/api/clients/delete",
            json={"machine_id": "machine-1"},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert not db.DB.ALL_VIEW_KEYS[view]["view_machines"]
    assert not db.DB.ALL_REPORT_KEYS[key]
    assert "machine-1" not in db.DB.CLIENT_SETTINGS
    assert (
        api.post(
            "/report", json={"machine_id": "machine-1", "report_key": key}
        ).status_code
        == 201
    )


def test_key_and_view_group_management(api, registered, admin_headers):
    key, view = registered
    response = api.post(
        "/admin/api/keys", json={"report_key_desc": "New key"}, headers=admin_headers
    )
    assert response.status_code == 201
    new_key = response.json()["report_key"]
    assert (
        api.post(
            "/admin/api/keys/update",
            json={"report_key": new_key, "report_key_desc": "Renamed"},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert db.DB.USER_REPORT_KEYS["1000"][new_key] == "Renamed"
    group = {
        "view_key": view,
        "view_name": "Private",
        "view_machines": ["machine-1"],
        "view_enabled": False,
    }
    assert (
        api.post(
            "/admin/api/views/update", json=group, headers=admin_headers
        ).status_code
        == 200
    )
    assert api.get("/view", params={"view_key": view}).status_code == 400
    assert (
        api.post(
            "/admin/api/views/delete", json={"view_key": view}, headers=admin_headers
        ).status_code
        == 200
    )
    assert view not in db.DB.USER_VIEW_KEYS["1000"]
    assert (
        api.post(
            "/admin/api/keys/delete",
            json={"report_key": new_key},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert new_key not in db.DB.ALL_REPORT_KEYS
    assert key in db.DB.ALL_REPORT_KEYS


def test_view_edit_cannot_add_another_owners_clients(api, registered, admin_headers):
    _, view = registered
    db.DB.UID_USERS["other"] = "other"
    key = db.create_new_report_key("other")["report_key"]
    db.store_new_report(MachineStatus(machine_id="foreign", report_key=key))
    response = api.post(
        "/admin/api/views/update",
        json={"view_key": view, "view_machines": ["foreign"]},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert db.DB.ALL_VIEW_KEYS[view]["view_machines"] == ["machine-1"]


def test_management_state_survives_restart_without_reviving_bootstrap_keys(
    api, monkeypatch, tmp_path
):
    path = str(tmp_path / "state.sqlite3")
    bootstrap_key = "A" * 32
    monkeypatch.setenv("MXSTATUS_REPORT_KEY", bootstrap_key)
    monkeypatch.setattr(db, "DB", db.Database(path))
    key = db.create_new_report_key("1000", report_key_desc="Persistent key")[
        "report_key"
    ]
    db.delete_report_key("1000", bootstrap_key)
    db.store_new_report(MachineStatus(machine_id="persistent-client", report_key=key))
    group = db.create_new_view_group(
        "1000",
        ViewGroup(
            view_machines=["persistent-client"],
            view_timer=datetime(2030, 1, 1, tzinfo=timezone.utc),
        ),
    )
    db.update_client(
        "persistent-client",
        ClientSettings(
            display_name="Persistent name", enabled=False, report_interval=45
        ),
    )
    db.update_settings(
        ServerSettings(server_name="Persistent server", accept_new_clients=False)
    )
    reloaded = db.Database(path)
    assert bootstrap_key not in reloaded.ALL_REPORT_KEYS
    assert reloaded.ALL_REPORT_KEYS[key] == {"persistent-client"}
    assert reloaded.ALL_VIEW_KEYS[group.view_key]["view_timer"].year == 2030
    assert reloaded.SETTINGS.server_name == "Persistent server"
    assert reloaded.CLIENT_SETTINGS["persistent-client"].enabled is False
    assert reloaded.CLIENT_SETTINGS["persistent-client"].report_interval == 45
    assert not reloaded.STATUS_DATA
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_failed_persistence_rolls_back_mutations(
    api, registered, admin_headers, monkeypatch
):
    key, view = registered

    def fail(state):
        raise OSError("Disk full")

    monkeypatch.setattr(db.DB.store, "save", fail)
    response = api.post(
        "/admin/api/keys/delete", json={"report_key": key}, headers=admin_headers
    )
    assert response.status_code == 500
    assert key in db.DB.ALL_REPORT_KEYS
    assert db.DB.ALL_VIEW_KEYS[view]["view_machines"] == ["machine-1"]
    assert "machine-1" in db.DB.STATUS_DATA
    assert (
        api.post(
            "/admin/api/settings",
            json={"server_name": "Should not persist"},
            headers=admin_headers,
        ).status_code
        == 500
    )
    assert db.DB.SETTINGS.server_name == "MXStatus"
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "new-client"}
        ).status_code
        == 500
    )
    assert "new-client" not in db.DB.ALL_REPORT_KEYS[key]
    assert "new-client" not in db.DB.STATUS_DATA
    # Existing client reports do not depend on writing management state each time.
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "machine-1"}
        ).status_code
        == 201
    )


def test_missing_client_updates_fail_without_creating_records(api, admin_headers):
    assert (
        api.post(
            "/admin/api/clients/update",
            json={"machine_id": "missing"},
            headers=admin_headers,
        ).status_code
        == 400
    )
    assert (
        api.post(
            "/admin/api/clients/delete",
            json={"machine_id": "missing"},
            headers=admin_headers,
        ).status_code
        == 400
    )
    assert not db.DB.CLIENT_SETTINGS


def test_clearing_client_alias_restores_reported_name(api, registered, admin_headers):
    key, view = registered
    api.post(
        "/report",
        json={
            "machine_id": "machine-1",
            "report_key": key,
            "name": "Original name",
            "hostname": "different-host",
        },
    )
    for name in ("Admin alias", ""):
        assert (
            api.post(
                "/admin/api/clients/update",
                json={
                    "machine_id": "machine-1",
                    "display_name": name,
                    "notes": "Notes only",
                },
                headers=admin_headers,
            ).status_code
            == 200
        )
        assert api.get("/view", params={"view_key": view}).json()[0]["name"] == (
            name or "Original name"
        )
    assert db.DB.STATUS_DATA["machine-1"]["name"] == "Original name"
