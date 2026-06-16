"""Unicidad de username case-insensitive (anti suplantación @Alex/@alex)

Revision ID: c2a7e9d4b1f8
Revises: b5c8e3f1a9d2
Create Date: 2026-06-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c2a7e9d4b1f8"
down_revision: Union[str, Sequence[str], None] = "b5c8e3f1a9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # En una comunidad no anónima, @Alex y @alex no deben poder coexistir: la
    # comprobación de la app ya es case-insensitive, pero el índice único de la
    # DB era case-sensitive, dejando una rendija por carrera. Sustituimos el
    # índice único por uno FUNCIONAL sobre LOWER(username). 0 duplicados al
    # migrar (verificado en prod). DROP doble por si era constraint o índice.
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS uq_usuarios_username")
    op.execute("DROP INDEX IF EXISTS uq_usuarios_username")
    op.execute("DROP INDEX IF EXISTS idx_usuarios_username_lower")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_username_ci "
        "ON usuarios (LOWER(username))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_usuarios_username_ci")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_username ON usuarios (username)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usuarios_username_lower "
        "ON usuarios (LOWER(username)) WHERE username IS NOT NULL"
    )
