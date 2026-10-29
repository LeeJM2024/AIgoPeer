"""Versioned aggregation and publication checks in isolated PostgreSQL schemas."""

import json

import pytest
from app.services import designated_review_service as service
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_teacher_delivery import reviewed_course
from test_teacher_integration import save_and_lock

from algorithm.algorithms.aggregation import ALGORITHM_VERSION, DEFAULT_PARAMETERS


def aggregate_all(c):
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert response.status_code == 200, response.text
    panels = response.json()["data"]["panels"]
    assert all(p["status"] == "COMPLETED" for p in panels), panels
    return panels


def test_unanimous_small_panels_persist_prior_and_publish_normal_blend(course):
    c = reviewed_course(course)
    with c["engine"].begin() as conn:
        conn.execute(text("UPDATE review_scores SET score=85"))
    panels = aggregate_all(c)
    with c["engine"].connect() as conn:
        runs = (
            conn.execute(
                text("SELECT * FROM algorithm_runs WHERE algorithm_name=:name"),
                {"name": service.ALGORITHM_NAME},
            )
            .mappings()
            .all()
        )
        assert len(runs) == 2
        for run in runs:
            assert run["version"] == ALGORITHM_VERSION == "1.0.1"
            assert run["parameters_json"] == service._run_parameters()
            assert all(
                run["parameters_json"][key] == value
                for key, value in DEFAULT_PARAMETERS.items()
            )
        profiles = (
            conn.execute(text("SELECT * FROM reviewer_profiles")).mappings().all()
        )
        assert len(profiles) == 10
        assert all(p["bias_json"] == {"bias": 0.0, "sigma": 0.12} for p in profiles)
        assert all(
            float(p["lazy_probability"]) == pytest.approx(1 / 21, abs=1e-4)
            for p in profiles
        )
        aggregates = (
            conn.execute(text("SELECT * FROM designated_review_aggregates"))
            .mappings()
            .all()
        )
        assert len(aggregates) == 2
        for item in aggregates:
            assert float(item["total_score"]) == 85
            assert item["confidence_json"]["fallback_reason"] == "PANEL_TOO_SMALL"
            assert item["confidence_json"]["uncertainty_evidence"] == {
                "interval_kind": "uncalibrated_model_around_median",
                "fallback_reason": "PANEL_TOO_SMALL",
                "posterior_available": False,
                "wide_interval_exempt": True,
            }
        assert (
            conn.execute(text("SELECT count(*) FROM anomaly_records")).scalar_one() == 0
        )
        assert set(
            conn.execute(text("SELECT final_review_status FROM submissions")).scalars()
        ) == {"NORMAL"}
    retry = aggregate_all(c)
    assert [p["algorithm_run_id"] for p in retry] == [
        p["algorithm_run_id"] for p in panels
    ]
    assert all(p["reused"] for p in retry)
    for sid in c["submissions"]:
        save_and_lock(c, sid, 90)
    published = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert published.status_code == 200, published.text
    with c["engine"].connect() as conn:
        grades = conn.execute(text("SELECT * FROM final_grades")).mappings().all()
        assert len(grades) == 2
        assert all(float(g["final_score"]) == 88 for g in grades)
        assert all(
            g["final_grade_source"] == "NORMAL_BLEND"
            and g["teacher_final_review_id"] is None
            for g in grades
        )
        before = [dict(g) for g in grades]
    blocked = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert blocked.status_code == 409
    with c["engine"].connect() as conn:
        assert [
            dict(g) for g in conn.execute(text("SELECT * FROM final_grades")).mappings()
        ] == before


def test_old_version_recomputes_archives_only_superseded_cases_and_preserves_history(
    course,
):
    c = reviewed_course(course)
    first = aggregate_all(c)
    old_run = first[0]["algorithm_run_id"]
    sid = c["submissions"][0]
    with c["engine"].begin() as conn:
        # Reconstruct a historical 1.0.0 result, including its wide-interval case.
        conn.execute(
            text(
                "UPDATE algorithm_runs SET version='1.0.0',parameters_json='{}' WHERE id=:id"
            ),
            {"id": old_run},
        )
        task = conn.execute(
            text("SELECT id FROM review_tasks WHERE submission_id=:sid LIMIT 1"),
            {"sid": sid},
        ).scalar_one()
        anomaly = conn.execute(
            text("""INSERT INTO anomaly_records(submission_id,review_task_id,algorithm_run_id,risk_level,risk_score,evidence_json)
            VALUES (:sid,:task,:run,'HIGH',0,CAST(:evidence AS jsonb)) RETURNING id"""),
            {
                "sid": sid,
                "task": task,
                "run": old_run,
                "evidence": json.dumps({"rules_triggered": ["WIDE_CREDIBLE_INTERVAL"]}),
            },
        ).scalar_one()
        conn.execute(
            text(
                "UPDATE submissions SET final_review_status='ESCALATED_FOR_TEACHER_FINAL_REVIEW' WHERE id=:sid"
            ),
            {"sid": sid},
        )
        old_snapshot = dict(
            conn.execute(
                text("SELECT * FROM algorithm_runs WHERE id=:id"), {"id": old_run}
            )
            .mappings()
            .one()
        )
        old_aggregate = dict(
            conn.execute(
                text(
                    "SELECT * FROM designated_review_aggregates WHERE algorithm_run_id=:id"
                ),
                {"id": old_run},
            )
            .mappings()
            .one()
        )
    second = aggregate_all(c)
    new_run = second[0]["algorithm_run_id"]
    assert new_run != old_run
    assert second[1]["reused"] is True
    with c["engine"].connect() as conn:
        assert (
            dict(
                conn.execute(
                    text("SELECT * FROM algorithm_runs WHERE id=:id"), {"id": old_run}
                )
                .mappings()
                .one()
            )
            == old_snapshot
        )
        assert (
            dict(
                conn.execute(
                    text(
                        "SELECT * FROM designated_review_aggregates WHERE algorithm_run_id=:id"
                    ),
                    {"id": old_run},
                )
                .mappings()
                .one()
            )
            == old_aggregate
        )
        finding = (
            conn.execute(
                text("SELECT * FROM anomaly_records WHERE id=:id"), {"id": anomaly}
            )
            .mappings()
            .one()
        )
        assert finding["status"] == "DISMISSED"
        assert finding["evidence_json"] == {
            "rules_triggered": ["WIDE_CREDIBLE_INTERVAL"]
        }
        assert finding["resolved_by"] is None
        assert str(new_run) in finding["resolution_note"]
        assert (
            conn.execute(
                text("SELECT final_review_status FROM submissions WHERE id=:id"),
                {"id": sid},
            ).scalar_one()
            == "NORMAL"
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM anomaly_records WHERE status='OPEN'")
            ).scalar_one()
            == 0
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE action='SUPERSEDE_ALGORITHM_FINDINGS'"
                )
            ).scalar_one()
            == 1
        )
    for submission in c["submissions"]:
        save_and_lock(c, submission)
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert response.status_code == 200, response.text


def test_different_parameters_do_not_reuse_run_even_at_same_version(course):
    c = reviewed_course(course)
    first = aggregate_all(c)
    with c["engine"].begin() as conn:
        conn.execute(
            text(
                "UPDATE algorithm_runs SET parameters_json=jsonb_set(parameters_json,'{min_completed_works}','4') WHERE id=:id"
            ),
            {"id": first[0]["algorithm_run_id"]},
        )
    second = aggregate_all(c)
    assert second[0]["algorithm_run_id"] != first[0]["algorithm_run_id"]
    assert second[1]["reused"] is True


def test_different_snapshot_does_not_silently_close_historical_high_case(course):
    c = reviewed_course(course)
    first = aggregate_all(c)
    old_run = first[0]["algorithm_run_id"]
    sid = c["submissions"][0]
    with c["engine"].begin() as conn:
        conn.execute(
            text(
                "UPDATE algorithm_runs SET version='1.0.0',input_hash='different-snapshot' WHERE id=:id"
            ),
            {"id": old_run},
        )
        finding = conn.execute(
            text("""INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json)
            VALUES (:sid,:run,'HIGH',45,'{"rules_triggered":["FOUR_VS_ONE_OUTLIER"]}') RETURNING id"""),
            {"sid": sid, "run": old_run},
        ).scalar_one()
        conn.execute(
            text(
                "UPDATE submissions SET final_review_status='ESCALATED_FOR_TEACHER_FINAL_REVIEW' WHERE id=:sid"
            ),
            {"sid": sid},
        )
    aggregate_all(c)
    with c["engine"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT status FROM anomaly_records WHERE id=:id"), {"id": finding}
            ).scalar_one()
            == "OPEN"
        )
        assert (
            conn.execute(
                text("SELECT final_review_status FROM submissions WHERE id=:id"),
                {"id": sid},
            ).scalar_one()
            == "ESCALATED_FOR_TEACHER_FINAL_REVIEW"
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs WHERE action='SUPERSEDE_ALGORITHM_FINDINGS'"
                )
            ).scalar_one()
            == 0
        )


def test_new_version_redetects_real_outlier_after_archiving_old_run(course):
    c = reviewed_course(course, high=True)
    first = aggregate_all(c)
    old_run = first[0]["algorithm_run_id"]
    with c["engine"].begin() as conn:
        conn.execute(
            text("UPDATE algorithm_runs SET version='1.0.0' WHERE id=:id"),
            {"id": old_run},
        )
    second = aggregate_all(c)
    new_run = second[0]["algorithm_run_id"]
    assert new_run != old_run
    with c["engine"].connect() as conn:
        assert set(
            conn.execute(
                text("SELECT status FROM anomaly_records WHERE algorithm_run_id=:id"),
                {"id": old_run},
            ).scalars()
        ) == {"DISMISSED"}
        findings = (
            conn.execute(
                text(
                    "SELECT evidence_json FROM anomaly_records WHERE algorithm_run_id=:id AND risk_level='HIGH' AND status='OPEN'"
                ),
                {"id": new_run},
            )
            .scalars()
            .all()
        )
        assert any(
            "FOUR_VS_ONE_OUTLIER" in finding["rules_triggered"] for finding in findings
        )
        assert (
            conn.execute(
                text("SELECT final_review_status FROM submissions WHERE id=:id"),
                {"id": c["submissions"][0]},
            ).scalar_one()
            == "ESCALATED_FOR_TEACHER_FINAL_REVIEW"
        )


def test_failed_em_does_not_persist_partial_profiles_scores_or_findings(
    course, monkeypatch
):
    c = reviewed_course(course)
    real_aggregate = service.aggregate_panel_scores

    def not_converged(request):
        result = real_aggregate(request)
        return result.model_copy(update={"fallback_reason": "MODEL_NOT_CONVERGED"})

    monkeypatch.setattr(service, "aggregate_panel_scores", not_converged)
    response = c["client"].post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert response.status_code == 200, response.text
    assert all(p["status"] == "FAILED" for p in response.json()["data"]["panels"])
    with c["engine"].connect() as conn:
        for table in (
            "reviewer_profiles",
            "designated_review_aggregates",
            "anomaly_records",
        ):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM algorithm_runs WHERE algorithm_name=:name AND status='FAILED'"
                ),
                {"name": service.ALGORITHM_NAME},
            ).scalar_one()
            == 2
        )
    monkeypatch.setattr(service, "aggregate_panel_scores", real_aggregate)
    aggregate_all(c)


def test_real_outlier_still_requires_final_review_and_locked_review_blocks_new_version(
    course,
):
    c = reviewed_course(course, high=True)
    panels = aggregate_all(c)
    sid = c["submissions"][0]
    with c["engine"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT final_review_status FROM submissions WHERE id=:id"),
                {"id": sid},
            ).scalar_one()
            == "ESCALATED_FOR_TEACHER_FINAL_REVIEW"
        )
        findings = (
            conn.execute(
                text(
                    "SELECT evidence_json FROM anomaly_records WHERE submission_id=:id AND risk_level='HIGH'"
                ),
                {"id": sid},
            )
            .scalars()
            .all()
        )
        assert any("FOUR_VS_ONE_OUTLIER" in f["rules_triggered"] for f in findings)
    for submission in c["submissions"]:
        save_and_lock(c, submission)
    assert (
        c["client"]
        .post(f"/api/teacher/assignments/{c['id']}/publish-results")
        .status_code
        == 424
    )
    response = c["client"].post(
        f"/api/teacher/submissions/{sid}/final-review",
        json={"final_score": 87, "reason": "核验四对一极端评分后的最终分"},
    )
    assert response.status_code == 201, response.text
    with c["engine"].begin() as conn:
        conn.execute(
            text("UPDATE algorithm_runs SET version='1.0.0' WHERE id=:id"),
            {"id": panels[0]["algorithm_run_id"]},
        )
        before = dict(
            conn.execute(
                text("SELECT * FROM teacher_final_reviews WHERE submission_id=:id"),
                {"id": sid},
            )
            .mappings()
            .one()
        )
    with Session(c["engine"]) as db, pytest.raises(HTTPException) as caught:
        service.aggregate_panel_and_persist(db, c["id"], c["panel_ids"][0])
    assert caught.value.detail == "FINAL_REVIEW_PREVENTS_REAGGREGATION"
    with c["engine"].connect() as conn:
        assert (
            dict(
                conn.execute(
                    text("SELECT * FROM teacher_final_reviews WHERE submission_id=:id"),
                    {"id": sid},
                )
                .mappings()
                .one()
            )
            == before
        )
    published = c["client"].post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert published.status_code == 200, published.text
    with c["engine"].connect() as conn:
        grade = (
            conn.execute(
                text("SELECT * FROM final_grades WHERE submission_id=:sid"),
                {"sid": sid},
            )
            .mappings()
            .one()
        )
        assert float(grade["final_score"]) == 87
        assert grade["final_grade_source"] == "TEACHER_FINAL_REVIEW"
