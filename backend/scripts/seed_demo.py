"""Create de-identified deterministic data for local integration and demonstrations.

Run inside the backend container after migrations:
    python scripts/seed_demo.py
It is deliberately small and idempotent enough for a fresh development database.
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionLocal


def scalar_id(db, statement: str, **params: object) -> int:
    return int(db.execute(text(statement), params).scalar_one())


def main() -> None:
    db = SessionLocal()
    try:
        teacher_id = scalar_id(
            db,
            """INSERT INTO users(student_no, name, password_hash, system_role)
               VALUES ('T001', '演示教师', 'DEMO_ONLY', 'TEACHER')
               ON CONFLICT (student_no) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
        )
        class_ids: dict[int, int] = {}
        for number in (1, 2):
            class_ids[number] = scalar_id(
                db,
                """INSERT INTO classes(name, course_term) VALUES (:name, '2026-秋')
                   ON CONFLICT (name, course_term) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
                name=f"算法设计与分析-{number}班",
            )

        students: dict[int, list[int]] = {1: [], 2: []}
        for class_number, class_id in class_ids.items():
            for index in range(1, 11):
                student_no = f"D{class_number}{index:02d}"
                user_id = scalar_id(
                    db,
                    """INSERT INTO users(student_no, name, password_hash, system_role)
                       VALUES (:student_no, :name, 'DEMO_ONLY', 'STUDENT')
                       ON CONFLICT (student_no) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
                    student_no=student_no,
                    name=f"{class_number}班学生{index:02d}",
                )
                db.execute(
                    text("INSERT INTO enrollments(user_id, class_id) VALUES (:user_id, :class_id) ON CONFLICT DO NOTHING"),
                    {"user_id": user_id, "class_id": class_id},
                )
                students[class_number].append(user_id)

        programming_assignment_id = db.execute(
            text("SELECT id FROM assignments WHERE title = '整数求和（编程题演示）' ORDER BY id LIMIT 1")
        ).scalar_one_or_none()
        if programming_assignment_id is None:
            programming_assignment_id = scalar_id(
                db,
                """INSERT INTO assignments(title, type, status, teacher_weight, designated_review_weight, created_by)
                   VALUES ('整数求和（编程题演示）', 'PROGRAMMING', 'PUBLISHED', 0.6, 0.4, :teacher_id)
                   RETURNING id""",
                teacher_id=teacher_id,
            )
            for class_id in class_ids.values():
                db.execute(
                    text("INSERT INTO assignment_classes(assignment_id, class_id) VALUES (:a, :c)"),
                    {"a": programming_assignment_id, "c": class_id},
                )
            db.execute(
                text(
                    """INSERT INTO programming_problems(
                         assignment_id, statement, input_description, output_description,
                         time_limit_ms, memory_limit_mb
                       ) VALUES (
                         :assignment_id, :statement, :input_description, :output_description, 2000, 256
                       )"""
                ),
                {
                    "assignment_id": programming_assignment_id,
                    "statement": "读入两个整数 a 和 b，输出它们的和 a + b。",
                    "input_description": "一行两个以空格分隔的整数 a、b。",
                    "output_description": "输出一个整数，表示 a + b。",
                },
            )
            for order, input_data, expected_output, is_public in (
                (1, "1 2\n", "3\n", True),
                (2, "-5 8\n", "3\n", True),
                (3, "0 0\n", "0\n", False),
                (4, "999999 -1\n", "999998\n", False),
                (5, "-123456 -654321\n", "-777777\n", False),
            ):
                db.execute(
                    text(
                        """INSERT INTO programming_test_cases(
                             problem_assignment_id, sort_order, input_data, expected_output, is_public
                           ) VALUES (:assignment_id, :sort_order, :input_data, :expected_output, :is_public)"""
                    ),
                    {
                        "assignment_id": programming_assignment_id,
                        "sort_order": order,
                        "input_data": input_data,
                        "expected_output": expected_output,
                        "is_public": is_public,
                    },
                )

        existing_assignment = db.execute(
            text("SELECT id FROM assignments WHERE title = '算法微课期末作业（演示）' ORDER BY id LIMIT 1")
        ).scalar_one_or_none()
        if existing_assignment is not None:
            db.commit()
            print(
                "Demo final-project seed already exists; programming problem is available: "
                f"assignment_id={programming_assignment_id}."
            )
            return

        assignment_id = scalar_id(
            db,
            """INSERT INTO assignments(title, type, status, teacher_weight, designated_review_weight, created_by)
               VALUES ('算法微课期末作业（演示）', 'FINAL_PROJECT', 'REVIEWER_GRADING', 0.6, 0.4, :teacher_id)
               RETURNING id""",
            teacher_id=teacher_id,
        )
        for class_id in class_ids.values():
            db.execute(text("INSERT INTO assignment_classes(assignment_id, class_id) VALUES (:a, :c)"), {"a": assignment_id, "c": class_id})
        rubric_id = scalar_id(
            db,
            "INSERT INTO rubrics(assignment_id, name, total_score) VALUES (:a, '微课评分量表', 100) RETURNING id",
            a=assignment_id,
        )
        for order, (name, max_score) in enumerate((("原理讲解", 30), ("例题与实现", 35), ("材料完整", 20), ("表达与规范", 15)), start=1):
            db.execute(text("INSERT INTO rubric_items(rubric_id, name, max_score, sort_order) VALUES (:r, :n, :m, :o)"), {"r": rubric_id, "n": name, "m": max_score, "o": order})

        topic_ids = list(db.execute(text("SELECT id FROM topics ORDER BY code")).scalars())
        if len(topic_ids) < 8:
            raise RuntimeError("the topic catalog must be seeded before demo data")

        for target_class, reviewer_class in ((1, 2), (2, 1)):
            panel_id = scalar_id(
                db,
                """INSERT INTO review_panels(assignment_id, target_class_id, reviewer_class_id, status)
                   VALUES (:assignment_id, :target, :reviewer, 'DRAFT') RETURNING id""",
                assignment_id=assignment_id, target=class_ids[target_class], reviewer=class_ids[reviewer_class],
            )
            for reviewer_id in students[reviewer_class][:5]:
                db.execute(text("INSERT INTO panel_reviewers(panel_id, reviewer_id) VALUES (:panel_id, :reviewer_id)"), {"panel_id": panel_id, "reviewer_id": reviewer_id})
            db.execute(text("UPDATE review_panels SET status = 'ACTIVE' WHERE id = :panel_id"), {"panel_id": panel_id})
            for sequence, author_id in enumerate(students[target_class][:8], start=1):
                topic_claim_id = scalar_id(
                    db,
                    """INSERT INTO topic_claims(assignment_id, student_id, topic_id)
                       VALUES (:assignment_id, :student_id, :topic_id)
                       ON CONFLICT (assignment_id, student_id) DO UPDATE SET topic_id = EXCLUDED.topic_id
                       RETURNING id""",
                    assignment_id=assignment_id,
                    student_id=author_id,
                    topic_id=topic_ids[sequence - 1],
                )
                submission_id = scalar_id(
                    db,
                    """INSERT INTO submissions(
                         assignment_id, author_id, class_id, status, anonymous_token, submitted_at, topic_claim_id
                       ) VALUES (
                         :assignment_id, :author_id, :class_id, 'VALID', :token, now(), :topic_claim_id
                       ) RETURNING id""",
                    assignment_id=assignment_id, author_id=author_id, class_id=class_ids[target_class], token=f"DEMO-{target_class}-{sequence:02d}", topic_claim_id=topic_claim_id,
                )
                db.execute(text("INSERT INTO material_checks(submission_id, status, checked_at) VALUES (:id, 'VALID', now())"), {"id": submission_id})
                for reviewer_id in students[reviewer_class][:5]:
                    db.execute(
                        text("""INSERT INTO review_tasks(panel_id, submission_id, reviewer_id, anonymous_token)
                                VALUES (:panel, :submission, :reviewer, :token)"""),
                        {"panel": panel_id, "submission": submission_id, "reviewer": reviewer_id, "token": f"DEMO-{target_class}-{sequence:02d}"},
                    )
        db.commit()
        print(f"Demo seed created: assignment_id={assignment_id}; two active panels; 80 review tasks.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
