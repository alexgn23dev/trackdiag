"""Tabla email_envios — candado anti-doble-envío de campañas de email

Revision ID: a9e5c2f7b3d8
Revises: f2a8c4d6e9b1
Create Date: 2026-06-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a9e5c2f7b3d8"
down_revision: Union[str, Sequence[str], None] = "f2a8c4d6e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Una fila por campaña enviada. El INSERT con ON CONFLICT DO NOTHING actúa
    # de candado: solo el proceso que consigue insertar la fila envía — un
    # redeploy o un segundo worker no pueden duplicar el envío.
    op.execute("""
        CREATE TABLE email_envios (
            campana VARCHAR(80) PRIMARY KEY,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            enviado_at TIMESTAMPTZ,
            n_enviados INT
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_envios")
