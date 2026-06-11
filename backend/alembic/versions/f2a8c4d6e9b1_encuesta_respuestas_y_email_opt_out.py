"""Tabla encuesta_respuestas + flag email_opt_out en usuarios

Revision ID: f2a8c4d6e9b1
Revises: d4e7f1b9c8a3
Create Date: 2026-06-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f2a8c4d6e9b1"
down_revision: Union[str, Sequence[str], None] = "d4e7f1b9c8a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Respuestas de encuestas enviadas por email a los usuarios.
    # `encuesta` identifica la campaña (p.ej. 'comunidad-2026-06').
    # `opcion` es la respuesta elegida (un clic en el email):
    #   todo            — compartiría mis tracks Y comentaría los de otros
    #   solo_compartir  — compartiría, pero no me veo comentando
    #   solo_comentar   — comentaría los de otros, pero aún no compartiría
    #   no              — no me interesa
    # Un voto por (encuesta, email); el último clic gana (upsert).
    op.execute("""
        CREATE TABLE encuesta_respuestas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            encuesta VARCHAR(60) NOT NULL,
            email VARCHAR(180) NOT NULL,
            opcion VARCHAR(40) NOT NULL,
            comentario TEXT,
            UNIQUE (encuesta, email)
        )
    """)
    op.execute("CREATE INDEX idx_encuesta_respuestas_encuesta ON encuesta_respuestas(encuesta)")
    # Baja voluntaria de emails no transaccionales (encuestas, novedades).
    # Los emails operativos (reset password) no se ven afectados.
    op.execute("ALTER TABLE usuarios ADD COLUMN email_opt_out BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS encuesta_respuestas")
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS email_opt_out")
