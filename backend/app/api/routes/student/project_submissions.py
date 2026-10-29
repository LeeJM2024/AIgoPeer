from __future__ import annotations

import json
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.common import ApiResponse
from app.schemas.student_submission import MaterialCheckResult, ProjectManifest
from app.services.student.material_check_service import get_material_check, run_material_check
from app.services.student.project_submission_service import (
    create_pending_submission,
    get_project_submission_view,
    get_upload_context,
    list_project_submissions,
    new_storage_path,
    store_archive,
    validate_archive_filename,
)

router = APIRouter()


def require_student(current_user: CurrentUser) -> CurrentUser:
    if current_user.system_role != "STUDENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    return current_user


@router.get("/student/assignments/{assignment_id}/project-submission", response_model=ApiResponse)
def read_current_project_submission(
    assignment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    current_user = require_student(current_user)
    view = get_project_submission_view(
        db=db, assignment_id=assignment_id, student_id=current_user.id
    )
    return ApiResponse(data=view.model_dump(mode="json"))


@router.get("/student/assignments/{assignment_id}/project-submissions", response_model=ApiResponse)
def read_project_submission_history(
    assignment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> ApiResponse:
    current_user = require_student(current_user)
    history = list_project_submissions(
        db=db,
        assignment_id=assignment_id,
        student_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data=history.model_dump(mode="json"))


@router.post(
    "/assignments/{assignment_id}/project-submissions",
    response_model=ApiResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["zip_file", "manifest"],
                        "properties": {
                            "zip_file": {"type": "string", "format": "binary"},
                            "manifest": {"type": "string", "description": "JSON 材料索引"},
                        },
                    }
                }
            },
        }
    },
)
async def create_project_submission(
    assignment_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    current_user = require_student(current_user)
    context = get_upload_context(db=db, assignment_id=assignment_id, student_id=current_user.id)
    # Unlike File/Form parameters, manual parsing runs AFTER identity, nonce,
    # rate and enrollment checks. Unauthenticated traffic never spools a ZIP.
    async with request.form(max_files=1, max_fields=1, max_part_size=256 * 1024) as form:
        zip_file, manifest = form.get("zip_file"), form.get("manifest")
        if not isinstance(zip_file, UploadFile) or not isinstance(manifest, str):
            raise HTTPException(422, "VALIDATION_ERROR")
        try:
            parsed_manifest = ProjectManifest.model_validate(json.loads(manifest))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(422, "VALIDATION_ERROR") from exc
        original_file_name = validate_archive_filename(file_name=zip_file.filename, context=context)
        storage_key, archive_path = new_storage_path(storage_root=settings.storage_dir)
        size_bytes, checksum = await store_archive(
            upload_file=zip_file,
            destination=archive_path,
            max_bytes=settings.max_project_archive_bytes,
        )
    try:
        created = create_pending_submission(
            db=db,
            context=context,
            manifest=parsed_manifest,
            original_file_name=original_file_name,
            storage_key=storage_key,
            size_bytes=size_bytes,
            checksum=checksum,
        )
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    background_tasks.add_task(run_material_check, created.submission_id)
    return ApiResponse(data=created.model_dump())


@router.get("/submissions/{submission_id}/material-check", response_model=ApiResponse)
def read_material_check(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse:
    result = MaterialCheckResult.model_validate(
        get_material_check(
            db=db,
            submission_id=submission_id,
            current_user_id=current_user.id,
            current_role=current_user.system_role,
        )
    )
    return ApiResponse(data=result.model_dump(mode="json"))
