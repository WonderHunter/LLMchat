from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, select

from app.db import engine, init_db
from app.models import User
from tests.conftest import reset_database


def test_migrations_build_the_schema_described_by_the_models():
    reset_database()
    init_db()
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, SQLModel.metadata)
    # Un écart ici veut dire qu'un modèle a changé sans sa migration.
    assert differences == []


def test_init_db_can_run_again_without_touching_data():
    reset_database()
    init_db()
    with Session(engine) as session:
        session.add(User(email="alice@example.com", password_hash="x"))
        session.commit()
    init_db()
    with Session(engine) as session:
        assert session.exec(select(User)).one().email == "alice@example.com"


def test_database_created_before_migrations_is_adopted_with_its_data():
    reset_database()
    # Comme le faisait la première version : tables créées directement, sans suivi de version.
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(email="ancien@example.com", password_hash="x"))
        session.commit()

    init_db()

    assert "alembic_version" in inspect(engine).get_table_names()
    with Session(engine) as session:
        assert session.exec(select(User)).one().email == "ancien@example.com"
