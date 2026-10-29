import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, require_teacher
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.video_ai import VideoAiSettingsInput, VideoAnalysisInput
from app.services.video_ai_provider import VideoAIError
from app.services.video_ai_settings import read_config, save_config
from app.services.video_analysis import (
    ERROR_MESSAGES,
    analyze_run,
    input_hash,
    material,
    rubric_for,
    test_connection,
)

router = APIRouter(dependencies=[Depends(require_teacher)])


def no_cache(response):
    response.headers["Cache-Control"] = "private, no-store"


def expire_stale(db, teacher_id):
    db.execute(
        text("""UPDATE video_analysis_runs SET status='FAILED',error_code='AI_INTERRUPTED',
      error_message=:m,finished_at=clock_timestamp() WHERE created_by=:t
      AND status IN ('QUEUED','PROCESSING')
      AND created_at < now() - interval '90 minutes' """),
        {"t": teacher_id, "m": ERROR_MESSAGES["AI_INTERRUPTED"]},
    )


@router.get("/ai-video/settings", response_model=ApiResponse)
def get_settings(
    response: Response,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    no_cache(response)
    return ApiResponse(
        data=read_config(db, teacher.id)
        or {
            "configured": False,
            "enabled": False,
            "provider": "qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen3.5-omni-flash",
        }
    )


@router.put("/ai-video/settings", response_model=ApiResponse)
def update_settings(
    payload: VideoAiSettingsInput,
    response: Response,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    no_cache(response)
    db.execute(text("SELECT id FROM users WHERE id=:t FOR UPDATE"), {"t": teacher.id})
    return ApiResponse(data=save_config(db, teacher.id, payload))


@router.delete("/ai-video/settings", response_model=ApiResponse)
def delete_settings(teacher: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    db.execute(text("SELECT id FROM users WHERE id=:t FOR UPDATE"), {"t": teacher.id})
    db.execute(text("DELETE FROM teacher_video_ai_settings WHERE teacher_id=:t"), {"t": teacher.id})
    db.execute(
        text("""UPDATE video_analysis_runs SET status='CANCELLED',finished_at=clock_timestamp()
      WHERE created_by=:t AND status IN ('QUEUED','PROCESSING')"""),
        {"t": teacher.id},
    )
    db.commit()
    return ApiResponse(data={"deleted": True})


@router.post("/ai-video/test", response_model=ApiResponse)
def check_connection(
    payload: VideoAiSettingsInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    if not db.execute(
        text("SELECT pg_try_advisory_xact_lock(68351, CAST(:t AS integer))"), {"t": teacher.id}
    ).scalar_one():
        raise HTTPException(409, "AI_TEST_BUSY")
    config = payload.model_dump()
    if not config["api_key"]:
        previous = read_config(db, teacher.id, secret=True)
        if not previous or (previous["provider"], previous["base_url"]) != (
            payload.provider,
            payload.base_url,
        ):
            raise HTTPException(422, "AI_KEY_REQUIRED")
        config["api_key"] = previous["api_key"]
    try:
        test_connection(config)
    except VideoAIError as exc:
        raise HTTPException(502, exc.code) from exc
    return ApiResponse(data={"ok": True, "message": "音视频请求已通过，可以保存配置并分析作品。"})


def list_runs(db, submission_id, teacher_id):
    return [
        dict(r)
        for r in db.execute(
            text("""SELECT v.id,v.provider,v.model,v.status,
      v.error_code,v.error_message,v.result_json,v.progress_json,v.created_at,v.finished_at
      FROM video_analysis_runs v JOIN submission_files f ON f.id=v.submission_file_id
      WHERE f.submission_id=:s AND v.created_by=:t ORDER BY v.id DESC LIMIT 10"""),
            {"s": submission_id, "t": teacher_id},
        ).mappings()
    ]


@router.get("/submissions/{submission_id}/video-analysis", response_model=ApiResponse)
def get_runs(
    submission_id: int,
    response: Response,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    no_cache(response)
    exists = db.execute(
        text("SELECT id FROM submissions WHERE id=:s"), {"s": submission_id}
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(404, "SUBMISSION_NOT_FOUND")
    expire_stale(db, teacher.id)
    db.commit()
    return ApiResponse(data={"runs": list_runs(db, submission_id, teacher.id)})


@router.post("/submissions/{submission_id}/video-analysis", response_model=ApiResponse)
def start_analysis(
    submission_id: int,
    payload: VideoAnalysisInput,
    background: BackgroundTasks,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    db.execute(text("SELECT id FROM users WHERE id=:t FOR UPDATE"), {"t": teacher.id})
    config = read_config(db, teacher.id, secret=True)
    if not config or not config["enabled"]:
        raise HTTPException(409, "AI_NOT_CONFIGURED")
    row, archive, path = material(db, submission_id)
    rubric = rubric_for(db, row["assignment_id"])
    if not rubric:
        raise HTTPException(422, "AI_RUBRIC_REQUIRED")
    expire_stale(db, teacher.id)
    fingerprint = input_hash(row["file_id"], archive, path, rubric, config)
    existing = (
        db.execute(
            text("""SELECT id,status FROM video_analysis_runs
      WHERE submission_file_id=:f AND created_by=:t AND
      (status IN ('QUEUED','PROCESSING') OR
        (input_hash=:h AND status='SUCCEEDED' AND NOT :force)) ORDER BY id DESC LIMIT 1"""),
            {"f": row["file_id"], "t": teacher.id, "h": fingerprint, "force": payload.force},
        )
        .mappings()
        .one_or_none()
    )
    if existing:
        db.commit()
        return ApiResponse(data={"run_id": existing["id"], "reused": True})
    active = db.execute(
        text("""SELECT count(*) FROM video_analysis_runs
      WHERE created_by=:t AND status IN ('QUEUED','PROCESSING')"""),
        {"t": teacher.id},
    ).scalar_one()
    if active >= 2:
        raise HTTPException(409, "AI_TOO_MANY_TASKS")
    run_id = db.execute(
        text("""INSERT INTO video_analysis_runs(submission_file_id,assignment_id,
      provider,model,rubric_snapshot_json,input_hash,status,created_by)
      VALUES (:f,:a,:p,:m,CAST(:r AS jsonb),:h,'QUEUED',:t) RETURNING id"""),
        {
            "f": row["file_id"],
            "a": row["assignment_id"],
            "p": config["provider"],
            "m": config["model"],
            "r": json.dumps(rubric, default=str),
            "h": fingerprint,
            "t": teacher.id,
        },
    ).scalar_one()
    bind = db.get_bind()
    db.commit()
    background.add_task(analyze_run, bind, run_id, config, archive, path)
    return ApiResponse(data={"run_id": run_id, "reused": False})


@router.post(
    "/submissions/{submission_id}/video-analysis/{run_id}/cancel", response_model=ApiResponse
)
def cancel_analysis(
    submission_id: int,
    run_id: int,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    changed = db.execute(
        text("""UPDATE video_analysis_runs v SET status='CANCELLED',
      finished_at=clock_timestamp() FROM submission_files f
      WHERE v.id=:id AND f.id=v.submission_file_id AND f.submission_id=:s AND v.created_by=:t
      AND v.status IN ('QUEUED','PROCESSING') RETURNING v.id"""),
        {"id": run_id, "s": submission_id, "t": teacher.id},
    ).scalar_one_or_none()
    if changed is None:
        raise HTTPException(409, "AI_TASK_NOT_ACTIVE")
    db.commit()
    return ApiResponse(data={"cancelled": True})
