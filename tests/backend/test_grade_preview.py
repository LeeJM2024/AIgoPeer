"""Grade previews follow current versions and never publish results."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.services.teacher_grade_service import grade_score_preview
from sqlalchemy import text


def preview_row(**changes):
    now = datetime.now(UTC)
    return {
        "status": "VALID",
        "material_status": "VALID",
        "teacher_score": Decimal("96.98"),
        "aggregate_score": Decimal("92.89"),
        "locked_at": now,
        "aggregate_created_at": now,
        "last_review_at": now - timedelta(seconds=1),
        "task_count": 5,
        "completed_tasks": 5,
        "final_review_status": "NORMAL",
        "final_review_score": None,
        "final_score": None,
        **changes,
    }


@pytest.mark.parametrize(
    "teacher,review,tw,rw,expected",
    [
        ("96.98", "92.89", "0.6", "0.4", "95.34"),
        ("0", "0", "0.6", "0.4", "0.00"),
        ("90", "80", "0.7", "0.3", "87.00"),
        ("90.01", "90", "0.5", "0.5", "90.01"),
    ],
)
def test_preview_uses_exact_weights_and_half_up_rounding(
    teacher, review, tw, rw, expected
):
    result = grade_score_preview(
        {"teacher_weight": Decimal(tw), "designated_review_weight": Decimal(rw)},
        preview_row(teacher_score=Decimal(teacher), aggregate_score=Decimal(review)),
    )
    assert result == {
        "score_preview": Decimal(expected),
        "score_preview_state": "WEIGHTED",
    }


@pytest.mark.parametrize(
    "changes,state,expected",
    [
        ({"locked_at": None}, "TEACHER_GRADE_UNLOCKED", "95.34"),
        ({"teacher_score": None}, "TEACHER_GRADE_REQUIRED", None),
        ({"completed_tasks": 4}, "REVIEWS_INCOMPLETE", None),
        ({"task_count": 4}, "REVIEWS_INCOMPLETE", None),
        ({"aggregate_score": None}, "AGGREGATE_NOT_READY", None),
        ({"material_status": "INVALID"}, "MATERIAL_NOT_VALID", None),
        (
            {"final_review_status": "ESCALATED_FOR_TEACHER_FINAL_REVIEW"},
            "FINAL_REVIEW_REQUIRED",
            None,
        ),
        ({"final_review_status": "FINAL_REVIEW_LOCKED"}, "FINAL_REVIEW_REQUIRED", None),
        (
            {
                "final_review_status": "FINAL_REVIEW_LOCKED",
                "final_review_score": Decimal(88),
            },
            "FINAL_REVIEW_LOCKED",
            "88",
        ),
        ({"final_score": Decimal(85), "teacher_score": None}, "PUBLISHED", "85"),
    ],
)
def test_preview_respects_review_and_publication_state(changes, state, expected):
    result = grade_score_preview(
        {"teacher_weight": Decimal("0.6"), "designated_review_weight": Decimal("0.4")},
        preview_row(**changes),
    )
    assert result["score_preview_state"] == state
    assert result["score_preview"] == (None if expected is None else Decimal(expected))


def test_workspace_uses_correction_then_lock_without_publishing(grading_course):
    from test_teacher_integration import save_and_lock

    c = grading_course
    sid = c["submissions"][0]
    url = f"/api/teacher/assignments/{c['id']}/grading"

    def current():
        response = c["client"].get(url)
        assert response.status_code == 200, response.text
        return next(
            row for row in response.json()["data"]["submissions"] if row["id"] == sid
        )

    assert current()["score_preview_state"] == "TEACHER_GRADE_REQUIRED"
    save_and_lock(c, sid, 90)
    assert Decimal(str(current()["score_preview"])) == Decimal(86)
    response = c["client"].post(
        f"/api/teacher/submissions/{sid}/grade-corrections",
        json={
            "rubric_scores": [{"rubric_item_id": c["rubric"], "score": 95}],
            "expected_version": 1,
            "reason": "核对后更正教师分",
        },
    )
    assert response.status_code == 201, response.text
    row = current()
    assert row["teacher_grade_version"] == 2
    assert row["score_preview_state"] == "TEACHER_GRADE_UNLOCKED"
    assert Decimal(str(row["score_preview"])) == Decimal(89)
    gid = response.json()["data"]["teacher_grade_id"]
    assert c["client"].post(f"/api/teacher/grades/{gid}/lock").status_code == 200
    assert current()["score_preview_state"] == "WEIGHTED"
    with c["engine"].begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM final_grades")).scalar_one() == 0
        # An aggregate predating the submitted reviews must not produce a total.
        conn.execute(
            text(
                "UPDATE designated_review_aggregates SET created_at=now()-interval '1 day' WHERE submission_id=:s"
            ),
            {"s": sid},
        )
    assert current()["score_preview"] is None
    assert current()["score_preview_state"] == "AGGREGATE_STALE"


def test_workspace_counts_reviews_once_when_multiple_anomalies_exist(grading_course):
    c = grading_course
    sid = c["submissions"][0]
    with c["engine"].begin() as conn:
        conn.execute(
            text("""
                INSERT INTO anomaly_records(
                    submission_id, algorithm_run_id, risk_level, risk_score, evidence_json, status
                )
                SELECT ag.submission_id, ag.algorithm_run_id, 'MEDIUM', .5, '{}', statuses.status
                FROM designated_review_aggregates ag
                CROSS JOIN (VALUES ('OPEN'), ('OPEN'), ('DISMISSED')) AS statuses(status)
                WHERE ag.submission_id = :s
            """),
            {"s": sid},
        )
    response = c["client"].get(f"/api/teacher/assignments/{c['id']}/grading")
    assert response.status_code == 200, response.text
    rows = response.json()["data"]["submissions"]
    assert len(rows) == len(c["submissions"])
    for row in rows:
        assert row["task_count"] == 5
        assert row["completed_tasks"] == 5
        assert row["open_anomaly_count"] == (2 if row["id"] == sid else 0)
        assert row["last_review_at"] <= row["aggregate_created_at"]
