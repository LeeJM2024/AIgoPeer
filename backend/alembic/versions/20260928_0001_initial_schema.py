"""initial AlgoPeer schema

Revision ID: 20260928_0001
Revises:
Create Date: 2026-09-28
"""

from alembic import op

revision = "20260928_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Text states keep the MVP easy to evolve; service-layer state transitions and
    # these relational constraints remain the authority, never the Vue client.
    op.execute("""
    CREATE TABLE users (
      id BIGSERIAL PRIMARY KEY,
      student_no VARCHAR(32) UNIQUE,
      name VARCHAR(100) NOT NULL,
      password_hash TEXT NOT NULL,
      system_role VARCHAR(16) NOT NULL CHECK (system_role IN ('TEACHER', 'STUDENT')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE classes (
      id BIGSERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL, course_term VARCHAR(64) NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(name, course_term)
    );
    CREATE TABLE enrollments (
      id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id),
      class_id BIGINT NOT NULL REFERENCES classes(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(user_id, class_id)
    );
    CREATE TABLE assignments (
      id BIGSERIAL PRIMARY KEY, title VARCHAR(200) NOT NULL,
      type VARCHAR(24) NOT NULL CHECK (type IN ('PROGRAMMING', 'FINAL_PROJECT')),
      status VARCHAR(32) NOT NULL DEFAULT 'DRAFT', submit_deadline TIMESTAMPTZ,
      review_deadline TIMESTAMPTZ, teacher_weight NUMERIC(5,4) NOT NULL DEFAULT 0.6000,
      designated_review_weight NUMERIC(5,4) NOT NULL DEFAULT 0.4000,
      created_by BIGINT NOT NULL REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK (teacher_weight >= 0 AND designated_review_weight >= 0 AND teacher_weight + designated_review_weight = 1.0000)
    );
    CREATE TABLE assignment_classes (
      assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
      class_id BIGINT NOT NULL REFERENCES classes(id), PRIMARY KEY (assignment_id, class_id)
    );
    CREATE TABLE rubrics (
      id BIGSERIAL PRIMARY KEY, assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
      name VARCHAR(100) NOT NULL, total_score NUMERIC(7,2) NOT NULL CHECK (total_score > 0),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE rubric_items (
      id BIGSERIAL PRIMARY KEY, rubric_id BIGINT NOT NULL REFERENCES rubrics(id) ON DELETE CASCADE,
      name VARCHAR(100) NOT NULL, max_score NUMERIC(7,2) NOT NULL CHECK (max_score > 0),
      sort_order INTEGER NOT NULL, description TEXT, UNIQUE(rubric_id, sort_order)
    );
    CREATE TABLE submissions (
      id BIGSERIAL PRIMARY KEY, assignment_id BIGINT NOT NULL REFERENCES assignments(id),
      author_id BIGINT NOT NULL REFERENCES users(id), class_id BIGINT NOT NULL REFERENCES classes(id),
      status VARCHAR(32) NOT NULL DEFAULT 'DRAFT', anonymous_token VARCHAR(64) NOT NULL UNIQUE,
      submitted_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_submissions_assignment_class_status ON submissions(assignment_id, class_id, status);
    CREATE TABLE submission_files (
      id BIGSERIAL PRIMARY KEY, submission_id BIGINT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
      file_kind VARCHAR(16) NOT NULL CHECK (file_kind IN ('PPT','VIDEO','EXAMPLES','CODE','TESTS','README','ZIP')),
      storage_key TEXT NOT NULL, file_name TEXT NOT NULL, size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
      checksum VARCHAR(128) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE material_checks (
      id BIGSERIAL PRIMARY KEY, submission_id BIGINT NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
      status VARCHAR(16) NOT NULL CHECK (status IN ('PENDING','VALID','INVALID','RETURNED')),
      missing_items JSONB NOT NULL DEFAULT '[]'::jsonb, checked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE review_panels (
      id BIGSERIAL PRIMARY KEY, assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
      target_class_id BIGINT NOT NULL REFERENCES classes(id), reviewer_class_id BIGINT NOT NULL REFERENCES classes(id),
      status VARCHAR(24) NOT NULL DEFAULT 'DRAFT', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK (target_class_id <> reviewer_class_id), UNIQUE(assignment_id, target_class_id, reviewer_class_id)
    );
    CREATE TABLE panel_reviewers (
      id BIGSERIAL PRIMARY KEY, panel_id BIGINT NOT NULL REFERENCES review_panels(id) ON DELETE CASCADE,
      reviewer_id BIGINT NOT NULL REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(panel_id, reviewer_id)
    );
    CREATE TABLE review_tasks (
      id BIGSERIAL PRIMARY KEY, panel_id BIGINT NOT NULL REFERENCES review_panels(id) ON DELETE CASCADE,
      submission_id BIGINT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
      reviewer_id BIGINT NOT NULL REFERENCES users(id), anonymous_token VARCHAR(64) NOT NULL,
      status VARCHAR(24) NOT NULL DEFAULT 'PENDING', started_at TIMESTAMPTZ, submitted_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(panel_id, submission_id, reviewer_id)
    );
    CREATE INDEX ix_review_tasks_reviewer_status ON review_tasks(reviewer_id, status);
    CREATE INDEX ix_review_tasks_submission_status ON review_tasks(submission_id, status);
    CREATE TABLE review_scores (
      id BIGSERIAL PRIMARY KEY, review_task_id BIGINT NOT NULL REFERENCES review_tasks(id) ON DELETE CASCADE,
      rubric_item_id BIGINT NOT NULL REFERENCES rubric_items(id), score NUMERIC(7,2) NOT NULL CHECK (score >= 0),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(review_task_id, rubric_item_id)
    );
    CREATE TABLE review_comments (
      id BIGSERIAL PRIMARY KEY, review_task_id BIGINT NOT NULL UNIQUE REFERENCES review_tasks(id) ON DELETE CASCADE,
      content TEXT NOT NULL, char_count INTEGER NOT NULL CHECK (char_count >= 0), created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE TABLE algorithm_runs (
      id BIGSERIAL PRIMARY KEY, assignment_id BIGINT NOT NULL REFERENCES assignments(id), panel_id BIGINT REFERENCES review_panels(id),
      algorithm_name VARCHAR(100) NOT NULL, version VARCHAR(40) NOT NULL, parameters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      input_hash VARCHAR(128) NOT NULL, status VARCHAR(20) NOT NULL, started_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ
    );
    CREATE TABLE designated_review_aggregates (
      id BIGSERIAL PRIMARY KEY, submission_id BIGINT NOT NULL REFERENCES submissions(id), panel_id BIGINT NOT NULL REFERENCES review_panels(id),
      algorithm_run_id BIGINT NOT NULL REFERENCES algorithm_runs(id), total_score NUMERIC(7,2) NOT NULL,
      rubric_scores_json JSONB NOT NULL, confidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(submission_id, algorithm_run_id)
    );
    CREATE TABLE reviewer_profiles (
      id BIGSERIAL PRIMARY KEY, assignment_id BIGINT NOT NULL REFERENCES assignments(id), panel_id BIGINT NOT NULL REFERENCES review_panels(id),
      reviewer_id BIGINT NOT NULL REFERENCES users(id), bias_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      reliability NUMERIC(6,5), lazy_probability NUMERIC(6,5), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(assignment_id, panel_id, reviewer_id)
    );
    CREATE TABLE anomaly_records (
      id BIGSERIAL PRIMARY KEY, submission_id BIGINT NOT NULL REFERENCES submissions(id), review_task_id BIGINT REFERENCES review_tasks(id),
      algorithm_run_id BIGINT NOT NULL REFERENCES algorithm_runs(id), risk_level VARCHAR(12) NOT NULL,
      risk_score NUMERIC(6,5) NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1), evidence_json JSONB NOT NULL,
      status VARCHAR(16) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CONFIRMED','DISMISSED')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX ix_anomaly_records_submission_status ON anomaly_records(submission_id, status);
    CREATE TABLE teacher_grades (
      id BIGSERIAL PRIMARY KEY, submission_id BIGINT NOT NULL REFERENCES submissions(id), rubric_scores_json JSONB NOT NULL,
      total_score NUMERIC(7,2) NOT NULL, version INTEGER NOT NULL CHECK (version > 0), locked_at TIMESTAMPTZ,
      entered_by BIGINT NOT NULL REFERENCES users(id), correction_reason TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(submission_id, version)
    );
    CREATE TABLE final_grades (
      id BIGSERIAL PRIMARY KEY, submission_id BIGINT NOT NULL UNIQUE REFERENCES submissions(id),
      teacher_grade_id BIGINT NOT NULL REFERENCES teacher_grades(id), aggregate_id BIGINT REFERENCES designated_review_aggregates(id),
      final_score NUMERIC(7,2) NOT NULL, published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      published_by BIGINT NOT NULL REFERENCES users(id)
    );
    CREATE TABLE audit_logs (
      id BIGSERIAL PRIMARY KEY, actor_id BIGINT REFERENCES users(id), action VARCHAR(100) NOT NULL,
      entity_type VARCHAR(64) NOT NULL, entity_id BIGINT NOT NULL, before_json JSONB, after_json JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE OR REPLACE FUNCTION ensure_panel_reviewer_cross_class() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM review_panels p JOIN enrollments e ON e.class_id = p.reviewer_class_id
        WHERE p.id = NEW.panel_id AND e.user_id = NEW.reviewer_id
      ) THEN RAISE EXCEPTION 'reviewer must belong to panel reviewer_class_id'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_panel_reviewer_cross_class BEFORE INSERT OR UPDATE ON panel_reviewers
      FOR EACH ROW EXECUTE FUNCTION ensure_panel_reviewer_cross_class();

    CREATE OR REPLACE FUNCTION ensure_active_panel_has_five_reviewers() RETURNS trigger AS $$
    BEGIN
      IF NEW.status = 'ACTIVE' AND OLD.status IS DISTINCT FROM 'ACTIVE' AND
         (SELECT count(*) FROM panel_reviewers WHERE panel_id = NEW.id) <> 5
      THEN RAISE EXCEPTION 'an active review panel must have exactly five reviewers'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_active_panel_has_five BEFORE UPDATE OF status ON review_panels
      FOR EACH ROW EXECUTE FUNCTION ensure_active_panel_has_five_reviewers();

    CREATE OR REPLACE FUNCTION ensure_review_task_matches_panel() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM panel_reviewers pr WHERE pr.panel_id = NEW.panel_id AND pr.reviewer_id = NEW.reviewer_id)
      THEN RAISE EXCEPTION 'review task reviewer is not a member of this panel'; END IF;
      IF NOT EXISTS (
        SELECT 1 FROM review_panels p JOIN submissions s ON s.class_id = p.target_class_id
        WHERE p.id = NEW.panel_id AND s.id = NEW.submission_id
      ) THEN RAISE EXCEPTION 'submission must belong to panel target class'; END IF;
      IF EXISTS (SELECT 1 FROM submissions s WHERE s.id = NEW.submission_id AND s.author_id = NEW.reviewer_id)
      THEN RAISE EXCEPTION 'author cannot review own submission'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_review_task_matches_panel BEFORE INSERT OR UPDATE ON review_tasks
      FOR EACH ROW EXECUTE FUNCTION ensure_review_task_matches_panel();

    CREATE OR REPLACE FUNCTION protect_teacher_grade() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'teacher grades are append-only'; END IF;
      IF NEW.submission_id <> OLD.submission_id OR NEW.rubric_scores_json <> OLD.rubric_scores_json OR
         NEW.total_score <> OLD.total_score OR NEW.version <> OLD.version OR NEW.entered_by <> OLD.entered_by OR
         NEW.correction_reason IS DISTINCT FROM OLD.correction_reason OR OLD.locked_at IS NOT NULL OR NEW.locked_at IS NULL
      THEN RAISE EXCEPTION 'teacher grade values are immutable; add a correction version instead'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_protect_teacher_grade BEFORE UPDATE OR DELETE ON teacher_grades
      FOR EACH ROW EXECUTE FUNCTION protect_teacher_grade();

    REVOKE ALL ON teacher_grades FROM PUBLIC;
    REVOKE ALL ON final_grades FROM PUBLIC;
    COMMENT ON TABLE teacher_grades IS 'Algorithm DB principal receives SELECT only; score values are immutable after insert.';
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS audit_logs, final_grades, teacher_grades, anomaly_records, reviewer_profiles,
      designated_review_aggregates, algorithm_runs, review_comments, review_scores, review_tasks,
      panel_reviewers, review_panels, material_checks, submission_files, submissions, rubric_items,
      rubrics, assignment_classes, assignments, enrollments, classes, users CASCADE;
    DROP FUNCTION IF EXISTS protect_teacher_grade(), ensure_review_task_matches_panel(),
      ensure_active_panel_has_five_reviewers(), ensure_panel_reviewer_cross_class() CASCADE;
    """)
