"""Freeze published programming content and validate final-review provenance."""

from alembic import op

revision = "20261009_0006"
down_revision = "20261008_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE reviewer_profiles ALTER COLUMN reliability TYPE NUMERIC(12,5);
    ALTER TABLE anomaly_records ALTER COLUMN risk_score TYPE NUMERIC(8,5);
    CREATE FUNCTION guard_programming_content() RETURNS trigger AS $$
    DECLARE aid BIGINT; state TEXT;
    BEGIN
      IF TG_TABLE_NAME='programming_problems' THEN
        aid := CASE WHEN TG_OP='DELETE' THEN OLD.assignment_id ELSE NEW.assignment_id END;
        IF TG_OP='UPDATE' AND NEW.assignment_id <> OLD.assignment_id THEN
          RAISE EXCEPTION 'problem ownership is immutable';
        END IF;
      ELSE
        aid := CASE WHEN TG_OP='DELETE' THEN OLD.problem_assignment_id ELSE NEW.problem_assignment_id END;
        IF TG_OP='UPDATE' AND NEW.problem_assignment_id <> OLD.problem_assignment_id THEN
          RAISE EXCEPTION 'test ownership is immutable';
        END IF;
      END IF;
      SELECT status INTO state FROM assignments WHERE id=aid FOR UPDATE;
      IF state IS NOT NULL AND state <> 'DRAFT' THEN
        RAISE EXCEPTION 'published programming content is immutable';
      END IF;
      IF EXISTS(SELECT 1 FROM code_submissions WHERE assignment_id=aid) THEN
        RAISE EXCEPTION 'submitted problem cannot change';
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_guard_programming_problem BEFORE INSERT OR UPDATE OR DELETE ON programming_problems
      FOR EACH ROW EXECUTE FUNCTION guard_programming_content();
    CREATE TRIGGER trg_guard_programming_case BEFORE INSERT OR UPDATE OR DELETE ON programming_test_cases
      FOR EACH ROW EXECUTE FUNCTION guard_programming_content();
    CREATE FUNCTION guard_final_grade_source() RETURNS trigger AS $$
    DECLARE review_state TEXT; review_row teacher_final_reviews%ROWTYPE;
    BEGIN
      SELECT final_review_status INTO review_state FROM submissions WHERE id=NEW.submission_id;
      IF review_state='ESCALATED_FOR_TEACHER_FINAL_REVIEW' THEN
        RAISE EXCEPTION 'teacher final review required';
      END IF;
      IF review_state='FINAL_REVIEW_LOCKED' AND NEW.final_grade_source <> 'TEACHER_FINAL_REVIEW' THEN
        RAISE EXCEPTION 'high risk submission requires final-review source';
      END IF;
      IF NEW.final_grade_source='NORMAL_BLEND' AND NEW.teacher_final_review_id IS NOT NULL THEN
        RAISE EXCEPTION 'normal blend cannot reference a final review';
      END IF;
      IF NEW.final_grade_source='TEACHER_FINAL_REVIEW' THEN
        SELECT * INTO review_row FROM teacher_final_reviews WHERE id=NEW.teacher_final_review_id;
        IF review_state <> 'FINAL_REVIEW_LOCKED' OR review_row.submission_id IS DISTINCT FROM NEW.submission_id THEN
          RAISE EXCEPTION 'invalid final review source';
        END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_guard_final_grade_source BEFORE INSERT ON final_grades
      FOR EACH ROW EXECUTE FUNCTION guard_final_grade_source();
    """)


def downgrade():
    op.execute("""
    -- Keep widened numeric columns: narrowing would discard valid historical results.
    DROP TRIGGER trg_guard_final_grade_source ON final_grades;
    DROP FUNCTION guard_final_grade_source();
    DROP TRIGGER trg_guard_programming_case ON programming_test_cases;
    DROP TRIGGER trg_guard_programming_problem ON programming_problems;
    DROP FUNCTION guard_programming_content();
    """)
