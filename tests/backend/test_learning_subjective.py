"""Submission-only work, flexible class selection and learning history."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.security import CurrentUser, get_current_user
from app.main import app
from app.schemas.teacher import AssignmentCreate
from app.services.learning_analytics import summarize_learning
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError


@contextmanager
def student(user_id):
    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id, "STUDENT")
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = previous


def test_learning_empty_has_no_fabricated_values():
    data = summarize_learning([], [], [], [], [], [])
    assert data["assignments"] == data["topics"] == []
    assert data["code_attempt_count"] == 0


def test_learning_separates_history_current_and_missing():
    assignments = [
        {"id": 1, "title": "求和", "type": "PROGRAMMING", "maximum_score": 100},
        {"id": 2, "title": "微课", "type": "FINAL_PROJECT", "maximum_score": 20},
    ]
    roster = [
        {"assignment_id": aid, "student_id": user}
        for aid in (1, 2)
        for user in (1, 2, 3, 4)
    ]
    codes = [
        {
            "assignment_id": 1,
            "author_id": user,
            "status": status,
            "is_current": current,
            "time_ms": time,
            "memory_kb": 200,
        }
        for user, status, current, time in [
            (1, "WA", False, 5),
            (1, "AC", True, 10),
            (2, "WA", True, 20),
            (3, "SYSTEM_ERROR", True, None),
        ]
    ]
    works = [
        {"assignment_id": 2, "author_id": 1, "is_current": True, "final_score": 16},
        {"assignment_id": 2, "author_id": 2, "is_current": True, "final_score": None},
    ]
    tags = [
        {"assignment_id": aid, "topic_id": 9, "code": "DP", "name": "递推"}
        for aid in (1, 2)
    ]
    report = summarize_learning(assignments, roster, codes, works, tags, [])
    code, proof = report["assignments"]
    assert code["ac_rate"] == code["difficulty"] == 0.5
    assert code["judged_students"] == 2 and code["submitted_students"] == 3
    assert code["unsubmitted_students"] == 1 and code["submission_count"] == 4
    assert code["error_counts"] == {"WA": 2} and code["system_errors"] == 1
    assert code["average_time_ms"] == 11.67
    assert proof["average_score"] == 16 and proof["published_count"] == 1
    topic = report["topics"][0]
    assert topic["mastery"] == 0.6 and topic["evidence_count"] == 3
    assert topic["student_count"] == topic["assignment_count"] == 2


@pytest.mark.parametrize("kind", ["ALGORITHM_ANALYSIS", "PROOF", "OPEN_ENDED"])
def test_subjective_schema_needs_statement_but_no_scoring_fields(kind):
    base = {"title": "题目", "type": kind, "class_ids": [1],
            "submit_deadline": "2030-01-01T00:00:00Z"}
    with pytest.raises(ValidationError):
        AssignmentCreate(**base)
    item = AssignmentCreate(**base, statement="请证明结论")
    assert item.rubric_items == [] and item.review_deadline is None
    # Old clients' scoring configuration is normalized away.
    item = AssignmentCreate(**base, statement="证明", teacher_weight=.5, designated_review_weight=.5,
                            rubric_items=[{"name": "正确性", "max_score": 100, "sort_order": 1}])
    assert item.teacher_weight == Decimal(1) and item.designated_review_weight == 0
    assert item.rubric_items == []


@pytest.mark.parametrize("kind", ["ALGORITHM_ANALYSIS", "PROOF", "OPEN_ENDED"])
@pytest.mark.parametrize("class_count", [1, 3])
def test_subjective_submission_completes_without_review_or_grading(course, kind, class_count):
    c, client = course, course["client"]
    third = client.post("/api/teacher/classes", json={"name": "第三班", "course_term": "TEST"}).json()["data"]["class_id"]
    classes = [c["classes"][0]] if class_count == 1 else [*c["classes"], third]
    result = client.post("/api/teacher/assignments", json={"title": "在线练习", "type": kind,
        "class_ids": classes, "statement": "给出完整推导与边界讨论。",
        "submit_deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat()})
    assert result.status_code == 201, result.text
    aid = result.json()["data"]["assignment_id"]
    base = f"/api/teacher/assignments/{aid}"
    assert client.post(base + "/publish").status_code == 200
    detail = client.get(base).json()["data"]
    assert detail["panels"] == detail["rubric_items"] == []
    assert len(detail["classes"]) == class_count and detail["review_deadline"] is None
    author = c["reviewers"][0][0]
    answer_url = f"/api/student/assignments/{aid}/subjective-submissions"
    with student(author):
        assert client.post(answer_url, json={"content": " "}).status_code == 422
        first = client.post(answer_url, json={"content": "旧版本：通过归纳进行分析。"})
        assert first.status_code == 200, first.text
        second = client.post(answer_url, json={"content": "先证明初始条件，再验证归纳步骤。"})
        assert second.status_code == 200, second.text
        sid = second.json()["data"]["submission_id"]
        history = client.get(answer_url + "/mine", params={"page_size": 1}).json()["data"]
        assert history["total"] == 2 and history["items"][0]["version"] == 2
        problem = client.get(f"/api/student/assignments/{aid}/subjective").json()["data"]
        assert problem["can_submit"] and problem["current"]["id"] == sid
        assert client.get("/api/reviewer/eligibility").json()["data"] == {"has_tasks": False}
        assert client.get(base + "/subjective-answers").status_code == 403
    with student(c["reviewers"][0][1]):
        assert client.get(answer_url + "/mine").json()["data"]["total"] == 0
    with student(c["reviewers"][1][0]):
        listed = client.get("/api/student/assignments").json()["data"]
        assert any(item["id"] == aid for item in listed) == (class_count == 3)
    assert client.get(base + "/grading").status_code == 400
    assert client.post(base + "/initialize-review-tasks").status_code == 400
    assert client.get(base + "/review-allocation-preview").status_code == 409
    assert client.put(base + "/review-deadline", json={"review_deadline": "2030-01-01T00:00:00Z", "reason": "仅作答题不应延期评审"}).status_code == 400
    assert client.post(base + "/aggregate-reviews").status_code == 400
    assert client.post(base + "/publish-results").status_code == 400
    grade = client.post(f"/api/teacher/submissions/{sid}/grades", json={
        "rubric_scores": [{"rubric_item_id": 1, "score": 90}], "comment": "不应评分"})
    assert grade.status_code == 400
    roster = client.get(base + "/subjective-answers").json()["data"]
    assert roster["submitted"] == 1 and roster["total"] == (10 if class_count == 1 else 20)
    row = next(item for item in roster["items"] if item["student_id"] == author)
    assert row["submission_id"] == sid and [v["version"] for v in row["versions"]] == [2, 1]
    assert client.get(f"/api/teacher/submissions/{sid}/evidence").json()["data"]["answer"].startswith("先证明")
    assert client.post(base + "/finish-submissions").status_code == 200
    with student(author):
        assert client.post(answer_url, json={"content": "迟交"}).status_code == 409
        assert not client.get(f"/api/student/assignments/{aid}/subjective").json()["data"]["can_submit"]
    with c["engine"].connect() as db:
        for table in ("review_panels", "rubrics", "algorithm_runs"):
            assert db.execute(text(f"SELECT count(*) FROM {table} WHERE assignment_id=:a"), {"a": aid}).scalar_one() == 0
        for table in ("teacher_grades", "final_grades"):
            assert db.execute(text(f"SELECT count(*) FROM {table} WHERE submission_id=:s"), {"s": sid}).scalar_one() == 0
    with pytest.raises(DBAPIError), c["engine"].begin() as db:
        db.execute(text("UPDATE subjective_answers SET content='改写' WHERE submission_id=:s"), {"s": sid})


def test_learning_api_and_teacher_history(course):
    c, client = course, course["client"]
    topic = client.post(
        "/api/teacher/topics",
        json={"code": "LA", "name": "求和", "chapter": "基础", "description": "求和"},
    ).json()["data"]["topic_id"]
    response = client.post(
        "/api/teacher/assignments",
        json={
            **c["payload"],
            "type": "PROGRAMMING",
            "topic_ids": [topic],
            "programming_problem": {
                "statement": "求和",
                "input_description": "输入",
                "output_description": "输出",
                "test_cases": [
                    {"input_data": "1", "expected_output": "1", "is_public": True},
                    {"input_data": "2", "expected_output": "2", "is_public": False},
                ],
            },
        },
    )
    assert response.status_code == 201, response.text
    aid = response.json()["data"]["assignment_id"]
    assert client.post(f"/api/teacher/assignments/{aid}/publish").status_code == 200
    assert client.delete(f"/api/teacher/topics/{topic}").status_code == 409
    with c["engine"].begin() as db:
        for version, status in enumerate(["CE", "WA", "AC"], 1):
            db.execute(
                text("""INSERT INTO code_submissions(assignment_id,author_id,class_id,language,source_code,
                version,is_current,status,time_ms,memory_kb) VALUES (:a,:u,:c,'cpp17','private source',:v,:current,:status,5,128)"""),
                {
                    "a": aid,
                    "u": c["reviewers"][0][0],
                    "c": c["classes"][0],
                    "v": version,
                    "current": version == 3,
                    "status": status,
                },
            )
    report = client.get("/api/teacher/learning-analysis")
    assert report.status_code == 200, report.text
    data = report.json()["data"]
    assert data["code_attempt_count"] == 3 and data["topics"][0]["mastery"] == 1
    assert data["error_counts"] == {"CE": 1, "WA": 1}
    other = client.get(
        "/api/teacher/learning-analysis", params={"class_id": c["classes"][1]}
    ).json()["data"]
    assert other["code_attempt_count"] == 0 and other["topics"][0]["mastery"] is None
    history = client.get(
        f"/api/teacher/assignments/{aid}/programming-history", params={"page_size": 2}
    ).json()["data"]
    assert history["total"] == 3 and [row["version"] for row in history["items"]] == [
        3,
        2,
    ]
    assert history["items"][0]["source_code"] == "private source"
    with student(c["reviewers"][0][0]):
        assert client.get("/api/teacher/learning-analysis").status_code == 403
        assert (
            client.get(
                f"/api/teacher/assignments/{aid}/programming-history"
            ).status_code
            == 403
        )
    with pytest.raises(DBAPIError), c["engine"].begin() as db:
        db.execute(
            text("DELETE FROM assignment_topics WHERE assignment_id=:a"), {"a": aid}
        )


def test_new_schema_contains_content_tables(pg_engine):
    assert inspect(pg_engine).has_table("subjective_answers")


def test_draft_type_and_statement_change_atomically(course):
    c, client = course, course["client"]
    url = f"/api/teacher/assignments/{c['id']}"
    for kind, statement in [("PROOF", "请给出完整的归纳证明。"), ("FINAL_PROJECT", "")]:
        payload = {
            **c["payload"],
            "type": kind,
            "statement": statement,
            "expected_updated_at": client.get(url).json()["data"]["updated_at"],
        }
        result = client.put(url, json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["data"]["panels_reset"]
        detail = client.get(url).json()["data"]
        assert detail["type"] == kind and detail["statement"] == statement


@pytest.mark.parametrize("classes", [[], [1], [1, 1], [1, 2, 3]])
def test_final_project_still_requires_two_distinct_classes(classes):
    with pytest.raises(ValidationError):
        AssignmentCreate(title="微课", type="FINAL_PROJECT", class_ids=classes,
            submit_deadline="2030-01-01T00:00:00Z", review_deadline="2030-01-02T00:00:00Z",
            rubric_items=[{"name": "内容", "max_score": 100, "sort_order": 1}])


@pytest.mark.parametrize("class_count", [1, 3])
def test_programming_publishes_to_any_number_of_classes(course, class_count):
    c, client = course, course["client"]
    third = client.post("/api/teacher/classes", json={"name": "编程第三班", "course_term": "TEST"}).json()["data"]["class_id"]
    classes = c["classes"][:1] if class_count == 1 else [*c["classes"], third]
    result = client.post("/api/teacher/assignments", json={**c["payload"], "type": "PROGRAMMING",
        "class_ids": classes, "review_deadline": None,
        "programming_problem": {"statement": "求和", "input_description": "输入", "output_description": "输出",
          "test_cases": [{"input_data": "1", "expected_output": "1", "is_public": True},
                         {"input_data": "2", "expected_output": "2", "is_public": False}]}})
    assert result.status_code == 201, result.text
    aid = result.json()["data"]["assignment_id"]
    base = f"/api/teacher/assignments/{aid}"
    assert client.post(base + "/publish").status_code == 200
    detail = client.get(base).json()["data"]
    assert len(detail["classes"]) == class_count and detail["panels"] == []
    assert detail["programming_problem"]["statement"] == "求和"
