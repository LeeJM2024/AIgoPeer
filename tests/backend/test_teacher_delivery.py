"""Member 1 delivery: real database, real aggregation, private evidence and judge setup."""

import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def reviewed_course(course, high=False):
    c = course
    client = c["client"]
    assert client.post(f"/api/teacher/assignments/{c['id']}/publish").status_code == 200
    ids = []
    with c["engine"].begin() as conn:
        for index in range(2):
            sid = conn.execute(
                text("""INSERT INTO submissions(assignment_id,author_id,class_id,status,anonymous_token)
                VALUES (:a,:u,:c,'VALID',:token) RETURNING id"""),
                {
                    "a": c["id"],
                    "u": c["reviewers"][index][0],
                    "c": c["classes"][index],
                    "token": f"REAL-{index}",
                },
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO material_checks(submission_id,status) VALUES (:s,'VALID')"
                ),
                {"s": sid},
            )
            ids.append(sid)
    assert (
        client.post(
            f"/api/teacher/assignments/{c['id']}/initialize-review-tasks"
        ).status_code
        == 200
    )
    with c["engine"].begin() as conn:
        rubric = conn.execute(
            text(
                "SELECT ri.id FROM rubric_items ri JOIN rubrics r ON r.id=ri.rubric_id WHERE r.assignment_id=:id"
            ),
            {"id": c["id"]},
        ).scalar_one()
        tasks = (
            conn.execute(
                text("SELECT id,submission_id,panel_id FROM review_tasks ORDER BY id")
            )
            .mappings()
            .all()
        )
        for i, task in enumerate(tasks):
            conn.execute(
                text(
                    "UPDATE review_tasks SET status='SUBMITTED',started_at=now()-interval '5 minutes',submitted_at=now() WHERE id=:id"
                ),
                {"id": task["id"]},
            )
            conn.execute(
                text(
                    "INSERT INTO review_scores(review_task_id,rubric_item_id,score) VALUES (:t,:r,:score)"
                ),
                {"t": task["id"], "r": rubric, "score": 10 if high and i == 0 else 80},
            )
            conn.execute(
                text(
                    "INSERT INTO review_comments(review_task_id,content,char_count) VALUES (:t,:comment,60)"
                ),
                {
                    "t": task["id"],
                    "comment": "算法说明和例题推演完整，复杂度分析清楚，已核对边界情况。"
                    * 3,
                },
            )
    return {
        **c,
        "submissions": ids,
        "rubric": rubric,
        "panel_ids": list(dict.fromkeys(t["panel_id"] for t in tasks)),
    }


def test_real_two_panel_aggregation_does_not_confuse_initialization_runs(course):
    from app.services.designated_review_service import aggregate_panel_and_persist

    c = reviewed_course(course)
    with Session(c["engine"]) as db:
        first = aggregate_panel_and_persist(db, c["id"], c["panel_ids"][0])
        assert first["status"] == "COMPLETED", first
        assert (
            db.execute(
                text("SELECT status FROM assignments WHERE id=:id"), {"id": c["id"]}
            ).scalar_one()
            == "REVIEWER_GRADING"
        )
        db.commit()
        second = aggregate_panel_and_persist(db, c["id"], c["panel_ids"][1])
        assert second["status"] == "COMPLETED", second
        assert (
            db.execute(
                text("SELECT status FROM assignments WHERE id=:id"), {"id": c["id"]}
            ).scalar_one()
            == "TEACHER_GRADING"
        )
        db.commit()
    retry = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert retry.status_code == 200, retry.text
    assert all(p["reused"] for p in retry.json()["data"]["panels"])


def test_failed_aggregate_persistence_rolls_back_partial_output_and_can_retry(course):
    c = reviewed_course(course)
    with c["engine"].begin() as conn:
        conn.execute(
            text("""CREATE FUNCTION reject_aggregate_test() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'test persistence failure'; END; $$ LANGUAGE plpgsql;
            CREATE TRIGGER reject_aggregate BEFORE INSERT ON designated_review_aggregates
            FOR EACH ROW EXECUTE FUNCTION reject_aggregate_test();""")
        )
    result = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert result.status_code == 200, result.text
    assert all(p["status"] == "FAILED" for p in result.json()["data"]["panels"])
    with c["engine"].begin() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM designated_review_aggregates")
            ).scalar_one()
            == 0
        )
        assert (
            conn.execute(text("SELECT count(*) FROM reviewer_profiles")).scalar_one()
            == 0
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM algorithm_runs WHERE status='FAILED'")
            ).scalar_one()
            == 2
        )
        conn.execute(
            text("DROP TRIGGER reject_aggregate ON designated_review_aggregates")
        )
    result = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert all(p["status"] == "COMPLETED" for p in result.json()["data"]["panels"])


def test_missing_fifth_review_blocks_aggregation(course):
    c = reviewed_course(course)
    with c["engine"].begin() as conn:
        conn.execute(
            text(
                "UPDATE review_tasks SET status='PENDING' WHERE id=(SELECT min(id) FROM review_tasks)"
            )
        )
    result = (
        c["client"]
        .post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
        .json()["data"]
    )
    assert result["panels"][0]["status"] == "INSUFFICIENT_REVIEWS"
    with c["engine"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT status FROM assignments WHERE id=:id"), {"id": c["id"]}
            ).scalar_one()
            == "REVIEWER_GRADING"
        )


def test_high_risk_final_review_is_idempotent_and_export_has_provenance(course):
    c = reviewed_course(course, high=True)
    assert (
        c["client"]
        .post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
        .status_code
        == 200
    )
    for sid in c["submissions"]:
        response = c["client"].post(
            f"/api/teacher/submissions/{sid}/grades",
            json={"rubric_scores": [{"rubric_item_id": c["rubric"], "score": 90}]},
        )
        assert response.status_code == 201, response.text
        grade_id = response.json()["data"]["teacher_grade_id"]
        assert (
            c["client"].post(f"/api/teacher/grades/{grade_id}/lock").status_code == 200
        )
    sid = c["submissions"][0]
    url = f"/api/teacher/submissions/{sid}/final-review"
    payload = {"final_score": 87, "reason": "核对原始材料和五人评分后确认"}
    response = c["client"].post(url, json=payload)
    assert response.status_code == 201, response.text
    retry = c["client"].post(url, json=payload)
    assert retry.status_code == 201 and retry.json() == response.json()
    assert c["client"].post(url, json={**payload, "final_score": 88}).status_code == 409
    evidence = (
        c["client"].get(f"/api/teacher/submissions/{sid}/evidence").json()["data"]
    )
    assert len(evidence["reviews"]) == 5
    assert evidence["final_review"]["reason"] == payload["reason"]
    # A one-work panel can also escalate on model uncertainty; handle every
    # actual finding, rather than bypassing publication guards in test fixtures.
    workspace = (
        c["client"].get(f"/api/teacher/assignments/{c['id']}/grading").json()["data"]
    )
    for item in workspace["submissions"]:
        if item["final_review_status"] == "ESCALATED_FOR_TEACHER_FINAL_REVIEW":
            assert (
                c["client"]
                .post(
                    f"/api/teacher/submissions/{item['id']}/final-review",
                    json={"final_score": 89, "reason": "小样本不确定性复核完成"},
                )
                .status_code
                == 201
            )
    publish = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert publish.status_code == 200, publish.text
    rows = (
        c["client"]
        .get(f"/api/teacher/assignments/{c['id']}/statistics")
        .json()["data"]["grades"]
    )
    high = next(r for r in rows if r["submission_id"] == sid)
    assert high["final_grade_source"] == "TEACHER_FINAL_REVIEW"
    assert float(high["final_score"]) == 87
    assert high["final_review_reason"] == payload["reason"]


def problem_payload(course):
    return {
        **course["payload"],
        "type": "PROGRAMMING",
        "title": "教师创建的求和题",
        "submit_deadline": "2030-01-01T00:00:00Z",
        "review_deadline": "2030-02-01T00:00:00Z",
        "programming_problem": {
            "statement": "求两个数的和",
            "input_description": "两个整数",
            "output_description": "一个整数",
            "test_cases": [
                {"input_data": "1 2\n", "expected_output": "3\n", "is_public": True},
                {
                    "input_data": " 999 1\n",
                    "expected_output": "1000\n",
                    "is_public": False,
                },
            ],
        },
    }


def test_teacher_programming_creation_publish_and_hidden_case_security(course):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    c = course
    response = c["client"].post("/api/teacher/assignments", json=problem_payload(c))
    assert response.status_code == 201, response.text
    aid = response.json()["data"]["assignment_id"]
    detail = c["client"].get(f"/api/teacher/assignments/{aid}").json()["data"]
    assert detail["programming_problem"]["test_cases"][1]["input_data"] == " 999 1\n"
    assert detail["panels"] == []
    assert (
        c["client"].post(f"/api/teacher/assignments/{aid}/publish").status_code == 200
    )
    assert (
        c["client"]
        .post(f"/api/teacher/assignments/{aid}/initialize-review-tasks")
        .status_code
        == 400
    )
    with pytest.raises(DBAPIError), c["engine"].begin() as conn:
        conn.execute(
            text(
                "UPDATE programming_test_cases SET expected_output='bad' WHERE problem_assignment_id=:id"
            ),
            {"id": aid},
        )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        c["reviewers"][0][0], "STUDENT"
    )
    assert c["client"].get(f"/api/teacher/assignments/{aid}").status_code == 403
    public = c["client"].get(f"/api/student/assignments/{aid}/programming-problem")
    assert public.status_code == 200
    assert len(public.json()["data"]["samples"]) == 1 and "999" not in public.text


def test_programming_draft_updates_are_atomic_and_require_complete_cases(course):
    c = course
    payload = problem_payload(c)
    invalid = {
        **payload,
        "programming_problem": {
            **payload["programming_problem"],
            "test_cases": [{"input_data": "", "expected_output": "", "is_public": True}]
            * 2,
        },
    }
    assert c["client"].post("/api/teacher/assignments", json=invalid).status_code == 422
    aid = (
        c["client"]
        .post("/api/teacher/assignments", json=payload)
        .json()["data"]["assignment_id"]
    )
    detail = c["client"].get(f"/api/teacher/assignments/{aid}").json()["data"]
    update = {
        **payload,
        "expected_updated_at": detail["updated_at"],
        "title": "已编辑题目",
    }
    assert (
        c["client"].put(f"/api/teacher/assignments/{aid}", json=update).status_code
        == 200
    )
    assert (
        c["client"].put(f"/api/teacher/assignments/{aid}", json=update).status_code
        == 409
    )
    assert c["client"].delete(f"/api/teacher/assignments/{aid}").status_code == 200


def attach_material(c, tmp_path, monkeypatch):
    from app.core.config import settings

    sid = c["submissions"][0]
    manifest = {
        "ppt_path": "slides.pptx",
        "video_path": "lesson.mp4",
        "readme_path": "README.md",
        "source_paths": ["main.cpp"],
        "examples": [{"location": "PPT", "pages": [1, 2, 3]}],
        "tests": [{"input_path": "case.in", "expected_path": "case.out"}] * 3,
    }
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    with ZipFile(tmp_path / "sample.zip", "w", ZIP_DEFLATED) as z:
        z.writestr("README.md", "原始材料说明")
        z.writestr("private.txt", "未声明的材料")
    with c["engine"].begin() as conn:
        conn.execute(
            text("UPDATE submissions SET manifest_json=CAST(:m AS jsonb) WHERE id=:s"),
            {"m": json.dumps(manifest), "s": sid},
        )
        conn.execute(
            text(
                "INSERT INTO submission_files(submission_id,file_kind,storage_key,file_name,size_bytes,checksum) VALUES (:s,'ZIP','sample.zip','sample.zip',100,'test')"
            ),
            {"s": sid},
        )
    return sid


def test_teacher_material_access_blocks_students_and_undeclared_entries(
    course, tmp_path, monkeypatch
):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    c = reviewed_course(course)
    sid = attach_material(c, tmp_path, monkeypatch)
    url = f"/api/teacher/submissions/{sid}/material"
    response = c["client"].get(url, params={"path": "README.md"})
    assert response.status_code == 200 and response.text == "原始材料说明"
    assert response.headers["cache-control"] == "private, no-store"
    assert c["client"].get(url).content.startswith(b"PK")
    for path in ["../secret", "private.txt", "/etc/passwd", "missing.mp4"]:
        assert c["client"].get(url, params={"path": path}).status_code == 404
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        c["reviewers"][0][0], "STUDENT"
    )
    assert c["client"].get(url, params={"path": "README.md"}).status_code == 403
    assert (
        c["client"].get(f"/api/teacher/submissions/{sid}/evidence").status_code == 403
    )


def test_late_material_check_cannot_reactivate_historical_submission(course):
    from app.services.student.material_check_service import _record_result

    c = reviewed_course(course)
    sid = c["submissions"][0]
    with c["engine"].begin() as conn:
        conn.execute(
            text(
                "UPDATE submissions SET is_current=false,status='SUPERSEDED' WHERE id=:s"
            ),
            {"s": sid},
        )
    with Session(c["engine"]) as db:
        _record_result(
            db=db,
            submission_id=sid,
            status_value="VALID",
            missing_items=[],
            warnings=[],
            details={},
        )
        assert (
            db.execute(
                text("SELECT status FROM submissions WHERE id=:s"), {"s": sid}
            ).scalar_one()
            == "SUPERSEDED"
        )
    workspace = (
        c["client"].get(f"/api/teacher/assignments/{c['id']}/grading").json()["data"]
    )
    assert sid not in [s["id"] for s in workspace["submissions"]]


def test_teacher_topic_management_preserves_claimed_history(course):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    c = course
    payload = {
        "code": "NEW01",
        "chapter": "动态规划",
        "name": "背包问题",
        "description": "状态转移与边界条件",
    }
    result = c["client"].post("/api/teacher/topics", json=payload)
    assert result.status_code == 201
    tid = result.json()["data"]["topic_id"]
    row = next(
        r
        for r in c["client"].get("/api/teacher/topics").json()["data"]
        if r["id"] == tid
    )
    update = {
        **payload,
        "name": "背包问题与状态压缩",
        "expected_updated_at": row["updated_at"],
    }
    assert c["client"].put(f"/api/teacher/topics/{tid}", json=update).status_code == 200
    assert c["client"].put(f"/api/teacher/topics/{tid}", json=update).status_code == 409
    with c["engine"].begin() as conn:
        conn.execute(
            text(
                "INSERT INTO topic_claims(assignment_id,student_id,topic_id) VALUES (:a,:s,:t)"
            ),
            {"a": c["id"], "s": c["reviewers"][0][0], "t": tid},
        )
    assert (
        c["client"].put(f"/api/teacher/topics/{tid}", json=update).json()["code"]
        == "TOPIC_ALREADY_CLAIMED"
    )
    assert c["client"].delete(f"/api/teacher/topics/{tid}").status_code == 409
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        c["reviewers"][0][0], "STUDENT"
    )
    assert c["client"].post("/api/teacher/topics", json=payload).status_code == 403


def test_programming_results_use_current_submission_and_exclude_source(course):
    c = course
    aid = (
        c["client"]
        .post("/api/teacher/assignments", json=problem_payload(c))
        .json()["data"]["assignment_id"]
    )
    with c["engine"].begin() as conn:
        for version in (1, 2):
            conn.execute(
                text("""INSERT INTO code_submissions(assignment_id,author_id,class_id,language,source_code,version,is_current,status)
                VALUES (:a,:u,:c,'cpp17','private-source',:v,:current,:status)"""),
                {
                    "a": aid,
                    "u": c["reviewers"][0][0],
                    "c": c["classes"][0],
                    "v": version,
                    "current": version == 2,
                    "status": "AC" if version == 2 else "WA",
                },
            )
    response = c["client"].get(f"/api/teacher/assignments/{aid}/programming-results")
    assert response.status_code == 200 and "private-source" not in response.text
    rows = response.json()["data"]
    assert len(rows) == 1 and rows[0]["version"] == 2 and rows[0]["status"] == "AC"
