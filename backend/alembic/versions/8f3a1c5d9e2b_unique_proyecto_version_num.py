"""unique (proyecto_id, version_num) para evitar duplicados por carrera

Revision ID: 8f3a1c5d9e2b
Revises: 2a7623b3dc33
Create Date: 2026-05-19 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "8f3a1c5d9e2b"
down_revision: Union[str, Sequence[str], None] = "2a7623b3dc33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Índice único parcial: solo aplica cuando hay proyecto + version_num.
    # Los análisis sueltos (proyecto_id IS NULL) o sin numerar quedan fuera.
    op.execute(
        "CREATE UNIQUE INDEX uq_analisis_proyecto_version "
        "ON analisis (proyecto_id, version_num) "
        "WHERE proyecto_id IS NOT NULL AND version_num IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_analisis_proyecto_version")
