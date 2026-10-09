"""Store fail-closed anonymous review packages.

The original student archive remains private to the author and teachers.  This
table records the separately generated archive that may be served to a
designated anonymous reviewer.
"""

from alembic import op

revision = "20261010_0007"
down_revision = "20261009_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE review_material_packages (
          submission_id BIGINT PRIMARY KEY REFERENCES submissions(id) ON DELETE CASCADE,
          storage_key VARCHAR(512),
          status VARCHAR(16) NOT NULL DEFAULT 'PENDING'
            CHECK (status IN ('PENDING','READY','FAILED')),
          failure_code VARCHAR(100),
          details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK ((status = 'READY' AND storage_key IS NOT NULL) OR status <> 'READY')
        );
        CREATE INDEX ix_review_material_packages_status
          ON review_material_packages(status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_material_packages;")
