"""Foto de perfil en usuarios — avatar de comunidad

Revision ID: b5c8e3f1a9d2
Revises: a2c6e9b4d7f3
Create Date: 2026-06-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b5c8e3f1a9d2"
down_revision: Union[str, Sequence[str], None] = "a2c6e9b4d7f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nombre de archivo del avatar (guardado en el volumen de Railway, junto al
    # audio de comunidad). NULL = sin foto (se muestra la inicial del username).
    op.execute("ALTER TABLE usuarios ADD COLUMN perfil_foto VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS perfil_foto")
