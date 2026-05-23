"""Añadir columna pais (ISO-2) a analisis para tracking geográfico

Revision ID: e9f4b71c25a8
Revises: d7e2b8c1f4a6
Create Date: 2026-05-20 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e9f4b71c25a8"
down_revision: Union[str, Sequence[str], None] = "d7e2b8c1f4a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHAR(2) para código ISO-3166-1 alpha-2 (ES, MX, AR, US, …).
    # NULLable: análisis anteriores y los hechos sin Cloudflare delante
    # (entorno local, scripts) no tienen país detectado.
    op.execute("ALTER TABLE analisis ADD COLUMN pais CHAR(2)")


def downgrade() -> None:
    op.execute("ALTER TABLE analisis DROP COLUMN IF EXISTS pais")
