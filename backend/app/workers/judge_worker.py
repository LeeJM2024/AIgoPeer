"""Redis consumer for isolated programming-submission judging."""

from __future__ import annotations

import logging
import time
from threading import Thread

from redis.exceptions import RedisError
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.judge_queue import enqueue_submission, queue_client
from app.services.judge_runner import JudgeCase, JudgeInfrastructureError, run_cpp17_submission

logger = logging.getLogger(__name__)


def _claim_submission(db, submission_id: int):
    return db.execute(
        text(
            """
            UPDATE code_submissions
            SET status = 'RUNNING', started_at = now(), updated_at = now()
            WHERE id = :submission_id AND status = 'QUEUED'
            RETURNING id, source_code, retry_count, assignment_id
            """
        ),
        {"submission_id": submission_id},
    ).mappings().one_or_none()


def _load_problem_and_cases(db, assignment_id: int):
    problem = db.execute(
        text(
            """
            SELECT time_limit_ms, memory_limit_mb
            FROM programming_problems WHERE assignment_id = :assignment_id
            """
        ),
        {"assignment_id": assignment_id},
    ).mappings().one_or_none()
    if problem is None:
        raise JudgeInfrastructureError("programming problem is missing")
    cases = db.execute(
        text(
            """
            SELECT input_data, expected_output FROM programming_test_cases
            WHERE problem_assignment_id = :assignment_id ORDER BY sort_order
            """
        ),
        {"assignment_id": assignment_id},
    ).mappings().all()
    return problem, [JudgeCase(**case) for case in cases]


def _store_result(db, submission_id: int, result) -> None:
    db.execute(
        text(
            """
            UPDATE code_submissions
            SET status = :status, finished_at = now(), time_ms = :time_ms, memory_kb = :memory_kb,
                executed_case_count = :executed_case_count, passed_case_count = :passed_case_count,
                compiler_output = :compiler_output, updated_at = now()
            WHERE id = :submission_id
            """
        ),
        {
            "submission_id": submission_id,
            "status": result.status,
            "time_ms": result.time_ms,
            "memory_kb": result.memory_kb,
            "executed_case_count": result.executed_case_count,
            "passed_case_count": result.passed_case_count,
            "compiler_output": result.compiler_output,
        },
    )
    db.commit()


def _retry_or_fail(db, submission_id: int, retry_count: int) -> bool:
    if retry_count < 1:
        db.execute(
            text(
                """
                UPDATE code_submissions
                SET status = 'QUEUED', retry_count = retry_count + 1, updated_at = now()
                WHERE id = :submission_id
                """
            ),
            {"submission_id": submission_id},
        )
        db.commit()
        enqueue_submission(submission_id)
        return True
    db.execute(
        text(
            """
            UPDATE code_submissions
            SET status = 'SYSTEM_ERROR', finished_at = now(), updated_at = now()
            WHERE id = :submission_id
            """
        ),
        {"submission_id": submission_id},
    )
    db.commit()
    return False


def process_submission(submission_id: int) -> None:
    db = SessionLocal()
    try:
        claimed = _claim_submission(db, submission_id)
        db.commit()
        if claimed is None:
            return
        try:
            problem, cases = _load_problem_and_cases(db, int(claimed["assignment_id"]))
            result = run_cpp17_submission(
                submission_id=submission_id,
                source_code=str(claimed["source_code"]),
                cases=cases,
                time_limit_ms=int(problem["time_limit_ms"]),
                memory_limit_mb=int(problem["memory_limit_mb"]),
            )
            _store_result(db, submission_id, result)
        except JudgeInfrastructureError:
            db.rollback()
            retried = _retry_or_fail(db, submission_id, int(claimed["retry_count"]))
            logger.warning("judge infrastructure error for submission %s; retried=%s", submission_id, retried)
        except Exception:
            db.rollback()
            retried = _retry_or_fail(db, submission_id, int(claimed["retry_count"]))
            logger.exception("unexpected judge failure for submission %s; retried=%s", submission_id, retried)
    except Exception:
        db.rollback()
        logger.exception("unexpected judge worker failure for submission %s", submission_id)
    finally:
        db.close()


def consume_queue() -> None:
    client = queue_client()
    logger.info("judge queue consumer started; queue=%s", settings.judge_queue_name)
    while True:
        try:
            item = client.blpop(settings.judge_queue_name, timeout=5)
            if item is None:
                continue
            _queue_name, raw_submission_id = item
            process_submission(int(raw_submission_id))
        except (RedisError, ValueError):
            logger.exception("judge queue is temporarily unavailable")
            time.sleep(2)


def main() -> None:
    worker_count = max(1, settings.judge_worker_concurrency)
    logger.info("judge worker started; concurrency=%s", worker_count)
    if worker_count == 1:
        consume_queue()
        return
    consumers = [Thread(target=consume_queue, daemon=False) for _ in range(worker_count)]
    for consumer in consumers:
        consumer.start()
    for consumer in consumers:
        consumer.join()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
