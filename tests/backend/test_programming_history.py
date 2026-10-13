"""Real database coverage for the student's read-only code submission history."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from app.core.security import CurrentUser, get_current_user
from app.main import app
from sqlalchemy import text


@contextmanager
def as_student(user_id):
    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id, "STUDENT")
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = previous


@pytest.fixture
def history_course(course):
    c = course
    deadline = datetime.now(UTC) - timedelta(days=1)
    payload = {
        **c["payload"], "type": "PROGRAMMING", "title": "历史测试",
        "submit_deadline": deadline.isoformat(),
        "review_deadline": (deadline + timedelta(days=2)).isoformat(),
        "programming_problem": {
            "statement": "整数求和", "input_description": "两个整数", "output_description": "和",
            "time_limit_ms": 2000, "memory_limit_mb": 256,
            "test_cases": [
                {"input_data": "1 2", "expected_output": "3", "is_public": True},
                {"input_data": "PRIVATE_HIDDEN_INPUT", "expected_output": "PRIVATE_HIDDEN_OUTPUT", "is_public": False},
            ],
        },
    }
    response = c["client"].post("/api/teacher/assignments", json=payload)
    assert response.status_code == 201, response.text
    aid = response.json()["data"]["assignment_id"]
    assert c["client"].post(f"/api/teacher/assignments/{aid}/publish").status_code == 200
    draft = c["client"].post("/api/teacher/assignments", json={**payload, "title": "历史草稿"})
    assert draft.status_code == 201
    own, other = c["reviewers"][0][:2]
    ids = []
    with c["engine"].begin() as db:
        outside = db.execute(text("""INSERT INTO users(student_no,name,password_hash,system_role)
            VALUES ('TEST-HISTORY-OUT','其他班学生','unused','STUDENT') RETURNING id""")).scalar_one()
        for version, status in enumerate(["CE", "WA", "AC"], 1):
            ids.append(db.execute(text("""INSERT INTO code_submissions
                (assignment_id,author_id,class_id,language,source_code,version,is_current,status,
                 executed_case_count,passed_case_count,compiler_output)
                VALUES (:a,:u,:c,'cpp17','PRIVATE_SOURCE',:v,:current,:status,2,1,:compiler)
                RETURNING id"""), {
                "a": aid, "u": own, "c": c["classes"][0], "v": version,
                "current": version == 3, "status": status,
                "compiler": "own syntax error" if status == "CE" else None,
            }).scalar_one())
        other_id = db.execute(text("""INSERT INTO code_submissions
            (assignment_id,author_id,class_id,language,source_code,version,status)
            VALUES (:a,:u,:c,'cpp17','OTHER_SOURCE',1,'RE') RETURNING id"""),
            {"a": aid, "u": other, "c": c["classes"][0]}).scalar_one()
    return {**c, "assignment": aid, "own": own, "other": other, "outside": outside,
            "draft": draft.json()["data"]["assignment_id"], "submission_ids": ids, "other_id": other_id}


def test_history_is_own_paginated_and_sanitized_after_deadline(history_course):
    c = history_course
    url = f"/api/student/assignments/{c['assignment']}/code-submissions"
    with as_student(c["own"]):
        response = c["client"].get(url, params={"page_size": 2})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert (data["total"], data["page"], data["page_size"]) == (3, 1, 2)
        assert [i["version"] for i in data["items"]] == [3, 2]
        assert [i["is_current"] for i in data["items"]] == [True, False]
        assert set(data["items"][0]) == {"id", "version", "language", "status", "submitted_at", "is_current"}
        for marker in ["PRIVATE_SOURCE", "OTHER_SOURCE", "PRIVATE_HIDDEN", "compiler_output", "author_id"]:
            assert marker not in response.text
        second = c["client"].get(url, params={"page_size": 2, "page": 2}).json()["data"]
        assert [i["version"] for i in second["items"]] == [1]
        assert c["client"].get(url, params={"page": 10}).json()["data"]["items"] == []
        detail = c["client"].get(f"/api/code-submissions/{c['submission_ids'][0]}")
        assert detail.status_code == 200 and detail.json()["data"]["compiler_output"] == "own syntax error"
        assert c["client"].get(f"/api/code-submissions/{c['other_id']}").status_code == 404
    with as_student(c["other"]):
        own_items = c["client"].get(url).json()["data"]["items"]
        assert [i["id"] for i in own_items] == [c["other_id"]]


def test_history_empty_and_invisible_assignments(history_course):
    c = history_course
    url = f"/api/student/assignments/{c['assignment']}/code-submissions"
    with as_student(c["reviewers"][1][0]):
        data = c["client"].get(url).json()["data"]
        assert data["items"] == [] and data["total"] == 0
    with as_student(c["outside"]):
        assert c["client"].get(url).status_code == 404
    with as_student(c["own"]):
        assert c["client"].get('/api/student/assignments/999999/code-submissions').status_code == 404
        # The original fixture is a final-project draft, not a visible programming task.
        assert c["client"].get(f"/api/student/assignments/{c['id']}/code-submissions").status_code == 404
        assert c["client"].get(f"/api/student/assignments/{c['draft']}/code-submissions").status_code == 404
    assert c["client"].post(f"/api/teacher/assignments/{c['id']}/publish").status_code == 200
    with as_student(c["own"]):
        assert c["client"].get(f"/api/student/assignments/{c['id']}/code-submissions").status_code == 404


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 51}])
def test_history_pagination_validation(history_course, params):
    c = history_course
    with as_student(c["own"]):
        response = c["client"].get(f"/api/student/assignments/{c['assignment']}/code-submissions", params=params)
        assert response.status_code == 422


def test_history_requires_authenticated_student(history_course):
    c = history_course
    url = f"/api/student/assignments/{c['assignment']}/code-submissions"
    assert c["client"].get(url).status_code == 403
    previous = app.dependency_overrides.pop(get_current_user)
    try:
        assert c["client"].get(url).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = previous
