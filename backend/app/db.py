from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.config import get_settings


def _make_engine():
    url = get_settings().database_url
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        # Base en mémoire : une seule connexion partagée, sinon chaque session voit une base vide.
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = _make_engine()


# Schéma des bases créées avant l'arrivée des migrations.
_FIRST_REVISION = "0001"


def init_db(revision: str = "head") -> None:
    """Amène la base au schéma voulu (le plus récent par défaut) en appliquant les migrations."""
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        tables = inspect(connection).get_table_names()
        if "user" in tables and "alembic_version" not in tables:
            # Base d'avant les migrations : elle a déjà le schéma initial, on le note seulement.
            command.stamp(config, _FIRST_REVISION)
        command.upgrade(config, revision)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
