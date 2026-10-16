"""Fixed final-project policy, initial-teacher ownership and anomaly publication guards."""

from alembic import op

revision = "20261010_0008"
down_revision = "20261010_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    -- Migrate only unfinished work. Published grades and their weight snapshots stay immutable.
    INSERT INTO audit_logs(action,entity_type,entity_id,before_json,after_json)
      SELECT 'MIGRATE_FIXED_REVIEW_POLICY','assignment',id,
        jsonb_build_object('teacher_weight',teacher_weight,'designated_review_weight',designated_review_weight),
        jsonb_build_object('teacher_weight',0.6,'designated_review_weight',0.4)
      FROM assignments WHERE type='FINAL_PROJECT' AND status <> 'PUBLISHED_RESULT'
        AND (teacher_weight <> .6 OR designated_review_weight <> .4);
    ALTER TABLE assignments DISABLE TRIGGER trg_guard_assignment_rules;
    UPDATE assignments SET teacher_weight=.6,designated_review_weight=.4,updated_at=now()
      WHERE type='FINAL_PROJECT' AND status <> 'PUBLISHED_RESULT'
        AND (teacher_weight <> .6 OR designated_review_weight <> .4);
    ALTER TABLE assignments ENABLE TRIGGER trg_guard_assignment_rules;
    CREATE FUNCTION guard_fixed_review_policy() RETURNS trigger AS $$
    BEGIN
      IF NEW.type='FINAL_PROJECT' AND (NEW.teacher_weight <> .6 OR NEW.designated_review_weight <> .4) THEN
        IF TG_OP='UPDATE' AND OLD.status='PUBLISHED_RESULT' AND NEW.status=OLD.status
          AND NEW.teacher_weight=OLD.teacher_weight AND NEW.designated_review_weight=OLD.designated_review_weight THEN
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'final project weights must be 0.60/0.40';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_fixed_review_policy BEFORE INSERT OR UPDATE ON assignments
      FOR EACH ROW EXECUTE FUNCTION guard_fixed_review_policy();

    CREATE FUNCTION guard_final_review_teacher() RETURNS trigger AS $$
    DECLARE initial_teacher BIGINT; latest_lock TIMESTAMPTZ;
    BEGIN
      PERFORM a.id FROM assignments a JOIN submissions s ON s.assignment_id=a.id
        WHERE s.id=NEW.submission_id FOR UPDATE OF a;
      SELECT entered_by INTO initial_teacher FROM teacher_grades
        WHERE submission_id=NEW.submission_id ORDER BY version LIMIT 1;
      SELECT locked_at INTO latest_lock FROM teacher_grades
        WHERE submission_id=NEW.submission_id ORDER BY version DESC LIMIT 1;
      IF initial_teacher IS NULL OR initial_teacher <> NEW.entered_by OR latest_lock IS NULL THEN
        RAISE EXCEPTION 'final review requires the initial teacher and a locked initial assessment';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_final_review_teacher BEFORE INSERT ON teacher_final_reviews
      FOR EACH ROW EXECUTE FUNCTION guard_final_review_teacher();

    CREATE FUNCTION guard_review_policy_publication() RETURNS trigger AS $$
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
    CREATE TRIGGER trg_review_policy_publication BEFORE INSERT ON final_grades
      FOR EACH ROW EXECUTE FUNCTION guard_review_policy_publication();

    """)


def downgrade():
    op.execute("""
    DROP TRIGGER trg_review_policy_publication ON final_grades;
    DROP FUNCTION guard_review_policy_publication();
    DROP TRIGGER trg_final_review_teacher ON teacher_final_reviews;
    DROP FUNCTION guard_final_review_teacher();
    DROP TRIGGER trg_fixed_review_policy ON assignments;
    DROP FUNCTION guard_fixed_review_policy();
    -- Do not undo audited weight changes or mutate any published history.
    """)
