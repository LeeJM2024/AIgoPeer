"""Learning reports own their snapshot even after caller authorization queries."""

from app.services.learning_analytics import get_learning_report
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_report_can_follow_existing_queries_without_changing_caller_transaction(pg_engine):
    with Session(pg_engine) as caller:
        caller.execute(text("SELECT 1"))
        transaction = caller.get_transaction()
        report = get_learning_report(caller)
        assert report["assignment_count"] == report["code_attempt_count"] == 0
        assert caller.get_transaction() is transaction
        assert caller.execute(text("SHOW transaction_isolation")).scalar_one() == "read committed"
        assert caller.execute(text("SHOW transaction_read_only")).scalar_one() == "off"
