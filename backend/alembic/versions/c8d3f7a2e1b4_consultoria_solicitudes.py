"""Tabla consultoria_solicitudes — formularios de admisión de la sesión 1:1

Revision ID: c8d3f7a2e1b4
Revises: b5c7e2a9d3f1
Create Date: 2026-05-28 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c8d3f7a2e1b4"
down_revision: Union[str, Sequence[str], None] = "b5c7e2a9d3f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE consultoria_solicitudes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            nombre VARCHAR(120) NOT NULL,
            email VARCHAR(180) NOT NULL,
            soundcloud TEXT NOT NULL,
            ref_cancion TEXT,
            ref_artistas TEXT,
            ref_sellos TEXT,
            contexto TEXT,
            estado VARCHAR(30) NOT NULL DEFAULT 'nueva',
            notas_admin TEXT,
            actualizada_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_consultoria_solicitudes_timestamp ON consultoria_solicitudes(timestamp DESC)")
    op.execute("CREATE INDEX idx_consultoria_solicitudes_estado ON consultoria_solicitudes(estado)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS consultoria_solicitudes")
