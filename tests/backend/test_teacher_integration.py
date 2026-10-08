from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def save_and_lock(course, sid, score=90):
    response = course["client"].post(
        f"/api/teacher/submissions/{sid}/grades",
        json={
            "rubric_scores": [{"rubric_item_id": course["rubric"], "score": score}],
            "comment": "测试反馈",
        },
    )
    assert response.status_code == 201, response.text
    gid = response.json()["data"]["teacher_grade_id"]
    response = course["client"].post(f"/api/teacher/grades/{gid}/lock")
    assert response.status_code == 200, response.text
    return gid


def test_publish_freezes_latest_version_weights_and_is_idempotent(grading_course):
    c = grading_course
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    url = f"/api/teacher/assignments/{c['id']}/publish-results"
    response = c["client"].post(url)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["published_count"] == 2
    assert c["client"].post(url).json() == response.json()
    with c["engine"].connect() as conn:
        grades = conn.execute(
            text(
                "SELECT final_score,teacher_weight,designated_review_weight FROM final_grades"
            )
        ).all()
        assert all(
            float(r.final_score) == 86 and float(r.teacher_weight) == 0.6
            for r in grades
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action='PUBLISH_RESULTS'")
            ).scalar_one()
            == 1
        )
    response = c["client"].post(
        f"/api/teacher/submissions/{c['submissions'][0]}/grade-corrections",
        json={
            "rubric_scores": [{"rubric_item_id": c["rubric"], "score": 95}],
            "expected_version": 1,
            "reason": "测试修正",
        },
    )
    assert response.status_code == 409


def test_unlocked_correction_blocks_old_locked_score(grading_course):
    c = grading_course
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    response = c["client"].post(
        f"/api/teacher/submissions/{c['submissions'][0]}/grade-corrections",
        json={
            "rubric_scores": [{"rubric_item_id": c["rubric"], "score": 95}],
            "expected_version": 1,
            "reason": "核对后更正",
        },
    )
    assert response.status_code == 201
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert response.status_code == 424
    assert "LATEST_GRADE_NOT_LOCKED" in response.text
    with c["engine"].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM final_grades")).scalar_one() == 0


@pytest.mark.parametrize(
    "condition,code",
    [
        ("missing", "REVIEWS_INCOMPLETE"),
        ("aggregate", "AGGREGATE_NOT_READY"),
        ("stale", "AGGREGATE_STALE"),
        ("material", "MATERIAL_NOT_VALID"),
        ("anomaly", "OPEN_ANOMALIES_REQUIRE_REVIEW"),
    ],
)
def test_publication_failures_are_atomic(grading_course, condition, code):
    c = grading_course
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    with c["engine"].begin() as conn:
        sid = c["submissions"][-1]
        if condition == "missing":
            conn.execute(
                text(
                    "UPDATE review_tasks SET status='PENDING' WHERE id=(SELECT max(id) FROM review_tasks)"
                )
            )
        elif condition == "aggregate":
            conn.execute(
                text("DELETE FROM designated_review_aggregates WHERE submission_id=:s"),
                {"s": sid},
            )
        elif condition == "stale":
            conn.execute(
                text(
                    "UPDATE review_tasks SET submitted_at=now()+interval '1 second' WHERE submission_id=:s"
                ),
                {"s": sid},
            )
        elif condition == "material":
            conn.execute(
                text(
                    "UPDATE material_checks SET status='INVALID' WHERE submission_id=:s"
                ),
                {"s": sid},
            )
        else:
            conn.execute(
                text("""INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json)
                SELECT :s,id,'HIGH',.9,'{}' FROM algorithm_runs ORDER BY id DESC LIMIT 1"""),
                {"s": sid},
            )
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert response.status_code == 424, response.text
    assert code in response.text
    with c["engine"].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM final_grades")).scalar_one() == 0
        assert (
            conn.execute(
                text("SELECT status FROM assignments WHERE id=:id"), {"id": c["id"]}
            ).scalar_one()
            == "TEACHER_GRADING"
        )


def test_concurrent_initial_grade_and_correction(grading_course):
    c = grading_course
    sid = c["submissions"][0]
    payload = {"rubric_scores": [{"rubric_item_id": c["rubric"], "score": 88}]}
    for path, body in [
        ("grades", payload),
        (
            "grade-corrections",
            {**payload, "expected_version": 1, "reason": "并发修正测试"},
        ),
    ]:
        barrier = Barrier(2)

        def request(barrier=barrier, path=path, body=body):
            barrier.wait(timeout=5)
            return c["client"].post(f"/api/teacher/submissions/{sid}/{path}", json=body)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: request(), range(2)))
        assert sorted(r.status_code for r in results) == [201, 409], [
            r.text for r in results
        ]
        gid = next(
            r.json()["data"]["teacher_grade_id"]
            for r in results
            if r.status_code == 201
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _, grade_id=gid: c["client"].post(
                        f"/api/teacher/grades/{grade_id}/lock"
                    ),
                    range(2),
                )
            )
        assert [r.status_code for r in responses] == [200, 200]
    with c["engine"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM teacher_grades WHERE submission_id=:s"),
                {"s": sid},
            ).scalar_one()
            == 2
        )


def test_database_trigger_protects_score_identity_and_history(grading_course):
    c = grading_course
    sid = c["submissions"][0]
    gid = save_and_lock(c, sid)
    for statement in [
        "UPDATE teacher_grades SET total_score=1 WHERE id=:id",
        "DELETE FROM teacher_grades WHERE id=:id",
        "UPDATE teacher_grades SET created_at=now() WHERE id=:id",
    ]:
        with pytest.raises(DBAPIError), c["engine"].begin() as conn:
            conn.execute(text(statement), {"id": gid})


def test_import_is_atomic_idempotent_and_does_not_reset_password(
    teacher_api, pg_engine
):
    client, _ = teacher_api
    cid = client.post(
        "/api/teacher/classes", json={"name": "导入测试", "course_term": "TEST"}
    ).json()["data"]["class_id"]
    url = f"/api/teacher/classes/{cid}/students/import"
    payload = {
        "students": [
            {
                "student_no": "IMPORT-1",
                "name": "测试学生",
                "password": "Test-password-123",
            }
        ]
    }
    assert client.post(url, json=payload).status_code == 200
    with pg_engine.connect() as conn:
        original = conn.execute(
            text("SELECT password_hash FROM users WHERE student_no='IMPORT-1'")
        ).scalar_one()
    payload["students"][0]["password"] = "Different-password"
    assert client.post(url, json=payload).json()["data"]["unchanged"] == 1
    with pg_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT password_hash FROM users WHERE student_no='IMPORT-1'")
            ).scalar_one()
            == original
        )
    response = client.post(
        url,
        json={
            "students": [
                {
                    "student_no": "AAA-NEW",
                    "name": "不应保存",
                    "password": "Test-password-123",
                },
                {"student_no": "IMPORT-1", "name": "冲突姓名"},
            ]
        },
    )
    assert response.status_code == 409
    with pg_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM users WHERE student_no='AAA-NEW'")
            ).scalar_one()
            == 0
        )


def test_draft_edit_preserves_panels_and_published_rules_are_frozen(course):
    c = course
    url = f"/api/teacher/assignments/{c['id']}"
    payload = {
        **c["payload"],
        "title": "修改后的草稿",
        "expected_updated_at": c["client"].get(url).json()["data"]["updated_at"],
    }
    assert c["client"].put(url, json=payload).status_code == 200
    assert len(c["client"].get(url).json()["data"]["panels"]) == 2
    assert c["client"].post(url + "/publish").status_code == 200
    assert c["client"].put(url, json=payload).status_code == 409
    assert c["client"].delete(url).status_code == 409


def test_high_risk_requires_final_review_and_medium_resolution_is_immutable(grading_course):
    c = grading_course
    with c["engine"].begin() as conn:
        high_aid = conn.execute(
            text("""INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json)
            SELECT :s,id,'HIGH',.9,'{}' FROM algorithm_runs ORDER BY id DESC LIMIT 1 RETURNING id"""),
            {"s": c["submissions"][0]},
        ).scalar_one()
    high_url = f"/api/teacher/anomalies/{high_aid}/resolve"
    assert (
        c["client"]
        .post(high_url, json={"status": "DISMISSED", "note": "已核对原始证据"})
        .status_code
        == 409
    )
    with c["engine"].connect() as conn:
        assert conn.execute(
            text("SELECT status FROM anomaly_records WHERE id=:id"), {"id": high_aid}
        ).scalar_one() == "OPEN"

    with c["engine"].begin() as conn:
        aid = conn.execute(
            text("""INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json)
            SELECT :s,id,'MEDIUM',.5,'{}' FROM algorithm_runs ORDER BY id DESC LIMIT 1 RETURNING id"""),
            {"s": c["submissions"][0]},
        ).scalar_one()
    url = f"/api/teacher/anomalies/{aid}/resolve"
    assert c["client"].post(
        url, json={"status": "DISMISSED", "note": "已核对原始证据"}
    ).status_code == 200
    assert (
        c["client"]
        .post(url, json={"status": "CONFIRMED", "note": "重复操作"})
        .status_code
        == 409
    )
    with c["engine"].connect() as conn:
        row = conn.execute(
            text(
                "SELECT resolved_by,resolution_note FROM anomaly_records WHERE id=:id"
            ),
            {"id": aid},
        ).one()
        assert (
            row.resolved_by == c["teacher"] and row.resolution_note == "已核对原始证据"
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action='RESOLVE_ANOMALY'")
            ).scalar_one()
            == 1
        )


def test_student_cannot_access_teacher_endpoints(teacher_api):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    client, _ = teacher_api
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(1, "STUDENT")
    for path in [
        "/classes",
        "/assignments/1/grading",
        "/assignments/1/statistics",
        "/submissions/1/grade-history",
    ]:
        assert client.get("/api/teacher" + path).status_code == 403


def test_migration_downgrade_upgrade(pg_engine):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "backend/alembic")
    )
    with pg_engine.begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, "20260929_0002")
        command.upgrade(config, "head")
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "20261008_0005"
        )


def test_published_results_and_inputs_are_immutable(grading_course):
    c = grading_course
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    assert (
        c["client"]
        .post(f"/api/teacher/assignments/{c['id']}/publish-results")
        .status_code
        == 200
    )
    for sql in [
        "UPDATE final_grades SET final_score=1",
        "UPDATE review_tasks SET status='PENDING'",
        "UPDATE designated_review_aggregates SET total_score=1",
        "UPDATE material_checks SET status='INVALID'",
        "DELETE FROM final_grades",
    ]:
        with pytest.raises(DBAPIError), c["engine"].begin() as conn:
            conn.execute(text(sql))


def test_stale_draft_is_rejected(course):
    c = course
    url = f"/api/teacher/assignments/{c['id']}"
    payload = {
        **c["payload"],
        "expected_updated_at": c["client"].get(url).json()["data"]["updated_at"],
    }
    assert (
        c["client"].put(url, json={**payload, "title": "较新的内容"}).status_code == 200
    )
    response = c["client"].put(url, json={**payload, "title": "过期内容"})
    assert response.status_code == 409 and "DRAFT_VERSION_CONFLICT" in response.text
    assert c["client"].get(url).json()["data"]["title"] == "较新的内容"


def test_second_insert_failure_rolls_back_whole_publication(grading_course):
    c = grading_course
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    with c["engine"].begin() as conn:
        conn.execute(
            text(f"""
            CREATE FUNCTION qa_fail_publish() RETURNS trigger AS $$ BEGIN
              IF NEW.submission_id={c["submissions"][1]} THEN
                RAISE EXCEPTION 'injected constraint failure' USING ERRCODE='23514';
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            CREATE TRIGGER qa_fail_publish BEFORE INSERT ON final_grades
              FOR EACH ROW EXECUTE FUNCTION qa_fail_publish();
        """)
        )
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert response.status_code == 409
    with c["engine"].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM final_grades")).scalar_one() == 0
        assert (
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action='PUBLISH_RESULTS'")
            ).scalar_one()
            == 0
        )


@pytest.mark.parametrize("bad_panels", ["four", "duplicate", "same_class"])
def test_invalid_panel_configuration_is_rejected(course, bad_panels):
    import copy

    c = course
    panels = copy.deepcopy(c["panels"])
    if bad_panels == "four":
        panels[0]["reviewer_ids"].pop()
    elif bad_panels == "duplicate":
        panels[0]["reviewer_ids"][1] = panels[0]["reviewer_ids"][0]
    else:
        panels[0]["reviewer_ids"] = c["reviewers"][0]
    response = c["client"].put(
        f"/api/teacher/assignments/{c['id']}/review-panels", json={"panels": panels}
    )
    assert response.status_code == 422
    assert (
        len(
            c["client"]
            .get(f"/api/teacher/assignments/{c['id']}")
            .json()["data"]["panels"]
        )
        == 2
    )


def test_published_rubric_cannot_be_deleted_or_reweighted(grading_course):
    c = grading_course
    for statement in [
        "DELETE FROM rubric_items",
        "DELETE FROM rubrics",
        "UPDATE assignments SET teacher_weight=.7,designated_review_weight=.3",
        "DELETE FROM assignment_classes",
    ]:
        with pytest.raises(DBAPIError), c["engine"].begin() as conn:
            conn.execute(text(statement))


def test_draft_delete_and_class_change_clear_panels(course):
    c = course
    url = f"/api/teacher/assignments/{c['id']}"
    cid = (
        c["client"]
        .post("/api/teacher/classes", json={"name": "第三班", "course_term": "TEST"})
        .json()["data"]["class_id"]
    )
    payload = {
        **c["payload"],
        "class_ids": [c["classes"][0], cid],
        "expected_updated_at": c["client"].get(url).json()["data"]["updated_at"],
    }
    result = c["client"].put(url, json=payload)
    assert result.status_code == 200 and result.json()["data"]["panels_reset"]
    assert c["client"].get(url).json()["data"]["panels"] == []
    assert c["client"].delete(url).status_code == 200
    assert c["client"].get(url).status_code == 404


def test_enrollment_cannot_break_saved_panel(course):
    c = course
    sid = c["reviewers"][0][0]
    assert (
        c["client"]
        .delete(f"/api/teacher/classes/{c['classes'][0]}/students/{sid}")
        .status_code
        == 409
    )
    response = c["client"].post(
        f"/api/teacher/classes/{c['classes'][1]}/students/import",
        json={"students": [{"student_no": "TEST-0-0", "name": "虚构学生"}]},
    )
    assert response.status_code == 409 and "REVIEWER_CLASS_CONFLICT" in response.text


def test_upgrade_preserves_published_history(grading_course):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    c = grading_course
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    assert (
        c["client"]
        .post(f"/api/teacher/assignments/{c['id']}/publish-results")
        .status_code
        == 200
    )
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "backend/alembic")
    )
    with c["engine"].begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, "20260929_0002")
        command.upgrade(config, "head")
        assert (
            conn.execute(
                text("SELECT count(*) FROM teacher_grades WHERE locked_at IS NOT NULL")
            ).scalar_one()
            == 2
        )
        rows = conn.execute(
            text("SELECT final_score,teacher_weight FROM final_grades")
        ).all()
        assert len(rows) == 2 and all(
            float(r.final_score) == 86 and float(r.teacher_weight) == 0.6 for r in rows
        )
