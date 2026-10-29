"""Teacher closure/deletion and overlapping submission/review with real PostgreSQL."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from test_cross_class_pipeline import prepare_final_package, seed_final_work, student
from test_teacher_integration import save_and_lock


def test_close_reopen_and_delete_published_assignment(course):
    c = course
    client = c["client"]
    url = f"/api/teacher/assignments/{c['id']}"
    assert client.post(url + "/publish").status_code == 200
    assert client.post(url + "/close").status_code == 200
    assert client.get(url).json()["data"]["closed_at"]
    assert client.post(url + "/initialize-review-tasks").status_code == 409
    with student(c["reviewers"][0][0]):
        assert client.get("/api/student/assignments").json()["data"] == []
        assert (
            client.get(
                f"/api/student/assignments/{c['id']}/project-submission"
            ).status_code
            == 409
        )
        assert client.post(url + "/reopen").status_code == 403
    assert client.post(url + "/reopen").status_code == 200
    with student(c["reviewers"][0][0]):
        assert len(client.get("/api/student/assignments").json()["data"]) == 1
    assert client.delete(url).status_code == 200
    assert client.get(url).status_code == 404
    assert client.get("/api/teacher/assignments").json()["data"] == []
    with student(c["reviewers"][0][0]):
        assert (
            client.get(
                f"/api/student/assignments/{c['id']}/project-submission"
            ).status_code
            == 404
        )


def test_published_results_can_be_closed_and_deleted_without_rewriting_grades(
    grading_course,
):
    c = grading_course
    client = c["client"]
    url = f"/api/teacher/assignments/{c['id']}"
    for sid in c["submissions"]:
        save_and_lock(c, sid)
    assert client.post(url + "/publish-results").status_code == 200
    assert client.post(url + "/close").status_code == 200
    assert client.delete(url).status_code == 200
    for path in [
        url + "/grading",
        url + "/statistics",
        f"/api/teacher/submissions/{c['submissions'][0]}/evidence",
    ]:
        assert client.get(path).status_code == 404
    with student(c["reviewers"][0][0]):
        assert (
            client.get(f"/api/student/grades?assignment_id={c['id']}").status_code
            == 404
        )
    with c["engine"].connect() as db:
        assert db.execute(text("SELECT count(*) FROM final_grades")).scalar_one() == 2


def test_parallel_intake_and_incremental_allocation_keep_existing_reviews(course, tmp_path, monkeypatch):
    prepare_final_package(tmp_path, monkeypatch)
    c = course
    client = c["client"]
    url = f"/api/teacher/assignments/{c['id']}"
    detail = client.get(url).json()["data"]
    response = client.put(
        url,
        json={
            **c["payload"],
            "type": "FINAL_PROJECT",
            "statement": "证明归并排序正确性。",
            "submit_deadline": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
            "expected_updated_at": detail["updated_at"],
        },
    )
    assert response.status_code == 200, response.text
    assert client.post(url + "/publish").status_code == 200
    for group, class_id in zip(c["reviewers"], c["classes"], strict=True):
        for user in group:
            seed_final_work(c["engine"], c["id"], user, class_id)
    preview = client.get(url + "/review-allocation-preview").json()["data"]
    assert preview["new_task_count"] == 100
    response = client.post(
        url + "/initialize-review-tasks",
        json={"expected_snapshot_hash": preview["snapshot_hash"]},
    )
    assert response.status_code == 200, response.text
    with c["engine"].connect() as db:
        old = db.execute(
            text(
                "SELECT id,reviewer_id,submission_id,status FROM review_tasks ORDER BY id"
            )
        ).all()
        rubric = db.execute(
            text("SELECT id FROM rubric_items ORDER BY id LIMIT 1")
        ).scalar_one()
    task = old[0]
    with student(task.reviewer_id):
        assert (
            client.get(f"/api/reviewer/review-tasks/{task.id}/materials/archive").status_code
            == 200
        )
        response = client.post(
            f"/api/reviewer/review-tasks/{task.id}/reviews",
            json={
                "rubric_scores": [{"rubric_item_id": rubric, "score": 88}],
                "comment": "归纳步骤与合并不变式对应，说明完整。",
            },
        )
        assert response.status_code == 200, response.text
    with student(c["reviewers"][0][0]):
        assert not client.get(f"/api/student/assignments/{c['id']}/project-submission").json()["data"]["can_submit"]
    newcomers = []
    with c["engine"].begin() as db:
        for ci, cls in enumerate(c["classes"]):
            for index in range(2):
                user = db.execute(
                    text(
                        "INSERT INTO users(student_no,name,password_hash,system_role) VALUES(:n,'新增学生','unused','STUDENT') RETURNING id"
                    ),
                    {"n": f"LATE-{ci}-{index}"},
                ).scalar_one()
                db.execute(
                    text("INSERT INTO enrollments(user_id,class_id) VALUES(:u,:c)"),
                    {"u": user, "c": cls},
                )
                newcomers.append(user)
    for index, user in enumerate(newcomers):
        with student(user):
            assert client.get(f"/api/student/assignments/{c['id']}/project-submission").json()["data"]["can_submit"]
        seed_final_work(c["engine"], c["id"], user, c["classes"][index // 2])
    preview = client.get(url + "/review-allocation-preview").json()["data"]
    assert preview["existing_task_count"] == 100 and preview["new_task_count"] == 20
    response = client.post(
        url + "/initialize-review-tasks",
        json={"expected_snapshot_hash": preview["snapshot_hash"]},
    )
    assert response.status_code == 200, response.text
    with c["engine"].connect() as db:
        rows = db.execute(
            text(
                "SELECT id,reviewer_id,submission_id,status FROM review_tasks ORDER BY id"
            )
        ).all()
        assert len(rows) == 120
        assert [(r.id, r.reviewer_id, r.submission_id) for r in rows[:100]] == [
            (r.id, r.reviewer_id, r.submission_id) for r in old
        ]
        assert rows[0].status == "SUBMITTED"
        pairs = set(
            db.execute(
                text(
                    "SELECT rt.reviewer_id,s.author_id FROM review_tasks rt JOIN submissions s ON s.id=rt.submission_id WHERE rt.is_active"
                )
            ).all()
        )
        assert not any((v, u) in pairs for u, v in pairs)
    assert client.post(url + "/initialize-review-tasks").json()["data"]["reused"]
    assert client.post(url + "/aggregate-reviews").status_code == 409
    assert client.post(url + "/finish-submissions").status_code == 200
    with student(newcomers[0]):
        assert not client.get(f"/api/student/assignments/{c['id']}/project-submission").json()[
            "data"
        ]["can_submit"]
