from app.schemas.review import AllocationWorkInput, InitializeRequest
from app.services.review_task_service import build_task_plan


def test_joint_random_plan_covers_all_works_with_distinct_cross_class_reviews():
    request = InitializeRequest(
        assignment_id=1,
        seed=22,
        works=[
            AllocationWorkInput(
                submission_id=i, author_id=i, class_id=1 if i <= 10 else 2
            )
            for i in range(1, 21)
        ],
    )
    plan = build_task_plan(request)
    assert len(plan.tasks) == plan.expected_task_count == 100
    pairs = {(t.reviewer_id, t.submission_id) for t in plan.tasks}
    assert all((v, u) not in pairs for u, v in pairs)
    assert len({t.reviewer_id for t in plan.tasks}) == 20
