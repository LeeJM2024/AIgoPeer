import pytest
from app.core.security import CurrentUser, get_current_user, verify_password
from app.main import app
from sqlalchemy import text


@pytest.fixture
def public_api(teacher_api):
    client, teacher = teacher_api
    del app.dependency_overrides[get_current_user]
    return client, teacher


def credentials(**changes):
    return {
        "student_no": "REGISTER-001",
        "name": "注册测试学生",
        "password": " StudentPassword2026! ",
        **changes,
    }


def test_registration_creates_student_can_login_but_has_no_class(public_api, pg_engine):
    client, _ = public_api
    payload = credentials(student_no=" REGISTER-001 ", name=" 注册测试学生 ")
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    user = response.json()["data"]["user"]
    assert user["role"] == "STUDENT" and user["name"] == "注册测试学生"
    assert "password" not in response.text and "access_token" not in response.text
    with pg_engine.connect() as conn:
        stored = (
            conn.execute(text("SELECT * FROM users WHERE id=:id"), {"id": user["id"]})
            .mappings()
            .one()
        )
        assert stored["password_hash"] != payload["password"]
        assert verify_password(payload["password"], stored["password_hash"])
        assert (
            conn.execute(
                text("SELECT count(*) FROM enrollments WHERE user_id=:id"),
                {"id": user["id"]},
            ).scalar_one()
            == 0
        )
    login = client.post(
        "/api/auth/login",
        json={"account": "REGISTER-001", "password": payload["password"]},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    assert client.get("/api/teacher/classes", headers=headers).status_code == 403
    assignments = client.get("/api/student/assignments", headers=headers)
    assert assignments.status_code == 200 and assignments.json()["data"] == []


def test_duplicate_registration_never_changes_existing_account(public_api, pg_engine):
    client, teacher = public_api
    assert client.post("/api/auth/register", json=credentials()).status_code == 201
    with pg_engine.connect() as conn:
        original = (
            conn.execute(
                text(
                    "SELECT name,password_hash,system_role FROM users WHERE student_no='REGISTER-001'"
                )
            )
            .mappings()
            .one()
        )
        teacher_original = (
            conn.execute(
                text("SELECT name,password_hash,system_role FROM users WHERE id=:id"),
                {"id": teacher},
            )
            .mappings()
            .one()
        )
    for account in ("REGISTER-001", "TEST-TEACHER"):
        response = client.post(
            "/api/auth/register",
            json=credentials(
                student_no=account, name="不同姓名", password="DifferentPassword2026!"
            ),
        )
        assert (
            response.status_code == 409
            and response.json()["code"] == "ACCOUNT_ALREADY_EXISTS"
        )
    with pg_engine.connect() as conn:
        assert dict(
            conn.execute(
                text(
                    "SELECT name,password_hash,system_role FROM users WHERE student_no='REGISTER-001'"
                )
            )
            .mappings()
            .one()
        ) == dict(original)
        assert dict(
            conn.execute(
                text("SELECT name,password_hash,system_role FROM users WHERE id=:id"),
                {"id": teacher},
            )
            .mappings()
            .one()
        ) == dict(teacher_original)


@pytest.mark.parametrize(
    "changes",
    [
        {"student_no": "   "},
        {"student_no": "invalid account"},
        {"student_no": "x" * 33},
        {"name": "   "},
        {"password": "short"},
        {"password": " " * 10},
        {"password": "x" * 129},
        {"system_role": "TEACHER"},
        {"role": "TEACHER"},
        {"class_id": 1},
    ],
)
def test_registration_validates_without_leaking_input(public_api, pg_engine, changes):
    client, _ = public_api
    response = client.post("/api/auth/register", json=credentials(**changes))
    assert response.status_code == 422
    assert credentials()["password"] not in response.text
    with pg_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM users WHERE system_role='STUDENT'")
            ).scalar_one()
            == 0
        )


def test_registration_has_independent_persistent_rate_limit(public_api):
    client, _ = public_api
    assert client.post("/api/auth/register", json=credentials()).status_code == 201
    for _ in range(4):
        assert client.post("/api/auth/register", json=credentials()).status_code == 409
    limited = client.post("/api/auth/register", json=credentials())
    assert limited.status_code == 429
    assert limited.json()["code"] == "REGISTRATION_RATE_LIMITED"
    assert limited.headers["Retry-After"] == "600"
    assert (
        client.post(
            "/api/auth/login",
            json={"account": "REGISTER-001", "password": credentials()["password"]},
        ).status_code
        == 200
    )


def test_teacher_enrolls_self_registered_student_without_resetting_password(
    public_api, pg_engine
):
    client, teacher = public_api
    registered = client.post("/api/auth/register", json=credentials()).json()["data"][
        "user"
    ]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(teacher, "TEACHER")
    class_id = client.post(
        "/api/teacher/classes", json={"name": "注册流程测试班", "course_term": "TEST"}
    ).json()["data"]["class_id"]
    response = client.post(
        f"/api/teacher/classes/{class_id}/students/import",
        json={
            "students": [{"student_no": "REGISTER-001", "name": credentials()["name"]}]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["created_accounts"] == 0
    assert response.json()["data"]["new_enrollments"] == 1
    with pg_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT class_id FROM enrollments WHERE user_id=:id"),
                {"id": registered["id"]},
            ).scalar_one()
            == class_id
        )
        stored = conn.execute(
            text("SELECT password_hash FROM users WHERE id=:id"),
            {"id": registered["id"]},
        ).scalar_one()
        assert verify_password(credentials()["password"], stored)
