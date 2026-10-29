import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

import pytest
from app.core.security import CurrentUser, get_current_user
from app.main import app
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


@contextmanager
def student(user):
    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user, "STUDENT")
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = previous


def prepare_final_package(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    archive = tmp_path / "review-materials" / "course.zip"
    archive.parent.mkdir(exist_ok=True)
    with ZipFile(archive, "w") as package:
        package.writestr("README.md", "匿名课程材料")


def seed_final_work(engine, assignment_id, author, class_id):
    with engine.begin() as db:
        sid = db.execute(text("""INSERT INTO submissions(assignment_id,author_id,class_id,status,anonymous_token,submitted_at)
            VALUES (:a,:u,:c,'VALID',:token,clock_timestamp()) RETURNING id"""),
            {"a": assignment_id, "u": author, "c": class_id, "token": f"WORK-{author}"}).scalar_one()
        db.execute(text("INSERT INTO material_checks(submission_id,status) VALUES (:s,'VALID')"), {"s": sid})
        db.execute(text("""INSERT INTO review_material_packages(submission_id,storage_key,status)
            VALUES (:s,'review-materials/course.zip','READY')"""), {"s": sid})
    return sid


@pytest.fixture
def random_course(teacher_api, pg_engine, tmp_path, monkeypatch):
    prepare_final_package(tmp_path, monkeypatch)
    client, _teacher = teacher_api
    classes, people = [], []
    with pg_engine.begin() as db:
        for ci in range(2):
            cls = db.execute(
                text(
                    "INSERT INTO classes(name,course_term) VALUES(:n,'TEST') RETURNING id"
                ),
                {"n": f"随机{ci}班"},
            ).scalar_one()
            classes.append(cls)
            for j in range(12):
                user = db.execute(
                    text("""INSERT INTO users(student_no,name,password_hash,system_role)
                  VALUES(:n,:name,'unused','STUDENT') RETURNING id"""),
                    {"n": f"R-{ci}-{j}", "name": f"参与学生{ci}-{j}"},
                ).scalar_one()
                db.execute(
                    text("INSERT INTO enrollments(user_id,class_id) VALUES(:u,:c)"),
                    {"u": user, "c": cls},
                )
                people.append((user, cls))
    deadline = datetime.now(UTC) + timedelta(seconds=3)
    response = client.post(
        "/api/teacher/assignments",
        json={
            "title": "稀疏评审微课作业",
            "type": "FINAL_PROJECT",
            "statement": "请给出证明与复杂度分析。",
            "class_ids": classes,
            "submit_deadline": deadline.isoformat(),
            "review_deadline": "2030-01-01T00:00:00Z",
            "rubric_items": [{"name": "推理", "max_score": 100, "sort_order": 1}],
        },
    )
    assert response.status_code == 201, response.text
    aid = response.json()["data"]["assignment_id"]
    assert client.post(f"/api/teacher/assignments/{aid}/publish").status_code == 200
    for user, cls in people:
        seed_final_work(pg_engine, aid, user, cls)
    time.sleep(max(0, (deadline - datetime.now(UTC)).total_seconds()) + 0.02)
    return {
        "client": client,
        "engine": pg_engine,
        "id": aid,
        "people": people,
        "classes": classes,
    }


def initialize(c):
    url = f"/api/teacher/assignments/{c['id']}"
    preview = c["client"].get(url + "/review-allocation-preview")
    assert preview.status_code == 200, preview.text
    assert preview.headers["cache-control"] == "private, no-store"
    data = preview.json()["data"]
    assert data["ready"] and data["total_tasks"] == 120
    result = c["client"].post(
        url + "/initialize-review-tasks",
        json={"expected_snapshot_hash": data["snapshot_hash"]},
    )
    assert result.status_code == 200, result.text
    return result.json()["data"]


def complete_reviews(c, except_task=None):
    with c["engine"].begin() as db:
        rubric = db.execute(
            text(
                "SELECT ri.id FROM rubric_items ri JOIN rubrics r ON r.id=ri.rubric_id WHERE r.assignment_id=:a"
            ),
            {"a": c["id"]},
        ).scalar_one()
        tasks = (
            db.execute(
                text(
                    "SELECT rt.id FROM review_tasks rt JOIN review_panels p ON p.id=rt.panel_id WHERE p.assignment_id=:a AND rt.is_active ORDER BY rt.id"
                ),
                {"a": c["id"]},
            )
            .scalars()
            .all()
        )
        for task in tasks:
            if task == except_task:
                continue
            db.execute(
                text(
                    "INSERT INTO review_scores(review_task_id,rubric_item_id,score) VALUES(:t,:r,80)"
                ),
                {"t": task, "r": rubric},
            )
            db.execute(
                text(
                    "INSERT INTO review_comments(review_task_id,content,char_count) VALUES(:t,'推导清晰完整，结论与边界讨论一致。',60)"
                ),
                {"t": task},
            )
            db.execute(
                text(
                    "UPDATE review_tasks SET status='SUBMITTED',started_at=clock_timestamp()-interval '5 minutes',submitted_at=clock_timestamp() WHERE id=:t"
                ),
                {"t": task},
            )
    return rubric, tasks


def test_preview_staleness_joint_constraints_and_retry(random_course):
    c = random_course
    url = f"/api/teacher/assignments/{c['id']}"
    stale = c["client"].post(
        url + "/initialize-review-tasks", json={"expected_snapshot_hash": "0" * 64}
    )
    assert stale.status_code == 409 and "ALLOCATION_PREVIEW_STALE" in stale.text
    first = initialize(c)
    retry = c["client"].post(url + "/initialize-review-tasks").json()["data"]
    assert retry["reused"] and sum(p["task_count"] for p in retry["panels"]) == 120
    with c["engine"].connect() as db:
        rows = (
            db.execute(
                text("""SELECT rt.reviewer_id,s.author_id,s.class_id,p.reviewer_class_id
          FROM review_tasks rt JOIN submissions s ON s.id=rt.submission_id JOIN review_panels p ON p.id=rt.panel_id""")
            )
            .mappings()
            .all()
        )
        pairs = {(r["reviewer_id"], r["author_id"]) for r in rows}
        assert len(rows) == 120
        assert all((v, u) not in pairs for u, v in pairs)
        assert all(r["class_id"] != r["reviewer_class_id"] for r in rows)
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM algorithm_runs WHERE algorithm_name='cross_class_fair_random'"
                )
            ).scalar_one()
            == 1
        )
    assert first["status"] == "REVIEWER_GRADING"
    assert (
        c["client"].put(url + "/review-panels", json={"panels": []}).status_code == 404
    )


def test_replacement_revokes_old_ownership_and_preserves_five(random_course):
    c = random_course
    initialize(c)
    with c["engine"].connect() as db:
        task = (
            db.execute(text("SELECT * FROM review_tasks ORDER BY id LIMIT 1"))
            .mappings()
            .one()
        )
    with student(task["reviewer_id"]):
        assert (
            c["client"]
            .get(f"/api/reviewer/review-tasks/{task['id']}/materials/archive")
            .status_code
            == 200
        )
        assert (
            c["client"]
            .post(
                f"/api/teacher/assignments/{c['id']}/review-tasks/{task['id']}/replace",
                json={"reason": "学生请假"},
            )
            .status_code
            == 403
        )
    response = c["client"].post(
        f"/api/teacher/assignments/{c['id']}/review-tasks/{task['id']}/replace",
        json={"reason": "学生请假，安排替补"},
    )
    assert response.status_code == 200, response.text
    fresh = response.json()["data"]["new_task_id"]
    with student(task["reviewer_id"]):
        assert (
            c["client"]
            .get(f"/api/reviewer/review-tasks/{task['id']}/materials/archive")
            .status_code
            == 403
        )
    with c["engine"].connect() as db:
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM review_tasks WHERE submission_id=:s AND is_active"
                ),
                {"s": task["submission_id"]},
            ).scalar_one()
            == 5
        )
        assert (
            db.execute(
                text("SELECT is_active FROM review_tasks WHERE id=:t"),
                {"t": task["id"]},
            ).scalar_one()
            is False
        )
        assert (
            db.execute(
                text(
                    "SELECT new_task_id FROM review_task_replacements WHERE old_task_id=:t"
                ),
                {"t": task["id"]},
            ).scalar_one()
            == fresh
        )
    complete_reviews(c)
    rejected = c["client"].post(
        f"/api/teacher/assignments/{c['id']}/review-tasks/{fresh}/replace",
        json={"reason": "不得替换已评分任务"},
    )
    assert rejected.status_code == 409


def test_missing_review_cannot_aggregate_or_publish(random_course):
    c = random_course
    initialize(c)
    with c["engine"].connect() as db:
        missing = db.execute(text("SELECT min(id) FROM review_tasks")).scalar_one()
    complete_reviews(c, missing)
    result = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert result.status_code == 200
    assert "INSUFFICIENT_REVIEWS" in result.text
    publish = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert publish.status_code == 424


def test_precheck_failure_is_audited_without_partial_tasks(random_course):
    c = random_course
    with c["engine"].begin() as db:
        db.execute(
            text(
                "UPDATE material_checks SET status='PENDING' WHERE submission_id=(SELECT min(id) FROM submissions)"
            )
        )
    url = f"/api/teacher/assignments/{c['id']}"
    preview = c["client"].get(url + "/review-allocation-preview").json()["data"]
    assert not preview["ready"] and "MATERIAL_CHECKS_PENDING" in preview["blockers"]
    response = c["client"].post(
        url + "/initialize-review-tasks",
        json={"expected_snapshot_hash": preview["snapshot_hash"]},
    )
    assert response.status_code == 424 and "MATERIAL_CHECKS_PENDING" in response.text
    with c["engine"].begin() as db:
        failed = (
            db.execute(
                text(
                    "SELECT status,parameters_json FROM algorithm_runs WHERE algorithm_name='cross_class_fair_random'"
                )
            )
            .mappings()
            .one()
        )
        assert failed["status"] == "FAILED"
        assert failed["parameters_json"]["failure_reason"] == "MATERIAL_CHECKS_PENDING"
        assert db.execute(text("SELECT count(*) FROM review_tasks")).scalar_one() == 0
        db.execute(text("UPDATE material_checks SET status='VALID'"))
    assert initialize(c)["status"] == "REVIEWER_GRADING"


def test_solver_failure_is_audited_and_retryable(random_course, monkeypatch):
    from app.services import random_review_service as service

    from algorithm.algorithms.allocation import AllocationError

    c = random_course
    original = service.allocate_reviews

    def fail(*args, **kwargs):
        raise AllocationError("ALLOCATION_SOLVER_LIMIT", {"solver_status": 1})

    monkeypatch.setattr(service, "allocate_reviews", fail)
    response = c["client"].post(
        f"/api/teacher/assignments/{c['id']}/initialize-review-tasks"
    )
    assert response.status_code == 409 and "ALLOCATION_SOLVER_LIMIT" in response.text
    with c["engine"].connect() as db:
        assert db.execute(text("SELECT count(*) FROM review_tasks")).scalar_one() == 0
        assert (
            db.execute(text("SELECT count(*) FROM panel_reviewers")).scalar_one() == 0
        )
        run = (
            db.execute(text("SELECT status,parameters_json FROM algorithm_runs"))
            .mappings()
            .one()
        )
        assert run["status"] == "FAILED"
        assert run["parameters_json"]["diagnostics"] == {"solver_status": 1}
    monkeypatch.setattr(service, "allocate_reviews", original)
    initialize(c)


def test_database_rejects_reciprocity_and_unaudited_replacement(random_course):
    c = random_course
    initialize(c)
    with c["engine"].connect() as db:
        task = (
            db.execute(
                text(
                    "SELECT rt.*,s.author_id FROM review_tasks rt JOIN submissions s ON s.id=rt.submission_id ORDER BY rt.id LIMIT 1"
                )
            )
            .mappings()
            .one()
        )
        reverse_work = (
            db.execute(
                text(
                    "SELECT s.id,s.anonymous_token,p.id AS panel_id FROM submissions s JOIN review_panels p ON p.assignment_id=s.assignment_id AND p.target_class_id=s.class_id WHERE s.author_id=:u"
                ),
                {"u": task["reviewer_id"]},
            )
            .mappings()
            .one()
        )
        replaced = db.execute(
            text("SELECT min(id) FROM review_tasks WHERE submission_id=:s"),
            {"s": reverse_work["id"]},
        ).scalar_one()
    with pytest.raises(DBAPIError), c["engine"].begin() as db:
        db.execute(
            text("UPDATE review_tasks SET is_active=false WHERE id=:t"), {"t": replaced}
        )
        db.execute(
            text(
                "INSERT INTO review_tasks(panel_id,submission_id,reviewer_id,anonymous_token) VALUES(:p,:s,:u,:token)"
            ),
            {
                "p": reverse_work["panel_id"],
                "s": reverse_work["id"],
                "u": task["author_id"],
                "token": reverse_work["anonymous_token"],
            },
        )
    # A legal new edge without the required append-only replacement row still
    # fails at transaction commit. API replacement supplies that row atomically.
    from app.services.random_review_service import replace_pending_task
    from app.services.teacher_workflow import lock_assignment
    from sqlalchemy.orm import Session

    with pytest.raises(DBAPIError), Session(c["engine"]) as db:
        assignment = lock_assignment(db, c["id"])
        with c["engine"].connect() as read:
            teacher = read.execute(
                text("SELECT id FROM users WHERE system_role='TEACHER'")
            ).scalar_one()
        replace_pending_task(db, assignment, task["id"], teacher, "测试替补审计")
        db.execute(
            text(
                "ALTER TABLE review_task_replacements DISABLE TRIGGER trg_replacement_record"
            )
        )
        db.execute(text("DELETE FROM review_task_replacements"))
        db.execute(
            text(
                "ALTER TABLE review_task_replacements ENABLE TRIGGER trg_replacement_record"
            )
        )
        db.commit()


def test_sparse_aggregation_profiles_history_and_publication(random_course):
    c = random_course
    initialize(c)
    rubric, tasks = complete_reviews(c)
    url = f"/api/teacher/assignments/{c['id']}"
    result = c["client"].post(url + "/aggregate-reviews")
    assert result.status_code == 200, result.text
    assert all(p["status"] == "COMPLETED" for p in result.json()["data"]["panels"]), (
        result.text
    )
    with c["engine"].connect() as db:
        assert db.execute(
            text("SELECT count(*) FROM review_relationship_observations")
        ).scalar_one() == len(tasks)
        profiles = (
            db.execute(text("SELECT bias_json FROM reviewer_profiles")).scalars().all()
        )
        assert len(profiles) == 24 and all(
            p["learned"] and p["completed_works"] == 5 for p in profiles
        )
        ids = (
            db.execute(
                text("SELECT id FROM submissions WHERE assignment_id=:a ORDER BY id"),
                {"a": c["id"]},
            )
            .scalars()
            .all()
        )
    assert all(
        p["reused"]
        for p in c["client"].post(url + "/aggregate-reviews").json()["data"]["panels"]
    )
    for sid in ids:
        saved = c["client"].post(
            f"/api/teacher/submissions/{sid}/grades",
            json={"rubric_scores": [{"rubric_item_id": rubric, "score": 90}]},
        )
        assert saved.status_code == 201, saved.text
        assert (
            c["client"]
            .post(
                f"/api/teacher/grades/{saved.json()['data']['teacher_grade_id']}/lock"
            )
            .status_code
            == 200
        )
    assert c["client"].get(url + "/publication-readiness").json()["data"]["ready"]
    published = c["client"].post(url + "/publish-results")
    assert published.status_code == 200, published.text
    with pytest.raises(DBAPIError), c["engine"].begin() as db:
        db.execute(text("DELETE FROM review_tasks WHERE id=:t"), {"t": tasks[0]})
    with pytest.raises(DBAPIError), c["engine"].begin() as db:
        db.execute(
            text("UPDATE review_scores SET score=20 WHERE review_task_id=:t"),
            {"t": tasks[0]},
        )


def test_history_uses_only_latest_successful_direction_runs(random_course):
    from app.services.relationship_service import relationship_history
    from sqlalchemy.orm import Session

    c = random_course
    initialize(c)
    complete_reviews(c)
    url = f"/api/teacher/assignments/{c['id']}/aggregate-reviews"
    first = c["client"].post(url)
    assert all(p["status"] == "COMPLETED" for p in first.json()["data"]["panels"])
    with c["engine"].begin() as db:
        db.execute(
            text(
                "UPDATE algorithm_runs SET version='previous-test' WHERE algorithm_name='panel_bayesian_robust'"
            )
        )
    second = c["client"].post(url)
    assert all(
        p["status"] == "COMPLETED" and not p.get("reused")
        for p in second.json()["data"]["panels"]
    )
    with c["engine"].begin() as db:
        teacher = db.execute(
            text("SELECT id FROM users WHERE system_role='TEACHER'")
        ).scalar_one()
        # A later assignment can read the earlier scores, but each task occurs
        # once even though both directions have been aggregated twice.
        later = db.execute(
            text(
                "INSERT INTO assignments(title,type,status,created_by,created_at) VALUES('下一轮','FINAL_PROJECT','DRAFT',:u,clock_timestamp()+interval '1 second') RETURNING id"
            ),
            {"u": teacher},
        ).scalar_one()
        for cls in c["classes"]:
            db.execute(
                text(
                    "INSERT INTO assignment_classes(assignment_id,class_id) VALUES(:a,:c)"
                ),
                {"a": later, "c": cls},
            )
        assert (
            db.execute(
                text("SELECT count(*) FROM review_relationship_observations")
            ).scalar_one()
            == 240
        )
    with Session(c["engine"]) as db:
        history = relationship_history(db, later)
        assert len(history) == len({o.task_id for o in history}) == 120
        latest = {p["algorithm_run_id"] for p in second.json()["data"]["panels"]}
        assert {o.algorithm_run_id for o in history} == latest
        assert relationship_history(db, c["id"]) == []
