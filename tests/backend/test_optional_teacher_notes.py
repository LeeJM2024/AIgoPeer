"""Optional teacher notes must pass API validation and PostgreSQL constraints."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


@pytest.mark.parametrize("extra", [{}, {"reason": ""}, {"reason": "   "}, {"reason": "好"}])
def test_teacher_reasons_are_optional(extra):
    from app.schemas.teacher import TeacherFinalReviewInput, TeacherGradeCorrectionInput

    expected = extra.get("reason", "").strip()
    assert TeacherFinalReviewInput(final_score=0, **extra).reason == expected
    assert TeacherGradeCorrectionInput(
        expected_version=1, rubric_scores=[{"rubric_item_id": 1, "score": 80}], **extra
    ).reason == expected


def test_initial_grade_and_correction_without_comments(grading_course):
    c = grading_course
    client, sid = c["client"], c["submissions"][0]
    scores = [{"rubric_item_id": c["rubric"], "score": 80}]
    response = client.post(f"/api/teacher/submissions/{sid}/grades", json={"rubric_scores": scores})
    assert response.status_code == 201, response.text
    gid = response.json()["data"]["teacher_grade_id"]
    correction = {"rubric_scores": scores, "expected_version": 1}
    # A reason being optional does not bypass the previous-version lock.
    assert client.post(f"/api/teacher/submissions/{sid}/grade-corrections", json=correction).status_code == 409
    assert client.post(f"/api/teacher/grades/{gid}/lock").status_code == 200
    response = client.post(f"/api/teacher/submissions/{sid}/grade-corrections", json=correction)
    assert response.status_code == 201, response.text
    new_id = response.json()["data"]["teacher_grade_id"]
    assert client.post(f"/api/teacher/grades/{new_id}/lock").status_code == 200
    with c["engine"].connect() as conn:
        row = conn.execute(text("SELECT version,correction_reason,feedback FROM teacher_grades WHERE id=:id"), {"id": new_id}).one()
        assert row.version == 2 and row.correction_reason == "" and row.feedback == ""
    # Database still rejects a skipped correction version.
    with pytest.raises(DBAPIError), c["engine"].begin() as conn:
        conn.execute(text("""INSERT INTO teacher_grades(submission_id,rubric_scores_json,total_score,version,entered_by)
            VALUES(:s,'{}',80,4,:t)"""), {"s": sid, "t": c["teacher"]})


@pytest.mark.parametrize("level,status,note", [
    ("LOW", "DISMISSED", {}),
    ("LOW", "CONFIRMED", {"note": ""}),
    ("MEDIUM", "DISMISSED", {"note": "   "}),
    ("MEDIUM", "CONFIRMED", {"note": "好"}),
])
def test_risk_resolution_with_optional_note(grading_course, level, status, note):
    c = grading_course
    with c["engine"].begin() as conn:
        aid = conn.execute(text("""INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json)
            SELECT :s,id,:level,0.5,'{}' FROM algorithm_runs ORDER BY id DESC LIMIT 1 RETURNING id"""), {"s": c["submissions"][0], "level": level}).scalar_one()
    response = c["client"].post(f"/api/teacher/anomalies/{aid}/resolve", json={"status": status, **note})
    assert response.status_code == 200, response.text
    with c["engine"].connect() as conn:
        row = conn.execute(text("SELECT status,resolution_note,resolved_by FROM anomaly_records WHERE id=:id"), {"id": aid}).one()
        assert row.status == status and row.resolution_note == note.get("note", "").strip()
        assert row.resolved_by == c["teacher"]


@pytest.mark.parametrize("reason", [{}, {"reason": ""}, {"reason": "好"}])
def test_high_risk_final_score_with_optional_reason(grading_course, reason):
    c = grading_course
    client, sid = c["client"], c["submissions"][0]
    response = client.post(f"/api/teacher/submissions/{sid}/grades", json={"rubric_scores": [{"rubric_item_id": c["rubric"], "score": 80}]})
    assert response.status_code == 201, response.text
    assert client.post(f"/api/teacher/grades/{response.json()['data']['teacher_grade_id']}/lock").status_code == 200
    with c["engine"].begin() as conn:
        conn.execute(text("""INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json)
            SELECT :s,algorithm_run_id,'HIGH',90,'{}' FROM designated_review_aggregates WHERE submission_id=:s"""), {"s": sid})
        conn.execute(text("UPDATE submissions SET final_review_status='ESCALATED_FOR_TEACHER_FINAL_REVIEW' WHERE id=:id"), {"id": sid})
    response = client.post(f"/api/teacher/submissions/{sid}/final-review", json={"final_score": 0, **reason})
    assert response.status_code == 201, response.text
    evidence = client.get(f"/api/teacher/submissions/{sid}/evidence").json()["data"]
    assert evidence["final_review"]["reason"] == reason.get("reason", "")
    assert float(evidence["final_review"]["final_score"]) == 0
