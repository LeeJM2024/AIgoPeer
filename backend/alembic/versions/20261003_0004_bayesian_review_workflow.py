"""Bayesian aggregation persistence and teacher final-review grades.

Revision ID: 20261003_0004
Revises: 20260930_0003
"""

from alembic import op

revision = "20261003_0004"
down_revision = "20260930_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE submissions ADD COLUMN final_review_status VARCHAR(48) NOT NULL DEFAULT 'NORMAL'
      CHECK (final_review_status IN ('NORMAL','ESCALATED_FOR_TEACHER_FINAL_REVIEW','FINAL_REVIEW_LOCKED'));
    CREATE TABLE teacher_final_reviews (
      id BIGSERIAL PRIMARY KEY, submission_id BIGINT NOT NULL UNIQUE REFERENCES submissions(id),
      algorithm_run_id BIGINT NOT NULL REFERENCES algorithm_runs(id), final_score NUMERIC(7,2) NOT NULL CHECK(final_score >= 0),
      reason TEXT NOT NULL CHECK(length(trim(reason)) >= 3), entered_by BIGINT NOT NULL REFERENCES users(id),
      locked_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    ALTER TABLE final_grades ADD COLUMN final_grade_source VARCHAR(32) NOT NULL DEFAULT 'NORMAL_BLEND'
      CHECK(final_grade_source IN ('NORMAL_BLEND','TEACHER_FINAL_REVIEW'));
    ALTER TABLE final_grades ADD COLUMN teacher_final_review_id BIGINT REFERENCES teacher_final_reviews(id);
    ALTER TABLE anomaly_records DROP CONSTRAINT IF EXISTS anomaly_records_risk_score_check;
    ALTER TABLE anomaly_records ADD CONSTRAINT anomaly_records_risk_score_check CHECK(risk_score >= 0 AND risk_score <= 100);
    CREATE FUNCTION guard_teacher_final_review() RETURNS trigger AS $$
    DECLARE state TEXT; maximum NUMERIC; run_assignment BIGINT;
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'teacher final reviews are immutable'; END IF;
      SELECT a.status INTO state FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE s.id=NEW.submission_id FOR UPDATE OF a;
      SELECT COALESCE(sum(ri.max_score),0) INTO maximum FROM submissions s JOIN rubrics r ON r.assignment_id=s.assignment_id
        JOIN rubric_items ri ON ri.rubric_id=r.id WHERE s.id=NEW.submission_id;
      IF state <> 'TEACHER_GRADING' THEN RAISE EXCEPTION 'assignment is not ready for final review'; END IF;
      IF NOT EXISTS(SELECT 1 FROM submissions WHERE id=NEW.submission_id AND final_review_status='ESCALATED_FOR_TEACHER_FINAL_REVIEW') THEN RAISE EXCEPTION 'submission is not escalated'; END IF;
      SELECT assignment_id INTO run_assignment FROM algorithm_runs WHERE id=NEW.algorithm_run_id AND status='COMPLETED';
      IF run_assignment IS NULL OR NEW.final_score > maximum OR NOT EXISTS(SELECT 1 FROM anomaly_records WHERE submission_id=NEW.submission_id AND algorithm_run_id=NEW.algorithm_run_id AND risk_level='HIGH') THEN RAISE EXCEPTION 'invalid final review score or run'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_guard_teacher_final_review BEFORE INSERT OR UPDATE OR DELETE ON teacher_final_reviews FOR EACH ROW EXECUTE FUNCTION guard_teacher_final_review();
    CREATE OR REPLACE FUNCTION guard_final_grade() RETURNS trigger AS $$
    DECLARE a assignments%ROWTYPE; grade teacher_grades%ROWTYPE; aggregate_score NUMERIC; reviewed_score NUMERIC;
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'published results are immutable'; END IF;
      SELECT x.* INTO a FROM assignments x JOIN submissions s ON s.assignment_id=x.id WHERE s.id=NEW.submission_id FOR UPDATE OF x;
      IF a.status <> 'TEACHER_GRADING' THEN RAISE EXCEPTION 'assignment is not ready for publication'; END IF;
      SELECT * INTO grade FROM teacher_grades WHERE submission_id=NEW.submission_id ORDER BY version DESC LIMIT 1;
      IF grade.id IS NULL OR grade.id <> NEW.teacher_grade_id OR grade.locked_at IS NULL THEN RAISE EXCEPTION 'publication requires latest locked teacher grade'; END IF;
      SELECT total_score INTO aggregate_score FROM designated_review_aggregates WHERE id=NEW.aggregate_id AND submission_id=NEW.submission_id;
      IF aggregate_score IS NULL OR NEW.teacher_weight <> a.teacher_weight OR NEW.designated_review_weight <> a.designated_review_weight THEN RAISE EXCEPTION 'invalid aggregate or weight snapshot'; END IF;
      IF NEW.final_grade_source='NORMAL_BLEND' AND NEW.final_score <> round(grade.total_score*NEW.teacher_weight+aggregate_score*NEW.designated_review_weight,2) THEN RAISE EXCEPTION 'incorrect blended final score'; END IF;
      IF NEW.final_grade_source='TEACHER_FINAL_REVIEW' THEN
        SELECT final_score INTO reviewed_score FROM teacher_final_reviews WHERE id=NEW.teacher_final_review_id AND submission_id=NEW.submission_id AND locked_at IS NOT NULL;
        IF reviewed_score IS NULL OR NEW.final_score <> reviewed_score THEN RAISE EXCEPTION 'locked teacher final review required'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TRIGGER IF EXISTS trg_guard_teacher_final_review ON teacher_final_reviews;
    DROP FUNCTION IF EXISTS guard_teacher_final_review();
    DROP TRIGGER IF EXISTS trg_guard_final_grade ON final_grades;
    ALTER TABLE final_grades DROP COLUMN teacher_final_review_id, DROP COLUMN final_grade_source;
    DROP TABLE teacher_final_reviews;
    ALTER TABLE anomaly_records DROP CONSTRAINT IF EXISTS anomaly_records_risk_score_check;
    ALTER TABLE anomaly_records ADD CONSTRAINT anomaly_records_risk_score_check CHECK(risk_score >= 0 AND risk_score <= 1);
    ALTER TABLE submissions DROP COLUMN final_review_status;
    CREATE OR REPLACE FUNCTION guard_final_grade() RETURNS trigger AS $$
    DECLARE a assignments%ROWTYPE; grade teacher_grades%ROWTYPE; aggregate_score NUMERIC;
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'published results are immutable'; END IF;
      SELECT x.* INTO a FROM assignments x JOIN submissions s ON s.assignment_id=x.id
        WHERE s.id=NEW.submission_id FOR UPDATE OF x;
      IF a.status <> 'TEACHER_GRADING' THEN RAISE EXCEPTION 'assignment is not ready for publication'; END IF;
      SELECT * INTO grade FROM teacher_grades WHERE submission_id=NEW.submission_id
        ORDER BY version DESC LIMIT 1;
      IF grade.id IS NULL OR grade.id <> NEW.teacher_grade_id OR grade.locked_at IS NULL THEN
        RAISE EXCEPTION 'publication requires latest locked teacher grade';
      END IF;
      SELECT ag.total_score INTO aggregate_score FROM designated_review_aggregates ag
        WHERE ag.id=NEW.aggregate_id AND ag.submission_id=NEW.submission_id;
      IF aggregate_score IS NULL THEN RAISE EXCEPTION 'aggregate must match submission'; END IF;
      IF NEW.teacher_weight <> a.teacher_weight OR NEW.designated_review_weight <> a.designated_review_weight OR
         NEW.final_score <> round(grade.total_score * NEW.teacher_weight + aggregate_score * NEW.designated_review_weight, 2)
      THEN RAISE EXCEPTION 'incorrect publication weights or final score'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_guard_final_grade BEFORE INSERT OR UPDATE OR DELETE ON final_grades
      FOR EACH ROW EXECUTE FUNCTION guard_final_grade();
    """)
