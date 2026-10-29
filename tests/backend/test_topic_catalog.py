"""The topic content migration preserves existing identities and other catalog entries."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def test_topic_descriptions_are_complete_and_preserve_catalog(pg_engine):
    path = (
        Path(__file__).resolve().parents[2]
        / "backend/alembic/versions/20261028_0011_topic_descriptions.py"
    )
    spec = spec_from_file_location("topic_content_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert set(migration.TOPIC_DESCRIPTIONS) == {f"{i:02d}" for i in range(1, 27)}

    with pg_engine.begin() as conn:
        before = conn.execute(text("SELECT id, code, chapter, name FROM topics ORDER BY code")).all()
        assert len(before) == 26
        for code, description in migration.TOPIC_DESCRIPTIONS.items():
            assert conn.execute(
                text("SELECT description FROM topics WHERE code=:code"), {"code": code}
            ).scalar_one() == description
        conn.execute(text("""
            INSERT INTO topics(code,chapter,name,description)
            VALUES ('CUSTOM','自定义章节','自定义知识点','保留教师目录')
        """))
        conn.execute(text("UPDATE topics SET description='旧简略说明' WHERE code='07'"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()
        after = conn.execute(
            text("SELECT id, code, chapter, name FROM topics WHERE code<>'CUSTOM' ORDER BY code")
        ).all()
        assert before == after
        assert conn.execute(text("SELECT count(*) FROM topics")).scalar_one() == 27
        assert conn.execute(
            text("SELECT description FROM topics WHERE code='07'")
        ).scalar_one() == migration.TOPIC_DESCRIPTIONS["07"]
        assert conn.execute(
            text("SELECT description FROM topics WHERE code='CUSTOM'")
        ).scalar_one() == "保留教师目录"
