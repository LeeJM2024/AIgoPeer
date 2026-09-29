from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.config import Settings, settings
from app.core.security import get_current_user
from app.main import app
from app.schemas.teacher import AssignmentCreate, TeacherGradeCorrectionInput
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text


def test_tokens_require_expiry_and_valid_identity():
    now = datetime.now(UTC)
    for payload in [
        {"sub": "1", "role": "TEACHER", "iat": now},
        {"sub": None, "role": "TEACHER", "iat": now, "exp": now + timedelta(minutes=5)},
        {
            "sub": "1",
            "role": "TEACHER",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
    ]:
        token = jwt.encode(
            payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        with TestClient(app) as client:
            assert (
                client.get(
                    "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
                ).status_code
                == 401
            )


def test_internal_endpoints_fail_closed(monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(settings, "internal_api_token", "")
        assert (
            client.post("/internal/designated-review/aggregate", json={}).status_code
            == 503
        )
        monkeypatch.setattr(settings, "internal_api_token", "test-service-secret")
        assert (
            client.post("/internal/designated-review/aggregate", json={}).status_code
            == 403
        )
        # Authenticated invalid requests reach schema validation, not the algorithm.
        assert (
            client.post(
                "/internal/designated-review/aggregate",
                json={},
                headers={"X-Internal-Token": "test-service-secret"},
            ).status_code
            == 422
        )


def test_production_rejects_default_secrets():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            jwt_secret="development-only-change-me",
            _env_file=None,
        )


def test_login_limit_persists_between_requests(teacher_api):
    client, _ = teacher_api
    del app.dependency_overrides[get_current_user]
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login", json={"account": "UNKNOWN", "password": "wrong"}
            ).status_code
            == 401
        )
    response = client.post(
        "/api/auth/login", json={"account": "UNKNOWN", "password": "wrong"}
    )
    assert response.status_code == 429 and response.headers["Retry-After"] == "600"
    assert response.json()["code"] == "LOGIN_RATE_LIMITED"


def test_validation_does_not_echo_passwords(teacher_api):
    client, _ = teacher_api
    response = client.post(
        "/api/teacher/classes/1/students/import",
        json={"students": [{"student_no": "x", "name": "x", "password": "SECRET"}]},
    )
    assert response.status_code == 422
    assert "SECRET" not in response.text


def test_grade_rejects_precision_and_blank_reasons():
    from app.schemas.teacher import StudentInput

    assert (
        StudentInput(
            student_no=" x ", name=" 学生 ", password="  preserve-spaces  "
        ).password
        == "  preserve-spaces  "
    )
    with pytest.raises(ValidationError):
        TeacherGradeCorrectionInput(
            expected_version=1,
            reason="   ",
            rubric_scores=[{"rubric_item_id": 1, "score": 80}],
        )
    with pytest.raises(ValidationError):
        TeacherGradeCorrectionInput(
            expected_version=1,
            reason="正常原因",
            rubric_scores=[{"rubric_item_id": 1, "score": 80.001}],
        )


def test_timezone_is_required():
    with pytest.raises(ValidationError):
        AssignmentCreate(
            title="时间测试",
            type="FINAL_PROJECT",
            class_ids=[1, 2],
            submit_deadline="2030-01-01T00:00:00",
            review_deadline="2030-02-01T00:00:00Z",
            teacher_weight=0.6,
            designated_review_weight=0.4,
            rubric_items=[{"name": "原理", "max_score": 100, "sort_order": 1}],
        )


def test_empty_assignment_cannot_publish(course):
    c = course
    with c["engine"].begin() as conn:
        conn.execute(
            text("UPDATE assignments SET status='TEACHER_GRADING' WHERE id=:id"),
            {"id": c["id"]},
        )
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert response.status_code == 424 and "NO_VALID_SUBMISSIONS" in response.text
