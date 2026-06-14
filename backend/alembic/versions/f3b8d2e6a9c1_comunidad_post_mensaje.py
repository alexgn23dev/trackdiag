"""Mensaje de presentación en los posts de la comunidad

Revision ID: f3b8d2e6a9c1
Revises: e1f4a7b2c5d8
Create Date: 2026-06-14 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f3b8d2e6a9c1"
down_revision: Union[str, Sequence[str], None] = "e1f4a7b2c5d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mensaje breve que el productor escribe al compartir, para dar contexto
    # ("WIP de melodic techno, no sé si el drop pega"). Se muestra junto al
    # reproductor en el muro.
    op.execute("ALTER TABLE comunidad_posts ADD COLUMN mensaje TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE comunidad_posts DROP COLUMN IF EXISTS mensaje")
