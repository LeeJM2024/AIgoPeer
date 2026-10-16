"""Teacher-owned problem configuration. Callers hold the assignment lock."""

from sqlalchemy import text


def save_programming_problem(db, assignment_id, problem):
    db.execute(
        text("DELETE FROM programming_problems WHERE assignment_id=:id"), {"id": assignment_id}
    )
    if problem is None:
        return
    db.execute(
        text("""INSERT INTO programming_problems
        (assignment_id,statement,input_description,output_description,time_limit_ms,memory_limit_mb)
        VALUES (:id,:statement,:input_description,:output_description,:time_limit_ms,:memory_limit_mb)
    """),
        {"id": assignment_id, **problem.model_dump(exclude={"test_cases"})},
    )
    for order, case in enumerate(problem.test_cases, 1):
        db.execute(
            text("""INSERT INTO programming_test_cases
            (problem_assignment_id,sort_order,input_data,expected_output,is_public)
            VALUES (:id,:order,:input_data,:expected_output,:is_public)
        """),
            {"id": assignment_id, "order": order, **case.model_dump()},
        )


def get_programming_problem(db, assignment_id):
    row = (
        db.execute(
            text("SELECT * FROM programming_problems WHERE assignment_id=:id"),
            {"id": assignment_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    cases = db.execute(
        text("""SELECT input_data,expected_output,is_public FROM programming_test_cases
        WHERE problem_assignment_id=:id ORDER BY sort_order"""),
        {"id": assignment_id},
    ).mappings()
    return {**dict(row), "test_cases": [dict(c) for c in cases]}
