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
        # Never fall back to public: its alembic_version could skip test migrations
        # and then route unqualified test writes into the application tables.
        url, connect_args={"options": f"-csearch_path={schema}"}
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
            for student in range(10):
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
    return {
        "id": assignment_id,
        "classes": classes,
        "reviewers": reviewers,
        "payload": payload,
        "teacher": teacher,
        "client": client,
        "engine": pg_engine,
    }


@pytest.fixture
def grading_course(course, request):
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
    seed_review_tasks(c)
    if getattr(request, "param", None) == "pending":
        with c["engine"].connect() as conn:
            rubric = conn.execute(
                text("SELECT id FROM rubric_items ORDER BY id LIMIT 1")
            ).scalar_one()
        c.update(submissions=submissions, rubric=rubric)
        return c
    with c["engine"].begin() as conn:
        # Explicit contract fixture for member 3's persistence output, not an implementation of its algorithm.
        rubric = conn.execute(
            text("SELECT id FROM rubric_items ORDER BY id LIMIT 1")
        ).scalar_one()
        for task in conn.execute(text("SELECT id FROM review_tasks")).scalars().all():
            conn.execute(
                text(
                    "INSERT INTO review_scores(review_task_id,rubric_item_id,score) VALUES(:t,:r,80)"
                ),
                {"t": task, "r": rubric},
            )
            conn.execute(
                text(
                    "INSERT INTO review_comments(review_task_id,content,char_count) VALUES(:t,'评分记录完备，推理清晰，边界讨论完整。',60)"
                ),
                {"t": task},
            )
        conn.execute(
            text(
                "UPDATE review_tasks SET status='SUBMITTED',started_at=now()-interval '5 minutes',submitted_at=clock_timestamp()"
            )
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
                total_score,rubric_scores_json,created_at) VALUES (:s,:p,:r,80,'{}',clock_timestamp())"""),
                {"s": sid, "p": panel, "r": run},
            )
    c.update(submissions=submissions, rubric=rubric)
    return c


def seed_review_tasks(course, assignment_id=None):
    """Partial snapshots for isolated grading/API contracts, not an allocator.

    Full roster allocation and publication are exercised separately by
    test_cross_class_pipeline. These small fixtures choose non-author reviewers
    so unrelated teacher/security tests remain focused and nonreciprocal.
    """
    from app.services.random_review_service import ensure_random_panels
    from sqlalchemy import text

    aid = assignment_id or course["id"]
    with course["engine"].begin() as db:
        db.execute(
            text("UPDATE assignments SET status='REVIEWER_INITIALIZING' WHERE id=:a"),
            {"a": aid},
        )
        ensure_random_panels(db, aid)
        rows = (
            db.execute(
                text(
                    "SELECT id,author_id,class_id,anonymous_token FROM submissions WHERE assignment_id=:a AND is_current AND status='VALID' ORDER BY id"
                ),
                {"a": aid},
            )
            .mappings()
            .all()
        )
        authors = {r["author_id"] for r in rows}
        for work in rows:
            panel = (
                db.execute(
                    text(
                        "SELECT id,reviewer_class_id FROM review_panels WHERE assignment_id=:a AND target_class_id=:c"
                    ),
                    {"a": aid, "c": work["class_id"]},
                )
                .mappings()
                .one()
            )
            candidates = (
                db.execute(
                    text(
                        "SELECT user_id FROM enrollments WHERE class_id=:c ORDER BY user_id"
                    ),
                    {"c": panel["reviewer_class_id"]},
                )
                .scalars()
                .all()
            )
            selected = [u for u in candidates if u not in authors][:5]
            assert len(selected) == 5
            for reviewer in selected:
                db.execute(
                    text(
                        "INSERT INTO panel_reviewers(panel_id,reviewer_id) VALUES(:p,:u) ON CONFLICT DO NOTHING"
                    ),
                    {"p": panel["id"], "u": reviewer},
                )
                db.execute(
                    text(
                        "INSERT INTO review_tasks(panel_id,submission_id,reviewer_id,anonymous_token) VALUES(:p,:s,:u,:t) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "p": panel["id"],
                        "s": work["id"],
                        "u": reviewer,
                        "t": work["anonymous_token"],
                    },
                )
        db.execute(
            text("UPDATE review_panels SET status='ACTIVE' WHERE assignment_id=:a"),
            {"a": aid},
        )
        db.execute(
            text("UPDATE assignments SET status='REVIEWER_GRADING' WHERE id=:a"),
            {"a": aid},
        )
