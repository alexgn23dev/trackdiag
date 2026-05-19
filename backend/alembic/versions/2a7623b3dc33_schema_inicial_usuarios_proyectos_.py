"""schema inicial: usuarios proyectos analisis ideas

Revision ID: 2a7623b3dc33
Revises:
Create Date: 2026-05-19 01:12:49.729267

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2a7623b3dc33"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- usuarios ----------
    op.create_table(
        "usuarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("fecha_registro", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
        sa.UniqueConstraint("username", name="uq_usuarios_username"),
    )
    op.execute("CREATE INDEX idx_usuarios_email_lower ON usuarios (LOWER(email))")
    op.execute(
        "CREATE INDEX idx_usuarios_username_lower ON usuarios (LOWER(username)) "
        "WHERE username IS NOT NULL"
    )

    # ---------- proyectos ----------
    op.create_table(
        "proyectos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("archivado", sa.Boolean(), nullable=False,
                  server_default=sa.text("FALSE")),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"],
                                ondelete="CASCADE", name="fk_proyectos_usuario"),
    )
    op.execute(
        "CREATE INDEX idx_proyectos_usuario ON proyectos "
        "(usuario_id, archivado, fecha_creacion DESC)"
    )

    # ---------- analisis ----------
    op.create_table(
        "analisis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proyecto_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version_num", sa.Integer(), nullable=True),
        sa.Column("version_etiqueta", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("nombre_proyecto_legacy", sa.Text(), nullable=True),
        sa.Column("formulario", postgresql.JSONB(), nullable=False),
        sa.Column("diagnostico", sa.Text(), nullable=False),
        sa.Column("senales", postgresql.JSONB(), nullable=False),
        sa.Column("fue_util", sa.Text(), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("feedback_real", sa.Text(), nullable=True),
        sa.Column("revision_alex", sa.Text(), nullable=True),
        sa.Column("nota_alex", sa.Numeric(), nullable=True),
        sa.Column("tutoriales_sugeridos", postgresql.JSONB(), nullable=True),
        sa.Column("tutorial_clickado", sa.Text(), nullable=True),
        sa.Column("genero_custom", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"],
                                ondelete="SET NULL", name="fk_analisis_usuario"),
        sa.ForeignKeyConstraint(["proyecto_id"], ["proyectos.id"],
                                ondelete="SET NULL", name="fk_analisis_proyecto"),
    )
    op.execute("CREATE INDEX idx_analisis_proyecto ON analisis (proyecto_id, version_num)")
    op.execute("CREATE INDEX idx_analisis_usuario_ts ON analisis (usuario_id, timestamp DESC)")
    op.execute("CREATE INDEX idx_analisis_email_lower ON analisis (LOWER(email))")

    # ---------- ideas ----------
    op.create_table(
        "ideas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("nombre", sa.Text(), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("fecha", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("votos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("archivada", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )
    op.execute("CREATE INDEX idx_ideas_votos ON ideas (votos DESC) WHERE NOT archivada")


def downgrade() -> None:
    op.drop_table("ideas")
    op.drop_table("analisis")
    op.drop_table("proyectos")
    op.drop_table("usuarios")
