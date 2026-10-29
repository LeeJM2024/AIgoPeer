"""Online subjective work and explicit assignment knowledge-point tags."""

from alembic import op

revision = "20261022_0009"
down_revision = "20261010_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE assignments DROP CONSTRAINT assignments_type_check;
    ALTER TABLE assignments ADD CONSTRAINT assignments_type_check CHECK
      (type IN ('PROGRAMMING','FINAL_PROJECT','ALGORITHM_ANALYSIS','PROOF','OPEN_ENDED'));
    ALTER TABLE assignments ADD COLUMN statement TEXT NOT NULL DEFAULT '';
    ALTER TABLE assignments ADD CONSTRAINT assignments_subjective_statement_check CHECK
      (type NOT IN ('ALGORITHM_ANALYSIS','PROOF','OPEN_ENDED') OR length(trim(statement)) > 0);
    CREATE TABLE assignment_topics (
      assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
      topic_id BIGINT NOT NULL REFERENCES topics(id), PRIMARY KEY (assignment_id,topic_id)
    );
    CREATE INDEX ix_assignment_topics_topic ON assignment_topics(topic_id);
    CREATE TABLE subjective_answers (
      submission_id BIGINT PRIMARY KEY REFERENCES submissions(id),
      content TEXT NOT NULL CHECK (length(trim(content)) BETWEEN 1 AND 50000)
    );
    CREATE FUNCTION guard_subjective_content() RETURNS trigger AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'subjective answer versions are immutable';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM submissions s JOIN assignments a ON a.id=s.assignment_id
        WHERE s.id=NEW.submission_id AND s.is_current AND s.status='VALID'
          AND a.type IN ('ALGORITHM_ANALYSIS','PROOF','OPEN_ENDED')
          AND a.status IN ('PUBLISHED','SUBMITTING')
          AND (a.submit_deadline IS NULL OR a.submit_deadline > clock_timestamp())) THEN
        RAISE EXCEPTION 'subjective submission is not open';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_subjective_content BEFORE INSERT OR UPDATE OR DELETE ON subjective_answers
      FOR EACH ROW EXECUTE FUNCTION guard_subjective_content();
    CREATE FUNCTION guard_assignment_learning_content() RETURNS trigger AS $$
    DECLARE aid BIGINT; state TEXT;
    BEGIN
      IF TG_TABLE_NAME='assignments' THEN
        IF OLD.status <> 'DRAFT' AND NEW.statement IS DISTINCT FROM OLD.statement THEN
          RAISE EXCEPTION 'published statement is immutable';
        END IF;
        RETURN NEW;
      END IF;
      aid := CASE WHEN TG_OP='DELETE' THEN OLD.assignment_id ELSE NEW.assignment_id END;
      IF TG_OP='UPDATE' AND NEW.assignment_id <> OLD.assignment_id THEN
        RAISE EXCEPTION 'topic ownership is immutable';
      END IF;
      SELECT status INTO state FROM assignments WHERE id=aid FOR UPDATE;
      IF state <> 'DRAFT' THEN RAISE EXCEPTION 'published topic tags are immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_assignment_statement BEFORE UPDATE ON assignments
      FOR EACH ROW EXECUTE FUNCTION guard_assignment_learning_content();
    CREATE TRIGGER trg_assignment_topics BEFORE INSERT OR UPDATE OR DELETE ON assignment_topics
      FOR EACH ROW EXECUTE FUNCTION guard_assignment_learning_content();
    CREATE OR REPLACE FUNCTION guard_fixed_review_policy() RETURNS trigger AS $$
    BEGIN
      IF NEW.type <> 'PROGRAMMING' AND
        (NEW.teacher_weight <> .6 OR NEW.designated_review_weight <> .4) THEN
        IF TG_OP='UPDATE' AND OLD.status='PUBLISHED_RESULT' AND NEW.status=OLD.status
          AND NEW.teacher_weight=OLD.teacher_weight
          AND NEW.designated_review_weight=OLD.designated_review_weight THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'reviewed assignment weights must be 0.60/0.40';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """)


def downgrade():
    # Refuse a lossy downgrade while any new business records exist.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM assignments WHERE type NOT IN ('PROGRAMMING','FINAL_PROJECT')) THEN
        RAISE EXCEPTION 'new subjective assignments must be preserved; downgrade refused';
      END IF;
    END $$;
    DROP TABLE subjective_answers, assignment_topics;
    DROP TRIGGER trg_assignment_statement ON assignments;
    DROP FUNCTION guard_subjective_content(), guard_assignment_learning_content();
    ALTER TABLE assignments DROP CONSTRAINT assignments_subjective_statement_check;
    ALTER TABLE assignments DROP COLUMN statement;
    ALTER TABLE assignments DROP CONSTRAINT assignments_type_check;
    ALTER TABLE assignments ADD CONSTRAINT assignments_type_check
      CHECK (type IN ('PROGRAMMING','FINAL_PROJECT'));
    """)
