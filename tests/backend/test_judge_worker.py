"""Completion timestamps must reflect wall time even in a long transaction."""
import pytest
from app.services.judge_runner import JudgeRunResult
from app.workers.judge_worker import _retry_or_fail, _store_result
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.mark.parametrize("status", ["AC", "TLE", "CE", "SYSTEM_ERROR"])
def test_completion_timestamp_is_after_work_in_existing_transaction(pg_engine, status):
    with pg_engine.connect() as connection, Session(bind=connection) as db:
        # A temporary table shadows the application table only on this connection.
        db.execute(text("""CREATE TEMP TABLE code_submissions (
            id integer, status text, finished_at timestamptz, updated_at timestamptz,
            time_ms integer, memory_kb integer, executed_case_count integer,
            passed_case_count integer, compiler_output text)"""))
        db.execute(text("INSERT INTO code_submissions(id,status) VALUES (1,'RUNNING')"))
        db.commit()
        transaction_start = db.execute(text("SELECT now()")).scalar_one()
        db.execute(text("SELECT pg_sleep(0.12)"))
        completed_after = db.execute(text("SELECT clock_timestamp()")).scalar_one()
        if status == "SYSTEM_ERROR":
            assert _retry_or_fail(db, 1, 1) is False
        else:
            _store_result(db, 1, JudgeRunResult(status, 1, int(status == "AC"), 10, 4096))
        row = db.execute(text("SELECT * FROM code_submissions WHERE id=1")).mappings().one()
        assert row["status"] == status
        assert row["finished_at"] >= completed_after
        assert row["updated_at"] >= completed_after
        assert (row["finished_at"] - transaction_start).total_seconds() >= 0.12
