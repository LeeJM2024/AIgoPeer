"""Transactional snapshots, joint cross-class allocation and teacher-triggered replacement."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime

from algorithm.algorithms.allocation import (
    ALLOCATION_NAME,
    ALLOCATION_VERSION,
    AllocationError,
    Edge,
    Work,
    allocate_reviews,
)
from algorithm.algorithms.incremental_allocation import (
    INCREMENTAL_VERSION,
    allocate_additional_reviews,
)
from fastapi import HTTPException
from sqlalchemy import text

from app.services.teacher_workflow import audit


def ensure_random_panels(db, assignment_id):
    kind = db.execute(text("SELECT type FROM assignments WHERE id=:id"),
                      {"id": assignment_id}).scalar_one_or_none()
    if kind != "FINAL_PROJECT":
        raise HTTPException(400, "REVIEWED_ASSIGNMENT_REQUIRED")
    classes = list(
        db.execute(
            text(
                "SELECT class_id FROM assignment_classes WHERE assignment_id=:a ORDER BY class_id"
            ),
            {"a": assignment_id},
        ).scalars()
    )
    if len(classes) != 2:
        raise HTTPException(422, "TWO_VALID_CLASSES_REQUIRED")
    for target, reviewer in (classes, classes[::-1]):
        db.execute(
            text("""INSERT INTO review_panels(assignment_id,target_class_id,reviewer_class_id)
          VALUES(:a,:t,:r) ON CONFLICT DO NOTHING"""),
            {"a": assignment_id, "t": target, "r": reviewer},
        )


def allocation_snapshot(db, assignment):
    if assignment["type"] != "FINAL_PROJECT":
        raise HTTPException(400, "REVIEWED_ASSIGNMENT_REQUIRED")
    aid = assignment["id"]
    classes = [
        dict(r)
        for r in db.execute(
            text("""SELECT c.id,c.name FROM classes c
      JOIN assignment_classes ac ON ac.class_id=c.id WHERE ac.assignment_id=:a ORDER BY c.id FOR SHARE OF c"""),
            {"a": aid},
        ).mappings()
    ]
    rows = [
        dict(r)
        for r in db.execute(
            text("""SELECT s.id,s.author_id,s.class_id,s.anonymous_token,
      u.name,u.student_no,mc.status AS material_status,
      EXISTS(SELECT 1 FROM submission_files WHERE submission_id=s.id AND file_kind='ZIP') AS has_zip,
      pkg.status AS package_status,
      EXISTS(SELECT 1 FROM enrollments WHERE user_id=s.author_id AND class_id=s.class_id) AS enrolled,
      (SELECT count(*) FROM enrollments e JOIN assignment_classes ac ON ac.class_id=e.class_id
        WHERE e.user_id=s.author_id AND ac.assignment_id=s.assignment_id) AS class_count
      FROM submissions s JOIN users u ON u.id=s.author_id
      LEFT JOIN material_checks mc ON mc.submission_id=s.id
      LEFT JOIN review_material_packages pkg ON pkg.submission_id=s.id
      WHERE s.assignment_id=:a AND s.is_current AND s.status='VALID' AND u.system_role='STUDENT'
      ORDER BY s.id"""),
            {"a": aid},
        ).mappings()
    ]
    pending = db.execute(
        text("""SELECT count(*) FROM submissions s LEFT JOIN material_checks mc ON mc.submission_id=s.id
      WHERE s.assignment_id=:a AND s.is_current AND s.status<>'DRAFT' AND (mc.id IS NULL OR mc.status='PENDING')"""),
        {"a": aid},
    ).scalar_one()
    blockers = []
    if pending:
        blockers.append("MATERIAL_CHECKS_PENDING")
    valid = [r for r in rows if r["material_status"] == "VALID"]
    if any(r["has_zip"] and r["package_status"] != "READY" for r in valid):
        blockers.append("ANONYMOUS_MATERIAL_NOT_READY")
    if any(
        not r["enrolled"]
        or r["class_count"] != 1
        or r["class_id"] not in {c["id"] for c in classes}
        for r in valid
    ):
        blockers.append("REVIEWER_CLASS_CONFLICT")
    works = [Work(r["id"], r["author_id"], r["class_id"]) for r in valid]
    fixed = [
        Edge(r.reviewer_id, r.submission_id)
        for r in db.execute(
            text("""SELECT rt.reviewer_id,rt.submission_id FROM review_tasks rt
      JOIN submissions s ON s.id=rt.submission_id WHERE s.assignment_id=:a AND rt.is_active ORDER BY rt.id"""),
            {"a": aid},
        )
    ]
    assigned_ids = {edge.submission_id for edge in fixed}
    new_task_count = 5 * sum(w.submission_id not in assigned_ids for w in works)
    # Snapshot recent assignments in these same two classes, not unrelated courses.
    history_rows = list(
        db.execute(
            text("""WITH recent AS (
        SELECT a.id,dense_rank() OVER(ORDER BY a.created_at DESC,a.id DESC) AS age
        FROM assignments a JOIN assignments current ON current.id=:a
        WHERE a.deleted_at IS NULL AND (a.created_at,a.id)<(current.created_at,current.id) AND EXISTS(SELECT 1 FROM assignment_classes ac
          WHERE ac.assignment_id=a.id AND ac.class_id=ANY(:classes))
        ORDER BY a.created_at DESC,a.id DESC LIMIT 20)
      SELECT rt.reviewer_id,s.author_id,sum(21-recent.age)::int AS cost
      FROM review_tasks rt JOIN submissions s ON s.id=rt.submission_id
      JOIN recent ON recent.id=s.assignment_id WHERE rt.is_active
      GROUP BY rt.reviewer_id,s.author_id ORDER BY rt.reviewer_id,s.author_id"""),
            {"a": aid, "classes": [c["id"] for c in classes]},
        ).mappings()
    )
    history = {(r["reviewer_id"], r["author_id"]): r["cost"] for r in history_rows}
    directions = []
    sizes = {c["id"]: sum(w.class_id == c["id"] for w in works) for c in classes}
    if (
        len(classes) != 2
        or any(n < 5 for n in sizes.values())
        or 5 * len(works) > sizes[classes[0]["id"]] * sizes[classes[1]["id"]]
    ):
        blockers.append("ALLOCATION_INFEASIBLE")
    for cls in classes:
        other = next((c for c in classes if c["id"] != cls["id"]), None)
        count = sizes[cls["id"]]
        total = 5 * sizes.get(other["id"], 0) if other else 0
        directions.append(
            {
                "reviewer_class_id": cls["id"],
                "reviewer_class_name": cls["name"],
                "target_class_id": other["id"] if other else None,
                "target_class_name": other["name"] if other else "",
                "reviewer_count": count,
                "submission_count": total // 5,
                "task_count": total,
                "min_load": total // count if count else 0,
                "max_load": (total + count - 1) // count if count else 0,
                "participants": [
                    {"id": r["author_id"], "name": r["name"], "student_no": r["student_no"]}
                    for r in valid
                    if r["class_id"] == cls["id"]
                ],
            }
        )
    canonical = {
        "works": [asdict(w) for w in works],
        "history": [dict(r) for r in history_rows],
        "seed": assignment["review_seed"],
        "version": ALLOCATION_VERSION,
        "blockers": sorted(set(blockers)),
        "review_deadline": str(assignment["review_deadline"]),
        "existing_edges": [asdict(edge) for edge in fixed],
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    preview = {
        "snapshot_hash": digest,
        "seed": assignment["review_seed"],
        "directions": directions,
        "blockers": sorted(set(blockers)),
        "required_reviews": 5,
        "ready": not blockers,
        "total_tasks": 5 * len(works),
        "existing_task_count": len(fixed),
        "new_task_count": new_task_count,
    }
    return works, history, valid, preview


def _allocation_results(db, aid):
    return [
        dict(r)
        for r in db.execute(
            text("""SELECT p.id AS panel_id,
        max(rt.allocation_run_id) AS algorithm_run_id,count(rt.id) AS task_count
      FROM review_panels p LEFT JOIN review_tasks rt ON rt.panel_id=p.id AND rt.is_active
      WHERE p.assignment_id=:a GROUP BY p.id ORDER BY p.id"""),
            {"a": aid},
        ).mappings()
    ]


def initialize_random_tasks(db, assignment, actor, expected_hash=None):
    aid = assignment["id"]
    works, history, valid, preview = allocation_snapshot(db, assignment)
    existing = db.execute(
        text("""SELECT id FROM algorithm_runs WHERE assignment_id=:a
      AND algorithm_name=:name AND status='COMPLETED' ORDER BY id DESC LIMIT 1"""),
        {"a": aid, "name": ALLOCATION_NAME},
    ).scalar_one_or_none()
    if existing and not preview["new_task_count"] and not preview["blockers"]:
        return {
            "assignment_id": aid,
            "status": assignment["status"],
            "panels": _allocation_results(db, aid),
            "reused": True,
        }
    if assignment["status"] not in {
        "PUBLISHED",
        "SUBMITTING",
        "REVIEWER_INITIALIZING",
        "REVIEWER_GRADING",
    }:
        raise HTTPException(409, "INVALID_STATE")
    if assignment["review_deadline"] <= datetime.now(UTC):
        raise HTTPException(409, "REVIEW_DEADLINE_PASSED")
    if expected_hash is not None and expected_hash != preview["snapshot_hash"]:
        raise HTTPException(409, "ALLOCATION_PREVIEW_STALE")
    params = {
        "seed": assignment["review_seed"],
        "required_reviews": 5,
        "history_window": 20,
        "snapshot": preview,
        "works": [asdict(w) for w in works],
        "history": [[u, v, cost] for (u, v), cost in sorted(history.items())],
    }
    run_id = db.execute(
        text("""INSERT INTO algorithm_runs(assignment_id,algorithm_name,version,
      parameters_json,input_hash,status) VALUES(:a,:name,:v,CAST(:p AS jsonb),:h,'RUNNING') RETURNING id"""),
        {
            "a": aid,
            "name": ALLOCATION_NAME,
            "v": INCREMENTAL_VERSION if preview["existing_task_count"] else ALLOCATION_VERSION,
            "p": json.dumps(params),
            "h": preview["snapshot_hash"],
        },
    ).scalar_one()
    if preview["blockers"]:
        params.update(failure_reason=preview["blockers"][0], blockers=preview["blockers"])
        db.execute(
            text(
                "UPDATE algorithm_runs SET status='FAILED',finished_at=now(),parameters_json=CAST(:p AS jsonb) WHERE id=:r"
            ),
            {"p": json.dumps(params), "r": run_id},
        )
        db.commit()
        raise HTTPException(
            424, {"code": preview["blockers"][0], "preview": preview, "algorithm_run_id": run_id}
        )
    try:
        fixed = [
            Edge(r.reviewer_id, r.submission_id)
            for r in db.execute(
                text("""SELECT rt.reviewer_id,rt.submission_id FROM review_tasks rt
          JOIN submissions s ON s.id=rt.submission_id WHERE s.assignment_id=:a AND rt.is_active"""),
                {"a": aid},
            )
        ]
        plan = (
            allocate_additional_reviews(works, assignment["review_seed"], fixed, history)
            if fixed
            else allocate_reviews(works, assignment["review_seed"], history)
        )
    except AllocationError as exc:
        params.update(failure_reason=exc.code, diagnostics=exc.details)
        db.execute(
            text("""UPDATE algorithm_runs SET status='FAILED',finished_at=now(),
          parameters_json=CAST(:p AS jsonb) WHERE id=:r"""),
            {"p": json.dumps(params), "r": run_id},
        )
        db.commit()
        raise HTTPException(409, {"code": exc.code, "algorithm_run_id": run_id}) from exc
    db.execute(
        text("UPDATE assignments SET status='REVIEWER_INITIALIZING',updated_at=now() WHERE id=:a"),
        {"a": aid},
    )
    ensure_random_panels(db, aid)
    panels = {
        r["target_class_id"]: r["id"]
        for r in db.execute(
            text("SELECT id,target_class_id FROM review_panels WHERE assignment_id=:a"), {"a": aid}
        ).mappings()
    }
    by_id = {r["id"]: r for r in valid}
    # Snapshot the full eligible pool, including participants with a zero lower quota.
    for person in works:
        for target, panel in panels.items():
            if target != person.class_id:
                db.execute(
                    text("""INSERT INTO panel_reviewers(panel_id,reviewer_id)
                  VALUES(:p,:u) ON CONFLICT DO NOTHING"""),
                    {"p": panel, "u": person.author_id},
                )
    fixed_set = set(fixed)
    for edge in plan.edges:
        if edge in fixed_set:
            continue
        work = by_id[edge.submission_id]
        panel = panels[work["class_id"]]
        db.execute(
            text(
                """INSERT INTO panel_reviewers(panel_id,reviewer_id) VALUES(:p,:u) ON CONFLICT DO NOTHING"""
            ),
            {"p": panel, "u": edge.reviewer_id},
        )
        db.execute(
            text("""INSERT INTO review_tasks(panel_id,submission_id,reviewer_id,anonymous_token,allocation_run_id)
          VALUES(:p,:s,:u,:t,:r)"""),
            {
                "p": panel,
                "s": work["id"],
                "u": edge.reviewer_id,
                "t": work["anonymous_token"],
                "r": run_id,
            },
        )
    params.update(
        diagnostics=plan.diagnostics,
        allocation_input_hash=plan.input_hash,
        loads=plan.loads,
        quotas=plan.quotas,
        edges=[asdict(edge) for edge in plan.edges],
    )
    db.execute(
        text("""UPDATE algorithm_runs SET status='COMPLETED',finished_at=now(),parameters_json=CAST(:p AS jsonb)
      WHERE id=:r"""),
        {"p": json.dumps(params), "r": run_id},
    )
    db.execute(
        text("UPDATE review_panels SET status='ACTIVE',updated_at=now() WHERE assignment_id=:a"),
        {"a": aid},
    )
    db.execute(
        text("UPDATE assignments SET status='REVIEWER_GRADING',updated_at=now() WHERE id=:a"),
        {"a": aid},
    )
    audit(
        db,
        actor,
        "INITIALIZE_RANDOM_REVIEW_TASKS",
        "assignment",
        aid,
        after={
            "algorithm_run_id": run_id,
            "snapshot_hash": preview["snapshot_hash"],
            "diagnostics": plan.diagnostics,
        },
    )
    return {
        "assignment_id": aid,
        "status": "REVIEWER_GRADING",
        "panels": _allocation_results(db, aid),
        "diagnostics": plan.diagnostics,
    }


def replace_pending_task(db, assignment, task_id, actor, reason):
    if assignment["type"] != "FINAL_PROJECT":
        raise HTTPException(400, "REVIEWED_ASSIGNMENT_REQUIRED")
    if len(reason.strip()) < 3:
        raise HTTPException(422, "REPLACEMENT_REASON_REQUIRED")
    if assignment["status"] != "REVIEWER_GRADING":
        raise HTTPException(409, "INVALID_STATE")
    if assignment["review_deadline"] <= datetime.now(UTC):
        raise HTTPException(409, "REVIEW_DEADLINE_PASSED")
    task = (
        db.execute(
            text("""SELECT rt.*,s.author_id,p.reviewer_class_id FROM review_tasks rt
      JOIN review_panels p ON p.id=rt.panel_id JOIN submissions s ON s.id=rt.submission_id
      WHERE rt.id=:t AND p.assignment_id=:a FOR UPDATE OF rt"""),
            {"t": task_id, "a": assignment["id"]},
        )
        .mappings()
        .one_or_none()
    )
    if task is None:
        raise HTTPException(404, "REVIEW_TASK_NOT_FOUND")
    if not task["is_active"] or task["status"] == "SUBMITTED":
        raise HTTPException(409, "REVIEW_TASK_NOT_REPLACEABLE")
    candidates = (
        db.execute(
            text("""SELECT pr.reviewer_id,
        (SELECT count(*) FROM review_tasks load JOIN review_panels lp ON lp.id=load.panel_id
          WHERE lp.assignment_id=:a AND load.reviewer_id=pr.reviewer_id AND load.is_active) AS load,
        (SELECT count(*) FROM review_tasks hist JOIN submissions hs ON hs.id=hist.submission_id
          WHERE hs.author_id=:author AND hist.reviewer_id=pr.reviewer_id AND hist.is_active) AS repeat_count
      FROM panel_reviewers pr JOIN users u ON u.id=pr.reviewer_id
      WHERE pr.panel_id=:p AND pr.reviewer_id<>:old AND u.system_role='STUDENT'
        AND EXISTS(SELECT 1 FROM enrollments WHERE user_id=pr.reviewer_id AND class_id=:class)
        AND NOT EXISTS(SELECT 1 FROM enrollments WHERE user_id=pr.reviewer_id AND class_id=
          (SELECT class_id FROM submissions WHERE id=:s))
        AND NOT EXISTS(SELECT 1 FROM review_tasks WHERE submission_id=:s AND reviewer_id=pr.reviewer_id)
        AND NOT EXISTS(SELECT 1 FROM review_tasks reverse JOIN submissions rs ON rs.id=reverse.submission_id
          WHERE rs.assignment_id=:a AND rs.author_id=pr.reviewer_id AND reverse.reviewer_id=:author AND reverse.is_active)
      ORDER BY load,repeat_count,pr.reviewer_id"""),
            {
                "a": assignment["id"],
                "author": task["author_id"],
                "p": task["panel_id"],
                "old": task["reviewer_id"],
                "class": task["reviewer_class_id"],
                "s": task["submission_id"],
            },
        )
        .mappings()
        .first()
    )
    if candidates is None:
        raise HTTPException(409, "NO_REPLACEMENT_REVIEWER")
    db.execute(
        text("UPDATE review_tasks SET is_active=false,updated_at=now() WHERE id=:t"), {"t": task_id}
    )
    fresh = db.execute(
        text("""INSERT INTO review_tasks(panel_id,submission_id,reviewer_id,anonymous_token,allocation_run_id)
      VALUES(:p,:s,:u,:token,:run) RETURNING id"""),
        {
            "p": task["panel_id"],
            "s": task["submission_id"],
            "u": candidates["reviewer_id"],
            "token": task["anonymous_token"],
            "run": task["allocation_run_id"],
        },
    ).scalar_one()
    db.execute(
        text("""INSERT INTO review_task_replacements(old_task_id,new_task_id,actor_id,reason)
      VALUES(:old,:new,:actor,:reason)"""),
        {"old": task_id, "new": fresh, "actor": actor, "reason": reason},
    )
    audit(
        db,
        actor,
        "REPLACE_REVIEW_TASK",
        "review_task",
        task_id,
        after={"new_task_id": fresh, "reviewer_id": candidates["reviewer_id"], "reason": reason},
    )
    return {"old_task_id": task_id, "new_task_id": fresh, "reviewer_id": candidates["reviewer_id"]}
