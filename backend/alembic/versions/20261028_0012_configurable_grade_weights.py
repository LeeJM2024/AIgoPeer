"""Allow draft grading weights to be configured, preserving published snapshots."""

from alembic import op

revision = "20261028_0012"
down_revision = "20261028_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    DROP TRIGGER trg_fixed_review_policy ON assignments;
    DROP FUNCTION guard_fixed_review_policy();
    CREATE OR REPLACE FUNCTION guard_review_policy_publication() RETURNS trigger AS $$
    BEGIN
      PERFORM a.id FROM assignments a JOIN submissions s ON s.assignment_id=a.id
        WHERE s.id=NEW.submission_id FOR UPDATE OF a;
      IF EXISTS(SELECT 1 FROM anomaly_records WHERE submission_id=NEW.submission_id AND status='OPEN') THEN
        RAISE EXCEPTION 'all anomalies require explicit resolution';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """)


def downgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM assignments WHERE type <> 'PROGRAMMING'
        AND (teacher_weight <> .6 OR designated_review_weight <> .4)) THEN
        RAISE EXCEPTION 'configured grading weights must be preserved; downgrade refused';
      END IF;
    END $$;
    CREATE FUNCTION guard_fixed_review_policy() RETURNS trigger AS $$
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
    CREATE TRIGGER trg_fixed_review_policy BEFORE INSERT OR UPDATE ON assignments
      FOR EACH ROW EXECUTE FUNCTION guard_fixed_review_policy();
    CREATE OR REPLACE FUNCTION guard_review_policy_publication() RETURNS trigger AS $$
    BEGIN
      PERFORM a.id FROM assignments a JOIN submissions s ON s.assignment_id=a.id
        WHERE s.id=NEW.submission_id FOR UPDATE OF a;
      IF NEW.teacher_weight <> .6 OR NEW.designated_review_weight <> .4 THEN
        RAISE EXCEPTION 'final project weights must be 0.60/0.40';
      END IF;
      IF EXISTS(SELECT 1 FROM anomaly_records WHERE submission_id=NEW.submission_id AND status='OPEN') THEN
        RAISE EXCEPTION 'all anomalies require explicit resolution';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """)
