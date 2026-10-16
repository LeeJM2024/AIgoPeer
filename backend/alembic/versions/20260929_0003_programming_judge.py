"""add programming judge workflow

Revision ID: 20260929_0003
Revises: 20260928_0002
Create Date: 2026-09-29
"""

from alembic import op

revision = "20260929_0003"
down_revision = "20260928_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE programming_problems (
      assignment_id BIGINT PRIMARY KEY REFERENCES assignments(id) ON DELETE CASCADE,
      statement TEXT NOT NULL,
      input_description TEXT NOT NULL,
      output_description TEXT NOT NULL,
      time_limit_ms INTEGER NOT NULL DEFAULT 2000 CHECK (time_limit_ms > 0 AND time_limit_ms <= 10000),
      memory_limit_mb INTEGER NOT NULL DEFAULT 256 CHECK (memory_limit_mb > 0 AND memory_limit_mb <= 1024),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE programming_test_cases (
      id BIGSERIAL PRIMARY KEY,
      problem_assignment_id BIGINT NOT NULL REFERENCES programming_problems(assignment_id) ON DELETE CASCADE,
      sort_order INTEGER NOT NULL CHECK (sort_order > 0),
      input_data TEXT NOT NULL CHECK (octet_length(input_data) <= 65536),
      expected_output TEXT NOT NULL CHECK (octet_length(expected_output) <= 65536),
      is_public BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(problem_assignment_id, sort_order)
    );
    CREATE INDEX ix_programming_test_cases_problem_visibility
      ON programming_test_cases(problem_assignment_id, is_public, sort_order);
    CREATE TABLE code_submissions (
      id BIGSERIAL PRIMARY KEY,
      assignment_id BIGINT NOT NULL REFERENCES assignments(id),
      author_id BIGINT NOT NULL REFERENCES users(id),
      class_id BIGINT NOT NULL REFERENCES classes(id),
      language VARCHAR(16) NOT NULL CHECK (language IN ('cpp17')),
      source_code TEXT NOT NULL CHECK (octet_length(source_code) <= 65536),
      version INTEGER NOT NULL CHECK (version > 0),
      is_current BOOLEAN NOT NULL DEFAULT TRUE,
      status VARCHAR(16) NOT NULL CHECK (status IN ('QUEUED','RUNNING','AC','WA','TLE','RE','CE','SYSTEM_ERROR')),
      queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      started_at TIMESTAMPTZ,
      finished_at TIMESTAMPTZ,
      time_ms INTEGER,
      memory_kb INTEGER,
      executed_case_count INTEGER NOT NULL DEFAULT 0 CHECK (executed_case_count >= 0),
      passed_case_count INTEGER NOT NULL DEFAULT 0 CHECK (passed_case_count >= 0),
      compiler_output TEXT,
      retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0 AND retry_count <= 1),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX uq_code_submissions_current_author_assignment
      ON code_submissions(assignment_id, author_id) WHERE is_current = TRUE;
    CREATE INDEX ix_code_submissions_status_queued_at ON code_submissions(status, queued_at);
    CREATE INDEX ix_code_submissions_author_assignment ON code_submissions(author_id, assignment_id, version DESC);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS code_submissions;
    DROP TABLE IF EXISTS programming_test_cases;
    DROP TABLE IF EXISTS programming_problems;
    """)
