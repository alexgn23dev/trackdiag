"""Tabla password_reset_tokens para reset de contraseña vía email transaccional

Revision ID: b5c7e2a9d3f1
Revises: a3c1f9b8e4d5
Create Date: 2026-05-27 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b5c7e2a9d3f1"
down_revision: Union[str, Sequence[str], None] = "a3c1f9b8e4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Token único de un solo uso para reset de contraseña. El token se genera
    # en Python (secrets.token_urlsafe) — VARCHAR amplio para futuro.
    # expires_at: timestamp absoluto, típicamente +1h desde create.
    # used_at: NULL hasta que se consuma; NOT NULL = ya usado, no reutilizable.
    op.execute("""
        CREATE TABLE password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            usuario_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            token VARCHAR(128) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_password_reset_tokens_token ON password_reset_tokens(token)")
    op.execute("CREATE INDEX idx_password_reset_tokens_usuario ON password_reset_tokens(usuario_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS password_reset_tokens")
