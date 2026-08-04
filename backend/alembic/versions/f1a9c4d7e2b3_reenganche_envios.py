"""reenganche_envios — registro por análisis del email de vuelta al día 3

Revision ID: f1a9c4d7e2b3
Revises: e7b3c1d9f4a2
Create Date: 2026-08-03 12:00:00.000000

email_envios no sirve para esto: su PK es (campana) sola, es un candado de
campaña one-shot. Aquí hace falta una fila por destinatario, y el UNIQUE sobre
analisis_id es lo que hace atómico el claim entre réplicas (ON CONFLICT DO
NOTHING) y lo que impide reenviar tras un redeploy.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f1a9c4d7e2b3"
down_revision: Union[str, Sequence[str], None] = "e7b3c1d9f4a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reenganche_envios (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            -- Un email como máximo por análisis: este UNIQUE es el candado.
            analisis_id    UUID NOT NULL UNIQUE REFERENCES analisis(id) ON DELETE CASCADE,
            usuario_id     UUID REFERENCES usuarios(id) ON DELETE SET NULL,
            email          VARCHAR(180) NOT NULL,
            -- timestamp = cuándo se reservó (claim); enviado_at = cuándo salió
            timestamp      TIMESTAMPTZ NOT NULL DEFAULT now(),
            enviado_at     TIMESTAMPTZ,
            -- claimed | enviado | fallido | descartado (envío de prueba)
            estado         VARCHAR(20) NOT NULL DEFAULT 'claimed',
            resend_id      VARCHAR(80),
            error          TEXT,
            -- copia del diag_principal al enviar, para estadísticas sin tocar JSONB
            diagnostico_id VARCHAR(50)
        )
        """
    )
    # Cooldown por persona: se consulta por email y fecha.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reenganche_email_ts "
        "ON reenganche_envios (lower(email), timestamp DESC)"
    )
    # Reaper de claims huérfanos y estadísticas por estado.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reenganche_estado "
        "ON reenganche_envios (estado, timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reenganche_envios")
