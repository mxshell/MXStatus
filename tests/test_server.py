import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from server import database as db
from server.data_model import MachineStatus, ViewGroup
from server.middleware import RequestSizeLimit


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/get", None),
        ("post", "/create_report_key", None),
        ("post", "/delete_report_key", None),
        ("post", "/create_view_group", {}),
        ("post", "/add_machines_to_view_group", []),
        ("post", "/remove_machines_from_view_group", []),
        ("post", "/set_machines_in_view_group", []),
    ],
)
def test_admin_routes_require_auth(api, method, path, body):
    response = api.request(
        method,
        path,
        params={"user_id": "1000", "report_key": "x", "view_key": "x"},
        json=body,
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_admin_fails_closed_without_configuration(api, monkeypatch):
    monkeypatch.delenv("MXSTATUS_ADMIN_TOKEN")
    assert api.get("/get").status_code == 503
    monkeypatch.setenv("MXSTATUS_ADMIN_TOKEN", "short")
    assert api.get("/get", headers={"Authorization": "Bearer short"}).status_code == 503


def test_invalid_admin_token(api):
    assert (
        api.get("/get", headers={"Authorization": "Bearer incorrect"}).status_code
        == 401
    )


def test_no_published_credentials(api):
    assert not db.DB.ALL_REPORT_KEYS
    assert not db.DB.ALL_VIEW_KEYS
    assert (
        api.post(
            "/report", json={"report_key": "dev@markhh.com", "machine_id": "m"}
        ).status_code
        == 400
    )
    assert api.get("/view", params={"view_key": "markhuang"}).status_code == 400


def test_public_and_admin_views_do_not_expose_report_key(
    api, registered, admin_headers
):
    key, view = registered
    for path, params in [
        ("/get", {}),
        ("/view", {"view_key": view}),
        ("/view_machine", {"view_key": view, "machine_id": "machine-1"}),
    ]:
        response = api.get(path, params=params, headers=admin_headers)
        assert response.status_code == 200, response.text
        assert key not in response.text
        assert "report_key" not in response.text
    assert "report_key" not in db.DB.STATUS_DATA["machine-1"]


def test_machine_status_error_codes(api, registered):
    _, view = registered
    params = {"view_key": view, "machine_id": "machine-1"}
    assert (
        api.get("/view_machine", params={**params, "machine_id": "unknown"}).status_code
        == 404
    )
    assert (
        api.get("/view_machine", params={**params, "view_key": "invalid"}).status_code
        == 404
    )
    for expiry in (0, -10):
        assert (
            api.get(
                "/view_machine", params={**params, "seconds_to_expire": expiry}
            ).status_code
            == 422
        )
    report = db.DB.STATUS_DATA["machine-1"]
    report["gpu_status"] = []
    assert api.get("/view_machine", params=params).status_code == 418
    report["created_at"] = datetime.now(timezone.utc) - timedelta(minutes=6)
    assert api.get("/view_machine", params=params).status_code == 417


@pytest.mark.parametrize("timer", ["2000-01-01T00:00:00", "2000-01-01T00:00:00+08:00"])
def test_expired_and_disabled_views_are_inaccessible(api, registered, timer):
    _, key = registered
    db.DB.ALL_VIEW_KEYS[key]["view_timer"] = ViewGroup(view_timer=timer).view_timer
    for path, code in [
        ("/view", 400),
        ("/view_machine", 404),
        ("/check_view_group", 404),
    ]:
        assert (
            api.get(
                path, params={"view_key": key, "machine_id": "machine-1"}
            ).status_code
            == code
        )
    db.DB.ALL_VIEW_KEYS[key].update(view_timer=None, view_enabled=False)
    assert api.get("/view", params={"view_key": key}).status_code == 400
    assert api.get("/check_view_group", params={"view_key": key}).status_code == 404


def test_server_owns_report_timestamp(api, registered):
    key, _ = registered
    response = api.post(
        "/report",
        json={
            "machine_id": "machine-1",
            "report_key": key,
            "created_at": "2999-01-01T00:00:00+08:00",
        },
    )
    assert response.status_code == 201
    assert (
        abs(
            (
                datetime.now(timezone.utc)
                - db.DB.STATUS_DATA["machine-1"]["created_at"]
            ).total_seconds()
        )
        < 5
    )


@pytest.mark.parametrize(
    "users", [{"all_users": "alice"}, {"online_users": [42]}, ["alice"]]
)
def test_malformed_users_return_validation_error(api, registered, users):
    key, _ = registered
    response = api.post(
        "/report", json={"report_key": key, "machine_id": "m", "users_info": users}
    )
    assert response.status_code == 422
    assert "input" not in response.text
    assert key not in response.text


def test_nonfinite_telemetry_is_rejected(api, registered):
    key, _ = registered
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "m", "cpu_usage": "NaN"}
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "m", "ipv4s": [42]}
        ).status_code
        == 422
    )


def test_masking_does_not_mutate_inputs():
    users = {"all_users": ["alice"]}
    status = MachineStatus(users_info=users)
    assert users == {"all_users": ["alice"]}
    assert status.users_info == {"all_users": ["al**e"]}


def test_keys_are_case_insensitive_and_collision_safe(api, admin_headers):
    key = "customreportkey1234"
    assert (
        api.post(
            "/create_report_key",
            params={"user_id": "1000", "report_key": key},
            headers=admin_headers,
        ).json()["report_key"]
        == key.upper()
    )
    assert (
        api.post(
            "/create_report_key",
            params={"user_id": "1000", "report_key": key.upper()},
            headers=admin_headers,
        ).status_code
        == 400
    )
    assert (
        api.post("/report", json={"report_key": key, "machine_id": "m"}).status_code
        == 201
    )
    view = "customviewkey12345"
    assert (
        api.post(
            "/create_view_group",
            params={"user_id": "1000"},
            json={"view_key": view, "view_machines": ["m"]},
            headers=admin_headers,
        ).status_code
        == 201
    )
    assert api.get("/view", params={"view_key": view.lower()}).status_code == 200
    assert (
        api.post(
            "/create_view_group",
            params={"user_id": "1000"},
            json={"view_key": view.upper()},
            headers=admin_headers,
        ).status_code
        == 400
    )


def test_machine_ownership_is_enforced(api, registered, admin_headers):
    key, view = registered
    db.DB.UID_USERS["other"] = "other"
    other_key = db.create_new_report_key("other")["report_key"]
    response = api.post(
        "/report",
        json={"report_key": other_key, "machine_id": "machine-1", "name": "spoofed"},
    )
    assert response.status_code == 400
    assert db.DB.STATUS_DATA["machine-1"]["name"] is None
    for path, body in [
        ("/create_view_group", {"view_machines": ["machine-1"]}),
        ("/add_machines_to_view_group", ["machine-1"]),
        ("/set_machines_in_view_group", ["machine-1"]),
    ]:
        response = api.post(
            path,
            params={"user_id": "other", "view_key": view},
            json=body,
            headers=admin_headers,
        )
        assert response.status_code == 400
    other_view = db.create_new_view_group("other", ViewGroup()).view_key
    for path in ("/add_machines_to_view_group", "/set_machines_in_view_group"):
        assert (
            api.post(
                path,
                params={"user_id": "other", "view_key": other_view},
                json=["machine-1"],
                headers=admin_headers,
            ).status_code
            == 400
        )


def test_view_membership_handles_none_duplicates_and_clear(
    api, registered, admin_headers
):
    _, view = registered
    params = {"user_id": "1000", "view_key": view}
    for path in ("/add_machines_to_view_group", "/set_machines_in_view_group"):
        response = api.post(
            path, params=params, json=["machine-1", "machine-1"], headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["view_machines"] == ["machine-1"]
    response = api.post(
        "/set_machines_in_view_group", params=params, json=[], headers=admin_headers
    )
    assert response.json()["view_machines"] == []
    response = api.post(
        "/create_view_group",
        params={"user_id": "1000"},
        json={"view_machines": None},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["view_machines"] == []
    params["view_key"] = response.json()["view_key"]
    assert (
        api.post(
            "/add_machines_to_view_group",
            params=params,
            json=["machine-1"],
            headers=admin_headers,
        ).status_code
        == 200
    )


def test_revoke_key_removes_reports_and_memberships(api, registered, admin_headers):
    key, view = registered
    assert (
        api.post(
            "/delete_report_key",
            params={"user_id": "1000", "report_key": key.lower()},
            headers=admin_headers,
        ).status_code
        == 200
    )
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "machine-1"}
        ).status_code
        == 400
    )
    assert api.get("/view", params={"view_key": view}).json() == []
    assert db.DB.ALL_VIEW_KEYS[view]["view_machines"] == []
    assert not db.DB.STATUS_DATA


def test_same_user_key_rotation_survives_old_key_deletion(api, registered):
    old_key, view = registered
    new_key = db.create_new_report_key("1000")["report_key"]
    db.store_new_report(MachineStatus(report_key=new_key, machine_id="machine-1"))
    db.delete_report_key("1000", old_key)
    assert db.get_view(view)[0]["machine_id"] == "machine-1"


@pytest.mark.parametrize("error", [ValueError, KeyError, RuntimeError])
def test_unexpected_errors_hide_internal_details(api, monkeypatch, error):
    def fail(key):
        raise error("secret database connection details")

    monkeypatch.setattr(db, "get_view", fail)
    response = api.get("/view", params={"view_key": "x"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_bootstrap_configuration(monkeypatch, api):
    monkeypatch.setenv("MXSTATUS_REPORT_KEY", "a" * 32)
    monkeypatch.setenv("MXSTATUS_VIEW_KEY", "b" * 32)
    monkeypatch.setenv("MXSTATUS_MACHINE_IDS", "m1, m2,m1")
    state = db.Database()
    assert state.ALL_REPORT_KEYS == {"A" * 32: {"m1", "m2"}}
    assert state.ALL_VIEW_KEYS["B" * 32]["view_machines"] == ["m1", "m2"]
    monkeypatch.delenv("MXSTATUS_REPORT_KEY")
    with pytest.raises(ValueError):
        db.Database()


def test_capacity_and_body_limits(api, registered, monkeypatch):
    key, _ = registered
    monkeypatch.setattr(db, "MAX_MACHINES", 1)
    assert (
        api.post("/report", json={"report_key": key, "machine_id": "new"}).status_code
        == 400
    )
    assert (
        api.post(
            "/report", json={"report_key": key, "machine_id": "machine-1"}
        ).status_code
        == 201
    )
    assert api.post("/report", content=b"x" * (1024 * 1024 + 1)).status_code == 413


def test_streamed_body_limit_without_content_length():
    async def check():
        messages = iter(
            [
                {"type": "http.request", "body": b"123", "more_body": True},
                {"type": "http.request", "body": b"456", "more_body": False},
            ]
        )
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        async def downstream(*args):
            pytest.fail("Oversized stream reached application")

        await RequestSizeLimit(downstream, 5)({"type": "http"}, receive, send)
        assert sent[0]["status"] == 413

    asyncio.run(check())
