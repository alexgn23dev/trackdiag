"""Reportes de contenido de la comunidad

Revision ID: d4f1a8c3e7b2
Revises: c2a7e9d4b1f8
Create Date: 2026-06-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4f1a8c3e7b2"
down_revision: Union[str, Sequence[str], None] = "c2a7e9d4b1f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE comunidad_reportes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id UUID NOT NULL REFERENCES comunidad_posts(id),
            reporter_id UUID REFERENCES usuarios(id),
            motivo TEXT,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            atendido BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_reportes_pendientes ON comunidad_reportes (atendido, timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS comunidad_reportes")
