"""PostgreSQL tests use a new private schema; existing application data is never touched."""

import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))


@pytest.fixture
def pg_engine():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to run isolated PostgreSQL integration tests"
        )
    admin = create_engine(url)
    schema = "teacher_test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema},public"}
    )
    try:
        config = Config()
        config.set_main_option("script_location", str(ROOT / "backend/alembic"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture
def teacher_api(pg_engine):
    from app.core.security import CurrentUser, get_current_user
    from app.db.session import get_db
    from app.main import app
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    with pg_engine.begin() as c:
        teacher = c.execute(
            text("""INSERT INTO users(student_no,name,password_hash,system_role)
            VALUES ('TEST-TEACHER','测试教师','unused','TEACHER') RETURNING id""")
        ).scalar_one()

    def session():
        with Session(pg_engine) as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(teacher, "TEACHER")
    with TestClient(app) as client:
        yield client, teacher
    app.dependency_overrides.clear()


@pytest.fixture
def course(teacher_api, pg_engine):
    from sqlalchemy import text

    client, teacher = teacher_api
    classes, reviewers = [], []
    for number in range(2):
        result = client.post(
            "/api/teacher/classes",
            json={"name": f"测试{number}班", "course_term": "TEST"},
        )
        assert result.status_code == 201, result.text
        class_id = result.json()["data"]["class_id"]
        classes.append(class_id)
        with pg_engine.begin() as c:
            users = []
            for student in range(5):
                user = c.execute(
                    text("""INSERT INTO users(student_no,name,password_hash,system_role)
                    VALUES (:n,'虚构学生','unused','STUDENT') RETURNING id"""),
                    {"n": f"TEST-{number}-{student}"},
                ).scalar_one()
                c.execute(
                    text("INSERT INTO enrollments(user_id,class_id) VALUES (:u,:c)"),
                    {"u": user, "c": class_id},
                )
                users.append(user)
            reviewers.append(users)
    payload = {
        "title": "集成测试作业",
        "type": "FINAL_PROJECT",
        "class_ids": classes,
        "submit_deadline": "2020-01-01T00:00:00Z",
        "review_deadline": "2030-01-01T00:00:00Z",
        "teacher_weight": 0.6,
        "designated_review_weight": 0.4,
        "rubric_items": [{"name": "原理", "max_score": 100, "sort_order": 1}],
    }
    result = client.post("/api/teacher/assignments", json=payload)
    assert result.status_code == 201, result.text
    assignment_id = result.json()["data"]["assignment_id"]
    panels = [
        {
            "target_class_id": classes[i],
            "reviewer_class_id": classes[1 - i],
            "reviewer_ids": reviewers[1 - i],
        }
        for i in range(2)
    ]
    result = client.put(
        f"/api/teacher/assignments/{assignment_id}/review-panels",
        json={"panels": panels},
    )
    assert result.status_code == 200, result.text
    return {
        "id": assignment_id,
        "classes": classes,
        "reviewers": reviewers,
        "payload": payload,
        "panels": panels,
        "teacher": teacher,
        "client": client,
        "engine": pg_engine,
    }


@pytest.fixture
def grading_course(course):
    from sqlalchemy import text

    c = course
    client = c["client"]
    response = client.post(f"/api/teacher/assignments/{c['id']}/publish")
    assert response.status_code == 200, response.text
    submissions = []
    with c["engine"].begin() as conn:
        for i in range(2):
            sid = conn.execute(
                text("""
                INSERT INTO submissions(assignment_id,author_id,class_id,status,anonymous_token,submitted_at)
                VALUES (:a,:u,:c,'VALID',:token,now()) RETURNING id
            """),
                {
                    "a": c["id"],
                    "u": c["reviewers"][i][0],
                    "c": c["classes"][i],
                    "token": f"TEST-{i}",
                },
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO material_checks(submission_id,status) VALUES (:s,'VALID')"
                ),
                {"s": sid},
            )
            submissions.append(sid)
    response = client.post(
        f"/api/teacher/assignments/{c['id']}/initialize-review-tasks"
    )
    assert response.status_code == 200, response.text
    with c["engine"].begin() as conn:
        # Explicit contract fixture for member 3's persistence output, not an implementation of its algorithm.
        conn.execute(
            text("UPDATE review_tasks SET status='SUBMITTED',submitted_at=now()")
        )
        conn.execute(
            text("UPDATE assignments SET status='TEACHER_GRADING' WHERE id=:id"),
            {"id": c["id"]},
        )
        rubric = conn.execute(
            text("SELECT id FROM rubric_items ORDER BY id LIMIT 1")
        ).scalar_one()
        for sid in submissions:
            panel = conn.execute(
                text(
                    "SELECT panel_id FROM review_tasks WHERE submission_id=:s LIMIT 1"
                ),
                {"s": sid},
            ).scalar_one()
            run = conn.execute(
                text("""INSERT INTO algorithm_runs(assignment_id,panel_id,algorithm_name,
                version,input_hash,status) VALUES (:a,:p,'contract_fixture','test','test','COMPLETED') RETURNING id"""),
                {"a": c["id"], "p": panel},
            ).scalar_one()
            conn.execute(
                text("""INSERT INTO designated_review_aggregates(submission_id,panel_id,algorithm_run_id,
                total_score,rubric_scores_json) VALUES (:s,:p,:r,80,'{}')"""),
                {"s": sid, "p": panel, "r": run},
            )
    c.update(submissions=submissions, rubric=rubric)
    return c
