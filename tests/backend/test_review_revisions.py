"""Submitted-review corrections use real isolated PostgreSQL transactions."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_reviewer_tasks import _as_student, _restore_student_override, _review_task


def _payload(rubric, score=91, version=1):
    return {"rubric_scores": [{"rubric_item_id": rubric, "score": score}],
            "comment": "重新核对证明和边界处理后给出评分。", "expected_version": version,
            "reason": "前次误填分数，核对材料后更正。"}


def _submitted(course, tmp_path, monkeypatch):
    reviewer, author, task, rubric = _review_task(course, tmp_path, monkeypatch)
    previous = _as_student(reviewer)
    try:
        assert course["client"].get(f"/api/reviewer/review-tasks/{task}/materials/archive").status_code == 200
        assert course["client"].post(f"/api/reviewer/review-tasks/{task}/reviews", json={
            "rubric_scores": [{"rubric_item_id": rubric, "score": 88}], "comment": "首次评分依据。"
        }).status_code == 200
    finally:
        _restore_student_override(previous)
    return reviewer, author, task, rubric


def test_revision_history_latest_values_and_conflicts(course, tmp_path, monkeypatch):
    reviewer, _author, task, rubric = _submitted(course, tmp_path, monkeypatch)
    client = course["client"]
    with course["engine"].connect() as db:
        first_time = db.execute(text("SELECT submitted_at FROM review_tasks WHERE id=:t"), {"t": task}).scalar_one()
    previous = _as_student(reviewer)
    try:
        path = f"/api/reviewer/review-tasks/{task}/revisions"
        payload = _payload(rubric)
        for reason in ("", "   ", "误"):
            assert client.post(path, json={**payload, "reason": reason}).status_code == 422
        assert client.post(path, json={**payload, "rubric_scores": [{"rubric_item_id": rubric, "score": 101}]}).status_code == 422
        assert client.post(path, json={**payload, "rubric_scores": payload["rubric_scores"] * 2}).status_code == 422
        first = client.post(path, json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["data"]["version"] == 2
        assert client.post(path, json=payload).status_code == 409  # stale browser tab
        unchanged = {**payload, "expected_version": 2}
        assert client.post(path, json=unchanged).json()["detail"] == "REVIEW_UNCHANGED"
        second = client.post(path, json=_payload(rubric, score=93, version=2))
        assert second.status_code == 200, second.text
        items = client.get("/api/reviewer/review-tasks/mine?status=SUBMITTED").json()["data"]
        own = next(item for item in items if item["task_id"] == task)
        assert own["review"]["version"] == 3 and own["can_amend"]
        assert own["review"]["rubric_scores"][0]["score"] == 93
        assert not any(item["task_id"] == task for item in client.get("/api/reviewer/review-tasks/mine").json()["data"])
        assert set(own).isdisjoint({"author_id", "author_name", "student_no", "teacher_score"})
    finally:
        _restore_student_override(previous)
    with course["engine"].connect() as db:
        assert db.execute(text("SELECT submitted_at FROM review_tasks WHERE id=:t"), {"t": task}).scalar_one() == first_time
        sid = db.execute(text("SELECT submission_id FROM review_tasks WHERE id=:t"), {"t": task}).scalar_one()
        assert db.execute(text("SELECT count(*) FROM review_tasks WHERE submission_id=:s AND is_active"), {"s": sid}).scalar_one() == 5
    evidence = client.get(f"/api/teacher/submissions/{sid}/evidence")
    assert evidence.status_code == 200, evidence.text
    review = next(item for item in evidence.json()["data"]["reviews"] if item["id"] == task)
    assert float(review["scores"][0]["score"]) == 93
    assert [rev["version"] for rev in review["revisions"]] == [2, 3]
    assert review["revisions"][0]["before"]["rubric_scores"][0]["score"] == 88
    assert review["revisions"][0]["after"]["rubric_scores"][0]["score"] == 91
    assert review["revisions"][1]["before"]["rubric_scores"][0]["score"] == 91
    assert review["revisions"][1]["reason"] == _payload(rubric)["reason"]
    assert review["revisions"][1]["created_at"]


def test_only_owner_can_revise_and_unsubmitted_task_rejected(course, tmp_path, monkeypatch):
    reviewer, author, task, rubric = _review_task(course, tmp_path, monkeypatch)
    client = course["client"]
    path = f"/api/reviewer/review-tasks/{task}/revisions"
    assert client.post(path, json=_payload(rubric)).status_code == 403  # teacher
    for user, expected in ((author, 403), (reviewer, 409)):
        previous = _as_student(user)
        try:
            assert client.post(path, json=_payload(rubric)).status_code == expected
        finally:
            _restore_student_override(previous)


@pytest.mark.parametrize("closed_by", ["deadline", "aggregation", "closed"])
def test_revisions_close_with_review_window(course, tmp_path, monkeypatch, closed_by):
    reviewer, _, task, rubric = _submitted(course, tmp_path, monkeypatch)
    sql = {"deadline": "review_deadline=now()-interval '1 minute'",
           "aggregation": "status='AGGREGATING'", "closed": "closed_at=now()"}[closed_by]
    with course["engine"].begin() as db:
        db.execute(text(f"UPDATE assignments SET {sql} WHERE id=:id"), {"id": course["id"]})
    previous = _as_student(reviewer)
    try:
        response = course["client"].post(f"/api/reviewer/review-tasks/{task}/revisions", json=_payload(rubric))
        assert response.status_code in (403, 409), response.text
        if closed_by != "closed":
            item = course["client"].get("/api/reviewer/review-tasks/mine?status=SUBMITTED").json()["data"][0]
            assert not item["can_amend"]
    finally:
        _restore_student_override(previous)
    with course["engine"].connect() as db:
        assert db.execute(text("SELECT count(*) FROM review_revisions")).scalar_one() == 0
        assert float(db.execute(text("SELECT score FROM review_scores WHERE review_task_id=:t"), {"t": task}).scalar_one()) == 88


def test_database_blocks_untracked_changes_and_history_tampering(course, tmp_path, monkeypatch):
    reviewer, _, task, rubric = _submitted(course, tmp_path, monkeypatch)
    previous = _as_student(reviewer)
    try:
        response = course["client"].post(f"/api/reviewer/review-tasks/{task}/revisions", json=_payload(rubric))
        assert response.status_code == 200, response.text
    finally:
        _restore_student_override(previous)
    for sql in ("UPDATE review_scores SET score=0 WHERE review_task_id=:t",
                "UPDATE review_comments SET content='tampered' WHERE review_task_id=:t",
                "UPDATE review_revisions SET reason='tampered' WHERE review_task_id=:t",
                "DELETE FROM review_revisions WHERE review_task_id=:t"):
        with pytest.raises(DBAPIError), course["engine"].begin() as db:
            db.execute(text(sql), {"t": task})
    with pytest.raises(DBAPIError), course["engine"].begin() as db:
        db.execute(text("""INSERT INTO review_revisions(review_task_id,version,actor_id,reason,before_json,after_json)
            VALUES(:t,3,:actor,'未实际保存修改',review_snapshot(:t),
              jsonb_set(review_snapshot(:t),'{comment}','"未实际保存"'::jsonb))"""),
            {"t": task, "actor": reviewer})


def test_revision_makes_prior_aggregate_stale_and_blocks_phase_advance(grading_course):
    from app.services.designated_review_service import _advance_if_complete
    from app.services.teacher_workflow import publication_readiness
    from sqlalchemy.orm import Session

    c = grading_course
    with c["engine"].begin() as db:
        db.execute(text("UPDATE assignments SET status='REVIEWER_GRADING' WHERE id=:a"), {"a": c["id"]})
        task, reviewer = db.execute(text("SELECT id,reviewer_id FROM review_tasks ORDER BY id LIMIT 1")).one()
    previous = _as_student(reviewer)
    try:
        response = c["client"].post(f"/api/reviewer/review-tasks/{task}/revisions", json=_payload(c["rubric"]))
        assert response.status_code == 200, response.text
    finally:
        _restore_student_override(previous)
    with Session(c["engine"]) as db:
        readiness, _ = publication_readiness(db, c["id"])
        assert "AGGREGATE_STALE" in {blocker["code"] for blocker in readiness["blockers"]}
        _advance_if_complete(db, c["id"])
        assert db.execute(text("SELECT status FROM assignments WHERE id=:a"), {"a": c["id"]}).scalar_one() == "REVIEWER_GRADING"


@pytest.mark.parametrize("new_score,new_comment", [(91, "重新核对证明和边界处理后给出评分。"), (88, "更正评分依据。")])
def test_aggregation_consumes_latest_revision_once(course, tmp_path, monkeypatch, new_score, new_comment):
    import hashlib
    import json

    from app.services import designated_review_service as service
    from sqlalchemy.orm import Session

    reviewer, _, task, rubric = _submitted(course, tmp_path, monkeypatch)
    previous = _as_student(reviewer)
    try:
        payload = {**_payload(rubric, score=new_score), "comment": new_comment}
        assert course["client"].post(f"/api/reviewer/review-tasks/{task}/revisions", json=payload).status_code == 200
    finally:
        _restore_student_override(previous)
    with course["engine"].begin() as db:
        panel = db.execute(text("SELECT panel_id FROM review_tasks WHERE id=:t"), {"t": task}).scalar_one()
        others = db.execute(text("SELECT id FROM review_tasks WHERE panel_id=:p AND id<>:t"), {"p": panel, "t": task}).scalars().all()
        for other in others:
            db.execute(text("INSERT INTO review_scores(review_task_id,rubric_item_id,score) VALUES(:t,:r,88)"), {"t": other, "r": rubric})
            db.execute(text("INSERT INTO review_comments(review_task_id,content,char_count) VALUES(:t,'认真核对材料后的评分。',12)"), {"t": other})
            db.execute(text("UPDATE review_tasks SET status='SUBMITTED',started_at=now()-interval '5 minutes',submitted_at=now() WHERE id=:t"), {"t": other})
    captured = []
    actual = service.aggregate_panel_scores
    def capture(request):
        captured.extend(request.observations)
        return actual(request)
    monkeypatch.setattr(service, "aggregate_panel_scores", capture)
    with Session(course["engine"]) as db:
        result = service.aggregate_panel_and_persist(db, course["id"], panel)
        db.commit()
    assert result["status"] == "COMPLETED"
    assert len(captured) == 5
    amended = [obs for obs in captured if obs.task_id == task]
    assert len(amended) == 1 and amended[0].rubric_scores[0].score == new_score
    # A same-length comment edit must not reuse the pre-revision aggregate.
    old_hash = hashlib.sha256(json.dumps({"scores": service._canonical_hash(captured), "history": []}, sort_keys=True).encode()).hexdigest()
    with course["engine"].connect() as db:
        persisted_hash = db.execute(text("SELECT input_hash FROM algorithm_runs WHERE id=:id"), {"id": result["algorithm_run_id"]}).scalar_one()
        assert persisted_hash != old_hash
