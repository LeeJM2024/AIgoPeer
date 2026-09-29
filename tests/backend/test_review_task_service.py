import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.schemas.review import InitializeRequest, PanelInput
from app.services.review_task_service import build_task_plan


def test_fixed_five_reviewers_receive_every_valid_submission() -> None:
    request = InitializeRequest(
        assignment_id=1,
        panel=PanelInput(panel_id=11, target_class_id=1, reviewer_class_id=2, reviewer_ids=[21, 22, 23, 24, 25]),
        valid_submission_ids=list(range(101, 109)),
    )
    plan = build_task_plan(request)

    assert plan.expected_task_count == 40
    assert len(plan.tasks) == 40
    assert {task.reviewer_id for task in plan.tasks} == {21, 22, 23, 24, 25}
    assert {task.submission_id for task in plan.tasks} == set(range(101, 109))
