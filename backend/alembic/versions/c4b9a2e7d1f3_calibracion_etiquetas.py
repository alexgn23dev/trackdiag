"""calibracion_etiquetas — feedback de Alex sobre análisis para calibrar el motor

Revision ID: c4b9a2e7d1f3
Revises: 8f3a1c5d9e2b
Create Date: 2026-05-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c4b9a2e7d1f3"
down_revision: Union[str, Sequence[str], None] = "8f3a1c5d9e2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE calibracion_etiquetas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analisis_id UUID NOT NULL REFERENCES analisis(id) ON DELETE CASCADE,
            etiquetador_email TEXT NOT NULL,
            veredicto TEXT,
            comentario TEXT,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (analisis_id, etiquetador_email)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_calibracion_etiquetas_email "
        "ON calibracion_etiquetas (etiquetador_email)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS calibracion_etiquetas")
