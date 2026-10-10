"""End-to-end acceptance coverage for the cross-class anonymous review loop.

The workflow uses the public APIs for every business action after isolated test
identities and classes have been created.  Only the external video remux binary
is replaced with a deterministic file copy so the test remains portable; the
archive, material check, anonymity package, review, aggregation and publication
code all execute normally.
"""

from __future__ import annotations

import io
import json
import shutil
from contextlib import contextmanager
from zipfile import ZipFile

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker


@contextmanager
def _as_student(user_id: int):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id, "STUDENT")
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


def _presentation_bytes() -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as presentation:
        for page in range(1, 4):
            presentation.writestr(
                f"ppt/slides/slide{page}.xml", "<p:sld xmlns:p='presentation'/>"
            )
    return buffer.getvalue()


def _project_archive() -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("slides.pptx", _presentation_bytes())
        archive.writestr("demo.mp4", b"deterministic test video payload")
        archive.writestr("README.md", "Algorithm explanation without personal details.")
        archive.writestr("solution.py", "def solve():\n    return 42\n")
        for number in range(1, 4):
            archive.writestr(f"tests/case{number}.in", f"{number}\n")
            archive.writestr(f"tests/case{number}.out", f"{number * 2}\n")
    return buffer.getvalue()


def _manifest() -> dict:
    return {
        "ppt_path": "slides.pptx",
        "video_path": "demo.mp4",
        "readme_path": "README.md",
        "source_paths": ["solution.py"],
        "examples": [{"location": "PPT", "pages": [1, 2, 3]}],
        "tests": [
            {"input_path": f"tests/case{number}.in", "expected_path": f"tests/case{number}.out"}
            for number in range(1, 4)
        ],
    }


def _create_topic(client, code: str) -> int:
    response = client.post(
        "/api/teacher/topics",
        json={
            "code": code,
            "chapter": "端到端验收",
            "name": f"匿名评审主题 {code}",
            "description": "用于跨班匿名评审闭环测试。",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["topic_id"]


def _upload_project(
    client, assignment_id: int, student_id: int, student_no: str, topic_id: int, topic_code: str
) -> int:
    with _as_student(student_id):
        claim = client.post(
            f"/api/assignments/{assignment_id}/topic-claim",
            json={"topic_id": topic_id},
        )
        assert claim.status_code == 200, claim.text
        upload = client.post(
            f"/api/assignments/{assignment_id}/project-submissions",
            data={"manifest": json.dumps(_manifest())},
            files={
                "zip_file": (
                    f"{student_no}_虚构学生_{topic_code}.zip",
                    _project_archive(),
                    "application/zip",
                )
            },
        )
        assert upload.status_code == 200, upload.text
        submission_id = upload.json()["data"]["submission_id"]
        material = client.get(f"/api/submissions/{submission_id}/material-check")
        assert material.status_code == 200, material.text
        assert material.json()["data"]["status"] == "VALID", material.text
    return submission_id


def _submit_panel_reviews(
    client, assignment_id: int, reviewer_ids: list[int], score_by_task_id: dict[int, int]
) -> None:
    for position, reviewer_id in enumerate(reviewer_ids):
        with _as_student(reviewer_id):
            listed = client.get("/api/reviewer/review-tasks/mine")
            assert listed.status_code == 200, listed.text
            tasks = [
                item
                for item in listed.json()["data"]
                if item["assignment_id"] == assignment_id and item["status"] == "PENDING"
            ]
            assert len(tasks) == 3
            for task in tasks:
                assert set(task).isdisjoint(
                    {"author_id", "author_name", "student_no", "aggregate_score", "teacher_score"}
                )
                archive = client.get(task["materials"][0]["download_url"])
                assert archive.status_code == 200, archive.text
                assert archive.headers["cache-control"] == "private, no-store"
                with ZipFile(io.BytesIO(archive.content)) as package:
                    assert package.namelist()
                    assert all(name.startswith("materials/") for name in package.namelist())
                    assert all("TEST-" not in name and "虚构学生" not in name for name in package.namelist())
                rubric_item_id = task["rubric_items"][0]["id"]
                score = score_by_task_id[task["task_id"]]
                submitted = client.post(
                    f"/api/reviewer/review-tasks/{task['task_id']}/reviews",
                    json={
                        "rubric_scores": [{"rubric_item_id": rubric_item_id, "score": score}],
                        "comment": f"第 {position + 1} 位评审人已按评分量表完成匿名评阅。",
                        "started_at": "2026-10-10T00:00:00Z",
                    },
                )
                assert submitted.status_code == 200, submitted.text
                assert submitted.json()["data"]["status"] == "SUBMITTED"


def test_cross_class_anonymous_review_workflow_e2e(course, monkeypatch, tmp_path):
    """Two submissions travel through upload, five reviews, aggregation and publication."""
    from app.core.config import settings
    from app.services.student import (
        material_check_service,
        review_anonymization_service,
    )

    c = course
    client = c["client"]
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(
        material_check_service, "SessionLocal", sessionmaker(bind=c["engine"])
    )
    monkeypatch.setattr(review_anonymization_service, "_safe_video_file", shutil.copyfile)

    published_assignment = client.post(f"/api/teacher/assignments/{c['id']}/publish")
    assert published_assignment.status_code == 200, published_assignment.text
    topics = [(_create_topic(client, code), code) for code in ("91", "92", "93", "94", "95", "96")]
    authors_by_class = [c["reviewers"][0][:3], c["reviewers"][1][:3]]
    submissions_by_class: list[list[int]] = [[], []]
    topic_index = 0
    for class_index, authors in enumerate(authors_by_class):
        for student_index, author in enumerate(authors):
            topic_id, topic_code = topics[topic_index]
            topic_index += 1
            submissions_by_class[class_index].append(
                _upload_project(
                    client,
                    c["id"],
                    author,
                    f"TEST-{class_index}-{student_index}",
                    topic_id,
                    topic_code,
                )
            )
    submissions = [submission for group in submissions_by_class for submission in group]

    initialized = client.post(f"/api/teacher/assignments/{c['id']}/initialize-review-tasks")
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()["data"]["status"] == "REVIEWER_GRADING"
    assert [panel["task_count"] for panel in initialized.json()["data"]["panels"]] == [15, 15]

    high_risk_submission = submissions_by_class[1][0]
    reviewer_positions = {
        reviewer_id: position
        for reviewer_group in c["reviewers"]
        for position, reviewer_id in enumerate(reviewer_group)
    }
    normal_bases = {
        submissions_by_class[0][0]: 72,
        submissions_by_class[0][1]: 80,
        submissions_by_class[0][2]: 88,
        submissions_by_class[1][1]: 70,
        submissions_by_class[1][2]: 90,
    }
    with c["engine"].connect() as connection:
        task_rows = connection.execute(
            text("SELECT id,submission_id,reviewer_id FROM review_tasks ORDER BY id")
        ).mappings().all()
    score_by_task_id = {}
    normal_offsets = [-1, 0, 1, 0, 0]
    for task in task_rows:
        position = reviewer_positions[task["reviewer_id"]]
        if task["submission_id"] == high_risk_submission:
            score_by_task_id[task["id"]] = 10 if position == 0 else 80
        else:
            score_by_task_id[task["id"]] = normal_bases[task["submission_id"]] + normal_offsets[position]
    assert len(score_by_task_id) == 30
    _submit_panel_reviews(client, c["id"], c["reviewers"][1], score_by_task_id)
    _submit_panel_reviews(client, c["id"], c["reviewers"][0], score_by_task_id)

    aggregated = client.post(f"/api/teacher/assignments/{c['id']}/aggregate-reviews")
    assert aggregated.status_code == 200, aggregated.text
    assert all(panel["status"] == "COMPLETED" for panel in aggregated.json()["data"]["panels"])

    workspace = client.get(f"/api/teacher/assignments/{c['id']}/grading")
    assert workspace.status_code == 200, workspace.text
    rows = {item["id"]: item for item in workspace.json()["data"]["submissions"]}
    normal_review_statuses = {
        submission_id: rows[submission_id]["final_review_status"]
        for submission_id in submissions
        if submission_id != high_risk_submission
    }
    assert set(normal_review_statuses.values()) == {"NORMAL"}, normal_review_statuses
    assert (
        rows[high_risk_submission]["final_review_status"]
        == "ESCALATED_FOR_TEACHER_FINAL_REVIEW"
    )
    expected_score_by_submission = {
        submission_id: (
            87
            if submission_id == high_risk_submission
            else round(90 * 0.6 + float(rows[submission_id]["aggregate_score"]) * 0.4, 2)
        )
        for submission_id in submissions
    }
    rubric_item_id = workspace.json()["data"]["rubric_items"][0]["id"]
    for submission_id in submissions:
        grade = client.post(
            f"/api/teacher/submissions/{submission_id}/grades",
            json={
                "rubric_scores": [{"rubric_item_id": rubric_item_id, "score": 90}],
                "comment": "教师已完成评分与反馈。",
            },
        )
        assert grade.status_code == 201, grade.text
        locked = client.post(f"/api/teacher/grades/{grade.json()['data']['teacher_grade_id']}/lock")
        assert locked.status_code == 200, locked.text

    blocked = client.post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert blocked.status_code == 424
    anomalies = client.get(f"/api/teacher/assignments/{c['id']}/anomalies")
    assert anomalies.status_code == 200, anomalies.text
    medium_anomalies = [
        anomaly
        for anomaly in anomalies.json()["data"]
        if anomaly["risk_level"] == "MEDIUM" and anomaly["status"] == "OPEN"
    ]
    assert medium_anomalies
    for anomaly in medium_anomalies:
        resolved = client.post(
            f"/api/teacher/anomalies/{anomaly['id']}/resolve",
            json={"status": "DISMISSED", "note": "已核对评审行为证据。"},
        )
        assert resolved.status_code == 200, resolved.text
    final_review = client.post(
        f"/api/teacher/submissions/{high_risk_submission}/final-review",
        json={"final_score": 87, "reason": "已复核高风险离群评分与原始材料。"},
    )
    assert final_review.status_code == 201, final_review.text
    published = client.post(f"/api/teacher/assignments/{c['id']}/publish-results")
    assert published.status_code == 200, published.text
    assert published.json()["data"]["published_count"] == 6

    author_scores = {
        author: expected_score_by_submission[submission_id]
        for authors, submission_ids in zip(authors_by_class, submissions_by_class, strict=True)
        for author, submission_id in zip(authors, submission_ids, strict=True)
    }
    for author, expected_score in author_scores.items():
        with _as_student(author):
            result = client.get(f"/api/student/grades?assignment_id={c['id']}")
            assert result.status_code == 200, result.text
            data = result.json()["data"]
            assert float(data["final_score"]) == expected_score
            assert len(data["anonymous_comments"]) == 5
            assert set(data).isdisjoint(
                {"teacher_score", "aggregate_score", "anomalies", "reviewers"}
            )
