"""Perfil de comunidad en usuarios

Revision ID: b3f8d1a6c9e2
Revises: a9e5c2f7b3d8
Create Date: 2026-06-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b3f8d1a6c9e2"
down_revision: Union[str, Sequence[str], None] = "a9e5c2f7b3d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Perfil público del usuario para la futura comunidad de feedback.
    # Da credibilidad al feedback: cada comentario muestra de un vistazo
    # cuánto lleva produciendo quien comenta, en qué estilos y su trayectoria.
    #   perfil_experiencia — años produciendo (mismo enum que el cuestionario:
    #                        menos_6m / 6m_2a / 2a_5a / mas_5a)
    #   perfil_estilos     — array de géneros que produce (values del catálogo)
    #   perfil_publicado   — trayectoria: no / autoeditado / plataformas / sellos
    #   perfil_donde       — texto libre (nombres de sellos / plataformas)
    #   perfil_bio         — bio corta opcional
    #   perfil_completo    — true cuando el usuario ha guardado su perfil
    op.execute("ALTER TABLE usuarios ADD COLUMN perfil_experiencia VARCHAR(20)")
    op.execute("ALTER TABLE usuarios ADD COLUMN perfil_estilos JSONB")
    op.execute("ALTER TABLE usuarios ADD COLUMN perfil_publicado VARCHAR(20)")
    op.execute("ALTER TABLE usuarios ADD COLUMN perfil_donde TEXT")
    op.execute("ALTER TABLE usuarios ADD COLUMN perfil_bio TEXT")
    op.execute("ALTER TABLE usuarios ADD COLUMN perfil_completo BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    for col in ("perfil_experiencia", "perfil_estilos", "perfil_publicado",
                "perfil_donde", "perfil_bio", "perfil_completo"):
        op.execute(f"ALTER TABLE usuarios DROP COLUMN IF EXISTS {col}")
