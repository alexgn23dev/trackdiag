"""calibracion_etiquetas: añadir columna descartado para excluir tracks no relevantes

Revision ID: d7e2b8c1f4a6
Revises: c4b9a2e7d1f3
Create Date: 2026-05-20 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d7e2b8c1f4a6"
down_revision: Union[str, Sequence[str], None] = "c4b9a2e7d1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE calibracion_etiquetas "
        "ADD COLUMN descartado BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE calibracion_etiquetas DROP COLUMN IF EXISTS descartado"
    )
