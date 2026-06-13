"""Tabla comunidad_comentarios — feedback en los tracks de la comunidad

Revision ID: d8e1a4c7f2b9
Revises: c7d2e9f4a1b6
Create Date: 2026-06-13 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d8e1a4c7f2b9"
down_revision: Union[str, Sequence[str], None] = "c7d2e9f4a1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Un comentario = feedback de un productor sobre el track de otro.
    # `util` lo marca el DUEÑO del track ("esto me ha ayudado") → reputación
    # para quien comentó. La reciprocidad (dar para poder publicar más) se
    # calcula al vuelo con COUNT, sin columnas extra.
    op.execute("""
        CREATE TABLE comunidad_comentarios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id UUID NOT NULL REFERENCES comunidad_posts(id),
            usuario_id UUID NOT NULL REFERENCES usuarios(id),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            texto TEXT NOT NULL,
            util BOOLEAN NOT NULL DEFAULT FALSE,
            activo BOOLEAN NOT NULL DEFAULT TRUE
        )
    """)
    op.execute("CREATE INDEX idx_comentarios_post ON comunidad_comentarios(post_id) WHERE activo")
    op.execute("CREATE INDEX idx_comentarios_usuario ON comunidad_comentarios(usuario_id) WHERE activo")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS comunidad_comentarios")
