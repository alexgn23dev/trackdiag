"""Flag pro en usuarios — tier de pago (FLAC lossless vs MP3)

Revision ID: a2c6e9b4d7f3
Revises: f3b8d2e6a9c1
Create Date: 2026-06-14 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a2c6e9b4d7f3"
down_revision: Union[str, Sequence[str], None] = "f3b8d2e6a9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tier Pro. De momento se activa a mano (DB); cuando haya pagos, lo pondrá
    # el webhook de Stripe. Usuarios Pro comparten en FLAC sin pérdida; los
    # gratis, en MP3 320.
    op.execute("ALTER TABLE usuarios ADD COLUMN pro BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP COLUMN IF EXISTS pro")
