"""Preserve published weights, grade identity and freeze published grade writes.

Revision ID: 20260930_0003
Revises: 20260929_0002
"""

from alembic import op

revision = "20260930_0003"
down_revision = "20260929_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE login_rate_limits (
          scope_key VARCHAR(64) PRIMARY KEY,
          window_start TIMESTAMPTZ NOT NULL DEFAULT now(),
          attempts INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX ix_login_rate_limits_window ON login_rate_limits(window_start);

        CREATE FUNCTION guard_assignment_rules() RETURNS trigger AS $$
        BEGIN
          IF OLD.status <> 'DRAFT' AND (
            NEW.teacher_weight IS DISTINCT FROM OLD.teacher_weight OR
            NEW.designated_review_weight IS DISTINCT FROM OLD.designated_review_weight OR
            NEW.type IS DISTINCT FROM OLD.type OR NEW.submit_deadline IS DISTINCT FROM OLD.submit_deadline
          ) THEN RAISE EXCEPTION 'published assignment rules are frozen'; END IF;
          IF OLD.status='PUBLISHED_RESULT' AND NEW.status <> OLD.status THEN
            RAISE EXCEPTION 'published result state cannot be reopened';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_guard_assignment_rules BEFORE UPDATE ON assignments
          FOR EACH ROW EXECUTE FUNCTION guard_assignment_rules();

        CREATE FUNCTION guard_rubric_rules() RETURNS trigger AS $$
        DECLARE row_data JSONB; assignment_id_value BIGINT; assignment_state TEXT;
        BEGIN
          row_data := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
          IF TG_OP='UPDATE' AND (
            row_data->'assignment_id' IS DISTINCT FROM to_jsonb(OLD)->'assignment_id' OR
            row_data->'rubric_id' IS DISTINCT FROM to_jsonb(OLD)->'rubric_id'
          ) THEN RAISE EXCEPTION 'rubric ownership is immutable'; END IF;
          IF TG_TABLE_NAME='rubric_items' THEN
            SELECT assignment_id INTO assignment_id_value FROM rubrics WHERE id=(row_data->>'rubric_id')::BIGINT;
          ELSE
            assignment_id_value := (row_data->>'assignment_id')::BIGINT;
          END IF;
          SELECT status INTO assignment_state FROM assignments WHERE id=assignment_id_value FOR UPDATE;
          IF assignment_state IS NOT NULL AND assignment_state <> 'DRAFT' THEN
            RAISE EXCEPTION 'rubric and assignment classes are frozen after publication';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        DO $$ DECLARE table_name TEXT; BEGIN
          FOREACH table_name IN ARRAY ARRAY['rubrics','rubric_items','assignment_classes'] LOOP
            EXECUTE format('CREATE TRIGGER trg_guard_rubric_rules BEFORE INSERT OR UPDATE OR DELETE ON %I
              FOR EACH ROW EXECUTE FUNCTION guard_rubric_rules()',table_name);
          END LOOP;
        END $$;
        ALTER TABLE final_grades ADD COLUMN teacher_weight NUMERIC(5,4);
        ALTER TABLE final_grades ADD COLUMN designated_review_weight NUMERIC(5,4);
        UPDATE final_grades f SET teacher_weight = a.teacher_weight,
          designated_review_weight = a.designated_review_weight
        FROM submissions s JOIN assignments a ON a.id = s.assignment_id
        WHERE s.id = f.submission_id;
        ALTER TABLE final_grades ALTER COLUMN teacher_weight SET NOT NULL;
        ALTER TABLE final_grades ALTER COLUMN designated_review_weight SET NOT NULL;
        ALTER TABLE final_grades ADD CONSTRAINT final_grade_weights CHECK (
          teacher_weight >= 0 AND designated_review_weight >= 0
          AND teacher_weight + designated_review_weight = 1);

        CREATE OR REPLACE FUNCTION protect_teacher_grade() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'teacher grades are append-only'; END IF;
          IF (to_jsonb(NEW) - 'locked_at') IS DISTINCT FROM (to_jsonb(OLD) - 'locked_at')
             OR OLD.locked_at IS NOT NULL OR NEW.locked_at IS NULL
          THEN RAISE EXCEPTION 'teacher grade values are immutable; add a correction version instead'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE FUNCTION guard_teacher_grade_write() RETURNS trigger AS $$
        DECLARE assignment_state TEXT; previous_version INTEGER; previous_locked TIMESTAMPTZ;
        BEGIN
          SELECT a.status INTO assignment_state FROM assignments a
          JOIN submissions s ON s.assignment_id = a.id WHERE s.id = NEW.submission_id
          FOR UPDATE OF a;
          IF assignment_state = 'PUBLISHED_RESULT' THEN
            RAISE EXCEPTION 'published teacher grades are frozen';
          END IF;
          SELECT version, locked_at INTO previous_version, previous_locked FROM teacher_grades
            WHERE submission_id = NEW.submission_id ORDER BY version DESC LIMIT 1;
          IF TG_OP = 'INSERT' THEN
            IF NEW.version <> COALESCE(previous_version, 0) + 1 THEN
              RAISE EXCEPTION 'teacher grade version must be sequential';
            END IF;
            IF previous_version IS NOT NULL AND
               (previous_locked IS NULL OR length(trim(COALESCE(NEW.correction_reason, ''))) < 3) THEN
              RAISE EXCEPTION 'correction requires locked previous version and reason';
            END IF;
          ELSIF NEW.version <> previous_version THEN
            RAISE EXCEPTION 'only latest teacher grade can be locked';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_guard_teacher_grade_write BEFORE INSERT OR UPDATE ON teacher_grades
          FOR EACH ROW EXECUTE FUNCTION guard_teacher_grade_write();

        CREATE FUNCTION guard_final_grade() RETURNS trigger AS $$
        DECLARE a assignments%ROWTYPE; grade teacher_grades%ROWTYPE; aggregate_score NUMERIC;
        BEGIN
          IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'published results are immutable'; END IF;
          SELECT x.* INTO a FROM assignments x JOIN submissions s ON s.assignment_id=x.id
            WHERE s.id=NEW.submission_id FOR UPDATE OF x;
          IF a.status <> 'TEACHER_GRADING' THEN RAISE EXCEPTION 'assignment is not ready for publication'; END IF;
          SELECT * INTO grade FROM teacher_grades WHERE submission_id=NEW.submission_id
            ORDER BY version DESC LIMIT 1;
          IF grade.id IS NULL OR grade.id <> NEW.teacher_grade_id OR grade.locked_at IS NULL THEN
            RAISE EXCEPTION 'publication requires latest locked teacher grade';
          END IF;
          SELECT ag.total_score INTO aggregate_score FROM designated_review_aggregates ag
            WHERE ag.id=NEW.aggregate_id AND ag.submission_id=NEW.submission_id;
          IF aggregate_score IS NULL THEN RAISE EXCEPTION 'aggregate must match submission'; END IF;
          IF NEW.teacher_weight <> a.teacher_weight OR NEW.designated_review_weight <> a.designated_review_weight OR
             NEW.final_score <> round(grade.total_score * NEW.teacher_weight + aggregate_score * NEW.designated_review_weight, 2)
          THEN RAISE EXCEPTION 'incorrect publication weights or final score'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_guard_final_grade BEFORE INSERT OR UPDATE OR DELETE ON final_grades
          FOR EACH ROW EXECUTE FUNCTION guard_final_grade();

        CREATE FUNCTION guard_publication_inputs() RETURNS trigger AS $$
        DECLARE row_data JSONB; assignment_id_value BIGINT; assignment_state TEXT;
        BEGIN
          row_data := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
          IF TG_OP='UPDATE' AND (
            row_data->'assignment_id' IS DISTINCT FROM to_jsonb(OLD)->'assignment_id' OR
            row_data->'submission_id' IS DISTINCT FROM to_jsonb(OLD)->'submission_id' OR
            row_data->'review_task_id' IS DISTINCT FROM to_jsonb(OLD)->'review_task_id' OR
            row_data->'author_id' IS DISTINCT FROM to_jsonb(OLD)->'author_id' OR
            row_data->'class_id' IS DISTINCT FROM to_jsonb(OLD)->'class_id'
          ) THEN RAISE EXCEPTION 'workflow input ownership is immutable'; END IF;
          IF TG_TABLE_NAME='submissions' THEN
            assignment_id_value := (row_data->>'assignment_id')::BIGINT;
          ELSIF TG_TABLE_NAME IN ('review_scores','review_comments') THEN
            SELECT s.assignment_id INTO assignment_id_value FROM submissions s
              JOIN review_tasks rt ON rt.submission_id=s.id WHERE rt.id=(row_data->>'review_task_id')::BIGINT;
          ELSE
            SELECT assignment_id INTO assignment_id_value FROM submissions
              WHERE id=(row_data->>'submission_id')::BIGINT;
          END IF;
          SELECT status INTO assignment_state FROM assignments WHERE id=assignment_id_value FOR UPDATE;
          IF assignment_state='PUBLISHED_RESULT' THEN
            RAISE EXCEPTION 'published result inputs are frozen';
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        DO $$ DECLARE table_name TEXT; BEGIN
          FOREACH table_name IN ARRAY ARRAY['submissions','material_checks','review_tasks','review_scores',
              'review_comments','designated_review_aggregates','anomaly_records'] LOOP
            EXECUTE format('CREATE TRIGGER trg_guard_publication_inputs BEFORE INSERT OR UPDATE OR DELETE ON %I
              FOR EACH ROW EXECUTE FUNCTION guard_publication_inputs()',table_name);
          END LOOP;
        END $$;
    """)


def downgrade():
    op.execute("""
        DROP TRIGGER trg_guard_assignment_rules ON assignments;
        DROP FUNCTION guard_assignment_rules();
        DO $$ DECLARE table_name TEXT; BEGIN
          FOREACH table_name IN ARRAY ARRAY['rubrics','rubric_items','assignment_classes'] LOOP
            EXECUTE format('DROP TRIGGER trg_guard_rubric_rules ON %I',table_name);
          END LOOP;
        END $$;
        DROP FUNCTION guard_rubric_rules();
        DO $$ DECLARE table_name TEXT; BEGIN
          FOREACH table_name IN ARRAY ARRAY['submissions','material_checks','review_tasks','review_scores',
              'review_comments','designated_review_aggregates','anomaly_records'] LOOP
            EXECUTE format('DROP TRIGGER trg_guard_publication_inputs ON %I',table_name);
          END LOOP;
        END $$;
        DROP FUNCTION guard_publication_inputs();
        DROP TABLE login_rate_limits;
        DROP TRIGGER trg_guard_final_grade ON final_grades;
        DROP FUNCTION guard_final_grade();
        DROP TRIGGER trg_guard_teacher_grade_write ON teacher_grades;
        DROP FUNCTION guard_teacher_grade_write();
        ALTER TABLE final_grades DROP CONSTRAINT final_grade_weights;
        ALTER TABLE final_grades DROP COLUMN teacher_weight, DROP COLUMN designated_review_weight;
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
    """)
