import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app


class FakeMappingResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> "FakeMappingResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self.rows


class FakeDb:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.statement = ""
        self.params: dict[str, object] | None = None

    def execute(self, statement, params: dict[str, object]) -> FakeMappingResult:
        self.statement = str(statement)
        self.params = params
        return FakeMappingResult(self.rows)


def override_db(db: FakeDb):
    def dependency():
        yield db

    return dependency


def test_student_workspace_returns_only_safe_current_student_summary() -> None:
    db = FakeDb(
        rows=[
            {
                "id": 12,
                "title": "算法微课期末作业",
                "type": "FINAL_PROJECT",
                "status": "SUBMITTING",
                "submit_deadline": datetime(2026, 12, 20, 15, 59, 59, tzinfo=UTC),
                "review_deadline": datetime(2026, 12, 27, 15, 59, 59, tzinfo=UTC),
                "submission_id": 301,
                "submission_status": "VALID",
                "material_check_status": "VALID",
            }
        ]
    )
    app.dependency_overrides[get_db] = override_db(db)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=42, system_role="STUDENT")
    try:
        response = TestClient(app).get("/api/student/assignments")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "data": [
            {
                "id": 12,
                "title": "算法微课期末作业",
                "type": "FINAL_PROJECT",
                "status": "SUBMITTING",
                "submit_deadline": "2026-12-20T15:59:59Z",
                "review_deadline": "2026-12-27T15:59:59Z",
                "submission": {
                    "id": 301,
                    "status": "VALID",
                    "material_check_status": "VALID",
                },
            }
        ],
    }
    assert db.params == {"student_id": 42}
    assert "a.status <> 'DRAFT'" in db.statement
    assert "enrollment.user_id = :student_id" in db.statement
    assert "author_id" not in response.text


def test_teacher_cannot_access_student_workspace() -> None:
    db = FakeDb(rows=[])
    app.dependency_overrides[get_db] = override_db(db)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1, system_role="TEACHER")
    try:
        response = TestClient(app).get("/api/student/assignments")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN"
    assert db.params is None
