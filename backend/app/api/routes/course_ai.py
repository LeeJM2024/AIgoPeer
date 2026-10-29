from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user, require_teacher
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.text_ai import AssistantQuestion, TextAiSettingsInput
from app.services import course_ai, text_ai_provider
from app.services.video_ai_provider import VideoAIError

router = APIRouter()


def student(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.system_role != "STUDENT":
        raise HTTPException(403, "FORBIDDEN")
    if not db.execute(
        text("SELECT EXISTS(SELECT 1 FROM enrollments WHERE user_id=:u)"), {"u": user.id}
    ).scalar_one():
        raise HTTPException(403, "FORBIDDEN")
    return user


@router.get("/teacher/ai-text/settings", response_model=ApiResponse)
def settings(
    response: Response, _: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)
):
    response.headers["Cache-Control"] = "private, no-store"
    return ApiResponse(data=course_ai.read_settings(db))


@router.put("/teacher/ai-text/settings", response_model=ApiResponse)
def save_settings(
    payload: TextAiSettingsInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    db.execute(text("SELECT pg_advisory_xact_lock(68352,1)"))
    return ApiResponse(data=course_ai.save_settings(db, teacher.id, payload))


@router.delete("/teacher/ai-text/settings", response_model=ApiResponse)
def delete_settings(_: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    db.execute(text("SELECT pg_advisory_xact_lock(68352,1)"))
    db.execute(text("DELETE FROM course_text_ai_settings WHERE id=1"))
    db.commit()
    return ApiResponse(data={"deleted": True})


@router.post("/teacher/ai-text/test", response_model=ApiResponse)
def test_settings(
    payload: TextAiSettingsInput,
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    if not db.execute(
        text("SELECT pg_try_advisory_xact_lock(68353,CAST(:u AS integer))"), {"u": teacher.id}
    ).scalar_one():
        raise HTTPException(409, "AI_TEST_BUSY")
    config = course_ai.resolve_key(db, payload)
    try:
        text_ai_provider.complete(
            config, [{"role": "user", "content": "请用中文回复：连接成功。"}], max_tokens=100
        )
    except VideoAIError as exc:
        raise HTTPException(502, exc.code) from exc
    return ApiResponse(data={"ok": True, "message": "文字模型连接成功，保存配置后即可使用。"})


@router.get("/student/ai/status", response_model=ApiResponse)
def status(_: CurrentUser = Depends(student), db: Session = Depends(get_db)):
    config = course_ai.read_settings(db)
    return ApiResponse(
        data={
            key: config[key]
            for key in ("configured", "enabled", "allow_full_solution", "student_daily_limit")
        }
    )


@router.get("/student/ai/topics", response_model=ApiResponse)
def topics(_: CurrentUser = Depends(student), db: Session = Depends(get_db)):
    return ApiResponse(
        data=[
            dict(row)
            for row in db.execute(
                text("SELECT id,code,chapter,name,description FROM topics ORDER BY code,id")
            ).mappings()
        ]
    )


@router.get("/student/assignments/{assignment_id}/ai/history", response_model=ApiResponse)
def programming_history(
    assignment_id: int, user: CurrentUser = Depends(student), db: Session = Depends(get_db)
):
    from app.services.student.programming_submission_service import get_programming_problem

    get_programming_problem(db=db, assignment_id=assignment_id, student_id=user.id)
    return ApiResponse(
        data={
            "items": course_ai.history(
                db, user.id, "PROGRAMMING", course_ai.context_key("PROGRAMMING", assignment_id)
            )
        }
    )


@router.post("/student/assignments/{assignment_id}/ai/messages", response_model=ApiResponse)
def programming_ask(
    assignment_id: int,
    payload: AssistantQuestion,
    user: CurrentUser = Depends(student),
    db: Session = Depends(get_db),
):
    context, meta = course_ai.programming_context(db, user.id, assignment_id, payload)
    return ApiResponse(
        data=course_ai.ask(
            db,
            user,
            "PROGRAMMING",
            course_ai.context_key("PROGRAMMING", assignment_id),
            context,
            meta,
            payload,
        )
    )


@router.get("/student/ai/topics/{topic_id}/history", response_model=ApiResponse)
def topic_history(
    topic_id: int, user: CurrentUser = Depends(student), db: Session = Depends(get_db)
):
    course_ai.topic_context(db, topic_id)
    return ApiResponse(
        data={
            "items": course_ai.history(
                db, user.id, "KNOWLEDGE", course_ai.context_key("KNOWLEDGE", topic_id)
            )
        }
    )


@router.post("/student/ai/topics/{topic_id}/messages", response_model=ApiResponse)
def topic_ask(
    topic_id: int,
    payload: AssistantQuestion,
    user: CurrentUser = Depends(student),
    db: Session = Depends(get_db),
):
    context, meta = course_ai.topic_context(db, topic_id)
    return ApiResponse(
        data=course_ai.ask(
            db,
            user,
            "KNOWLEDGE",
            course_ai.context_key("KNOWLEDGE", topic_id),
            context,
            meta,
            payload,
        )
    )


@router.get("/teacher/ai/teaching/history", response_model=ApiResponse)
def teaching_history(
    class_id: int | None = Query(None, gt=0),
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return ApiResponse(
        data={
            "items": course_ai.history(
                db, teacher.id, "TEACHING", course_ai.context_key("TEACHING", class_id)
            )
        }
    )


@router.post("/teacher/ai/teaching/messages", response_model=ApiResponse)
def teaching_ask(
    payload: AssistantQuestion,
    class_id: int | None = Query(None, gt=0),
    teacher: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    context, meta = course_ai.teaching_context(db, class_id)
    return ApiResponse(
        data=course_ai.ask(
            db,
            teacher,
            "TEACHING",
            course_ai.context_key("TEACHING", class_id),
            context,
            meta,
            payload,
        )
    )
