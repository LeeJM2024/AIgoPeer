"""Versioned random allocation, immutable replacement history and active task guards."""

from alembic import op

revision = "20261022_0010"
down_revision = "20261022_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM assignments) THEN
        RAISE EXCEPTION 'Clear pre-upgrade assignments before installing random allocation';
      END IF;
    END $$;
    ALTER TABLE assignments ADD COLUMN review_seed BIGINT NOT NULL DEFAULT 20261022;
    ALTER TABLE review_tasks ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
    ALTER TABLE review_tasks ADD COLUMN allocation_run_id BIGINT REFERENCES algorithm_runs(id);
    CREATE INDEX ix_review_tasks_active ON review_tasks(panel_id,submission_id) WHERE is_active;
    CREATE TABLE review_task_replacements (
      id BIGSERIAL PRIMARY KEY,
      old_task_id BIGINT NOT NULL UNIQUE REFERENCES review_tasks(id),
      new_task_id BIGINT NOT NULL UNIQUE REFERENCES review_tasks(id),
      actor_id BIGINT NOT NULL REFERENCES users(id), reason TEXT NOT NULL CHECK(length(trim(reason))>=3),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), CHECK(old_task_id<>new_task_id)
    );
    CREATE TABLE review_relationship_observations (
      id BIGSERIAL PRIMARY KEY,
      assignment_id BIGINT NOT NULL REFERENCES assignments(id),
      algorithm_run_id BIGINT NOT NULL REFERENCES algorithm_runs(id),
      task_id BIGINT NOT NULL REFERENCES review_tasks(id),
      reviewer_id BIGINT NOT NULL REFERENCES users(id),
      author_id BIGINT NOT NULL REFERENCES users(id),
      residual DOUBLE PRECISION NOT NULL CHECK(residual BETWEEN -1000 AND 1000),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(algorithm_run_id,task_id)
    );
    CREATE INDEX ix_relationship_pair ON review_relationship_observations(reviewer_id,author_id,assignment_id);
    CREATE FUNCTION freeze_relationship_observation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'relationship observations are append-only'; END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_relationship_observation BEFORE UPDATE OR DELETE ON review_relationship_observations
      FOR EACH ROW EXECUTE FUNCTION freeze_relationship_observation();
    CREATE FUNCTION freeze_review_allocation_policy() RETURNS trigger AS $$
    BEGIN
      IF OLD.status <> 'DRAFT' AND NEW.review_seed <> OLD.review_seed
      THEN RAISE EXCEPTION 'published allocation policy is frozen'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_freeze_allocation_policy BEFORE UPDATE ON assignments
      FOR EACH ROW EXECUTE FUNCTION freeze_review_allocation_policy();

    DROP TRIGGER trg_active_panel_has_five ON review_panels;
    DROP FUNCTION ensure_active_panel_has_five_reviewers();

    CREATE FUNCTION guard_random_review_task() RETURNS trigger AS $$
    DECLARE aid BIGINT; state TEXT; target BIGINT; reviewer_class BIGINT; author BIGINT;
    BEGIN
      IF TG_OP='DELETE' THEN
        IF EXISTS(SELECT 1 FROM review_panels p JOIN assignments a ON a.id=p.assignment_id
          WHERE p.id=OLD.panel_id)
        THEN RAISE EXCEPTION 'random review history cannot be deleted'; END IF;
        RETURN OLD;
      END IF;
      SELECT a.id,a.status,p.target_class_id,p.reviewer_class_id
        INTO aid,state,target,reviewer_class
      FROM review_panels p JOIN assignments a ON a.id=p.assignment_id
      WHERE p.id=NEW.panel_id FOR UPDATE OF a;
      IF TG_OP='INSERT' AND NOT NEW.is_active THEN
        RAISE EXCEPTION 'new review tasks must be active';
      END IF;
      IF TG_OP='UPDATE' THEN
        IF (to_jsonb(NEW)-'is_active'-'status'-'started_at'-'submitted_at'-'updated_at')
           IS DISTINCT FROM (to_jsonb(OLD)-'is_active'-'status'-'started_at'-'submitted_at'-'updated_at')
        THEN RAISE EXCEPTION 'allocated task identity is immutable'; END IF;
        IF NOT OLD.is_active OR OLD.status='SUBMITTED' OR state='PUBLISHED_RESULT'
        THEN RAISE EXCEPTION 'completed or replaced review is immutable'; END IF;
      END IF;
      IF NEW.is_active THEN
        IF state NOT IN ('REVIEWER_INITIALIZING','REVIEWER_GRADING')
        THEN RAISE EXCEPTION 'review allocation is closed'; END IF;
        SELECT author_id INTO author FROM submissions WHERE id=NEW.submission_id
          AND assignment_id=aid AND class_id=target AND is_current AND status='VALID';
        IF author IS NULL OR author=NEW.reviewer_id
          OR NOT EXISTS(SELECT 1 FROM enrollments WHERE user_id=NEW.reviewer_id AND class_id=reviewer_class)
          OR EXISTS(SELECT 1 FROM enrollments WHERE user_id=NEW.reviewer_id AND class_id=target)
          OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.reviewer_id AND system_role='STUDENT')
        THEN RAISE EXCEPTION 'invalid cross-class reviewer'; END IF;
        IF (SELECT count(*) FROM review_tasks WHERE submission_id=NEW.submission_id
              AND is_active AND id<>NEW.id)>=5
        THEN RAISE EXCEPTION 'at most five active reviews per work'; END IF;
        IF EXISTS(SELECT 1 FROM review_tasks rt JOIN submissions s ON s.id=rt.submission_id
          WHERE s.assignment_id=aid AND s.author_id=NEW.reviewer_id
            AND rt.reviewer_id=author AND rt.is_active AND rt.id<>NEW.id)
        THEN RAISE EXCEPTION 'reciprocal reviews are forbidden'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_random_review_task BEFORE INSERT OR UPDATE OR DELETE ON review_tasks
      FOR EACH ROW EXECUTE FUNCTION guard_random_review_task();

    CREATE FUNCTION guard_random_review_input() RETURNS trigger AS $$
    DECLARE tid BIGINT; aid BIGINT; state TEXT; active BOOLEAN;
    BEGIN
      IF TG_OP='UPDATE' AND NEW.review_task_id<>OLD.review_task_id THEN
        RAISE EXCEPTION 'review input ownership is immutable';
      END IF;
      tid := CASE WHEN TG_OP='DELETE' THEN OLD.review_task_id ELSE NEW.review_task_id END;
      SELECT a.id INTO aid FROM assignments a
        JOIN review_panels p ON p.assignment_id=a.id JOIN review_tasks rt ON rt.panel_id=p.id
        WHERE rt.id=tid FOR UPDATE OF a;
      IF aid IS NOT NULL THEN
        SELECT status,is_active INTO state,active FROM review_tasks WHERE id=tid;
        IF state='SUBMITTED' OR NOT active THEN
          RAISE EXCEPTION 'submitted or replaced review inputs are immutable'; END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_random_review_scores BEFORE INSERT OR UPDATE OR DELETE ON review_scores
      FOR EACH ROW EXECUTE FUNCTION guard_random_review_input();
    CREATE TRIGGER trg_random_review_comments BEFORE INSERT OR UPDATE OR DELETE ON review_comments
      FOR EACH ROW EXECUTE FUNCTION guard_random_review_input();

    CREATE FUNCTION guard_random_five_reviews() RETURNS trigger AS $$
    DECLARE sid BIGINT; state TEXT;
    BEGIN
      sid := CASE WHEN TG_OP='DELETE' THEN OLD.submission_id ELSE NEW.submission_id END;
      SELECT a.status INTO state FROM assignments a
        JOIN submissions s ON s.assignment_id=a.id WHERE s.id=sid;
      IF state IN ('REVIEWER_GRADING','AGGREGATING','TEACHER_GRADING','PUBLISHED_RESULT')
        AND (SELECT count(*) FROM review_tasks WHERE submission_id=sid AND is_active)<>5
      THEN RAISE EXCEPTION 'a random-review work requires exactly five active reviews'; END IF;
      IF TG_OP='UPDATE' AND OLD.is_active AND NOT NEW.is_active
        AND NOT EXISTS(SELECT 1 FROM review_task_replacements WHERE old_task_id=NEW.id)
      THEN RAISE EXCEPTION 'deactivated review requires replacement history'; END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;
    CREATE CONSTRAINT TRIGGER trg_random_five_reviews AFTER INSERT OR UPDATE OR DELETE ON review_tasks
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_random_five_reviews();

    CREATE FUNCTION guard_complete_random_publication() RETURNS trigger AS $$
    BEGIN
      IF EXISTS(SELECT 1 FROM assignments a JOIN submissions s ON s.assignment_id=a.id
        WHERE s.id=NEW.submission_id) THEN
        IF (SELECT count(DISTINCT reviewer_id) FROM review_tasks
          WHERE submission_id=NEW.submission_id AND is_active AND status='SUBMITTED')<>5
          OR EXISTS(SELECT 1 FROM review_tasks rt WHERE rt.submission_id=NEW.submission_id AND rt.is_active
            AND (NOT EXISTS(SELECT 1 FROM review_comments WHERE review_task_id=rt.id)
              OR EXISTS(SELECT 1 FROM rubric_items ri JOIN rubrics r ON r.id=ri.rubric_id
                JOIN submissions s ON s.assignment_id=r.assignment_id WHERE s.id=rt.submission_id
                  AND NOT EXISTS(SELECT 1 FROM review_scores rs WHERE rs.review_task_id=rt.id AND rs.rubric_item_id=ri.id))))
        THEN RAISE EXCEPTION 'five complete active reviews required for publication'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_complete_random_publication BEFORE INSERT ON final_grades
      FOR EACH ROW EXECUTE FUNCTION guard_complete_random_publication();

    CREATE FUNCTION guard_replacement_record() RETURNS trigger AS $$
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'replacement records are append-only'; END IF;
      IF NOT EXISTS(SELECT 1 FROM review_tasks previous_task JOIN review_tasks fresh
        ON fresh.submission_id=previous_task.submission_id AND fresh.panel_id=previous_task.panel_id
        WHERE previous_task.id=NEW.old_task_id AND fresh.id=NEW.new_task_id AND NOT previous_task.is_active
          AND previous_task.status<>'SUBMITTED' AND fresh.is_active AND previous_task.reviewer_id<>fresh.reviewer_id)
      THEN RAISE EXCEPTION 'invalid replacement record'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_replacement_record BEFORE INSERT OR UPDATE OR DELETE ON review_task_replacements
      FOR EACH ROW EXECUTE FUNCTION guard_replacement_record();
    """)


def downgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM assignments)
      THEN RAISE EXCEPTION 'retain random-review history before downgrade'; END IF;
    END $$;
    DROP TABLE review_relationship_observations;
    DROP FUNCTION freeze_relationship_observation();
    DROP TABLE review_task_replacements;
    DROP FUNCTION guard_replacement_record();
    DROP TRIGGER trg_complete_random_publication ON final_grades;
    DROP FUNCTION guard_complete_random_publication();
    DROP TRIGGER trg_random_five_reviews ON review_tasks;
    DROP FUNCTION guard_random_five_reviews();
    DROP TRIGGER trg_random_review_scores ON review_scores;
    DROP TRIGGER trg_random_review_comments ON review_comments;
    DROP FUNCTION guard_random_review_input();
    DROP TRIGGER trg_random_review_task ON review_tasks;
    DROP FUNCTION guard_random_review_task();
    DROP TRIGGER trg_freeze_allocation_policy ON assignments;
    DROP FUNCTION freeze_review_allocation_policy();
    ALTER TABLE review_tasks DROP COLUMN allocation_run_id, DROP COLUMN is_active;
    ALTER TABLE assignments DROP COLUMN review_seed;
    CREATE FUNCTION ensure_active_panel_has_five_reviewers() RETURNS trigger AS $$
    BEGIN
      IF NEW.status='ACTIVE' AND OLD.status IS DISTINCT FROM 'ACTIVE'
        AND (SELECT count(*) FROM panel_reviewers WHERE panel_id=NEW.id)<>5
      THEN RAISE EXCEPTION 'a panel requires exactly five reviewers'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_active_panel_has_five BEFORE UPDATE OF status ON review_panels
      FOR EACH ROW EXECUTE FUNCTION ensure_active_panel_has_five_reviewers();
    """)
