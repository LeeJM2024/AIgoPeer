import secrets
import time

import pytest
from app.core.security import get_current_user, hash_password, verify_password
from app.main import app
from app.schemas.auth import ChangePasswordInput
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

OLD = "OriginalPassword2026!"
NEW = " NewPassword2026! "


def test_public_registration_is_removed():
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "student_no": "SHOULD-NOT-EXIST",
                    "name": "不能自助注册",
                    "password": NEW,
                },
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/auth/change-password",
                json={
                    "current_password": OLD,
                    "new_password": NEW,
                    "confirm_password": NEW,
                },
            ).status_code
            == 401
        )
    assert "/api/auth/register" not in app.openapi()["paths"]


@pytest.fixture
def password_api(teacher_api, pg_engine, monkeypatch):
    client, teacher = teacher_api
    with pg_engine.begin() as db:
        db.execute(
            text("UPDATE users SET password_hash=:p WHERE id=:id"),
            {"p": hash_password(OLD), "id": teacher},
        )
        student = db.execute(
            text("""INSERT INTO users(student_no,name,password_hash,system_role)
            VALUES ('PASSWORD-STUDENT','密码测试学生',:p,'STUDENT') RETURNING id"""),
            {"p": hash_password(OLD)},
        ).scalar_one()
    del app.dependency_overrides[get_current_user]
    original = client.request

    def request(method, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        if "Authorization" in headers and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            headers.setdefault("X-Request-Nonce", secrets.token_hex(16))
            headers.setdefault("X-Request-Timestamp", str(int(time.time())))
        kwargs["headers"] = headers
        return original(method, url, **kwargs)

    monkeypatch.setattr(client, "request", request)
    return client, teacher, student


def auth(client, account, password=OLD):
    response = client.post(
        "/api/auth/login", json={"account": account, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}


@pytest.mark.parametrize("account", ["TEST-TEACHER", "PASSWORD-STUDENT"])
def test_each_role_changes_only_own_password(password_api, pg_engine, account):
    client, teacher, student = password_api
    headers = auth(client, account)
    response = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": OLD, "new_password": NEW, "confirm_password": NEW},
    )
    assert response.status_code == 200 and response.json()["data"]["changed"] is True
    assert OLD not in response.text and NEW not in response.text
    own = teacher if account == "TEST-TEACHER" else student
    other = student if own == teacher else teacher
    with pg_engine.connect() as db:
        hashes = dict(db.execute(text("SELECT id,password_hash FROM users")).all())
        assert verify_password(NEW, hashes[own]) and not verify_password(
            OLD, hashes[own]
        )
        assert verify_password(OLD, hashes[other])
        audit = db.execute(
            text(
                "SELECT actor_id,entity_id,before_json,after_json FROM audit_logs WHERE action='CHANGE_PASSWORD'"
            )
        ).one()
        assert audit.actor_id == own == audit.entity_id
        assert (
            OLD not in str(audit)
            and NEW not in str(audit)
            and hashes[own] not in str(audit)
        )
    assert (
        client.post(
            "/api/auth/login", json={"account": account, "password": OLD}
        ).status_code
        == 401
    )
    assert (
        client.get("/api/auth/me", headers=auth(client, account, NEW)).status_code
        == 200
    )


def test_wrong_current_password_cannot_change_or_target_another_user(
    password_api, pg_engine
):
    client, teacher, _ = password_api
    headers = auth(client, "TEST-TEACHER")
    data = {
        "current_password": "WrongPassword!",
        "new_password": NEW,
        "confirm_password": NEW,
    }
    response = client.post("/api/auth/change-password", headers=headers, json=data)
    assert (
        response.status_code == 400
        and response.json()["code"] == "CURRENT_PASSWORD_INCORRECT"
    )
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    for extra in ({"user_id": teacher}, {"account": "PASSWORD-STUDENT"}):
        assert (
            client.post(
                "/api/auth/change-password", headers=headers, json=dict(data, **extra)
            ).status_code
            == 422
        )
    data.update(current_password=OLD, new_password=OLD, confirm_password=OLD)
    response = client.post("/api/auth/change-password", headers=headers, json=data)
    assert (
        response.status_code == 400
        and response.json()["code"] == "NEW_PASSWORD_UNCHANGED"
    )
    data.update(new_password=NEW, confirm_password="MismatchPassword2026!")
    assert (
        client.post("/api/auth/change-password", headers=headers, json=data).status_code
        == 422
    )
    with pg_engine.connect() as db:
        assert verify_password(
            OLD,
            db.execute(
                text("SELECT password_hash FROM users WHERE id=:id"), {"id": teacher}
            ).scalar_one(),
        )
        assert (
            db.execute(
                text("SELECT count(*) FROM audit_logs WHERE action='CHANGE_PASSWORD'")
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize("password", ["short", " " * 10, "x" * 129])
def test_password_policy(password):
    with pytest.raises(ValidationError):
        ChangePasswordInput(
            current_password=OLD, new_password=password, confirm_password=password
        )


def test_password_change_has_independent_rate_limit(password_api):
    client, _, _ = password_api
    headers = auth(client, "PASSWORD-STUDENT")
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/change-password",
                headers=headers,
                json={
                    "current_password": "WrongPassword!",
                    "new_password": NEW,
                    "confirm_password": NEW,
                },
            ).status_code
            == 400
        )
    response = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": OLD, "new_password": NEW, "confirm_password": NEW},
    )
    assert (
        response.status_code == 429
        and response.json()["code"] == "PASSWORD_CHANGE_RATE_LIMITED"
    )
    assert response.headers["Retry-After"] == "600"
    assert auth(client, "PASSWORD-STUDENT")


def test_teacher_added_name_is_the_student_login_display_name(password_api):
    client, _, _ = password_api
    headers = auth(client, "TEST-TEACHER")
    class_response = client.post(
        "/api/teacher/classes",
        headers=headers,
        json={"name": "姓名绑定测试班", "course_term": "TEST"},
    )
    assert class_response.status_code == 201
    class_id = class_response.json()["data"]["class_id"]
    response = client.post(
        f"/api/teacher/classes/{class_id}/students/import",
        headers=headers,
        json={
            "students": [
                {"student_no": "NAMED-STUDENT", "name": "王小明", "password": OLD}
            ]
        },
    )
    assert response.status_code == 200, response.text
    login = client.post(
        "/api/auth/login", json={"account": "NAMED-STUDENT", "password": OLD}
    )
    assert login.status_code == 200
    assert login.json()["data"]["user"]["name"] == "王小明"
    roster = client.get(f"/api/teacher/classes/{class_id}/students", headers=headers)
    assert roster.status_code == 200
    assert any(
        s["student_no"] == "NAMED-STUDENT" and s["name"] == "王小明"
        for s in roster.json()["data"]
    )
