"""Risk policy migration preserves scores and removes obsolete review work."""

import importlib.util
import json
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from test_profile_fallback_persistence import aggregate_all
from test_teacher_delivery import reviewed_course
from test_teacher_integration import save_and_lock


def test_migration_reclassifies_history_without_reaggregating_locked_scores(course):
    c = reviewed_course(course, high=True)
    aggregate_all(c)
    sid = c["submissions"][0]
    save_and_lock(c, sid)
    response = c["client"].post(f"/api/teacher/submissions/{sid}/final-review",
                              json={"final_score": 81, "reason": "核对材料后给出最终分"})
    assert response.status_code == 201, response.text
    path = Path(__file__).resolve().parents[2] / "backend/alembic/versions/20261029_0015_retire_short_review_signals.py"
    spec = importlib.util.spec_from_file_location("retire_signals", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    tables = ("teacher_grades", "teacher_final_reviews", "designated_review_aggregates",
              "algorithm_runs", "reviewer_profiles", "submissions")
    with c["engine"].begin() as conn:
        original = {table: conn.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()
                    for table in tables}
        high = conn.execute(text("SELECT * FROM anomaly_records WHERE risk_level='HIGH' LIMIT 1")).mappings().one()
        for extra in ([], ["LOW_SCORE_DIVERSITY"]):
            conn.execute(text("""INSERT INTO anomaly_records(submission_id,review_task_id,algorithm_run_id,
                risk_level,risk_score,evidence_json) VALUES (:sid,:task,:run,'MEDIUM',:score,CAST(:evidence AS jsonb))"""),
                {"sid": sid, "task": high["review_task_id"], "run": high["algorithm_run_id"],
                 "score": 20 if extra else 15,
                 "evidence": json.dumps({"rules_triggered": ["SHORT_DURATION", "SHORT_COMMENT", *extra],
                                         "rubric_evidence": [], "behavior_evidence": {"duration_seconds": 1, "comment_char_count": 1}})})
        high_evidence = {**high["evidence_json"], "rules_triggered": [*high["evidence_json"]["rules_triggered"], "SHORT_DURATION", "SHORT_COMMENT"]}
        conn.execute(text("UPDATE anomaly_records SET evidence_json=CAST(:e AS jsonb) WHERE id=:id"),
                     {"e": json.dumps(high_evidence), "id": high["id"]})
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        migration.upgrade()  # Policy application is idempotent.
        assert {table: conn.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()
                for table in tables} == original
        changed = conn.execute(text("SELECT * FROM anomaly_records WHERE evidence_json->>'risk_policy'='score_and_relationship_v2' ORDER BY id")).mappings().all()
        assert len(changed) == 3
        assert changed[0]["risk_level"] == "HIGH"
        assert changed[0]["status"] == high["status"]
        assert changed[1]["risk_level"] == "LOW" and changed[1]["risk_score"] == 0
        assert changed[1]["status"] == "DISMISSED"
        assert changed[1]["evidence_json"]["risk_policy_retired"] is True
        assert changed[2]["risk_level"] == "LOW" and changed[2]["risk_score"] == 5
        assert changed[2]["status"] == "OPEN"
        assert changed[2]["evidence_json"]["rules_triggered"] == ["LOW_SCORE_DIVERSITY"]
        assert conn.execute(text("SELECT count(*) FROM audit_logs WHERE action='RETIRE_SHORT_REVIEW_SIGNALS'")).scalar_one() == 3
        retired_id = changed[1]["id"]
    findings = c["client"].get(f"/api/teacher/assignments/{c['id']}/anomalies").json()["data"]
    assert all(item["id"] != retired_id for item in findings)
    assert all(not {"SHORT_DURATION", "SHORT_COMMENT"}.intersection(item["evidence_json"]["rules_triggered"])
               for item in findings)
    evidence = c["client"].get(f"/api/teacher/submissions/{sid}/evidence").json()["data"]
    assert all(item["evidence_json"].get("risk_policy_retired") is not True for item in evidence["anomalies"])
