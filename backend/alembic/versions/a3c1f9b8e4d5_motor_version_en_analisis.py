"""Añadir columna motor_version a analisis para medir antes/después de recalibrados

Revision ID: a3c1f9b8e4d5
Revises: e9f4b71c25a8
Create Date: 2026-05-26 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a3c1f9b8e4d5"
down_revision: Union[str, Sequence[str], None] = "e9f4b71c25a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # VARCHAR(20) — capacidad para semver tipo "0.5.16" o "0.6.0-beta".
    # NULLable: los análisis previos a esta migración quedan sin etiqueta
    # de versión (no se puede inferir cuál era el motor en ese momento).
    op.execute("ALTER TABLE analisis ADD COLUMN motor_version VARCHAR(20)")


def downgrade() -> None:
    op.execute("ALTER TABLE analisis DROP COLUMN IF EXISTS motor_version")
