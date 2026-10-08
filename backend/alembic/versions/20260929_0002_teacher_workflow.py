"""teacher workflow and advisory video analysis

Revision ID: 20260929_0002
Revises: 20260928_0001
Create Date: 2026-09-29
"""

from alembic import op

revision = "20260929_0002"
down_revision = "20260928_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE teacher_grades ADD COLUMN feedback TEXT NOT NULL DEFAULT '';
    ALTER TABLE anomaly_records ADD COLUMN resolution_note TEXT;
    ALTER TABLE anomaly_records ADD COLUMN resolved_by BIGINT REFERENCES users(id);
    ALTER TABLE anomaly_records ADD COLUMN resolved_at TIMESTAMPTZ;

    CREATE OR REPLACE FUNCTION protect_teacher_grade() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'teacher grades are append-only'; END IF;
      IF NEW.submission_id <> OLD.submission_id OR NEW.rubric_scores_json <> OLD.rubric_scores_json OR
         NEW.total_score <> OLD.total_score OR NEW.version <> OLD.version OR NEW.entered_by <> OLD.entered_by OR
         NEW.correction_reason IS DISTINCT FROM OLD.correction_reason OR NEW.feedback IS DISTINCT FROM OLD.feedback OR
         OLD.locked_at IS NOT NULL OR NEW.locked_at IS NULL
      THEN RAISE EXCEPTION 'teacher grade values are immutable; add a correction version instead'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;

    CREATE TABLE video_analysis_runs (
      id BIGSERIAL PRIMARY KEY,
      submission_file_id BIGINT NOT NULL REFERENCES submission_files(id) ON DELETE CASCADE,
      assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
      provider VARCHAR(64) NOT NULL,
      model VARCHAR(128) NOT NULL,
      provider_job_id VARCHAR(256),
      rubric_snapshot_json JSONB NOT NULL,
      input_hash VARCHAR(128) NOT NULL,
      status VARCHAR(24) NOT NULL CHECK (status IN ('QUEUED','PROCESSING','SUCCEEDED','FAILED','CANCELLED')),
      error_code VARCHAR(100),
      error_message TEXT,
      created_by BIGINT NOT NULL REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      started_at TIMESTAMPTZ,
      finished_at TIMESTAMPTZ
    );
    CREATE INDEX ix_video_analysis_runs_file_status ON video_analysis_runs(submission_file_id, status);

    CREATE TABLE ai_rubric_assessments (
      id BIGSERIAL PRIMARY KEY,
      video_analysis_run_id BIGINT NOT NULL REFERENCES video_analysis_runs(id) ON DELETE CASCADE,
      rubric_item_id BIGINT NOT NULL REFERENCES rubric_items(id),
      suggested_score NUMERIC(7,2) NOT NULL CHECK (suggested_score >= 0),
      confidence NUMERIC(6,5) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
      rationale TEXT NOT NULL,
      evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(video_analysis_run_id, rubric_item_id)
    );
    COMMENT ON TABLE ai_rubric_assessments IS
      'Advisory evidence only. Rows never become teacher or final grades without explicit teacher action.';
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS ai_rubric_assessments, video_analysis_runs CASCADE;
    ALTER TABLE anomaly_records DROP COLUMN IF EXISTS resolved_at;
    ALTER TABLE anomaly_records DROP COLUMN IF EXISTS resolved_by;
    ALTER TABLE anomaly_records DROP COLUMN IF EXISTS resolution_note;
    ALTER TABLE teacher_grades DROP COLUMN IF EXISTS feedback;
    CREATE OR REPLACE FUNCTION protect_teacher_grade() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'teacher grades are append-only'; END IF;
      IF NEW.submission_id <> OLD.submission_id OR NEW.rubric_scores_json <> OLD.rubric_scores_json OR
         NEW.total_score <> OLD.total_score OR NEW.version <> OLD.version OR NEW.entered_by <> OLD.entered_by OR
         NEW.correction_reason IS DISTINCT FROM OLD.correction_reason OR OLD.locked_at IS NOT NULL OR NEW.locked_at IS NULL
      THEN RAISE EXCEPTION 'teacher grade values are immutable; add a correction version instead'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """)
