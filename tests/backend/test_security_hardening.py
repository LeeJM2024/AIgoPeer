"""Security checks use an isolated schema; no demonstration accounts are touched."""

import io
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from zipfile import ZIP_DEFLATED, ZipFile

import jwt
import pytest
from app.core.archive_security import (
    UnsafeArchive,
    inspect_office,
    inspect_zip,
    safe_archive_path,
)
from app.core.config import settings
from app.core.security import get_current_user, hash_password
from app.main import app
from app.schemas.auth import LoginInput
from app.schemas.teacher import StudentImportInput, StudentInput
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

PASSWORD = "SecurityTest2026!"


def proof(token, *, nonce=None, timestamp=None):
    return {
        "Authorization": "Bearer " + token,
        "X-Request-Nonce": nonce or secrets.token_hex(16),
        "X-Request-Timestamp": str(
            int(time.time()) if timestamp is None else timestamp
        ),
    }


@pytest.fixture
def security_api(teacher_api, pg_engine):
    client, teacher = teacher_api
    with pg_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET password_hash=:p WHERE id=:id"),
            {"p": hash_password(PASSWORD), "id": teacher},
        )
        connection.execute(
            text("""INSERT INTO users(student_no,name,password_hash,system_role)
            VALUES ('SEC-STUDENT','安全测试学生',:p,'STUDENT')"""),
            {"p": hash_password(PASSWORD)},
        )
    del app.dependency_overrides[get_current_user]

    def login(account="TEST-TEACHER"):
        response = client.post(
            "/api/auth/login", json={"account": account, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]["access_token"]

    return client, login, teacher


def test_account_canonicalization_preserves_password_and_detects_duplicates():
    account = LoginInput(account=" Ｄ１０１ ", password=" Ａbc123456! ")
    assert account.account == "D101" and account.password == " Ａbc123456! "
    with pytest.raises(ValidationError):
        StudentImportInput(
            students=[
                {"student_no": "D101", "name": "学生甲"},
                {"student_no": "Ｄ１０１", "name": "学生乙"},
            ]
        )


@pytest.mark.parametrize(
    "account", ["D\u200b101", "D\u202e101", "D/101", "D\\101", "D' OR 1=1", None, 123]
)
def test_ambiguous_accounts_are_rejected(account):
    with pytest.raises(ValidationError):
        LoginInput(account=account, password=PASSWORD)


@pytest.mark.parametrize("name", ["张\u200b三", "<script>", "../张三", "张三\x00"])
def test_names_cannot_create_unsafe_upload_paths(name):
    with pytest.raises(ValidationError):
        StudentInput(student_no="D101", name=name)


def test_security_headers_and_cross_site_request_rejection():
    with TestClient(app) as client:
        response = client.get("/api/not-a-real-route")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Cache-Control"] == "private, no-store"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert (
            client.get("/api/health", headers={"Host": "attacker.invalid"}).status_code
            == 400
        )
        response = client.post(
            "/api/auth/login",
            headers={"Origin": "https://attacker.invalid"},
            json={"account": "TEST", "password": PASSWORD},
        )
        assert (
            response.status_code == 403
            and response.json()["code"] == "ORIGIN_NOT_ALLOWED"
        )


def test_request_limit_checks_declared_and_streamed_size():
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/auth/login",
                content=b"{}",
                headers={"Content-Length": str(9 * 1024 * 1024)},
            ).status_code
            == 413
        )
        response = client.post(
            "/api/auth/login",
            content=iter([b" " * (9 * 1024 * 1024)]),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413, response.text


def test_upload_authentication_precedes_multipart_parsing(monkeypatch):
    from starlette.requests import Request

    def forbidden_parse(*args, **kwargs):
        raise AssertionError("Unauthenticated upload must not parse its body")

    monkeypatch.setattr(Request, "form", forbidden_parse)
    with TestClient(app) as client:
        response = client.post(
            "/api/assignments/1/project-submissions",
            content=b"not-a-valid-multipart",
            headers={"Content-Type": "multipart/form-data; boundary=x"},
        )
        assert response.status_code == 401


def test_replay_rejected_even_after_business_failure(security_api):
    client, login, _ = security_api
    headers = proof(login())
    # Valid JSON, invalid fields: a failed operation still consumes its nonce.
    assert (
        client.post("/api/teacher/classes", headers=headers, json={}).status_code == 422
    )
    result = client.post(
        "/api/teacher/classes",
        headers=headers,
        json={"name": "不可重放", "course_term": "TEST"},
    )
    assert result.status_code == 409 and result.json()["code"] == "REQUEST_REPLAYED"


def test_concurrent_replays_mutate_only_once(security_api, pg_engine):
    client, login, _ = security_api
    headers = proof(login())

    def send(_):
        return client.post(
            "/api/teacher/classes",
            headers=headers,
            json={"name": "唯一安全测试班", "course_term": "TEST"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(send, range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["code"]
        == "REQUEST_REPLAYED"
    )
    with pg_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM classes WHERE name='唯一安全测试班'")
            ).scalar_one()
            == 1
        )


def test_missing_stale_future_proofs_and_student_privilege(security_api):
    client, login, _ = security_api
    token = login()
    payload = {"name": "TEST", "course_term": "TEST"}
    assert (
        client.post(
            "/api/teacher/classes",
            headers={"Authorization": "Bearer " + token},
            json=payload,
        ).status_code
        == 400
    )
    for age in (-1000, 1000):
        response = client.post(
            "/api/teacher/classes",
            headers=proof(token, timestamp=int(time.time()) + age),
            json=payload,
        )
        assert (
            response.status_code == 409 and response.json()["code"] == "REQUEST_EXPIRED"
        )
    student = login("SEC-STUDENT")
    assert client.get("/api/teacher/classes", headers=proof(student)).status_code == 403
    assert (
        client.post(
            "/api/teacher/classes", headers=proof(student), json=payload
        ).status_code
        == 403
    )


def test_authentication_does_not_start_analytics_transaction(security_api):
    client, login, _ = security_api
    response = client.get("/api/teacher/learning-analysis", headers=proof(login()))
    assert response.status_code == 200, response.text


def test_password_rotation_and_logout_revoke_captured_tokens(security_api):
    client, login, _ = security_api
    old, other_device = login(), login()
    result = client.post(
        "/api/auth/change-password",
        headers=proof(old),
        json={
            "current_password": PASSWORD,
            "new_password": "ChangedSecurity2026!",
            "confirm_password": "ChangedSecurity2026!",
        },
    )
    assert result.status_code == 200, result.text
    new = result.json()["data"]["access_token"]
    for token in (old, other_device):
        assert client.get("/api/auth/me", headers=proof(token)).status_code == 401
    assert client.get("/api/auth/me", headers=proof(new)).status_code == 200
    assert client.post("/api/auth/logout", headers=proof(new)).status_code == 200
    assert client.get("/api/auth/me", headers=proof(new)).status_code == 401


def test_direct_password_reset_invalidates_existing_sessions(security_api, pg_engine):
    client, login, teacher = security_api
    token = login()
    with pg_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET password_hash=:p WHERE id=:id"),
            {"p": hash_password("ResetSecurity2026!"), "id": teacher},
        )
    assert client.get("/api/auth/me", headers=proof(token)).status_code == 401


def test_forged_claims_cannot_reuse_a_student_session(security_api):
    client, login, teacher = security_api
    student_token = login("SEC-STUDENT")
    payload = jwt.decode(student_token, options={"verify_signature": False})
    for updates in (
        {"role": "TEACHER"},
        {"sub": str(teacher), "role": "TEACHER"},
        {"aud": "another-application"},
        {"iss": "another-issuer"},
    ):
        forged = jwt.encode(
            {**payload, **updates},
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        assert client.get("/api/auth/me", headers=proof(forged)).status_code == 401


def test_api_rate_limit_is_enforced_before_mutation(security_api, pg_engine):
    import hashlib
    import hmac

    client, login, teacher = security_api
    token = login()
    first = client.post(
        "/api/teacher/classes",
        headers=proof(token),
        json={"name": "限速前", "course_term": "TEST"},
    )
    assert first.status_code == 201
    key = hmac.new(
        settings.jwt_secret.encode(), f"api:write:{teacher}".encode(), hashlib.sha256
    ).hexdigest()
    with pg_engine.begin() as connection:
        connection.execute(
            text("UPDATE login_rate_limits SET attempts=120 WHERE scope_key=:key"),
            {"key": key},
        )
    blocked = client.post(
        "/api/teacher/classes",
        headers=proof(token),
        json={"name": "限速后", "course_term": "TEST"},
    )
    assert blocked.status_code == 429 and blocked.json()["code"] == "API_RATE_LIMITED"
    with pg_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM classes WHERE name='限速后'")
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize(
    "path",
    ["../private", "／etc/passwd", "．．/private", "C:/secret", "x\\y", "x\x00y"],
)
def test_archive_path_traversal_and_width_bypasses(path):
    with pytest.raises(UnsafeArchive):
        safe_archive_path(path)


def test_nested_compression_bomb_and_active_office_content():
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", "A" * 200_000)
    with ZipFile(buffer) as archive, pytest.raises(UnsafeArchive, match="COMPRESSION"):
        inspect_office(archive)
    for name, content in [
        ("ppt/vbaProject.bin", b"macro"),
        ("ppt/slides/slide1.xml", b'<!DOCTYPE x [<!ENTITY y "x">]>'),
        (
            "ppt/_rels/presentation.xml.rels",
            b'<Relationship TargetMode="External" Target="file:///secret"/>',
        ),
    ]:
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr(name, content)
        with ZipFile(buffer) as archive, pytest.raises(UnsafeArchive):
            inspect_office(archive)


def test_duplicate_normalized_archive_entries_are_rejected():
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("README.md", "safe")
        archive.writestr("ＲＥＡＤＭＥ.md", "ambiguous")
    with ZipFile(buffer) as archive, pytest.raises(UnsafeArchive, match="DUPLICATE"):
        inspect_zip(archive)
