"""Tabla cta_eventos — embudo de conversión de la auditoría 1:1

Revision ID: d4e7f1b9c8a3
Revises: c8d3f7a2e1b4
Create Date: 2026-05-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e7f1b9c8a3"
down_revision: Union[str, Sequence[str], None] = "c8d3f7a2e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eventos del embudo. La columna `evento` toma uno de:
    #   cta_visto              — CTA renderizado tras un análisis (impresión)
    #   cta_clicked            — usuario clickó el CTA
    #   consultoria_visit      — entró en /consultoria
    #   consultoria_form_started — focus en el primer campo del form
    #   consultoria_form_submit  — submit OK del form
    # `session_id` es un hash anónimo guardado en localStorage para enlazar
    # eventos del mismo navegador entre páginas (SPA + /consultoria).
    # `diagnostico_id` solo aplica a cta_visto/cta_clicked.
    op.execute("""
        CREATE TABLE cta_eventos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            evento VARCHAR(50) NOT NULL,
            session_id VARCHAR(64),
            diagnostico_id VARCHAR(50),
            email VARCHAR(180),
            user_agent TEXT
        )
    """)
    op.execute("CREATE INDEX idx_cta_eventos_timestamp ON cta_eventos(timestamp DESC)")
    op.execute("CREATE INDEX idx_cta_eventos_evento ON cta_eventos(evento)")
    op.execute("CREATE INDEX idx_cta_eventos_session ON cta_eventos(session_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cta_eventos")
