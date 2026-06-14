"""Flag comunidad_beta en usuarios — habilitar cuentas a la comunidad sin tocar env

Revision ID: e1f4a7b2c5d8
Revises: d8e1a4c7f2b9
Create Date: 2026-06-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e1f4a7b2c5d8"
down_revision: Union[str, Sequence[str], None] = "d8e1a4c7f2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Permite habilitar usuarios concretos a la comunidad (pruebas privadas /
    # beta) desde la DB, sin editar la env COMUNIDAD_EMAILS ni redesplegar.
    op.execute("ALTER TABLE usuarios ADD COLUMN comunidad_beta BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS comunidad_beta")
