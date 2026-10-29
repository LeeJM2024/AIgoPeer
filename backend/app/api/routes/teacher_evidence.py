"""Teacher-only evidence access; never reused by anonymous reviewer routes."""

from pathlib import PurePosixPath
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, require_teacher
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.student_submission import ProjectManifest
from app.services.designated_review_service import aggregate_panel_and_persist
from app.services.teacher_workflow import audit, lock_assignment

router = APIRouter(dependencies=[Depends(require_teacher)])


@router.get("/assignments/{assignment_id}/subjective-answers", response_model=ApiResponse)
def subjective_answers(
    assignment_id: int,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    kind = db.execute(text("SELECT type FROM assignments WHERE id=:id"),
                      {"id": assignment_id}).scalar_one_or_none()
    if kind is None:
        raise HTTPException(404, "ASSIGNMENT_NOT_FOUND")
    if kind not in {"PROOF", "OPEN_ENDED", "ALGORITHM_ANALYSIS"}:
        raise HTTPException(400, "SUBJECTIVE_ASSIGNMENT_REQUIRED")
    response.headers["Cache-Control"] = "private, no-store"
    roster = """WITH roster AS (
        SELECT e.user_id FROM enrollments e
        JOIN assignment_classes ac ON ac.class_id=e.class_id
        JOIN users u ON u.id=e.user_id
        WHERE ac.assignment_id=:id AND u.system_role='STUDENT'
        UNION SELECT author_id FROM submissions WHERE assignment_id=:id
    ) """
    params = {"id": assignment_id, "limit": page_size, "offset": (page - 1) * page_size}
    total = db.execute(text(roster + "SELECT count(*) FROM roster"), params).scalar_one()
    submitted = db.execute(text("""SELECT count(DISTINCT author_id) FROM submissions
        WHERE assignment_id=:id AND is_current AND status='VALID'"""), params).scalar_one()
    rows = db.execute(text(roster + """
        SELECT u.id AS student_id,u.student_no,u.name,
          COALESCE((SELECT string_agg(c.name,'、' ORDER BY c.id) FROM classes c
            JOIN enrollments e ON e.class_id=c.id
            JOIN assignment_classes ac ON ac.class_id=c.id
            WHERE ac.assignment_id=:id AND e.user_id=u.id),
            (SELECT c.name FROM classes c WHERE c.id=s.class_id)) AS class_name,
          s.id AS submission_id,s.version,s.submitted_at,
          COALESCE((SELECT jsonb_agg(jsonb_build_object('id',h.id,'version',h.version,
              'submitted_at',h.submitted_at,'is_current',h.is_current) ORDER BY h.version DESC)
            FROM submissions h WHERE h.assignment_id=:id AND h.author_id=u.id),'[]') AS versions
        FROM roster JOIN users u ON u.id=roster.user_id
        LEFT JOIN submissions s ON s.assignment_id=:id AND s.author_id=u.id AND s.is_current
        ORDER BY u.student_no,u.id LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    return ApiResponse(data={"items": [dict(row) for row in rows], "total": total,
                             "submitted": submitted, "page": page})


@router.get("/assignments/{assignment_id}/programming-results", response_model=ApiResponse)
def programming_results(assignment_id: int, db: Session = Depends(get_db)):
    kind = db.execute(
        text("SELECT type FROM assignments WHERE id=:id"), {"id": assignment_id}
    ).scalar_one_or_none()
    if kind != "PROGRAMMING":
        raise HTTPException(404, "NOT_FOUND")
    rows = (
        db.execute(
            text("""SELECT cs.id,cs.version,cs.status,cs.created_at,cs.time_ms,cs.memory_kb,
        cs.executed_case_count,cs.passed_case_count,u.name,u.student_no,c.name AS class_name
        FROM code_submissions cs JOIN users u ON u.id=cs.author_id JOIN classes c ON c.id=cs.class_id
        WHERE cs.assignment_id=:id AND cs.is_current ORDER BY c.name,u.student_no"""),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(r) for r in rows])


@router.get("/assignments/{assignment_id}/programming-history", response_model=ApiResponse)
def programming_history(assignment_id: int, response: Response, page: int = Query(1, ge=1),
                        page_size: int = Query(20, ge=1, le=100),
                        student_id: int | None = Query(None, ge=1), db: Session = Depends(get_db)):
    if db.execute(text("SELECT type FROM assignments WHERE id=:id"),
                  {"id": assignment_id}).scalar_one_or_none() != "PROGRAMMING":
        raise HTTPException(404, "NOT_FOUND")
    response.headers["Cache-Control"] = "private, no-store"
    condition = "cs.assignment_id=:id AND (CAST(:student AS bigint) IS NULL OR cs.author_id=:student)"
    params = {"id": assignment_id, "student": student_id,
              "limit": page_size, "offset": (page - 1) * page_size}
    total = db.execute(text(f"SELECT count(*) FROM code_submissions cs WHERE {condition}"),
                       params).scalar_one()
    rows = db.execute(text(f"""SELECT cs.id,cs.author_id,cs.version,cs.status,cs.is_current,
        cs.queued_at,cs.started_at,cs.finished_at,cs.source_code,cs.compiler_output,
        cs.time_ms,cs.memory_kb,cs.executed_case_count,cs.passed_case_count,
        u.student_no,u.name,c.name AS class_name FROM code_submissions cs
        JOIN users u ON u.id=cs.author_id JOIN classes c ON c.id=cs.class_id
        WHERE {condition} ORDER BY cs.id DESC LIMIT :limit OFFSET :offset"""), params).mappings()
    return ApiResponse(data={"items": [dict(row) for row in rows], "total": total, "page": page})


def _submission(db, submission_id):
    row = (
        db.execute(text("SELECT * FROM submissions WHERE id=:id"), {"id": submission_id})
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "SUBMISSION_NOT_FOUND")
    return row


def _materials(row):
    if not row["manifest_json"]:
        return []
    try:
        manifest = ProjectManifest.model_validate(row["manifest_json"])
    except ValueError:
        return []
    items = [
        ("PPT", manifest.ppt_path),
        ("VIDEO", manifest.video_path),
        ("README", manifest.readme_path),
    ]
    items += [("CODE", path) for path in manifest.source_paths]
    items += [("EXAMPLES", e.path) for e in manifest.examples if e.path]
    for case in manifest.tests:
        items += [("TESTS", case.input_path), ("TESTS", case.expected_path)]
    return [{"kind": kind, "path": path} for kind, path in dict.fromkeys(items)]


@router.get("/submissions/{submission_id}/evidence", response_model=ApiResponse)
def get_evidence(submission_id: int, db: Session = Depends(get_db)):
    row = _submission(db, submission_id)
    reviews = (
        db.execute(
            text("""SELECT rt.id,rt.status,rt.is_active,rt.started_at,rt.submitted_at,
        (SELECT jsonb_build_object('new_task_id',r.new_task_id,'reason',r.reason,'created_at',r.created_at)
          FROM review_task_replacements r WHERE r.old_task_id=rt.id) AS replacement,
        u.name AS reviewer_name,u.student_no,rc.content AS comment,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('name',ri.name,'score',rs.score,'max_score',ri.max_score)
            ORDER BY ri.sort_order) FROM review_scores rs JOIN rubric_items ri ON ri.id=rs.rubric_item_id
            WHERE rs.review_task_id=rt.id),'[]'::jsonb) AS scores,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('version',rev.version,'reason',rev.reason,
          'before',rev.before_json,'after',rev.after_json,'created_at',rev.created_at) ORDER BY rev.version)
          FROM review_revisions rev WHERE rev.review_task_id=rt.id),'[]'::jsonb) AS revisions
        FROM review_tasks rt JOIN users u ON u.id=rt.reviewer_id
        LEFT JOIN review_comments rc ON rc.review_task_id=rt.id
        WHERE rt.submission_id=:id ORDER BY rt.id"""),
            {"id": submission_id},
        )
        .mappings()
        .all()
    )
    anomalies = (
        db.execute(
            text(
                "SELECT risk_level,status,evidence_json,resolution_note FROM anomaly_records WHERE submission_id=:id AND evidence_json->>'risk_policy_retired' IS DISTINCT FROM 'true' ORDER BY id"
            ),
            {"id": submission_id},
        )
        .mappings()
        .all()
    )
    final_review = (
        db.execute(
            text("""SELECT fr.final_score,fr.reason,fr.locked_at,u.name AS entered_by_name
        FROM teacher_final_reviews fr JOIN users u ON u.id=fr.entered_by WHERE fr.submission_id=:id"""),
            {"id": submission_id},
        )
        .mappings()
        .one_or_none()
    )
    archive = db.execute(
        text(
            "SELECT EXISTS(SELECT 1 FROM submission_files WHERE submission_id=:id AND file_kind='ZIP')"
        ),
        {"id": submission_id},
    ).scalar_one()
    return ApiResponse(
        data={
            "materials": _materials(row),
            "answer": db.execute(text("SELECT content FROM subjective_answers WHERE submission_id=:id"),
                                 {"id": submission_id}).scalar_one_or_none(),
            "archive_available": archive,
            "version": row["version"],
            "is_current": row["is_current"],
            "reviews": [dict(r) for r in reviews],
            "anomalies": [dict(a) for a in anomalies],
            "final_review": dict(final_review) if final_review else None,
        }
    )


@router.get("/submissions/{submission_id}/material")
def read_material(
    submission_id: int,
    path: str | None = Query(default=None, max_length=1000),
    db: Session = Depends(get_db),
):
    row = _submission(db, submission_id)
    file = (
        db.execute(
            text(
                "SELECT storage_key FROM submission_files WHERE submission_id=:id AND file_kind='ZIP' ORDER BY id DESC LIMIT 1"
            ),
            {"id": submission_id},
        )
        .mappings()
        .one_or_none()
    )
    if file is None:
        raise HTTPException(404, "MATERIAL_NOT_FOUND")
    root = settings.storage_dir.resolve()
    archive = (root / file["storage_key"]).resolve()
    if not archive.is_relative_to(root) or not archive.is_file():
        raise HTTPException(404, "MATERIAL_NOT_FOUND")
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if path is None:
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=f"submission-{submission_id}.zip",
            headers=headers,
        )
    if path not in {m["path"] for m in _materials(row)}:
        raise HTTPException(404, "MATERIAL_NOT_FOUND")
    try:
        with ZipFile(archive) as z:
            info = z.getinfo(path)
            if (
                info.is_dir()
                or info.file_size > 500 * 1024 * 1024
                or info.file_size / max(1, info.compress_size) > 100
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise HTTPException(422, "UNSAFE_ARCHIVE_ENTRY")
    except (BadZipFile, KeyError, OSError) as exc:
        raise HTTPException(404, "MATERIAL_NOT_FOUND") from exc

    def chunks():
        with ZipFile(archive) as z, z.open(path) as entry:
            while chunk := entry.read(256 * 1024):
                yield chunk

    extension = PurePosixPath(path).suffix.lower()
    media_type = (
        "video/mp4"
        if extension == ".mp4"
        else "text/plain"
        if extension in {".md", ".txt", ".cpp", ".py", ".in", ".out"}
        else "application/octet-stream"
    )
    headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(
        PurePosixPath(path).name, safe=""
    )
    headers["Content-Length"] = str(info.file_size)
    return StreamingResponse(chunks(), media_type=media_type, headers=headers)


@router.get("/assignments/{assignment_id}/algorithm-runs", response_model=ApiResponse)
def algorithm_runs(assignment_id: int, db: Session = Depends(get_db)):
    rows = (
        db.execute(
            text("""SELECT id,panel_id,algorithm_name,version,status,started_at,finished_at,parameters_json
        FROM algorithm_runs WHERE assignment_id=:id ORDER BY id DESC LIMIT 30"""),
            {"id": assignment_id},
        )
        .mappings()
        .all()
    )
    return ApiResponse(data=[dict(r) for r in rows])


@router.post("/assignments/{assignment_id}/aggregate-reviews", response_model=ApiResponse)
def aggregate_reviews(
    assignment_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = lock_assignment(db, assignment_id)
    if assignment["type"] != "FINAL_PROJECT":
        raise HTTPException(400, "REVIEWED_ASSIGNMENT_REQUIRED")
    if assignment["type"] == "PROGRAMMING" or assignment["status"] not in {
        "REVIEWER_GRADING",
        "AGGREGATING",
        "TEACHER_GRADING",
    }:
        raise HTTPException(400, "INVALID_STATE")
    panels = list(
        db.execute(
            text("SELECT id FROM review_panels WHERE assignment_id=:id ORDER BY id"),
            {"id": assignment_id},
        ).scalars()
    )
    if len(panels) != 2:
        raise HTTPException(424, "PANEL_NOT_READY")
    results = [
        {"panel_id": panel, **aggregate_panel_and_persist(db, assignment_id, panel)}
        for panel in panels
    ]
    audit(db, teacher.id, "AGGREGATE_REVIEWS", "assignment", assignment_id, after=results)
    db.commit()
    return ApiResponse(data={"panels": results})
