"""Teacher policy regression on the integrated student review workflow."""

from pathlib import Path

import pytest
from app.core.security import CurrentUser, get_current_user
from app.main import app
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_reviewer_tasks import _review_task
from test_teacher_delivery import reviewed_course
from test_teacher_integration import save_and_lock


def as_user(c, user, role="STUDENT"):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user, role)
    return c["client"]


def test_fixed_weights_rejected_at_api_and_database(course):
    c = course
    response = c["client"].post(
        "/api/teacher/assignments",
        json={**c["payload"], "teacher_weight": 0.7, "designated_review_weight": 0.3},
    )
    assert response.status_code == 422
    detail = c["client"].get(f"/api/teacher/assignments/{c['id']}").json()["data"]
    response = c["client"].put(
        f"/api/teacher/assignments/{c['id']}",
        json={
            **c["payload"],
            "expected_updated_at": detail["updated_at"],
            "teacher_weight": 1,
            "designated_review_weight": 0,
        },
    )
    assert response.status_code == 422
    with pytest.raises(DBAPIError), c["engine"].begin() as conn:
        conn.execute(
            text(
                "UPDATE assignments SET teacher_weight=.7,designated_review_weight=.3 WHERE id=:id"
            ),
            {"id": c["id"]},
        )


def test_reviewer_requires_real_tasks_and_cross_class_current_membership(
    course, tmp_path, monkeypatch
):
    c = course
    # Panel membership without any assigned task must not grant entry.
    client = as_user(c, c["reviewers"][0][0])
    assert client.get("/api/reviewer/eligibility").json()["data"] == {
        "has_tasks": False
    }
    assert client.get("/api/reviewer/review-tasks/mine").status_code == 403
    as_user(c, c["teacher"], "TEACHER")
    reviewer, _author, task, rubric = _review_task(c, tmp_path, monkeypatch)
    client = as_user(c, reviewer)
    assert client.get("/api/reviewer/eligibility").json()["data"] == {"has_tasks": True}
    assert (
        client.get("/api/reviewer/review-tasks/mine").headers["cache-control"]
        == "private, no-store"
    )
    url = f"/api/reviewer/review-tasks/{task}/materials/archive"
    assert client.get(url).status_code == 200
    with c["engine"].begin() as conn:
        conn.execute(
            text("INSERT INTO enrollments(user_id,class_id) VALUES (:u,:c)"),
            {"u": reviewer, "c": c["classes"][0]},
        )
    assert client.get("/api/reviewer/eligibility").json()["data"] == {
        "has_tasks": False
    }
    assert client.get(url).status_code == 403
    assert (
        client.post(
            f"/api/reviewer/review-tasks/{task}/reviews",
            json={
                "rubric_scores": [{"rubric_item_id": rubric, "score": 80}],
                "comment": "越权尝试",
            },
        ).status_code
        == 403
    )


def test_reviewer_download_failure_does_not_start_and_submit_is_atomic(
    course, tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    c = course
    reviewer, author, task, rubric = _review_task(c, tmp_path, monkeypatch)
    client = as_user(c, reviewer)
    url = f"/api/reviewer/review-tasks/{task}"
    path = tmp_path / "review-materials/safe.zip"
    contents = path.read_bytes()
    path.unlink()
    assert client.get(url + "/materials/archive").status_code == 424
    with c["engine"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT started_at FROM review_tasks WHERE id=:id"), {"id": task}
            ).scalar_one()
            is None
        )
    path.write_bytes(contents)
    assert client.get(url + "/materials/archive").status_code == 200
    payload = {
        "rubric_scores": [{"rubric_item_id": rubric, "score": 80}],
        "comment": "核对材料后的真实评语",
        "started_at": "2000-01-01T00:00:00Z",
    }
    assert (
        client.post(
            url + "/reviews", json={**payload, "reviewer_id": author}
        ).status_code
        == 422
    )
    with c["engine"].begin() as conn:
        conn.execute(
            text("""CREATE FUNCTION fail_review_comment() RETURNS trigger AS $$
          BEGIN RAISE EXCEPTION 'simulated comment write failure'; END; $$ LANGUAGE plpgsql;
          CREATE TRIGGER test_fail_comment BEFORE INSERT ON review_comments FOR EACH ROW EXECUTE FUNCTION fail_review_comment();""")
        )
    with pytest.raises(DBAPIError):
        client.post(url + "/reviews", json=payload)
    with c["engine"].begin() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM review_scores")).scalar_one() == 0
        )
        assert (
            conn.execute(
                text("SELECT status FROM review_tasks WHERE id=:id"), {"id": task}
            ).scalar_one()
            == "IN_PROGRESS"
        )
        conn.execute(text("DROP TRIGGER test_fail_comment ON review_comments"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(url + "/reviews", json=payload).status_code,
                range(2),
            )
        )
    assert sorted(results) == [200, 409]
    with c["engine"].connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM review_scores")).scalar_one() == 1
        )
        assert (
            conn.execute(
                text("SELECT started_at FROM review_tasks WHERE id=:id"), {"id": task}
            )
            .scalar_one()
            .year
            > 2000
        )


def test_historical_submission_does_not_grant_review_access(
    course, tmp_path, monkeypatch
):
    c = course
    reviewer, _, task, _ = _review_task(c, tmp_path, monkeypatch)
    client = as_user(c, reviewer)
    with c["engine"].begin() as conn:
        conn.execute(
            text("UPDATE submissions SET is_current=false,status='SUPERSEDED'")
        )
    assert client.get("/api/reviewer/eligibility").json()["data"] == {
        "has_tasks": False
    }
    assert (
        client.get(f"/api/reviewer/review-tasks/{task}/materials/archive").status_code
        == 403
    )


def test_low_and_medium_require_explicit_resolution(grading_course):
    c = grading_course
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    with c["engine"].begin() as conn:
        run = conn.execute(
            text("SELECT id FROM algorithm_runs ORDER BY id LIMIT 1")
        ).scalar_one()
        for risk in ["LOW", "MEDIUM"]:
            conn.execute(
                text(
                    "INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json) VALUES (:s,:r,:risk,10,'{}')"
                ),
                {"s": c["submissions"][0], "r": run, "risk": risk},
            )
    url = f"/api/teacher/assignments/{c['id']}/publish-results"
    assert c["client"].post(url).status_code == 424
    anomalies = (
        c["client"].get(f"/api/teacher/assignments/{c['id']}/anomalies").json()["data"]
    )
    for item in anomalies:
        assert (
            c["client"]
            .post(
                f"/api/teacher/anomalies/{item['id']}/resolve",
                json={
                    "status": "CONFIRMED"
                    if item["risk_level"] == "LOW"
                    else "DISMISSED",
                    "note": "已核查原始材料与评分依据",
                },
            )
            .status_code
            == 200
        )
    assert c["client"].post(url).status_code == 200
    with c["engine"].connect() as conn:
        assert all(
            float(v) == 86
            for v in conn.execute(
                text("SELECT final_score FROM final_grades")
            ).scalars()
        )


def test_final_review_requires_locked_initial_grade_and_same_teacher(course):
    c = reviewed_course(course, high=True)
    assert (
        c["client"]
        .post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
        .status_code
        == 200
    )
    sid = c["submissions"][0]
    url = f"/api/teacher/submissions/{sid}/final-review"
    payload = {"final_score": 87, "reason": "核对全部证据后的复核结论"}
    assert (
        c["client"].post(url, json=payload).json()["code"] == "INITIAL_GRADE_REQUIRED"
    )
    grade = (
        c["client"]
        .post(
            f"/api/teacher/submissions/{sid}/grades",
            json={"rubric_scores": [{"rubric_item_id": c["rubric"], "score": 80}]},
        )
        .json()["data"]["teacher_grade_id"]
    )
    assert (
        c["client"].post(url, json=payload).json()["code"] == "LATEST_GRADE_NOT_LOCKED"
    )
    assert c["client"].post(f"/api/teacher/grades/{grade}/lock").status_code == 200
    with c["engine"].begin() as conn:
        other = conn.execute(
            text(
                "INSERT INTO users(student_no,name,password_hash,system_role) VALUES ('SECOND','另一个教师','unused','TEACHER') RETURNING id"
            )
        ).scalar_one()
        run = conn.execute(
            text(
                "SELECT algorithm_run_id FROM anomaly_records WHERE submission_id=:s AND risk_level='HIGH' LIMIT 1"
            ),
            {"s": sid},
        ).scalar_one()
    assert as_user(c, other, "TEACHER").post(url, json=payload).status_code == 403
    with pytest.raises(DBAPIError), c["engine"].begin() as conn:
        conn.execute(
            text(
                "INSERT INTO teacher_final_reviews(submission_id,algorithm_run_id,final_score,reason,entered_by) VALUES (:s,:r,87,'跨教师尝试',:u)"
            ),
            {"s": sid, "r": run, "u": other},
        )
    assert (
        as_user(c, c["teacher"], "TEACHER").post(url, json=payload).status_code == 201
    )


def test_policy_upgrade_preserves_published_history_and_audits_unfinished(course):
    from alembic import command
    from alembic.config import Config

    c = course
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "backend/alembic")
    )
    with c["engine"].begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, "20261010_0007")
        conn.execute(
            text(
                "UPDATE assignments SET teacher_weight=.7,designated_review_weight=.3 WHERE id=:a"
            ),
            {"a": c["id"]},
        )
        historical = conn.execute(
            text(
                "INSERT INTO assignments(title,type,status,teacher_weight,designated_review_weight,created_by) VALUES ('已发布历史','FINAL_PROJECT','PUBLISHED_RESULT',.8,.2,:u) RETURNING id"
            ),
            {"u": c["teacher"]},
        ).scalar_one()
        command.upgrade(config, "head")
        assert (
            float(
                conn.execute(
                    text("SELECT teacher_weight FROM assignments WHERE id=:a"),
                    {"a": c["id"]},
                ).scalar_one()
            )
            == 0.6
        )
        assert (
            float(
                conn.execute(
                    text("SELECT teacher_weight FROM assignments WHERE id=:a"),
                    {"a": historical},
                ).scalar_one()
            )
            == 0.8
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE action='MIGRATE_FIXED_REVIEW_POLICY'"
                )
            ).scalar_one()
            == 1
        )


def test_real_low_evidence_persists_and_old_runs_backfill_without_duplicates(course):
    c = reviewed_course(course)
    with c["engine"].begin() as conn:
        for class_index in range(2):
            panel = c["panel_ids"][class_index]
            for number in (1, 2):
                sid = conn.execute(
                    text("""INSERT INTO submissions(assignment_id,author_id,class_id,status,anonymous_token)
                    VALUES (:a,:u,:c,'VALID',:token) RETURNING id"""),
                    {
                        "a": c["id"],
                        "u": c["reviewers"][class_index][number],
                        "c": c["classes"][class_index],
                        "token": f"MORE-{class_index}-{number}",
                    },
                ).scalar_one()
                conn.execute(
                    text(
                        "INSERT INTO material_checks(submission_id,status) VALUES (:s,'VALID')"
                    ),
                    {"s": sid},
                )
                for reviewer in c["reviewers"][1 - class_index]:
                    task = conn.execute(
                        text("""INSERT INTO review_tasks(panel_id,submission_id,reviewer_id,anonymous_token,status,started_at,submitted_at)
                        VALUES (:p,:s,:r,:token,'SUBMITTED',now()-interval '5 minutes',now()) RETURNING id"""),
                        {
                            "p": panel,
                            "s": sid,
                            "r": reviewer,
                            "token": f"MORE-{class_index}-{number}",
                        },
                    ).scalar_one()
                    conn.execute(
                        text(
                            "INSERT INTO review_scores(review_task_id,rubric_item_id,score) VALUES (:t,:r,:score)"
                        ),
                        {
                            "t": task,
                            "r": c["rubric"],
                            "score": 75 if number == 1 else 90,
                        },
                    )
                    conn.execute(
                        text(
                            "INSERT INTO review_comments(review_task_id,content,char_count) VALUES (:t,'完整的测试评语',60)"
                        ),
                        {"t": task},
                    )
        first = conn.execute(text("SELECT min(id) FROM review_tasks")).scalar_one()
        conn.execute(
            text(
                "UPDATE review_tasks SET started_at=submitted_at-interval '20 seconds' WHERE id=:t"
            ),
            {"t": first},
        )
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert all(p["status"] == "COMPLETED" for p in response.json()["data"]["panels"]), (
        response.text
    )
    with c["engine"].begin() as conn:
        lows = (
            conn.execute(text("SELECT * FROM anomaly_records WHERE risk_level='LOW'"))
            .mappings()
            .all()
        )
        assert len(lows) == 1
        assert "SHORT_DURATION" in lows[0]["evidence_json"]["rules_triggered"]
        assert (
            conn.execute(text("SELECT count(*) FROM anomaly_records")).scalar_one() == 1
        )
        conn.execute(text("DELETE FROM anomaly_records WHERE risk_level='LOW'"))
        conn.execute(
            text(
                "UPDATE algorithm_runs SET parameters_json=parameters_json-'low_evidence_policy' WHERE algorithm_name='panel_bayesian_robust'"
            )
        )
    checks = c["client"].get(
        f"/api/teacher/assignments/{c['id']}/publication-readiness"
    )
    assert "LOW_EVIDENCE_REFRESH_REQUIRED" in checks.text
    for _ in range(2):
        response = c["client"].post(
            f"/api/teacher/assignments/{c['id']}/aggregate-reviews"
        )
        assert all(p["reused"] for p in response.json()["data"]["panels"])
    with c["engine"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM anomaly_records WHERE risk_level='LOW'")
            ).scalar_one()
            == 1
        )
