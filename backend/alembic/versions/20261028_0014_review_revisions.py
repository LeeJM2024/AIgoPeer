"""Reasoned, append-only revisions of submitted student reviews."""

from alembic import op

revision = "20261028_0014"
down_revision = "20261028_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE review_revisions (
      id BIGSERIAL PRIMARY KEY,
      review_task_id BIGINT NOT NULL REFERENCES review_tasks(id),
      version INTEGER NOT NULL CHECK(version >= 2),
      actor_id BIGINT NOT NULL REFERENCES users(id),
      reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 3 AND 1000),
      before_json JSONB NOT NULL,
      after_json JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
      transaction_id BIGINT NOT NULL DEFAULT txid_current(),
      UNIQUE(review_task_id, version),
      UNIQUE(review_task_id, transaction_id)
    );

    CREATE FUNCTION review_snapshot(tid BIGINT) RETURNS JSONB AS $$
      SELECT jsonb_build_object(
        'rubric_scores', COALESCE((SELECT jsonb_agg(jsonb_build_object(
          'rubric_item_id', ri.id, 'name', ri.name, 'max_score', ri.max_score, 'score', rs.score)
          ORDER BY ri.sort_order,ri.id) FROM review_scores rs
          JOIN rubric_items ri ON ri.id=rs.rubric_item_id WHERE rs.review_task_id=tid), '[]'::jsonb),
        'comment', COALESCE((SELECT content FROM review_comments WHERE review_task_id=tid), ''));
    $$ LANGUAGE sql STABLE;

    CREATE FUNCTION guard_review_revision() RETURNS trigger AS $$
    DECLARE task_state TEXT; aid BIGINT; owner_id BIGINT; active BOOLEAN; assignment_state TEXT;
      deadline TIMESTAMPTZ; closed TIMESTAMPTZ; deleted TIMESTAMPTZ; previous_version INTEGER;
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'review revision history is append-only'; END IF;
      SELECT a.id,a.status,a.review_deadline,a.closed_at,a.deleted_at,rt.status,rt.is_active,rt.reviewer_id
        INTO aid,assignment_state,deadline,closed,deleted,task_state,active,owner_id
        FROM review_tasks rt JOIN review_panels p ON p.id=rt.panel_id
        JOIN assignments a ON a.id=p.assignment_id WHERE rt.id=NEW.review_task_id FOR UPDATE OF a,rt;
      IF aid IS NULL OR NOT active OR task_state <> 'SUBMITTED' OR owner_id <> NEW.actor_id
        OR assignment_state <> 'REVIEWER_GRADING' OR closed IS NOT NULL OR deleted IS NOT NULL
        OR (deadline IS NOT NULL AND deadline <= clock_timestamp())
      THEN RAISE EXCEPTION 'review is not open for revision'; END IF;
      SELECT COALESCE(max(version),1) INTO previous_version FROM review_revisions
        WHERE review_task_id=NEW.review_task_id;
      IF NEW.version <> previous_version+1 OR NEW.before_json IS DISTINCT FROM review_snapshot(NEW.review_task_id)
        OR NEW.after_json IS NOT DISTINCT FROM NEW.before_json
      THEN RAISE EXCEPTION 'review revision does not match current version'; END IF;
      NEW.created_at := clock_timestamp();
      NEW.transaction_id := txid_current();
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_guard_review_revision BEFORE INSERT OR UPDATE OR DELETE ON review_revisions
      FOR EACH ROW EXECUTE FUNCTION guard_review_revision();

    CREATE OR REPLACE FUNCTION guard_random_review_input() RETURNS trigger AS $$
    DECLARE tid BIGINT; aid BIGINT; state TEXT; active BOOLEAN; revision_row review_revisions%ROWTYPE;
      old_score JSONB; new_score JSONB;
    BEGIN
      IF TG_OP='UPDATE' AND NEW.review_task_id<>OLD.review_task_id THEN
        RAISE EXCEPTION 'review input ownership is immutable'; END IF;
      tid := CASE WHEN TG_OP='DELETE' THEN OLD.review_task_id ELSE NEW.review_task_id END;
      SELECT a.id INTO aid FROM assignments a
        JOIN review_panels p ON p.assignment_id=a.id JOIN review_tasks rt ON rt.panel_id=p.id
        WHERE rt.id=tid FOR UPDATE OF a;
      IF aid IS NOT NULL THEN
        SELECT status,is_active INTO state,active FROM review_tasks WHERE id=tid;
        IF NOT active THEN RAISE EXCEPTION 'replaced review inputs are immutable'; END IF;
        IF state='SUBMITTED' THEN
          IF TG_OP <> 'UPDATE' THEN RAISE EXCEPTION 'submitted reviews require a revision'; END IF;
          SELECT * INTO revision_row FROM review_revisions
            WHERE review_task_id=tid AND transaction_id=txid_current();
          IF revision_row.id IS NULL THEN RAISE EXCEPTION 'submitted reviews require a revision'; END IF;
          IF TG_TABLE_NAME='review_scores' THEN
            SELECT value INTO old_score FROM jsonb_array_elements(revision_row.before_json->'rubric_scores')
              WHERE (value->>'rubric_item_id')::BIGINT=OLD.rubric_item_id;
            SELECT value INTO new_score FROM jsonb_array_elements(revision_row.after_json->'rubric_scores')
              WHERE (value->>'rubric_item_id')::BIGINT=NEW.rubric_item_id;
            IF NEW.rubric_item_id<>OLD.rubric_item_id OR old_score IS NULL OR new_score IS NULL
              OR (old_score->>'score')::NUMERIC IS DISTINCT FROM OLD.score
              OR (new_score->>'score')::NUMERIC IS DISTINCT FROM NEW.score
              OR NEW.score > (new_score->>'max_score')::NUMERIC
            THEN RAISE EXCEPTION 'score differs from revision'; END IF;
          ELSE
            IF OLD.content IS DISTINCT FROM revision_row.before_json->>'comment'
              OR NEW.content IS DISTINCT FROM revision_row.after_json->>'comment'
              OR NEW.char_count<>length(NEW.content)
            THEN RAISE EXCEPTION 'comment differs from revision'; END IF;
          END IF;
        END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;

    CREATE FUNCTION check_review_revision_applied() RETURNS trigger AS $$
    BEGIN
      IF NEW.after_json IS DISTINCT FROM review_snapshot(NEW.review_task_id)
      THEN RAISE EXCEPTION 'review revision must match persisted scores and comment'; END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;
    CREATE CONSTRAINT TRIGGER trg_review_revision_applied AFTER INSERT ON review_revisions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_review_revision_applied();
    """)


def downgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM review_revisions)
      THEN RAISE EXCEPTION 'retain review revision history before downgrade'; END IF;
    END $$;
    CREATE OR REPLACE FUNCTION guard_random_review_input() RETURNS trigger AS $$
    DECLARE tid BIGINT; aid BIGINT; state TEXT; active BOOLEAN;
    BEGIN
      IF TG_OP='UPDATE' AND NEW.review_task_id<>OLD.review_task_id THEN
        RAISE EXCEPTION 'review input ownership is immutable'; END IF;
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
    DROP TABLE review_revisions;
    DROP FUNCTION guard_review_revision();
    DROP FUNCTION check_review_revision_applied();
    DROP FUNCTION review_snapshot(BIGINT);
    """)
