"""Retire duration/comment risk signals in unpublished review evidence."""

import json

from sqlalchemy import text

from alembic import op

revision = "20261029_0015"
down_revision = "20261028_0014"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # Publication freezes its inputs. This policy update changes risk evidence
    # only for unfinished assignments, including those with locked final reviews.
    rows = connection.execute(text("""
        SELECT ar.*, run.parameters_json FROM anomaly_records ar
        JOIN algorithm_runs run ON run.id=ar.algorithm_run_id
        JOIN submissions s ON s.id=ar.submission_id
        JOIN assignments a ON a.id=s.assignment_id
        WHERE a.status<>'PUBLISHED_RESULT'
          AND run.algorithm_name='panel_bayesian_robust'
          AND (ar.evidence_json->'rules_triggered') ?| ARRAY['SHORT_DURATION','SHORT_COMMENT']
        ORDER BY a.id,ar.id FOR UPDATE OF a,ar
    """)).mappings().all()
    for row in rows:
        before = {key: row[key] for key in (
            "risk_level", "risk_score", "evidence_json", "status", "resolution_note",
            "resolved_by", "resolved_at",
        )}
        evidence = dict(row["evidence_json"])
        rules = [rule for rule in evidence["rules_triggered"]
                 if rule not in {"SHORT_DURATION", "SHORT_COMMENT"}]
        parameters = row["parameters_json"]
        posterior = max((float(item.get("posterior_anomaly_probability", 0))
                         for item in evidence.get("rubric_evidence", [])), default=0)
        score = round(100 * min(1,
            float(parameters.get("hard_outlier_weight", .45)) * ("FOUR_VS_ONE_OUTLIER" in rules)
            + float(parameters.get("posterior_weight", .35)) * posterior
            + float(parameters.get("low_entropy_weight", .05)) * ("LOW_SCORE_DIVERSITY" in rules)
        ), 4)
        relationship = evidence.get("relationship_evidence") or {}
        score = max(score, float(relationship.get("risk_score", 0)))
        if row["risk_level"] == "HIGH":
            level = "HIGH"  # The retired signals never triggered HIGH.
        elif score >= float(parameters.get("medium_risk_threshold", 50)) or relationship.get("risk_level") == "MEDIUM":
            level = "MEDIUM"
        else:
            level = "LOW"
        evidence.update(rules_triggered=rules, risk_level=level, risk_score=score,
                        risk_policy="score_and_relationship_v2", risk_policy_retired=not rules)
        status = row["status"]
        note = row["resolution_note"]
        if not rules and status == "OPEN":
            status = "DISMISSED"
            note = "复核规则调整：评阅用时与评语字数不再作为风险依据，系统取消此待处理项。"
        connection.execute(text("""
            UPDATE anomaly_records SET risk_level=:level,risk_score=:score,
                evidence_json=CAST(:evidence AS jsonb),status=CAST(:status AS text),resolution_note=:note,
                resolved_at=CASE WHEN status='OPEN' AND CAST(:status AS text)='DISMISSED' THEN now() ELSE resolved_at END
            WHERE id=:id
        """), {"id": row["id"], "level": level, "score": score,
               "evidence": json.dumps(evidence, ensure_ascii=False), "status": status, "note": note})
        connection.execute(text("""
            INSERT INTO audit_logs(action,entity_type,entity_id,before_json,after_json)
            VALUES ('RETIRE_SHORT_REVIEW_SIGNALS','anomaly_record',:id,
                    CAST(:before AS jsonb),CAST(:after AS jsonb))
        """), {"id": row["id"], "before": json.dumps(before, default=str, ensure_ascii=False),
               "after": json.dumps({"risk_level": level, "risk_score": score,
                                    "rules_triggered": rules, "status": status}, ensure_ascii=False)})


def downgrade():
    # The old evidence is retained in audit_logs. Reverting application code
    # must not reopen cases or erase teacher decisions made after this change.
    pass
