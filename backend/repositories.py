"""
Capa de acceso a Postgres.
Una función por operación SQL. Sin ORM — asyncpg directo.

Todas las funciones reciben el `pool` como primer argumento explícito.
Esto facilita testing y evita estado global escondido.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg


# =============================================================================
# USUARIOS
# =============================================================================

async def get_user_by_email(pool: asyncpg.Pool, email: str) -> Optional[dict]:
    email = (email or "").strip().lower()
    if not email:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, password_hash, username, fecha_registro
               FROM usuarios WHERE LOWER(email) = $1""",
            email,
        )
    return dict(row) if row else None


async def get_user_by_username(pool: asyncpg.Pool, username: str) -> Optional[dict]:
    username = (username or "").strip()
    if not username:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, email, password_hash, username, fecha_registro
               FROM usuarios WHERE LOWER(username) = LOWER($1)""",
            username,
        )
    return dict(row) if row else None


async def get_user_by_identifier(pool: asyncpg.Pool, identifier: str) -> Optional[dict]:
    """Email si contiene '@', si no username."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    if "@" in ident:
        return await get_user_by_email(pool, ident)
    return await get_user_by_username(pool, ident)


async def create_user(
    pool: asyncpg.Pool, email: str, password_hash: str, username: Optional[str] = None
) -> dict:
    email = (email or "").strip().lower()
    username = (username or "").strip() or None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO usuarios (email, password_hash, username)
               VALUES ($1, $2, $3)
               RETURNING id, email, password_hash, username, fecha_registro""",
            email, password_hash, username,
        )
    return dict(row)


async def update_user_password(
    pool: asyncpg.Pool, user_id: UUID, new_hash: str
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE usuarios SET password_hash = $1 WHERE id = $2",
            new_hash, user_id,
        )
    return result.endswith(" 1")


async def update_user_username(
    pool: asyncpg.Pool, user_id: UUID, username: str
) -> bool:
    username = (username or "").strip()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE usuarios SET username = $1 WHERE id = $2",
            username, user_id,
        )
    return result.endswith(" 1")


async def is_username_available(pool: asyncpg.Pool, username: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM usuarios WHERE LOWER(username) = LOWER($1) LIMIT 1",
            username,
        )
    return row is None


# =============================================================================
# PROYECTOS
# =============================================================================

async def list_proyectos_usuario(
    pool: asyncpg.Pool, usuario_id: UUID, include_archivados: bool = False
) -> list[dict]:
    async with pool.acquire() as conn:
        if include_archivados:
            rows = await conn.fetch(
                """SELECT id, nombre, fecha_creacion, archivado
                   FROM proyectos WHERE usuario_id = $1
                   ORDER BY fecha_creacion DESC""",
                usuario_id,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, nombre, fecha_creacion, archivado
                   FROM proyectos
                   WHERE usuario_id = $1 AND NOT archivado
                   ORDER BY fecha_creacion DESC""",
                usuario_id,
            )
    return [dict(r) for r in rows]


async def create_proyecto(
    pool: asyncpg.Pool, usuario_id: UUID, nombre: str
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO proyectos (usuario_id, nombre)
               VALUES ($1, $2)
               RETURNING id, nombre, fecha_creacion, archivado""",
            usuario_id, nombre.strip(),
        )
    return dict(row)


async def archivar_proyecto(
    pool: asyncpg.Pool, proyecto_id: UUID, usuario_id: UUID, archivar: bool = True
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE proyectos SET archivado = $1
               WHERE id = $2 AND usuario_id = $3""",
            archivar, proyecto_id, usuario_id,
        )
    return result.endswith(" 1")


async def renombrar_proyecto(
    pool: asyncpg.Pool, proyecto_id: UUID, usuario_id: UUID, nuevo_nombre: str
) -> bool:
    nuevo = nuevo_nombre.strip()
    if not nuevo:
        return False
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE proyectos SET nombre = $1
               WHERE id = $2 AND usuario_id = $3""",
            nuevo, proyecto_id, usuario_id,
        )
    return result.endswith(" 1")


async def next_version_num(
    pool: asyncpg.Pool, proyecto_id: UUID
) -> int:
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COALESCE(MAX(version_num), 0) + 1 FROM analisis WHERE proyecto_id = $1",
            proyecto_id,
        )
    return int(val)


# =============================================================================
# ANÁLISIS
# =============================================================================

async def create_analisis(
    pool: asyncpg.Pool,
    *,
    usuario_id: Optional[UUID],
    proyecto_id: Optional[UUID],
    version_num: Optional[int],
    version_etiqueta: Optional[str],
    timestamp: datetime,
    email: str,
    nombre_proyecto_legacy: Optional[str],
    formulario: dict,
    diagnostico: str,
    senales: dict,
    genero_custom: Optional[str] = None,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO analisis (
                usuario_id, proyecto_id, version_num, version_etiqueta,
                timestamp, email, nombre_proyecto_legacy,
                formulario, diagnostico, senales, genero_custom
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id, timestamp, version_num""",
            usuario_id, proyecto_id, version_num, version_etiqueta,
            timestamp, email.strip().lower(), nombre_proyecto_legacy,
            formulario, diagnostico, senales, genero_custom,
        )
    return dict(row)


async def list_analisis_usuario(
    pool: asyncpg.Pool, usuario_id: UUID, limit: int = 200
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, proyecto_id, version_num, version_etiqueta,
                      timestamp, email, nombre_proyecto_legacy,
                      formulario, diagnostico, senales,
                      fue_util, comentario, feedback_real, genero_custom
               FROM analisis
               WHERE usuario_id = $1
               ORDER BY timestamp DESC
               LIMIT $2""",
            usuario_id, limit,
        )
    return [dict(r) for r in rows]


async def list_analisis_proyecto(
    pool: asyncpg.Pool, proyecto_id: UUID
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, version_num, version_etiqueta, timestamp,
                      formulario, diagnostico, senales,
                      fue_util, comentario, feedback_real
               FROM analisis
               WHERE proyecto_id = $1
               ORDER BY version_num ASC, timestamp ASC""",
            proyecto_id,
        )
    return [dict(r) for r in rows]


async def update_analisis_feedback(
    pool: asyncpg.Pool, analisis_id: UUID, *,
    fue_util: Optional[str] = None,
    comentario: Optional[str] = None,
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE analisis
               SET fue_util = COALESCE($1, fue_util),
                   comentario = COALESCE($2, comentario)
               WHERE id = $3""",
            fue_util, comentario, analisis_id,
        )
    return result.endswith(" 1")


async def update_analisis_feedback_real(
    pool: asyncpg.Pool, analisis_id: UUID, enlace: str
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE analisis SET feedback_real = $1 WHERE id = $2",
            enlace.strip(), analisis_id,
        )
    return result.endswith(" 1")


async def find_latest_analisis_by_email(
    pool: asyncpg.Pool, email: str
) -> Optional[dict]:
    """Compatibilidad: encontrar el análisis más reciente por email
    (usado por el flujo de feedback que no manda analisis_id)."""
    email = (email or "").strip().lower()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, timestamp FROM analisis
               WHERE LOWER(email) = $1
               ORDER BY timestamp DESC LIMIT 1""",
            email,
        )
    return dict(row) if row else None


# =============================================================================
# IDEAS
# =============================================================================

async def list_ideas(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, nombre, titulo, descripcion, fecha, votos
               FROM ideas
               WHERE NOT archivada
               ORDER BY votos DESC, fecha DESC"""
        )
    return [dict(r) for r in rows]


async def create_idea(
    pool: asyncpg.Pool, *, nombre: str, titulo: str, descripcion: str
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO ideas (nombre, titulo, descripcion)
               VALUES ($1, $2, $3)
               RETURNING id, nombre, titulo, descripcion, fecha, votos""",
            nombre.strip()[:100], titulo.strip()[:200], descripcion.strip()[:1000],
        )
    return dict(row)


async def vote_idea(pool: asyncpg.Pool, idea_id: UUID, delta: int) -> Optional[int]:
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            """UPDATE ideas SET votos = votos + $1
               WHERE id = $2 AND NOT archivada
               RETURNING votos""",
            int(delta), idea_id,
        )
    return int(val) if val is not None else None
