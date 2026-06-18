"""token_version en usuarios — invalidación de sesiones (reset expulsa tokens)

Revision ID: e7b3c1d9f4a2
Revises: d4f1a8c3e7b2
Create Date: 2026-06-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e7b3c1d9f4a2"
down_revision: Union[str, Sequence[str], None] = "d4f1a8c3e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Versión de sesión. El JWT lleva 'tv' = este valor al emitirse; al cambiar la
    # contraseña (reset) se incrementa, invalidando todos los tokens previos. Los
    # tokens emitidos antes de esta columna no llevan 'tv' (se tratan como 0 == default).
    op.execute("ALTER TABLE usuarios ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS token_version")
