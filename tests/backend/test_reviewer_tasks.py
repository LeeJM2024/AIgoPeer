"""Integration contracts for the anonymous designated-reviewer surface."""

from pathlib import Path

from sqlalchemy import text


def _review_task(course, tmp_path: Path, monkeypatch):
    from app.core.config import settings

    c = course
    assert c["client"].post(f"/api/teacher/assignments/{c['id']}/publish").status_code == 200
    author = c["reviewers"][0][0]
    reviewer = c["reviewers"][1][0]
    with c["engine"].begin() as connection:
        submission_id = connection.execute(
            text("""INSERT INTO submissions(assignment_id,author_id,class_id,status,anonymous_token,submitted_at)
                VALUES (:assignment,:author,:class_id,'VALID','ANON-ONLY',now()) RETURNING id"""),
            {"assignment": c["id"], "author": author, "class_id": c["classes"][0]},
        ).scalar_one()
        connection.execute(text("INSERT INTO material_checks(submission_id,status) VALUES (:id,'VALID')"), {"id": submission_id})
    assert c["client"].post(f"/api/teacher/assignments/{c['id']}/initialize-review-tasks").status_code == 200
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    package = tmp_path / "review-materials" / "safe.zip"
    package.parent.mkdir()
    package.write_bytes(b"safe anonymous package")
    with c["engine"].begin() as connection:
        connection.execute(
            text("""INSERT INTO review_material_packages(submission_id,storage_key,status)
                VALUES (:submission,'review-materials/safe.zip','READY')"""),
            {"submission": submission_id},
        )
        task_id = connection.execute(
            text("SELECT id FROM review_tasks WHERE submission_id=:submission AND reviewer_id=:reviewer"),
            {"submission": submission_id, "reviewer": reviewer},
        ).scalar_one()
        rubric = connection.execute(text("SELECT id FROM rubric_items WHERE rubric_id=(SELECT id FROM rubrics WHERE assignment_id=:assignment)"), {"assignment": c["id"]}).scalar_one()
    return reviewer, author, task_id, rubric


def _as_student(user_id: int):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id, "STUDENT")
    return previous


def _restore_student_override(previous) -> None:
    from app.core.security import get_current_user
    from app.main import app

    if previous is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous


def test_reviewer_can_only_read_download_and_submit_own_anonymous_task(course, tmp_path, monkeypatch):
    reviewer, author, task_id, rubric = _review_task(course, tmp_path, monkeypatch)
    previous = _as_student(reviewer)
    try:
        response = course["client"].get("/api/reviewer/review-tasks/mine")
        assert response.status_code == 200
        task = response.json()["data"][0]
        assert task["task_id"] == task_id
        assert set(task).isdisjoint({"author_id", "author_name", "student_no", "aggregate_score", "teacher_score"})
        assert task["materials"] == [{"kind": "ANONYMOUS_REVIEW_PACKAGE", "download_url": f"/api/reviewer/review-tasks/{task_id}/materials/archive"}]

        download = course["client"].get(f"/api/reviewer/review-tasks/{task_id}/materials/archive")
        assert download.status_code == 200
        assert download.headers["cache-control"] == "private, no-store"
        payload = {"rubric_scores": [{"rubric_item_id": rubric, "score": 88}], "comment": "依据 Rubric 给出意见。", "started_at": "2026-01-01T00:00:00Z"}
        assert course["client"].post(f"/api/reviewer/review-tasks/{task_id}/reviews", json=payload).status_code == 200
        assert course["client"].post(f"/api/reviewer/review-tasks/{task_id}/reviews", json=payload).status_code == 409
    finally:
        _restore_student_override(previous)

    previous = _as_student(author)
    try:
        assert course["client"].get(f"/api/reviewer/review-tasks/{task_id}/materials/archive").status_code == 403
    finally:
        _restore_student_override(previous)


def test_student_without_panel_cannot_open_reviewer_surface(course):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    with course["engine"].begin() as connection:
        outsider = connection.execute(
            text("""INSERT INTO users(student_no,name,password_hash,system_role)
                VALUES ('OUTSIDER','无任务学生','unused','STUDENT') RETURNING id""")
        ).scalar_one()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(outsider, "STUDENT")
    try:
        response = course["client"].get("/api/reviewer/review-tasks/mine")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_student_grade_endpoint_only_exposes_published_final_feedback(grading_course):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    c = grading_course
    for submission_id in c["submissions"]:
        response = c["client"].post(
            f"/api/teacher/submissions/{submission_id}/grades",
            json={"rubric_scores": [{"rubric_item_id": c["rubric"], "score": 90}], "comment": "教师反馈"},
        )
        grade_id = response.json()["data"]["teacher_grade_id"]
        assert c["client"].post(f"/api/teacher/grades/{grade_id}/lock").status_code == 200
    assert c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results").status_code == 200

    author = c["reviewers"][0][0]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(author, "STUDENT")
    try:
        response = c["client"].get(f"/api/student/grades?assignment_id={c['id']}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    data = response.json()["data"]
    assert float(data["final_score"]) == 86
    assert set(data).isdisjoint({"teacher_score", "aggregate_score", "anomalies", "reviewers"})
    assert data["rubric_items"][0]["name"] == "原理"
