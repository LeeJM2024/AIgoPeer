"""Snapshot and persist calibrated historical reviewer-author residuals."""

from dataclasses import asdict
from statistics import mean

from algorithm.algorithms.relationships import RelationshipObservation, detect_relationships
from sqlalchemy import text


def relationship_history(db, assignment_id):
    rows = db.execute(
        text("""WITH recent AS (
        SELECT a.id FROM assignments a JOIN assignments current ON current.id=:a
        WHERE a.deleted_at IS NULL AND (a.created_at,a.id)<(current.created_at,current.id) AND EXISTS(
          SELECT 1 FROM assignment_classes ac JOIN assignment_classes cc ON cc.class_id=ac.class_id
          WHERE ac.assignment_id=a.id AND cc.assignment_id=current.id)
        ORDER BY a.created_at DESC,a.id DESC LIMIT 20
      ), latest AS (
        SELECT DISTINCT ON (ar.assignment_id,ar.panel_id) ar.id
        FROM algorithm_runs ar JOIN recent ON recent.id=ar.assignment_id
        WHERE ar.status='COMPLETED' AND ar.algorithm_name='panel_bayesian_robust'
        ORDER BY ar.assignment_id,ar.panel_id,ar.finished_at DESC,ar.id DESC)
      SELECT o.assignment_id,o.reviewer_id,o.author_id,o.task_id,o.residual,o.algorithm_run_id
      FROM review_relationship_observations o JOIN latest ON latest.id=o.algorithm_run_id
      ORDER BY o.assignment_id,o.task_id"""),
        {"a": assignment_id},
    ).mappings()
    return [RelationshipObservation(**dict(row)) for row in rows]


def apply_relationship_evidence(db, assignment_id, run_id, result, history):
    authors = dict(
        db.execute(
            text("SELECT id,author_id FROM submissions WHERE assignment_id=:a"),
            {"a": assignment_id},
        ).all()
    )
    profiles = {p.reviewer_id: p for p in result.reviewer_profiles}
    aggregates = {item.submission_id: item for item in result.results}
    current = []
    for finding in result.anomalies:
        if not finding.evidence["uncertainty_evidence"]["posterior_available"]:
            continue
        profile = profiles[finding.reviewer_id]
        rows = finding.evidence["rubric_evidence"]
        residual = mean(
            (
                r["reviewer_score"] / r["max_score"]
                - profile.bias
                - r["bayesian_score"] / r["max_score"]
            )
            / max(profile.sigma, 0.05)
            for r in rows
        )
        observation = RelationshipObservation(
            assignment_id,
            finding.reviewer_id,
            authors[finding.submission_id],
            finding.review_task_id,
            residual,
            run_id,
        )
        current.append(observation)
        db.execute(
            text("""INSERT INTO review_relationship_observations
          (assignment_id,algorithm_run_id,task_id,reviewer_id,author_id,residual)
          VALUES(:assignment_id,:algorithm_run_id,:task_id,:reviewer_id,:author_id,:residual)"""),
            asdict(observation),
        )
    evidence = detect_relationships(current, history)
    ranks = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    for finding in result.anomalies:
        relationship = evidence.get(finding.review_task_id)
        if relationship is None:
            continue
        finding.evidence["relationship_evidence"] = relationship
        finding.evidence["rules_triggered"].extend(relationship["rules_triggered"])
        finding.risk_score = max(finding.risk_score, relationship["risk_score"])
        if ranks[relationship["risk_level"]] > ranks[finding.risk_level]:
            finding.risk_level = relationship["risk_level"]
        finding.evidence.update(risk_level=finding.risk_level, risk_score=finding.risk_score)
        if finding.risk_level == "HIGH":
            aggregates[finding.submission_id].risk_level = "HIGH"
