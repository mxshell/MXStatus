import pytest
from fastapi.testclient import TestClient

from server import database as db
from server.main import app


@pytest.fixture
def api(monkeypatch):
    for key in ("REPORT_KEY", "VIEW_KEY", "MACHINE_IDS", "ADMIN_USER_ID"):
        monkeypatch.delenv("MXSTATUS_" + key, raising=False)
    monkeypatch.setenv("MXSTATUS_ADMIN_TOKEN", "admin-token-for-tests-" + "x" * 32)
    monkeypatch.setattr(db, "DB", db.Database())
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def admin_headers():
    return {"Authorization": "Bearer admin-token-for-tests-" + "x" * 32}


@pytest.fixture
def registered(api, admin_headers):
    key = api.post(
        "/create_report_key", params={"user_id": "1000"}, headers=admin_headers
    ).json()["report_key"]
    assert (
        api.post(
            "/report",
            json={
                "machine_id": "machine-1",
                "report_key": key,
                "gpu_status": [{"index": 0}],
            },
        ).status_code
        == 201
    )
    group = api.post(
        "/create_view_group",
        params={"user_id": "1000"},
        json={"view_machines": ["machine-1"]},
        headers=admin_headers,
    )
    assert group.status_code == 201
    return key, group.json()["view_key"]
