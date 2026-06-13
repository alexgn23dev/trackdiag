"""Tabla comunidad_posts — tracks compartidos con la comunidad

Revision ID: c7d2e9f4a1b6
Revises: b3f8d1a6c9e2
Create Date: 2026-06-12 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7d2e9f4a1b6"
down_revision: Union[str, Sequence[str], None] = "b3f8d1a6c9e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Un post = un track compartido para recibir feedback de la comunidad.
    # Snapshot de los datos objetivos del análisis (decisión de Alex 2026-06-12:
    # estilo, bpm editable, loudness, balance, compat mono, objetivo — sin
    # duración como dato visible; se guarda duracion_seg para el player).
    # El audio vive en el volumen de Railway (/data/comunidad/{id}.{ext});
    # `waveform` guarda ~240 picos RMS normalizados para pintar la onda.
    op.execute("""
        CREATE TABLE comunidad_posts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            usuario_id UUID NOT NULL REFERENCES usuarios(id),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            titulo VARCHAR(120) NOT NULL,
            estilo VARCHAR(40),
            estilo_custom VARCHAR(60),
            bpm INT,
            objetivo VARCHAR(20),
            lufs REAL,
            balance VARCHAR(30),
            mono_correlacion REAL,
            mono_nivel VARCHAR(30),
            estado_track VARCHAR(40),
            duracion_seg REAL,
            waveform JSONB,
            audio_file VARCHAR(80) NOT NULL,
            audio_mime VARCHAR(40),
            audio_bytes INT,
            descargo_aceptado BOOLEAN NOT NULL DEFAULT FALSE,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            analisis_id UUID
        )
    """)
    op.execute("CREATE INDEX idx_comunidad_posts_timestamp ON comunidad_posts(timestamp DESC)")
    op.execute("CREATE INDEX idx_comunidad_posts_usuario ON comunidad_posts(usuario_id)")
    op.execute("CREATE INDEX idx_comunidad_posts_estilo ON comunidad_posts(estilo) WHERE activo")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS comunidad_posts")
