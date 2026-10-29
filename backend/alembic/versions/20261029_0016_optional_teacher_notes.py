"""Allow optional teacher grading and risk-review notes."""

from sqlalchemy import text

from alembic import op

revision = "20261029_0016"
down_revision = "20261029_0015"
branch_labels = None
depends_on = None


def _grade_guard(require_reason: bool) -> None:
    correction_check = (
        "(previous_locked IS NULL OR length(trim(COALESCE(NEW.correction_reason, ''))) < 3)"
        if require_reason
        else "previous_locked IS NULL"
    )
    message = (
        "correction requires locked previous version and reason"
        if require_reason
        else "correction requires locked previous version"
    )
    op.execute(f"""
        CREATE OR REPLACE FUNCTION guard_teacher_grade_write() RETURNS trigger AS $$
        DECLARE assignment_state TEXT; previous_version INTEGER; previous_locked TIMESTAMPTZ;
        BEGIN
          SELECT a.status INTO assignment_state FROM assignments a
          JOIN submissions s ON s.assignment_id = a.id WHERE s.id = NEW.submission_id
          FOR UPDATE OF a;
          IF assignment_state = 'PUBLISHED_RESULT' THEN
            RAISE EXCEPTION 'published teacher grades are frozen';
          END IF;
          SELECT version, locked_at INTO previous_version, previous_locked FROM teacher_grades
            WHERE submission_id = NEW.submission_id ORDER BY version DESC LIMIT 1;
          IF TG_OP = 'INSERT' THEN
            IF NEW.version <> COALESCE(previous_version, 0) + 1 THEN
              RAISE EXCEPTION 'teacher grade version must be sequential';
            END IF;
            IF previous_version IS NOT NULL AND {correction_check} THEN
              RAISE EXCEPTION '{message}';
            END IF;
          ELSIF NEW.version <> previous_version THEN
            RAISE EXCEPTION 'only latest teacher grade can be locked';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)


def upgrade() -> None:
    op.execute("""
        ALTER TABLE teacher_final_reviews
        DROP CONSTRAINT teacher_final_reviews_reason_check;
    """)
    _grade_guard(require_reason=False)


def downgrade() -> None:
    # Preserve submitted notes and immutable score history on rollback.
    incompatible = op.get_bind().execute(text("""
        SELECT EXISTS(
          SELECT 1 FROM teacher_final_reviews WHERE length(trim(reason)) < 3
          UNION ALL
          SELECT 1 FROM teacher_grades
          WHERE version > 1 AND length(trim(COALESCE(correction_reason, ''))) < 3
        )
    """)).scalar_one()
    if incompatible:
        raise RuntimeError("Cannot restore mandatory notes while optional-note grades exist")
    _grade_guard(require_reason=True)
    op.execute("""
        ALTER TABLE teacher_final_reviews ADD CONSTRAINT teacher_final_reviews_reason_check
        CHECK(length(trim(reason)) >= 3);
    """)
