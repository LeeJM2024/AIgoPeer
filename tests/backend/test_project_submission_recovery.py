"""Real persistence coverage for upload cutoff and current project recovery."""
import json
import shutil
import time
from contextlib import contextmanager
from datetime import timedelta

import pytest
from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.main import app
from app.services.student import material_check_service, review_anonymization_service
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from test_review_workflow_e2e import _manifest, _project_archive


@contextmanager
def as_student(user):
    old = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user, "STUDENT")
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = old


@pytest.fixture
def project_course(course, monkeypatch, tmp_path, request):
    c = course
    with c["engine"].begin() as db:
        deadline = db.execute(text("SELECT clock_timestamp()")).scalar_one() + timedelta(seconds=getattr(request, "param", 86400))
        db.execute(text("UPDATE assignments SET submit_deadline=:deadline WHERE id=:a"), {"a": c["id"], "deadline": deadline})
    assert c["client"].post(f"/api/teacher/assignments/{c['id']}/publish").status_code == 200
    topic = c["client"].post("/api/teacher/topics", json={
        "code": "89", "chapter": "TEST", "name": "上传恢复", "description": "合成测试",
    })
    assert topic.status_code == 201
    own = c["reviewers"][0][0]
    with as_student(own):
        assert c["client"].post(f"/api/assignments/{c['id']}/topic-claim", json={"topic_id": topic.json()["data"]["topic_id"]}).status_code == 200
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(material_check_service, "SessionLocal", sessionmaker(bind=c["engine"]))
    monkeypatch.setattr(review_anonymization_service, "_safe_video_file", shutil.copyfile)
    return {**c, "own": own, "storage": tmp_path, "deadline": deadline}


def upload(c):
    return c["client"].post(f"/api/assignments/{c['id']}/project-submissions",
        data={"manifest": json.dumps(_manifest())},
        files={"zip_file": ("TEST-0-0_虚构学生_89.zip", _project_archive(), "application/zip")})


def view(c):
    return c["client"].get(f"/api/student/assignments/{c['id']}/project-submission")


def seconds_until_deadline(c):
    # Windows and the Docker VM can have different clocks. The API uses PostgreSQL time.
    with c["engine"].connect() as db:
        return max(0, float(db.execute(text("SELECT EXTRACT(EPOCH FROM (:deadline - clock_timestamp()))"),
                                      {"deadline": c["deadline"]}).scalar_one()))


def test_current_project_is_own_safe_and_restorable_after_reupload(project_course):
    c = project_course
    with as_student(c["own"]):
        empty = view(c).json()["data"]
        assert empty["submission"] is None and empty["can_submit"] is True
        first = upload(c)
        assert first.status_code == 200, first.text
        second = upload(c)
        assert second.status_code == 200, second.text
        current = view(c).json()["data"]
        assert set(current) == {"assignment_id", "title", "status", "submit_deadline", "can_submit", "submission"}
        assert set(current["submission"]) == {"id", "version", "status", "submitted_at"}
        assert current["submission"]["id"] == second.json()["data"]["submission_id"]
        assert current["submission"]["version"] == 2
        assert current["submission"]["status"] == "VALID"
        sid = current["submission"]["id"]
        assert c["client"].get(f"/api/submissions/{sid}/material-check").json()["data"]["status"] == "VALID"
    with as_student(c["reviewers"][0][1]):
        assert view(c).json()["data"]["submission"] is None
        assert c["client"].get(f"/api/submissions/{sid}/material-check").status_code == 403
    with c["engine"].connect() as db:
        rows = db.execute(text("SELECT version,is_current,status FROM submissions ORDER BY version")).all()
        assert rows == [(1, False, "SUPERSEDED"), (2, True, "VALID")]


@pytest.mark.parametrize("closed_by", ["deadline", "teacher_finished"])
@pytest.mark.parametrize("project_course", [4], indirect=True)
def test_closed_project_is_readable_but_upload_rejected(project_course, closed_by):
    c = project_course
    with as_student(c["own"]):
        accepted = upload(c)
        assert accepted.status_code == 200
        sid = accepted.json()["data"]["submission_id"]
    if closed_by == "deadline":
        time.sleep(seconds_until_deadline(c) + .1)
    else:
        assert c["client"].post(f"/api/teacher/assignments/{c['id']}/finish-submissions").status_code == 200
    with as_student(c["own"]):
        current = view(c).json()["data"]
        assert current["can_submit"] is False and current["submission"]["id"] == sid
        assert c["client"].get(f"/api/submissions/{sid}/material-check").status_code == 200
        rejected = upload(c)
        assert rejected.status_code == 400 and rejected.json()["detail"] == "INVALID_STATE"
    assert len(list((c["storage"] / "project-submissions").glob("*.zip"))) == 1


def test_unassigned_project_can_be_updated_during_review(project_course):
    c = project_course
    with c["engine"].begin() as db:
        db.execute(text("UPDATE assignments SET status='REVIEWER_GRADING' WHERE id=:a"), {"a": c["id"]})
    with as_student(c["own"]):
        assert view(c).json()["data"]["can_submit"]
        assert upload(c).status_code == 200
        assert upload(c).status_code == 200
        assert view(c).json()["data"]["submission"]["version"] == 2


def test_assigned_project_version_is_locked_during_parallel_intake(project_course):
    from conftest import seed_review_tasks
    c = project_course
    with as_student(c["own"]):
        first = upload(c)
        assert first.status_code == 200
    seed_review_tasks(c)
    with as_student(c["own"]):
        assert not view(c).json()["data"]["can_submit"]
        response = upload(c)
        assert response.status_code == 409 and response.json()["code"] == "SUBMISSION_ALREADY_ASSIGNED"
        assert view(c).json()["data"]["submission"]["id"] == first.json()["data"]["submission_id"]


@pytest.mark.parametrize("project_course", [4], indirect=True)
def test_cutoff_after_file_received_rolls_back_and_cleans_new_archive(project_course, monkeypatch):
    import asyncio

    from app.api.routes.student import project_submissions as route
    c = project_course
    with as_student(c["own"]):
        first = upload(c)
        assert first.status_code == 200
        sid = first.json()["data"]["submission_id"]
    real_store = route.store_archive

    async def expire_after_receiving(**kwargs):
        result = await real_store(**kwargs)
        await asyncio.sleep(seconds_until_deadline(c) + .1)
        return result

    monkeypatch.setattr(route, "store_archive", expire_after_receiving)
    with as_student(c["own"]):
        rejected = upload(c)
        assert rejected.status_code == 400 and rejected.json()["detail"] == "INVALID_STATE"
        assert view(c).json()["data"]["submission"]["id"] == sid
    with c["engine"].connect() as db:
        assert db.execute(text("SELECT id,version,is_current,status FROM submissions")).all() == [(sid, 1, True, "VALID")]
        assert db.execute(text("SELECT count(*) FROM material_checks")).scalar_one() == 1
        assert db.execute(text("SELECT count(*) FROM submission_files WHERE file_kind='ZIP'")).scalar_one() == 1
    assert len(list((c["storage"] / "project-submissions").glob("*.zip"))) == 1


def test_current_project_permissions_and_type(project_course):
    c = project_course
    assert view(c).status_code == 403
    with c["engine"].begin() as db:
        outsider = db.execute(text("INSERT INTO users(student_no,name,password_hash,system_role) VALUES ('TEST-PROJECT-OUT','外班','unused','STUDENT') RETURNING id")).scalar_one()
    with as_student(outsider):
        assert view(c).status_code == 404
        assert upload(c).status_code == 404
    with as_student(c["own"]):
        assert c["client"].get('/api/student/assignments/999999/project-submission').status_code == 404
    old = app.dependency_overrides.pop(get_current_user)
    try:
        assert view(c).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = old
    for type_, status_ in [("FINAL_PROJECT", "DRAFT"), ("PROGRAMMING", "PUBLISHED")]:
        with c["engine"].begin() as db:
            db.execute(text("UPDATE assignments SET type=:t,status=:s WHERE id=:a"), {"t": type_, "s": status_, "a": c["id"]})
        with as_student(c["own"]):
            assert view(c).status_code == 404
