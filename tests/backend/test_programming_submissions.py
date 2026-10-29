import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.api.routes.student import programming_submissions
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.schemas.programming import (
    CodeSubmissionCreated,
    CodeSubmissionResult,
    ProgrammingProblemView,
    PublicSample,
)
from app.services.judge_runner import _normalized_output


class UnusedDb:
    pass


def override_db():
    yield UnusedDb()


def test_student_can_read_problem_but_response_has_only_public_samples(monkeypatch) -> None:
    def fake_problem(**_kwargs):
        return ProgrammingProblemView(
            assignment_id=7,
            title="整数求和",
            statement="求和",
            input_description="两个整数",
            output_description="一个整数",
            time_limit_ms=2000,
            memory_limit_mb=256,
            samples=[PublicSample(input_data="1 2\n", expected_output="3\n")],
        )

    monkeypatch.setattr(programming_submissions, "get_programming_problem", fake_problem)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=42, system_role="STUDENT")
    try:
        response = TestClient(app).get("/api/student/assignments/7/programming-problem")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["samples"] == [{"input_data": "1 2\n", "expected_output": "3\n"}]
    assert "999998" not in response.text


def test_code_submission_is_queued_after_database_record_is_created(monkeypatch) -> None:
    created = CodeSubmissionCreated(submission_id=12, version=2)
    enqueued: list[int] = []
    monkeypatch.setattr(programming_submissions, "create_code_submission", lambda **_kwargs: created)
    monkeypatch.setattr(programming_submissions, "enqueue_submission", enqueued.append)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=42, system_role="STUDENT")
    try:
        response = TestClient(app).post(
            "/api/assignments/7/code-submissions",
            json={"language": "cpp17", "source_code": "int main() {}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"] == {"submission_id": 12, "version": 2, "status": "QUEUED"}
    assert enqueued == [12]


def test_student_cannot_read_another_students_code_submission(monkeypatch) -> None:
    from fastapi import HTTPException

    def hidden_submission(**_kwargs):
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    monkeypatch.setattr(programming_submissions, "get_code_submission", hidden_submission)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=99, system_role="STUDENT")
    try:
        response = TestClient(app).get("/api/code-submissions/12")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "source_code" not in response.text


def test_teacher_cannot_use_student_judge_endpoints() -> None:
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1, system_role="TEACHER")
    try:
        response = TestClient(app).get("/api/student/assignments/7/programming-problem")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN"


def test_programming_result_does_not_include_source_or_testcase_data(monkeypatch) -> None:
    def result(**_kwargs):
        return CodeSubmissionResult(
            id=12,
            assignment_id=7,
            language="cpp17",
            version=1,
            status="AC",
            submitted_at=datetime(2026, 9, 29, tzinfo=UTC),
            time_ms=3,
            memory_kb=1200,
            executed_case_count=5,
            passed_case_count=5,
        )

    monkeypatch.setattr(programming_submissions, "get_code_submission", result)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=42, system_role="STUDENT")
    try:
        response = TestClient(app).get("/api/code-submissions/12")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert set(response.json()["data"]) == {
        "id", "assignment_id", "language", "version", "status", "submitted_at", "started_at",
        "finished_at", "time_ms", "memory_kb", "executed_case_count", "passed_case_count", "compiler_output",
    }
    assert "source_code" not in response.text
    assert "expected_output" not in response.text


@pytest.mark.parametrize(
    ("actual", "expected"),
    [("3 \n\n", "3\n"), ("3\n4\n", "3\n4"), ("3\n5", "3\n4")],
)
def test_output_normalization_only_ignores_trailing_whitespace(actual: str, expected: str) -> None:
    equal = _normalized_output(actual) == _normalized_output(expected)
    assert equal is (actual != "3\n5")
