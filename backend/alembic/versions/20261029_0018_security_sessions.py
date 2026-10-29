"""Revocable sessions and durable one-use request identifiers."""

from alembic import op

revision = "20261029_0018"
down_revision = "20261029_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE auth_sessions (
      id VARCHAR(64) PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      credential_stamp VARCHAR(64) NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      revoked_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_auth_sessions_expiry ON auth_sessions(expires_at);
    CREATE INDEX ix_auth_sessions_user ON auth_sessions(user_id);
    CREATE TABLE request_nonces (
      session_id VARCHAR(64) NOT NULL REFERENCES auth_sessions(id) ON DELETE CASCADE,
      nonce VARCHAR(64) NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '10 minutes',
      PRIMARY KEY(session_id, nonce)
    );
    CREATE INDEX ix_request_nonces_expiry ON request_nonces(expires_at);
    """)


def downgrade():
    op.execute("DROP TABLE request_nonces; DROP TABLE auth_sessions;")
