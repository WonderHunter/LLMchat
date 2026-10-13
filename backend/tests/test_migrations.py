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
    # Comme le laissait la première version : le schéma initial, sans suivi de version.
    init_db("0001")
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.exec_driver_sql(
            "INSERT INTO user (email, password_hash, created_at) "
            "VALUES ('ancien@example.com', 'x', '2026-10-13 08:00:00')"
        )

    init_db()

    assert "alembic_version" in inspect(engine).get_table_names()
    with Session(engine) as session:
        adopted = session.exec(select(User)).one()
    assert adopted.email == "ancien@example.com"
    # La colonne ajoutée depuis est remplie pour les comptes existants.
    assert adopted.token_version == 0
