"""Teacher-owned encrypted AI settings and persisted analysis results."""

from alembic import op

revision = "20261029_0017"
down_revision = "20261029_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE teacher_video_ai_settings (
      teacher_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      provider VARCHAR(32) NOT NULL CHECK(provider IN ('qwen','gemini')),
      base_url VARCHAR(1000) NOT NULL,
      model VARCHAR(128) NOT NULL,
      api_key_encrypted TEXT NOT NULL,
      enabled BOOLEAN NOT NULL DEFAULT true,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    ALTER TABLE video_analysis_runs ADD COLUMN result_json JSONB;
    ALTER TABLE video_analysis_runs ADD COLUMN progress_json JSONB NOT NULL DEFAULT '{}';
    CREATE INDEX ix_video_analysis_owner ON video_analysis_runs(created_by,created_at DESC);
    CREATE UNIQUE INDEX uq_video_analysis_active ON video_analysis_runs(created_by,submission_file_id)
      WHERE status IN ('QUEUED','PROCESSING');
    """)


def downgrade():
    op.execute("""
    DROP INDEX uq_video_analysis_active;
    DROP INDEX ix_video_analysis_owner;
    ALTER TABLE video_analysis_runs DROP COLUMN progress_json;
    ALTER TABLE video_analysis_runs DROP COLUMN result_json;
    DROP TABLE teacher_video_ai_settings;
    """)
