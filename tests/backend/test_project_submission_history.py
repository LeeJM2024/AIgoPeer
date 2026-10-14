"""Student-only project history remains readable after the upload cutoff."""
import pytest
from app.core.security import get_current_user
from app.main import app
from sqlalchemy import text
from test_project_submission_recovery import as_student


@pytest.fixture
def project_history(course):
    c = course
    assert c["client"].post(f"/api/teacher/assignments/{c['id']}/publish").status_code == 200
    own, other = c["reviewers"][0][:2]
    ids = []
    with c["engine"].begin() as db:
        for version, check in enumerate(["INVALID", "VALID", "PENDING", "RETURNED", None, "VALID", "VALID"], 1):
            sid = db.execute(text("""INSERT INTO submissions
                (assignment_id,author_id,class_id,status,anonymous_token,version,is_current,submitted_at,manifest_json)
                VALUES (:a,:u,:c,:status,:token,:v,:current,clock_timestamp(),'{"PRIVATE_MANIFEST":"secret"}') RETURNING id"""),
                {"a": c["id"], "u": own, "c": c["classes"][0], "v": version, "current": version == 7,
                 "status": "VALID" if version == 7 else "SUPERSEDED", "token": f"history-{version}"}).scalar_one()
            ids.append(sid)
            if check:
                db.execute(text("""INSERT INTO material_checks(submission_id,status,missing_items,warnings)
                    VALUES (:s,:status,CAST(:missing AS jsonb),'[]')"""),
                    {"s": sid, "status": check, "missing": '["VIDEO"]' if check == "INVALID" else '[]'})
        other_id = db.execute(text("""INSERT INTO submissions
            (assignment_id,author_id,class_id,status,anonymous_token,version,submitted_at)
            VALUES (:a,:u,:c,'PENDING','other-token',1,clock_timestamp()) RETURNING id"""),
            {"a": c["id"], "u": other, "c": c["classes"][0]}).scalar_one()
        outside = db.execute(text("""INSERT INTO users(student_no,name,password_hash,system_role)
            VALUES ('TEST-HISTORY-PROJECT-OUT','外班学生','unused','STUDENT') RETURNING id""")).scalar_one()
    draft = c["client"].post("/api/teacher/assignments", json={**c["payload"], "title": "历史草稿"})
    assert draft.status_code == 201
    return {**c, "own": own, "other": other, "other_id": other_id, "outside": outside,
            "ids": ids, "draft": draft.json()["data"]["assignment_id"]}


def url(c):
    return f"/api/student/assignments/{c['id']}/project-submissions"


def test_history_own_paginated_sanitized_and_available_after_deadline(project_history):
    c = project_history
    with as_student(c["own"]):
        response = c["client"].get(url(c), params={"page_size": 5})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert (data["total"], data["page"], data["page_size"]) == (7, 1, 5)
        assert [i["version"] for i in data["items"]] == [7, 6, 5, 4, 3]
        assert set(data["items"][0]) == {"id", "version", "submitted_at", "is_current", "material_check_status"}
        assert data["items"][0]["is_current"] is True
        assert data["items"][2]["material_check_status"] is None
        assert data["items"][3]["material_check_status"] == "RETURNED"
        assert data["items"][4]["material_check_status"] == "PENDING"
        for value in ["PRIVATE_MANIFEST", "author_id", "anonymous_token", "storage_key", "teacher_score", "aggregate_score"]:
            assert value not in response.text
        second = c["client"].get(url(c), params={"page_size": 5, "page": 2}).json()["data"]
        assert [i["version"] for i in second["items"]] == [2, 1]
        assert [i["material_check_status"] for i in second["items"]] == ["VALID", "INVALID"]
        old = c["client"].get(f"/api/submissions/{c['ids'][0]}/material-check")
        assert old.status_code == 200 and old.json()["data"]["missing_items"] == ["VIDEO"]
        assert c["client"].get(url(c), params={"page": 50}).json()["data"]["items"] == []
        assert c["client"].get(url(c)).json()["data"]["page_size"] == 20
    with as_student(c["other"]):
        assert [i["id"] for i in c["client"].get(url(c)).json()["data"]["items"]] == [c["other_id"]]
        assert c["client"].get(f"/api/submissions/{c['ids'][0]}/material-check").status_code == 403


def test_history_empty_and_invisible_assignment(project_history):
    c = project_history
    with as_student(c["reviewers"][1][0]):
        data = c["client"].get(url(c)).json()["data"]
        assert data["items"] == [] and data["total"] == 0
    with as_student(c["outside"]):
        assert c["client"].get(url(c)).status_code == 404
    with as_student(c["own"]):
        assert c["client"].get('/api/student/assignments/999999/project-submissions').status_code == 404
        assert c["client"].get(f"/api/student/assignments/{c['draft']}/project-submissions").status_code == 404
    with c["engine"].begin() as db:
        db.execute(text("UPDATE assignments SET type='PROGRAMMING' WHERE id=:a"), {"a": c["draft"]})
        db.execute(text("UPDATE assignments SET status='PUBLISHED' WHERE id=:a"), {"a": c["draft"]})
    with as_student(c["own"]):
        assert c["client"].get(f"/api/student/assignments/{c['draft']}/project-submissions").status_code == 404


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 51}])
def test_history_pagination_bounds(project_history, params):
    c = project_history
    with as_student(c["own"]):
        assert c["client"].get(url(c), params=params).status_code == 422


def test_history_authentication_and_read_only_behavior(project_history):
    c = project_history
    assert c["client"].get(url(c)).status_code == 403
    old = app.dependency_overrides.pop(get_current_user)
    try:
        assert c["client"].get(url(c)).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = old
    with c["engine"].connect() as db:
        before = db.execute(text("SELECT id,version,is_current,status FROM submissions ORDER BY id")).all()
    with as_student(c["own"]):
        for _ in range(2):
            assert c["client"].get(url(c)).status_code == 200
            assert c["client"].get(f"/api/submissions/{c['ids'][2]}/material-check").json()["data"]["status"] == "PENDING"
    with c["engine"].connect() as db:
        assert db.execute(text("SELECT id,version,is_current,status FROM submissions ORDER BY id")).all() == before
