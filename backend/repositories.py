"""
Capa de acceso a Postgres.
Una función por operación SQL. Sin ORM — asyncpg directo.

Todas las funciones reciben el `pool` como primer argumento explícito.
Esto facilita testing y evita estado global escondido.
"""
import asyncio
import json
from datetime import datetime, timezone
from functools import wraps
from typing import Optional
from uuid import UUID

import asyncpg


def _is_transient_connection_error(exc: BaseException) -> bool:
    """True si el error proviene de una conexión TCP caída (Railway proxy,
    timeouts, etc.). Detectado por tipo o por mensaje porque asyncpg a veces
    envuelve OSError en su propia jerarquía."""
    if isinstance(exc, (
        asyncpg.exceptions.ConnectionDoesNotExistError,
        asyncpg.exceptions.InterfaceError,
        asyncpg.exceptions.ConnectionFailureError,
        ConnectionResetError,
        OSError,
        TimeoutError,
        asyncio.TimeoutError,
    )):
        return True
    msg = str(exc).lower()
    return any(s in msg for s in (
        "connection reset", "connection was closed",
        "connection lost", "broken pipe",
        "errno 54", "errno 32",
    ))


def with_retry(retries: int = 5, delay: float = 0.2):
    """Decorador: reintenta una operación si la conexión se cerró.
    Mitiga el problema del proxy TCP de Railway cortando conexiones
    idle sin avisar al cliente. En el siguiente intento, asyncpg coge una
    conexión distinta del pool (que pasa por el setup ping)."""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            last = None
            for i in range(retries):
                try:
                    return await fn(*args, **kwargs)
                except BaseException as e:
                    if not _is_transient_connection_error(e):
                        raise
                    last = e
                    if i < retries - 1:
                        await asyncio.sleep(delay * (i + 1))
            raise last

        return wrapper

    return decorator


# =============================================================================
# USUARIOS
# =============================================================================

@with_retry()
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


@with_retry()
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


@with_retry()
async def get_user_by_identifier(pool: asyncpg.Pool, identifier: str) -> Optional[dict]:
    """Email si contiene '@', si no username."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    if "@" in ident:
        return await get_user_by_email(pool, ident)
    return await get_user_by_username(pool, ident)


@with_retry()
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


@with_retry()
async def update_user_password(
    pool: asyncpg.Pool, user_id: UUID, new_hash: str
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE usuarios SET password_hash = $1 WHERE id = $2",
            new_hash, user_id,
        )
    return result.endswith(" 1")


@with_retry()
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


@with_retry()
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

@with_retry()
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


@with_retry()
async def list_proyectos_con_resumen(
    pool: asyncpg.Pool, usuario_id: UUID, include_archivados: bool = False
) -> list[dict]:
    """Lista proyectos del usuario con conteo de versiones y fecha de última.
    Útil para la vista de cards del panel."""
    where_archivado = "" if include_archivados else "AND NOT p.archivado"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT p.id, p.nombre, p.fecha_creacion, p.archivado,
                       COUNT(a.id) AS n_versiones,
                       MAX(a.timestamp) AS fecha_ultima_version
                FROM proyectos p
                LEFT JOIN analisis a ON a.proyecto_id = p.id
                WHERE p.usuario_id = $1 {where_archivado}
                GROUP BY p.id
                ORDER BY COALESCE(MAX(a.timestamp), p.fecha_creacion) DESC""",
            usuario_id,
        )
    return [dict(r) for r in rows]


@with_retry()
async def get_proyecto(
    pool: asyncpg.Pool, proyecto_id: UUID, usuario_id: UUID
) -> Optional[dict]:
    """Devuelve el proyecto si pertenece al usuario, o None."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, nombre, fecha_creacion, archivado
               FROM proyectos
               WHERE id = $1 AND usuario_id = $2""",
            proyecto_id, usuario_id,
        )
    return dict(row) if row else None


@with_retry()
async def find_proyecto_by_nombre(
    pool: asyncpg.Pool, usuario_id: UUID, nombre: str
) -> Optional[dict]:
    """Busca un proyecto por nombre exact-match case-insensitive del usuario."""
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, nombre, fecha_creacion, archivado
               FROM proyectos
               WHERE usuario_id = $1 AND LOWER(TRIM(nombre)) = LOWER(TRIM($2))""",
            usuario_id, nombre,
        )
    return dict(row) if row else None


@with_retry()
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


@with_retry()
async def get_or_create_proyecto(
    pool: asyncpg.Pool, usuario_id: UUID, nombre: str
) -> dict:
    """Atomicidad: busca por nombre exact, si no existe crea."""
    existing = await find_proyecto_by_nombre(pool, usuario_id, nombre)
    if existing:
        return existing
    return await create_proyecto(pool, usuario_id, nombre)


@with_retry()
async def list_analisis_sueltos_usuario(
    pool: asyncpg.Pool, usuario_id: UUID, limit: int = 200
) -> list[dict]:
    """Análisis del usuario sin proyecto asignado (legacy o aún no reasignados)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, timestamp, nombre_proyecto_legacy,
                      formulario, diagnostico, senales
               FROM analisis
               WHERE usuario_id = $1 AND proyecto_id IS NULL
               ORDER BY timestamp DESC
               LIMIT $2""",
            usuario_id, limit,
        )
    return [dict(r) for r in rows]


@with_retry()
async def asignar_analisis_a_proyecto(
    pool: asyncpg.Pool, analisis_id: UUID, proyecto_id: UUID, usuario_id: UUID
) -> bool:
    """Reasigna un análisis suelto a un proyecto y renumera todas las versiones
    del proyecto por orden cronológico. Atómico.

    Renumerar tras la asignación garantiza que el suelto antiguo no termine
    siendo \"v3\" cuando es anterior a v1 — el `version_num` siempre refleja
    el orden por timestamp.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Bloqueo del proyecto para evitar carreras en la renumeración.
            proyecto_owner = await conn.fetchval(
                "SELECT 1 FROM proyectos WHERE id = $1 AND usuario_id = $2 FOR UPDATE",
                proyecto_id, usuario_id,
            )
            if not proyecto_owner:
                return False
            owner = await conn.fetchval(
                """SELECT 1 FROM analisis a
                   WHERE a.id = $1 AND a.usuario_id = $2 AND a.proyecto_id IS NULL""",
                analisis_id, usuario_id,
            )
            if not owner:
                return False
            # Asignación temporal con version_num=NULL para que la renumeración
            # incluya este análisis ya dentro del proyecto.
            await conn.execute(
                """UPDATE analisis
                   SET proyecto_id = $1, version_num = NULL
                   WHERE id = $2""",
                proyecto_id, analisis_id,
            )
            # Renumerar todo el proyecto por orden cronológico (timestamp ASC).
            # Empuje en dos pasos para evitar colisiones con la futura UNIQUE
            # constraint: primero a negativos, luego a positivos.
            await conn.execute(
                """WITH ordered AS (
                       SELECT id, ROW_NUMBER() OVER (ORDER BY timestamp ASC, id) AS new_num
                       FROM analisis WHERE proyecto_id = $1
                   )
                   UPDATE analisis a
                   SET version_num = -o.new_num
                   FROM ordered o WHERE a.id = o.id""",
                proyecto_id,
            )
            await conn.execute(
                "UPDATE analisis SET version_num = -version_num WHERE proyecto_id = $1",
                proyecto_id,
            )
    return True


@with_retry()
async def renumerar_proyecto(
    pool: asyncpg.Pool, proyecto_id: UUID
) -> int:
    """Renumera todas las versiones de un proyecto por orden cronológico.
    Útil para arreglar proyectos con versiones desordenadas (legacy o tras
    operaciones manuales). Devuelve nº de versiones renumeradas."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT 1 FROM proyectos WHERE id = $1 FOR UPDATE",
                proyecto_id,
            )
            await conn.execute(
                """WITH ordered AS (
                       SELECT id, ROW_NUMBER() OVER (ORDER BY timestamp ASC, id) AS new_num
                       FROM analisis WHERE proyecto_id = $1
                   )
                   UPDATE analisis a
                   SET version_num = -o.new_num
                   FROM ordered o WHERE a.id = o.id""",
                proyecto_id,
            )
            result = await conn.execute(
                "UPDATE analisis SET version_num = -version_num WHERE proyecto_id = $1",
                proyecto_id,
            )
    # result viene como "UPDATE N"; extraemos N.
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


@with_retry()
async def update_version_etiqueta(
    pool: asyncpg.Pool, analisis_id: UUID, usuario_id: UUID, etiqueta: str
) -> bool:
    """Renombrar etiqueta de una versión concreta. Solo el dueño puede."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE analisis SET version_etiqueta = $1
               WHERE id = $2 AND usuario_id = $3""",
            (etiqueta.strip() or None), analisis_id, usuario_id,
        )
    return result.endswith(" 1")


@with_retry()
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


@with_retry()
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


@with_retry()
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

@with_retry()
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
    """Inserta un análisis. Si colisiona con uq_analisis_proyecto_version
    (dos requests concurrentes calcularon el mismo `version_num`), reintenta
    hasta 3 veces recalculando version_num bajo lock para resolver la carrera."""
    sql_insert = """INSERT INTO analisis (
                        usuario_id, proyecto_id, version_num, version_etiqueta,
                        timestamp, email, nombre_proyecto_legacy,
                        formulario, diagnostico, senales, genero_custom
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING id, timestamp, version_num"""
    email_norm = email.strip().lower()
    for attempt in range(3):
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql_insert,
                    usuario_id, proyecto_id, version_num, version_etiqueta,
                    timestamp, email_norm, nombre_proyecto_legacy,
                    formulario, diagnostico, senales, genero_custom,
                )
            return dict(row)
        except asyncpg.exceptions.UniqueViolationError:
            # Colisión: otra request acabó de insertar la misma version_num.
            # Sólo reintentamos si está vinculado a un proyecto — para sueltos
            # no hay carrera posible (proyecto_id NULL no está en el índice).
            if proyecto_id is None or version_num is None:
                raise
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT 1 FROM proyectos WHERE id = $1 FOR UPDATE",
                        proyecto_id,
                    )
                    version_num = await conn.fetchval(
                        "SELECT COALESCE(MAX(version_num), 0) + 1 FROM analisis WHERE proyecto_id = $1",
                        proyecto_id,
                    )
                    version_num = int(version_num)
            # vuelve al bucle a reintentar el INSERT con el nuevo version_num
    # Si llegamos aquí, ni 3 intentos resolvieron — propagar el último error.
    raise RuntimeError("create_analisis: colisión de version_num tras 3 intentos")


@with_retry()
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


@with_retry()
async def list_analisis_proyecto(
    pool: asyncpg.Pool, proyecto_id: UUID
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, version_num, version_etiqueta, timestamp,
                      formulario, diagnostico, senales,
                      fue_util, comentario, feedback_real, genero_custom
               FROM analisis
               WHERE proyecto_id = $1
               ORDER BY timestamp ASC, version_num ASC""",
            proyecto_id,
        )
    return [dict(r) for r in rows]


@with_retry()
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


@with_retry()
async def update_analisis_feedback_real(
    pool: asyncpg.Pool, analisis_id: UUID, enlace: str
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE analisis SET feedback_real = $1 WHERE id = $2",
            enlace.strip(), analisis_id,
        )
    return result.endswith(" 1")


@with_retry()
async def list_all_analisis(pool: asyncpg.Pool, limit: int = 10000) -> list[dict]:
    """Lista todos los análisis (admin/dashboard). Usar con cuidado al escalar.

    Orden ASC para preservar el contrato legacy: el dashboard espera filas
    en orden cronológico ascendente (oldest first) y luego hace .reverse()
    para mostrar las más recientes primero. Era el orden natural de Sheets."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, usuario_id, proyecto_id, version_num, version_etiqueta,
                      timestamp, email, nombre_proyecto_legacy,
                      formulario, diagnostico, senales,
                      fue_util, comentario, feedback_real,
                      revision_alex, nota_alex,
                      tutoriales_sugeridos, tutorial_clickado,
                      genero_custom
               FROM analisis
               ORDER BY timestamp ASC
               LIMIT $1""",
            limit,
        )
    return [dict(r) for r in rows]


@with_retry()
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

@with_retry()
async def list_ideas(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, nombre, titulo, descripcion, fecha, votos
               FROM ideas
               WHERE NOT archivada
               ORDER BY votos DESC, fecha DESC"""
        )
    return [dict(r) for r in rows]


@with_retry()
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


@with_retry()
async def vote_idea(pool: asyncpg.Pool, idea_id: UUID, delta: int) -> Optional[int]:
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            """UPDATE ideas SET votos = votos + $1
               WHERE id = $2 AND NOT archivada
               RETURNING votos""",
            int(delta), idea_id,
        )
    return int(val) if val is not None else None
