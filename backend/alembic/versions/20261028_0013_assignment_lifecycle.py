"""Teacher-controlled closure and deletion without rewriting grading history."""

from alembic import op

revision = "20261028_0013"
down_revision = "20261028_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE assignments ADD COLUMN closed_at TIMESTAMPTZ;
    ALTER TABLE assignments ADD COLUMN deleted_at TIMESTAMPTZ;
    ALTER TABLE assignments ADD COLUMN submissions_closed_at TIMESTAMPTZ;
    CREATE OR REPLACE FUNCTION guard_subjective_content() RETURNS trigger AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'subjective answer versions are immutable'; END IF;
      IF NOT EXISTS(SELECT 1 FROM submissions s JOIN assignments a ON a.id=s.assignment_id
        WHERE s.id=NEW.submission_id AND s.is_current AND s.status='VALID'
          AND a.type IN ('ALGORITHM_ANALYSIS','PROOF','OPEN_ENDED')
          AND a.status IN ('PUBLISHED','SUBMITTING','REVIEWER_GRADING')
          AND a.closed_at IS NULL AND a.deleted_at IS NULL AND a.submissions_closed_at IS NULL
          AND (a.submit_deadline IS NULL OR a.submit_deadline > clock_timestamp())) THEN
        RAISE EXCEPTION 'subjective submission is not open';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE FUNCTION freeze_assigned_submission_version() RETURNS trigger AS $$
    BEGIN
      IF OLD.is_current AND (NOT NEW.is_current OR NEW.status='SUPERSEDED')
        AND EXISTS(SELECT 1 FROM review_tasks WHERE submission_id=OLD.id AND is_active) THEN
        RAISE EXCEPTION 'assigned submission version is locked';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_freeze_assigned_submission BEFORE UPDATE ON submissions
      FOR EACH ROW EXECUTE FUNCTION freeze_assigned_submission_version();
    """)


def downgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM assignments WHERE closed_at IS NOT NULL OR deleted_at IS NOT NULL OR submissions_closed_at IS NOT NULL) THEN
        RAISE EXCEPTION 'closed or deleted assignments must be preserved; downgrade refused';
      END IF;
    END $$;
    DROP TRIGGER trg_freeze_assigned_submission ON submissions;
    DROP FUNCTION freeze_assigned_submission_version();
    CREATE OR REPLACE FUNCTION guard_subjective_content() RETURNS trigger AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'subjective answer versions are immutable'; END IF;
      IF NOT EXISTS(SELECT 1 FROM submissions s JOIN assignments a ON a.id=s.assignment_id
        WHERE s.id=NEW.submission_id AND s.is_current AND s.status='VALID'
          AND a.type IN ('ALGORITHM_ANALYSIS','PROOF','OPEN_ENDED')
          AND a.status IN ('PUBLISHED','SUBMITTING')
          AND (a.submit_deadline IS NULL OR a.submit_deadline > clock_timestamp())) THEN
        RAISE EXCEPTION 'subjective submission is not open';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    ALTER TABLE assignments DROP COLUMN closed_at, DROP COLUMN deleted_at, DROP COLUMN submissions_closed_at;
    """)
