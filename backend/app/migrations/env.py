from alembic import context
from sqlmodel import SQLModel

from app import models  # noqa: F401  (enregistre les tables)
from app.db import engine


def run(connection) -> None:
    # render_as_batch : SQLite ne sait pas modifier une colonne, Alembic recrée alors la table.
    context.configure(
        connection=connection, target_metadata=SQLModel.metadata, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


# L'application fournit sa connexion ; en ligne de commande, on en ouvre une.
provided = context.config.attributes.get("connection")
if provided is not None:
    run(provided)
else:
    with engine.begin() as connection:
        run(connection)
