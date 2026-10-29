"""Descriptive learning indicators, not inferred student ability or causal difficulty."""

from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

JUDGED = {"AC", "WA", "TLE", "RE", "CE"}


def summarize_learning(assignments, roster, codes, works, tags, claims):
    by_code, by_work, students = defaultdict(list), defaultdict(list), defaultdict(set)
    topic_ids, topic_meta = defaultdict(set), {}
    for row in roster:
        students[row["assignment_id"]].add(row["student_id"])
    for row in codes:
        by_code[row["assignment_id"]].append(row)
    for row in works:
        by_work[row["assignment_id"]].append(row)
    for row in tags:
        topic_ids[row["assignment_id"]].add(row["topic_id"])
        topic_meta[row["topic_id"]] = row
    claim_topics = {}
    for row in claims:
        claim_topics[(row["assignment_id"], row["student_id"])] = row["topic_id"]
        topic_meta[row["topic_id"]] = row
    knowledge = defaultdict(list)
    rows = []
    for assignment in assignments:
        aid = assignment["id"]
        code = by_code[aid]
        work = by_work[aid]
        cohort = students[aid]
        row = {
            "id": aid,
            "title": assignment["title"],
            "type": assignment["type"],
            "enrolled_students": len(cohort),
            "maximum_score": assignment["maximum_score"],
        }
        if assignment["type"] == "PROGRAMMING":
            judged = [item for item in code if item["status"] in JUDGED]
            judged_students = {item["author_id"] for item in judged}
            ever_passed = {item["author_id"] for item in judged if item["status"] == "AC"}
            current = [item for item in code if item["is_current"]]
            row.update(
                {
                    "submission_count": len(code),
                    "submitted_students": len({item["author_id"] for item in code}),
                    "judged_students": len(judged_students),
                    "passed_students": len(ever_passed),
                    "current_passed_students": sum(item["status"] == "AC" for item in current),
                    "ac_rate": round(len(ever_passed) / len(judged_students), 4)
                    if judged_students
                    else None,
                    "difficulty": round(1 - len(ever_passed) / len(judged_students), 4)
                    if judged_students
                    else None,
                    "average_attempts": round(
                        len(code) / len({item["author_id"] for item in code}), 2
                    )
                    if code
                    else None,
                    "error_counts": dict(
                        Counter(item["status"] for item in judged if item["status"] != "AC")
                    ),
                    "system_errors": sum(item["status"] == "SYSTEM_ERROR" for item in code),
                    "pending_count": sum(item["status"] in {"QUEUED", "RUNNING"} for item in code),
                    "average_time_ms": _average([item["time_ms"] for item in judged]),
                    "peak_memory_kb": max(
                        (item["memory_kb"] for item in judged if item["memory_kb"] is not None),
                        default=None,
                    ),
                    "published_count": 0,
                    "average_score": None,
                }
            )
            evidence = [
                (item["author_id"], float(item["status"] == "AC"))
                for item in current
                if item["status"] in JUDGED
            ]
        else:
            current = [item for item in work if item["is_current"]]
            published = [item for item in current if item["final_score"] is not None] if assignment["type"] == "FINAL_PROJECT" else []
            if assignment["type"] != "FINAL_PROJECT":
                row["maximum_score"] = None
            row.update(
                {
                    "submission_count": len(work),
                    "submitted_students": len({item["author_id"] for item in current}),
                    "published_count": len(published),
                    "average_score": _average([item["final_score"] for item in published]),
                    "ac_rate": None,
                    "difficulty": None,
                    "error_counts": {},
                }
            )
            maximum = float(assignment["maximum_score"])
            evidence = [
                (item["author_id"], float(item["final_score"]) / maximum)
                for item in published
                if maximum > 0
            ]
        row["unsubmitted_students"] = len(cohort - {item["author_id"] for item in current})
        rows.append(row)
        for student, value in evidence:
            linked = set(topic_ids[aid])
            claim = claim_topics.get((aid, student))
            if claim is not None:
                linked.add(claim)
            for topic in linked:
                knowledge[topic].append((student, aid, value))
    topic_rows = []
    for tid, meta in topic_meta.items():
        samples = knowledge[tid]
        topic_rows.append(
            {
                "id": tid,
                "code": meta["code"],
                "name": meta["name"],
                "evidence_count": len(samples),
                "student_count": len({item[0] for item in samples}),
                "assignment_count": len({item[1] for item in samples}),
                "mastery": round(sum(item[2] for item in samples) / len(samples), 4)
                if samples
                else None,
            }
        )
    return {
        "assignments": rows,
        "topics": sorted(topic_rows, key=lambda item: item["code"]),
        "generated_at": datetime.now(UTC),
        "assignment_count": len(rows),
        "code_attempt_count": len(codes),
        "error_counts": dict(
            Counter(item["status"] for item in codes if item["status"] in JUDGED - {"AC"})
        ),
        "definitions": {
            "ac_rate": "曾通过人数 / 至少有一次有效判题的提交人数；未提交者另列，不计入分母。",
            "difficulty": "1 − AC率，仅为本次提交样本的描述性难度，不是题目固有难度。",
            "mastery": "当前有效判题 AC=1、WA/TLE/RE/CE=0；期末微课作业取已发布分/满分；仅作答题不计算分数或掌握率，按学生-作业等权平均。",
            "missing": "未提交、排队、系统故障、未发布成绩不当作零分；历史代码用于尝试次数和错误统计，不重复计入掌握度。",
        },
    }


def _average(values):
    values = [float(value) for value in values if value is not None]
    return round(sum(values) / len(values), 2) if values else None


def get_learning_report(db, class_id=None):
    # The caller may already have authenticated or loaded a class. Own the report
    # transaction so its snapshot never depends on the caller's transaction state.
    with Session(bind=db.get_bind()) as report_db:
        return _read_learning_report(report_db, class_id)


def _read_learning_report(db, class_id):
    # One read-only repeatable snapshot keeps denominators and evidence coherent.
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    params = {"class_id": class_id}
    assignments = list(
        db.execute(
            text("""
        SELECT a.id,a.title,a.type,COALESCE((SELECT sum(ri.max_score) FROM rubric_items ri
          JOIN rubrics r ON r.id=ri.rubric_id WHERE r.assignment_id=a.id),0) AS maximum_score
        FROM assignments a WHERE a.status <> 'DRAFT' AND a.deleted_at IS NULL AND EXISTS (
          SELECT 1 FROM assignment_classes ac WHERE ac.assignment_id=a.id
          AND (CAST(:class_id AS bigint) IS NULL OR ac.class_id=:class_id)) ORDER BY a.id
    """),
            params,
        ).mappings()
    )
    ids = [item["id"] for item in assignments]
    params["ids"] = ids

    def read(sql):
        return list(db.execute(text(sql), params).mappings())

    roster = read("""SELECT DISTINCT ac.assignment_id,e.user_id AS student_id
        FROM assignment_classes ac JOIN enrollments e ON e.class_id=ac.class_id
        JOIN users u ON u.id=e.user_id WHERE ac.assignment_id=ANY(:ids) AND u.system_role='STUDENT'
        AND (CAST(:class_id AS bigint) IS NULL OR ac.class_id=:class_id)""")
    codes = read("""SELECT assignment_id,author_id,status,is_current,time_ms,memory_kb
        FROM code_submissions WHERE assignment_id=ANY(:ids)
        AND (CAST(:class_id AS bigint) IS NULL OR class_id=:class_id)""")
    works = read("""SELECT s.assignment_id,s.author_id,s.is_current,f.final_score
        FROM submissions s LEFT JOIN final_grades f ON f.submission_id=s.id
        WHERE s.assignment_id=ANY(:ids)
        AND (CAST(:class_id AS bigint) IS NULL OR s.class_id=:class_id)""")
    tags = read("""SELECT x.assignment_id,t.id AS topic_id,t.code,t.name FROM assignment_topics x
        JOIN topics t ON t.id=x.topic_id WHERE x.assignment_id=ANY(:ids)""")
    claims = read("""SELECT x.assignment_id,x.student_id,t.id AS topic_id,t.code,t.name
        FROM topic_claims x JOIN topics t ON t.id=x.topic_id WHERE x.assignment_id=ANY(:ids)
        AND (CAST(:class_id AS bigint) IS NULL OR EXISTS(SELECT 1 FROM enrollments e
          WHERE e.user_id=x.student_id AND e.class_id=:class_id))""")
    return summarize_learning(assignments, roster, codes, works, tags, claims)
