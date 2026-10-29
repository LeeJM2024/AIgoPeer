"""Course text assistant configuration, conversations and metered requests."""

from alembic import op

revision = "20261029_0019"
down_revision = "20261029_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE course_text_ai_settings (
      id SMALLINT PRIMARY KEY CHECK(id=1),
      teacher_id BIGINT NOT NULL REFERENCES users(id),
      base_url VARCHAR(1000) NOT NULL,
      model VARCHAR(128) NOT NULL,
      api_key_encrypted TEXT NOT NULL,
      enabled BOOLEAN NOT NULL DEFAULT true,
      student_daily_limit INTEGER NOT NULL DEFAULT 30 CHECK(student_daily_limit BETWEEN 1 AND 200),
      allow_full_solution BOOLEAN NOT NULL DEFAULT false,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE text_ai_requests (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id),
      conversation_id UUID NOT NULL,
      mode VARCHAR(20) NOT NULL CHECK(mode IN ('PROGRAMMING','KNOWLEDGE','TEACHING')),
      context_key VARCHAR(100) NOT NULL,
      model VARCHAR(128) NOT NULL,
      question TEXT NOT NULL,
      answer TEXT,
      status VARCHAR(20) NOT NULL CHECK(status IN ('PROCESSING','SUCCEEDED','FAILED')),
      error_code VARCHAR(100),
      context_meta JSONB NOT NULL DEFAULT '{}',
      usage_json JSONB NOT NULL DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      finished_at TIMESTAMPTZ
    );
    CREATE INDEX ix_text_ai_user_context ON text_ai_requests(user_id,mode,context_key,id DESC);
    CREATE INDEX ix_text_ai_conversation ON text_ai_requests(conversation_id,id);
    CREATE UNIQUE INDEX uq_text_ai_user_active ON text_ai_requests(user_id) WHERE status='PROCESSING';
    """)


def downgrade():
    op.execute("DROP TABLE text_ai_requests; DROP TABLE course_text_ai_settings;")
