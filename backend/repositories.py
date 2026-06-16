"""
Capa de acceso a Postgres.
Una función por operación SQL. Sin ORM — asyncpg directo.

Todas las funciones reciben el `pool` como primer argumento explícito.
Esto facilita testing y evita estado global escondido.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
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
async def get_user_by_id(pool: asyncpg.Pool, usuario_id) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, email_opt_out FROM usuarios WHERE id = $1",
            usuario_id,
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
async def update_user_foto(pool: asyncpg.Pool, email: str, filename: Optional[str]) -> Optional[str]:
    """Fija (o limpia, con None) el avatar del usuario. Devuelve el nombre del
    archivo ANTERIOR para poder borrarlo del volumen, o None si no había."""
    email = (email or "").strip().lower()
    async with pool.acquire() as conn:
        async with conn.transaction():
            antigua = await conn.fetchval(
                "SELECT perfil_foto FROM usuarios WHERE LOWER(email) = $1", email
            )
            await conn.execute(
                "UPDATE usuarios SET perfil_foto = $2 WHERE LOWER(email) = $1",
                email, filename,
            )
    return antigua


@with_retry()
async def is_username_available(pool: asyncpg.Pool, username: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM usuarios WHERE LOWER(username) = LOWER($1) LIMIT 1",
            username,
        )
    return row is None


@with_retry()
async def list_emails_migrated(pool: asyncpg.Pool) -> list[str]:
    """Devuelve todos los emails de usuarios con password_hash placeholder.
    Se usa para el self-heal bulk del cutover B: cada email se consulta a
    Sheets para obtener el hash real y copiarlo a Postgres."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT email FROM usuarios WHERE password_hash = '__MIGRATED__' ORDER BY email"
        )
    return [r["email"] for r in rows]


@with_retry()
async def stats_usuarios_migrated(pool: asyncpg.Pool) -> dict:
    """Inventario del cierre del cutover B. Devuelve cuántos usuarios tienen
    password_hash placeholder (__MIGRATED__) — los que todavía dependen del
    fallback Sheets para autenticar — y cuántos tienen análisis recientes."""
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM usuarios")
        migrated = await conn.fetchval(
            "SELECT COUNT(*) FROM usuarios WHERE password_hash = '__MIGRATED__'"
        )
        # Cuántos de los __MIGRATED__ tienen al menos un análisis. Los que no
        # tienen ningún análisis, casi seguro son cuentas zombi.
        con_actividad = await conn.fetchval(
            """SELECT COUNT(DISTINCT u.id) FROM usuarios u
               JOIN analisis a ON a.usuario_id = u.id
               WHERE u.password_hash = '__MIGRATED__'"""
        )
        # Cuántos con actividad reciente (últimos 30 días). Si son cero,
        # podemos eliminar el fallback sin afectar a nadie activo.
        recientes = await conn.fetchval(
            """SELECT COUNT(DISTINCT u.id) FROM usuarios u
               JOIN analisis a ON a.usuario_id = u.id
               WHERE u.password_hash = '__MIGRATED__'
                 AND a.timestamp > now() - INTERVAL '30 days'"""
        )
        ultima = await conn.fetchval(
            """SELECT MAX(a.timestamp) FROM usuarios u
               JOIN analisis a ON a.usuario_id = u.id
               WHERE u.password_hash = '__MIGRATED__'"""
        )
    return {
        "usuarios_total": int(total or 0),
        "migrated_pending": int(migrated or 0),
        "migrated_con_actividad_alguna_vez": int(con_actividad or 0),
        "migrated_con_actividad_ultimos_30d": int(recientes or 0),
        "ultima_actividad_migrated": ultima.isoformat() if ultima else None,
    }


# =============================================================================
# MÉTRICAS PÚBLICAS — para página /metricas (cache en main.py)
# =============================================================================

@with_retry()
async def get_public_metrics(pool: asyncpg.Pool) -> dict:
    """Devuelve totales agregados + serie de 30 días + top géneros para la
    página pública de métricas. Sin PII (emails, nombres). Pensado para
    cachearse 6h en memoria — no es una query barata si la tabla crece."""
    today = datetime.now(timezone.utc).date()
    rango_inicio = today - timedelta(days=29)  # 30 días incluyendo hoy

    async with pool.acquire() as conn:
        total_analisis = await conn.fetchval("SELECT COUNT(*) FROM analisis")
        total_usuarios = await conn.fetchval("SELECT COUNT(*) FROM usuarios")
        total_proyectos = await conn.fetchval("SELECT COUNT(*) FROM proyectos")

        # Acumulados ANTES del rango (para construir la línea desde el día 0).
        base_analisis = await conn.fetchval(
            "SELECT COUNT(*) FROM analisis WHERE timestamp::date < $1", rango_inicio,
        ) or 0
        # IMPORTANTE: usamos "fecha del primer análisis del usuario" en lugar de
        # `usuarios.fecha_registro`. Razón: los 316 usuarios migrados desde Sheets
        # tienen fecha_registro = fecha de la migración (~19 mayo 2026), lo que
        # hacía la curva plana en cero antes del cutover y un salto brusco después.
        # `MIN(timestamp)` por usuario refleja cuándo realmente empezó a usar
        # Mentotrack — mucho más representativo para la gráfica de crecimiento.
        base_usuarios = await conn.fetchval(
            """SELECT COUNT(*) FROM (
                 SELECT usuario_id, MIN(timestamp::date) AS first_day
                 FROM analisis WHERE usuario_id IS NOT NULL
                 GROUP BY usuario_id
               ) fs WHERE fs.first_day < $1""",
            rango_inicio,
        ) or 0

        # Conteos diarios dentro del rango
        analisis_rows = await conn.fetch(
            """SELECT timestamp::date AS d, COUNT(*) AS n
               FROM analisis WHERE timestamp::date >= $1
               GROUP BY 1 ORDER BY 1""",
            rango_inicio,
        )
        usuarios_rows = await conn.fetch(
            """WITH first_seen AS (
                 SELECT usuario_id, MIN(timestamp::date) AS first_day
                 FROM analisis WHERE usuario_id IS NOT NULL
                 GROUP BY usuario_id
               )
               SELECT first_day AS d, COUNT(*) AS n
               FROM first_seen WHERE first_day >= $1
               GROUP BY first_day ORDER BY first_day""",
            rango_inicio,
        )

        # Top géneros (formulario JSONB, key 'genero' = label en ES)
        generos_rows = await conn.fetch(
            """SELECT COALESCE(NULLIF(TRIM(formulario->>'genero'), ''), '—') AS genero,
                      COUNT(*) AS n
               FROM analisis
               WHERE formulario IS NOT NULL
               GROUP BY 1
               ORDER BY 2 DESC
               LIMIT 12"""
        )

    # Construir serie acumulada en Python (más simple y rápido que SQL recursivo)
    analisis_por_dia = {r["d"]: int(r["n"]) for r in analisis_rows}
    usuarios_por_dia = {r["d"]: int(r["n"]) for r in usuarios_rows}

    serie = []
    acum_a = int(base_analisis)
    acum_u = int(base_usuarios)
    for i in range(30):
        d = rango_inicio + timedelta(days=i)
        acum_a += analisis_por_dia.get(d, 0)
        acum_u += usuarios_por_dia.get(d, 0)
        serie.append({
            "date": d.isoformat(),
            "analisis": acum_a,
            "usuarios": acum_u,
        })

    generos_top = [
        {"genero": r["genero"], "n": int(r["n"])} for r in generos_rows
    ]

    return {
        "totales": {
            "analisis": int(total_analisis or 0),
            "usuarios": int(total_usuarios or 0),
            "proyectos": int(total_proyectos or 0),
        },
        "serie_30d": serie,
        "generos_top": generos_top,
    }


# =============================================================================
# CTA EVENTOS — embudo de conversión de la auditoría 1:1
# =============================================================================

_CTA_EVENTOS_VALIDOS = (
    "cta_visto",
    "cta_clicked",
    "consultoria_visit",
    "consultoria_calendly_click",   # clic en "Reserva tu llamada gratis" → Calendly
    "consultoria_form_started",     # legacy: form retirado (flujo llamada-primero)
    "consultoria_form_submit",      # legacy: form retirado (flujo llamada-primero)
)


@with_retry()
async def create_cta_evento(
    pool: asyncpg.Pool,
    *,
    evento: str,
    session_id: Optional[str] = None,
    diagnostico_id: Optional[str] = None,
    email: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    """Inserta un evento del embudo. Devuelve None si el evento no es válido."""
    if evento not in _CTA_EVENTOS_VALIDOS:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO cta_eventos
                   (evento, session_id, diagnostico_id, email, user_agent)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING id, timestamp, evento""",
            evento,
            (session_id or None),
            (diagnostico_id or None),
            (email or None),
            (user_agent or None),
        )
    return dict(row)


@with_retry()
async def stats_embudo_cta(pool: asyncpg.Pool, dias: int = 30) -> dict:
    """Agregados del embudo de los últimos N días + totales globales."""
    async with pool.acquire() as conn:
        totales = await conn.fetch(
            """SELECT evento, COUNT(*) AS n,
                      COUNT(DISTINCT session_id) AS sesiones
               FROM cta_eventos
               GROUP BY evento"""
        )
        recientes = await conn.fetch(
            """SELECT evento, COUNT(*) AS n,
                      COUNT(DISTINCT session_id) AS sesiones
               FROM cta_eventos
               WHERE timestamp > now() - ($1 || ' days')::INTERVAL
               GROUP BY evento""",
            str(dias),
        )
        serie_rows = await conn.fetch(
            """SELECT date_trunc('day', timestamp) AS d, evento, COUNT(*) AS n
               FROM cta_eventos
               WHERE timestamp > now() - ($1 || ' days')::INTERVAL
               GROUP BY 1, 2
               ORDER BY 1""",
            str(dias),
        )
        top_dx = await conn.fetch(
            """SELECT diagnostico_id, COUNT(*) AS n
               FROM cta_eventos
               WHERE evento = 'cta_visto' AND diagnostico_id IS NOT NULL
               GROUP BY diagnostico_id
               ORDER BY n DESC
               LIMIT 10"""
        )

    def _to_map(rows):
        return {r["evento"]: {"n": int(r["n"]), "sesiones": int(r["sesiones"])} for r in rows}

    serie = [
        {"date": r["d"].date().isoformat(), "evento": r["evento"], "n": int(r["n"])}
        for r in serie_rows
    ]
    return {
        "totales_global": _to_map(totales),
        "totales_recientes": _to_map(recientes),
        "dias_recientes": dias,
        "serie": serie,
        "top_dx": [{"dx": r["diagnostico_id"], "n": int(r["n"])} for r in top_dx],
    }


# =============================================================================
# CONSULTORÍA — solicitudes de la sesión 1:1 (formulario público)
# =============================================================================

_ESTADOS_CONSULTORIA = ("nueva", "aceptada", "rechazada", "completada", "reembolsada")


@with_retry()
async def create_consultoria_solicitud(
    pool: asyncpg.Pool,
    *,
    nombre: str,
    email: str,
    soundcloud: str,
    ref_cancion: str = "",
    ref_artistas: str = "",
    ref_sellos: str = "",
    contexto: str = "",
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO consultoria_solicitudes
                   (nombre, email, soundcloud, ref_cancion, ref_artistas, ref_sellos, contexto)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING id, timestamp, nombre, email, soundcloud,
                         ref_cancion, ref_artistas, ref_sellos, contexto,
                         estado, notas_admin, actualizada_en""",
            nombre, email, soundcloud,
            ref_cancion or None, ref_artistas or None,
            ref_sellos or None, contexto or None,
        )
    return dict(row)


@with_retry()
async def list_consultoria_solicitudes(
    pool: asyncpg.Pool, limit: int = 500
) -> list[dict]:
    """Lista solicitudes ordenadas por más recientes primero. Para uso admin."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, timestamp, nombre, email, soundcloud,
                      ref_cancion, ref_artistas, ref_sellos, contexto,
                      estado, notas_admin, actualizada_en
               FROM consultoria_solicitudes
               ORDER BY timestamp DESC
               LIMIT $1""",
            limit,
        )
    return [dict(r) for r in rows]


@with_retry()
async def update_consultoria_solicitud_estado(
    pool: asyncpg.Pool, solicitud_id: UUID,
    estado: Optional[str] = None,
    notas: Optional[str] = None,
) -> bool:
    """Actualiza estado y/o notas. Si estado se pasa, debe ser uno de
    _ESTADOS_CONSULTORIA. Si solo cambia notas, estado se queda igual."""
    if estado is not None and estado not in _ESTADOS_CONSULTORIA:
        return False
    sets, values = [], []
    if estado is not None:
        sets.append(f"estado = ${len(values) + 1}")
        values.append(estado)
    if notas is not None:
        sets.append(f"notas_admin = ${len(values) + 1}")
        values.append(notas)
    if not sets:
        return False
    sets.append("actualizada_en = now()")
    values.append(solicitud_id)
    sql = f"UPDATE consultoria_solicitudes SET {', '.join(sets)} WHERE id = ${len(values)}"
    async with pool.acquire() as conn:
        result = await conn.execute(sql, *values)
    return result.endswith(" 1")


# =============================================================================
# PASSWORD RESET TOKENS — reset de contraseña vía email transaccional
# =============================================================================

@with_retry()
async def create_password_reset_token(
    pool: asyncpg.Pool, usuario_id: UUID, token: str, expires_at: datetime
) -> dict:
    """Inserta un token de reset. El token se genera fuera con
    secrets.token_urlsafe(48). expires_at: TZ-aware (UTC)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO password_reset_tokens (usuario_id, token, expires_at)
               VALUES ($1, $2, $3)
               RETURNING id, usuario_id, token, expires_at, created_at""",
            usuario_id, token, expires_at,
        )
    return dict(row)


@with_retry()
async def get_password_reset_token(
    pool: asyncpg.Pool, token: str
) -> Optional[dict]:
    """Devuelve el token si existe, NO está usado y NO ha expirado, junto
    con el email del usuario asociado. None si no es válido."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT t.id, t.usuario_id, t.token, t.expires_at, t.used_at,
                      u.email
               FROM password_reset_tokens t
               JOIN usuarios u ON u.id = t.usuario_id
               WHERE t.token = $1
                 AND t.used_at IS NULL
                 AND t.expires_at > now()""",
            token,
        )
    return dict(row) if row else None


@with_retry()
async def mark_password_reset_token_used(
    pool: asyncpg.Pool, token_id: UUID
) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE password_reset_tokens SET used_at = now() WHERE id = $1",
            token_id,
        )
    return result.endswith(" 1")


@with_retry()
async def invalidate_active_tokens_for_user(
    pool: asyncpg.Pool, usuario_id: UUID
) -> int:
    """Marca como usados todos los tokens activos del usuario.
    Se llama antes de generar uno nuevo, por si pide varios resets seguidos."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE password_reset_tokens
               SET used_at = now()
               WHERE usuario_id = $1
                 AND used_at IS NULL
                 AND expires_at > now()""",
            usuario_id,
        )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


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
    pais: Optional[str] = None,
    motor_version: Optional[str] = None,
) -> dict:
    """Inserta un análisis. Si colisiona con uq_analisis_proyecto_version
    (dos requests concurrentes calcularon el mismo `version_num`), reintenta
    hasta 3 veces recalculando version_num bajo lock para resolver la carrera."""
    sql_insert = """INSERT INTO analisis (
                        usuario_id, proyecto_id, version_num, version_etiqueta,
                        timestamp, email, nombre_proyecto_legacy,
                        formulario, diagnostico, senales, genero_custom, pais,
                        motor_version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    RETURNING id, timestamp, version_num"""
    email_norm = email.strip().lower()
    for attempt in range(3):
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    sql_insert,
                    usuario_id, proyecto_id, version_num, version_etiqueta,
                    timestamp, email_norm, nombre_proyecto_legacy,
                    formulario, diagnostico, senales, genero_custom, pais,
                    motor_version,
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
async def update_tutorial_clickado(
    pool: asyncpg.Pool, analisis_id: UUID, tutorial_url: str
) -> bool:
    """Registra qué tutorial de YouTube clickó el usuario sobre un análisis.
    El campo `tutoriales_sugeridos` se hidrata al crear el análisis; este
    UPDATE sólo registra cuál de ellos llegó a abrir."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE analisis SET tutorial_clickado = $1 WHERE id = $2",
            tutorial_url.strip(), analisis_id,
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
                      genero_custom, pais, motor_version
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


# =============================================================================
# CALIBRACIÓN — etiquetas de Alex sobre análisis para entrenar el motor
# =============================================================================

@with_retry()
async def list_analisis_con_feedback_real(
    pool: asyncpg.Pool, etiquetador_email: str, limit: int = 200
) -> list[dict]:
    """Lista análisis con feedback_real no vacío, joinea con etiquetas del
    etiquetador para saber cuáles ya están etiquetados o descartados.

    Devuelve la fila del análisis + (etiqueta_id, veredicto, comentario,
    descartado, fecha_etiqueta) cuando existe."""
    email = (etiquetador_email or "").strip().lower()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT
                   a.id, a.timestamp, a.email, a.nombre_proyecto_legacy,
                   a.formulario, a.diagnostico, a.senales,
                   a.feedback_real, a.genero_custom, a.proyecto_id,
                   a.version_num,
                   c.id AS etiqueta_id,
                   c.veredicto,
                   c.comentario,
                   c.descartado,
                   c.timestamp AS fecha_etiqueta
               FROM analisis a
               LEFT JOIN calibracion_etiquetas c
                   ON c.analisis_id = a.id AND LOWER(c.etiquetador_email) = $1
               WHERE a.feedback_real IS NOT NULL AND a.feedback_real <> ''
               ORDER BY a.timestamp DESC
               LIMIT $2""",
            email, limit,
        )
    return [dict(r) for r in rows]


@with_retry()
async def upsert_etiqueta_calibracion(
    pool: asyncpg.Pool,
    *,
    analisis_id: UUID,
    etiquetador_email: str,
    veredicto: Optional[str],
    comentario: Optional[str],
    descartado: bool = False,
) -> dict:
    """Inserta o actualiza la etiqueta de calibración del etiquetador para
    ese análisis. Único por (analisis_id, etiquetador_email)."""
    email = (etiquetador_email or "").strip().lower()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO calibracion_etiquetas
                   (analisis_id, etiquetador_email, veredicto, comentario, descartado)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (analisis_id, etiquetador_email) DO UPDATE
                   SET veredicto = EXCLUDED.veredicto,
                       comentario = EXCLUDED.comentario,
                       descartado = EXCLUDED.descartado,
                       timestamp = now()
               RETURNING id, analisis_id, etiquetador_email,
                         veredicto, comentario, descartado, timestamp""",
            analisis_id, email, veredicto, comentario, descartado,
        )
    return dict(row)


@with_retry()
async def delete_etiqueta_calibracion(
    pool: asyncpg.Pool, analisis_id: UUID, etiquetador_email: str
) -> bool:
    email = (etiquetador_email or "").strip().lower()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """DELETE FROM calibracion_etiquetas
               WHERE analisis_id = $1 AND LOWER(etiquetador_email) = $2""",
            analisis_id, email,
        )
    return result.endswith(" 1")


@with_retry()
async def get_stats_calibracion_raw(
    pool: asyncpg.Pool, etiquetador_email: str
) -> dict:
    """Devuelve las etiquetas del admin con el diagnóstico del motor asociado
    y el total de análisis disponibles para etiquetar. La agregación en
    estadísticas se hace en Python para no acoplar SQL al formato del diag."""
    email = (etiquetador_email or "").strip().lower()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.veredicto, c.comentario, c.descartado, a.diagnostico
               FROM calibracion_etiquetas c
               JOIN analisis a ON c.analisis_id = a.id
               WHERE LOWER(c.etiquetador_email) = $1""",
            email,
        )
        total = await conn.fetchval(
            """SELECT COUNT(*) FROM analisis
               WHERE feedback_real IS NOT NULL AND feedback_real <> ''"""
        )
    return {
        "etiquetas": [dict(r) for r in rows],
        "total_disponibles": int(total or 0),
    }


# =============================================================================
# REPORTE MENSUAL — MÉTRICAS GENERALES DE MENTOTRACK
# =============================================================================

@with_retry()
async def stats_reporte_mensual(pool: asyncpg.Pool, year: int, month: int) -> dict:
    """Calcula todas las métricas para el reporte mensual:
    - Análisis ese mes (desglosado por semana)
    - Análisis totales desde inicio
    - Usuarios totales
    - Usuarios nuevos ese mes (desglosado por semana)
    - Análisis por persona (promedio, mediana) — toda la historia + solo ese mes
    - Stats del embudo CTA (desde stats_embudo_cta)
    """
    async with pool.acquire() as conn:
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        # Análisis en el mes, desglosado por semana ISO
        analisis_por_semana = await conn.fetch(
            """SELECT
                 to_char(timestamp, 'WW') as semana_num,
                 to_char(timestamp, 'YYYY-MM-DD') as fecha_inicio_semana,
                 COUNT(*) as analisis
               FROM analisis
               WHERE timestamp >= $1 AND timestamp < $2
               GROUP BY semana_num, fecha_inicio_semana
               ORDER BY semana_num ASC""",
            start_date, end_date,
        )

        # Total de análisis ese mes
        total_mes = await conn.fetchval(
            """SELECT COUNT(*) FROM analisis
               WHERE timestamp >= $1 AND timestamp < $2""",
            start_date, end_date,
        )

        # Total de análisis desde el inicio
        total_all_time = await conn.fetchval(
            """SELECT COUNT(*) FROM analisis"""
        )

        # Análisis con track de referencia — la sección se escribe en el texto
        # del informe desde v0.5.32; no hay columna dedicada, se detecta por LIKE
        con_ref_mes = await conn.fetchval(
            """SELECT COUNT(*) FROM analisis
               WHERE timestamp >= $1 AND timestamp < $2
                 AND diagnostico LIKE '%COMPARACIÓN CON REFERENCIA%'""",
            start_date, end_date,
        )
        con_ref_all_time = await conn.fetchval(
            """SELECT COUNT(*) FROM analisis
               WHERE diagnostico LIKE '%COMPARACIÓN CON REFERENCIA%'"""
        )

        # Total de usuarios
        total_usuarios = await conn.fetchval(
            """SELECT COUNT(*) FROM usuarios"""
        )

        # Usuarios nuevos ese mes, desglosado por semana ISO
        usuarios_nuevos_por_semana = await conn.fetch(
            """SELECT
                 to_char(fecha_registro, 'WW') as semana_num,
                 to_char(fecha_registro, 'YYYY-MM-DD') as fecha_inicio_semana,
                 COUNT(*) as usuarios_nuevos
               FROM usuarios
               WHERE fecha_registro >= $1 AND fecha_registro < $2
               GROUP BY semana_num, fecha_inicio_semana
               ORDER BY semana_num ASC""",
            start_date, end_date,
        )

        # Usuarios nuevos en el mes
        usuarios_nuevos_mes = await conn.fetchval(
            """SELECT COUNT(*) FROM usuarios
               WHERE fecha_registro >= $1 AND fecha_registro < $2""",
            start_date, end_date,
        )

        # Análisis por persona — TODA la historia
        stats_all_time = await conn.fetchrow(
            """SELECT
                 COUNT(DISTINCT usuario_id) as usuarios_con_analisis,
                 AVG(analisis_count) as promedio,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY analisis_count) as mediana,
                 MAX(analisis_count) as maximo,
                 MIN(analisis_count) as minimo
               FROM (
                 SELECT usuario_id, COUNT(*) as analisis_count
                 FROM analisis
                 WHERE usuario_id IS NOT NULL
                 GROUP BY usuario_id
               ) user_counts"""
        )

        # Análisis por persona — SOLO ese mes
        stats_mes = await conn.fetchrow(
            """SELECT
                 COUNT(DISTINCT usuario_id) as usuarios_con_analisis,
                 AVG(analisis_count) as promedio,
                 PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY analisis_count) as mediana,
                 MAX(analisis_count) as maximo,
                 MIN(analisis_count) as minimo
               FROM (
                 SELECT usuario_id, COUNT(*) as analisis_count
                 FROM analisis
                 WHERE usuario_id IS NOT NULL
                   AND timestamp >= $1 AND timestamp < $2
                 GROUP BY usuario_id
               ) user_counts""",
            start_date, end_date,
        )

    return {
        "mes": f"{year}-{month:02d}",
        "analisis": {
            "total_mes": int(total_mes or 0),
            "total_all_time": int(total_all_time or 0),
            "con_referencia_mes": int(con_ref_mes or 0),
            "con_referencia_all_time": int(con_ref_all_time or 0),
            "por_semana": [
                {
                    "semana": row["semana_num"],
                    "fecha_inicio": row["fecha_inicio_semana"],
                    "count": row["analisis"],
                }
                for row in analisis_por_semana
            ],
        },
        "usuarios": {
            "total": int(total_usuarios or 0),
            "nuevos_mes": int(usuarios_nuevos_mes or 0),
            "nuevos_por_semana": [
                {
                    "semana": row["semana_num"],
                    "fecha_inicio": row["fecha_inicio_semana"],
                    "count": row["usuarios_nuevos"],
                }
                for row in usuarios_nuevos_por_semana
            ],
        },
        "analisis_por_persona": {
            "all_time": {
                "usuarios_con_analisis": int(stats_all_time["usuarios_con_analisis"] or 0),
                "promedio": float(stats_all_time["promedio"] or 0),
                "mediana": float(stats_all_time["mediana"] or 0),
                "maximo": int(stats_all_time["maximo"] or 0),
                "minimo": int(stats_all_time["minimo"] or 0),
            },
            "mes": {
                "usuarios_con_analisis": int(stats_mes["usuarios_con_analisis"] or 0),
                "promedio": float(stats_mes["promedio"] or 0),
                "mediana": float(stats_mes["mediana"] or 0),
                "maximo": int(stats_mes["maximo"] or 0),
                "minimo": int(stats_mes["minimo"] or 0),
            },
        },
    }


# =========================================================================
# Encuestas por email (v0.5.34)
# =========================================================================


@with_retry()
async def tiene_respuesta_encuesta(pool: asyncpg.Pool, encuesta: str, email: str) -> bool:
    """¿Ya respondió este usuario a la encuesta? (para no mostrarle el CTA in-app
    si ya votó por email o dentro de la app)."""
    email = (email or "").strip().lower()
    if not email:
        return False
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT 1 FROM encuesta_respuestas WHERE encuesta = $1 AND email = $2",
            encuesta, email,
        )
    return v is not None


@with_retry()
async def upsert_encuesta_respuesta(
    pool: asyncpg.Pool, encuesta: str, email: str, opcion: str
) -> None:
    """Registra (o actualiza) el voto de un usuario en una encuesta.
    Un voto por (encuesta, email); el último clic gana. El comentario
    previo se conserva si el usuario solo cambia la opción."""
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO encuesta_respuestas (encuesta, email, opcion)
               VALUES ($1, lower($2), $3)
               ON CONFLICT (encuesta, email)
               DO UPDATE SET opcion = EXCLUDED.opcion, timestamp = now()""",
            encuesta, email, opcion,
        )


@with_retry()
async def set_encuesta_comentario(
    pool: asyncpg.Pool, encuesta: str, email: str, comentario: str
) -> bool:
    """Añade el comentario libre a un voto ya registrado. Devuelve False
    si el usuario aún no ha votado en esa encuesta."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE encuesta_respuestas SET comentario = $3
               WHERE encuesta = $1 AND email = lower($2)""",
            encuesta, email, comentario,
        )
    return result == "UPDATE 1"


@with_retry()
async def set_email_opt_out(pool: asyncpg.Pool, email: str) -> bool:
    """Marca al usuario como dado de baja de emails no transaccionales."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE usuarios SET email_opt_out = TRUE WHERE lower(email) = lower($1)",
            email,
        )
    return result.startswith("UPDATE") and not result.endswith(" 0")


@with_retry()
async def emails_para_envio(pool: asyncpg.Pool) -> list[dict]:
    """Usuarios con email válido que NO se han dado de baja. Para envíos
    de encuestas/novedades vía Resend."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT email, username FROM usuarios
               WHERE email LIKE '%@%' AND NOT email_opt_out
               ORDER BY fecha_registro ASC"""
        )
    return [dict(r) for r in rows]


@with_retry()
async def stats_encuesta(pool: asyncpg.Pool, encuesta: str) -> dict:
    """Resultados de una encuesta: conteo por opción + comentarios."""
    async with pool.acquire() as conn:
        counts = await conn.fetch(
            """SELECT opcion, COUNT(*) AS n FROM encuesta_respuestas
               WHERE encuesta = $1 GROUP BY opcion ORDER BY n DESC""",
            encuesta,
        )
        comentarios = await conn.fetch(
            """SELECT email, opcion, comentario, timestamp
               FROM encuesta_respuestas
               WHERE encuesta = $1 AND comentario IS NOT NULL AND comentario != ''
               ORDER BY timestamp DESC""",
            encuesta,
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM encuesta_respuestas WHERE encuesta = $1",
            encuesta,
        )
    return {
        "encuesta": encuesta,
        "total_respuestas": int(total or 0),
        "por_opcion": {r["opcion"]: int(r["n"]) for r in counts},
        "comentarios": [
            {
                "email": r["email"],
                "opcion": r["opcion"],
                "comentario": r["comentario"],
                "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
            }
            for r in comentarios
        ],
    }


@with_retry()
async def claim_envio_campana(pool: asyncpg.Pool, campana: str) -> bool:
    """Candado anti-doble-envío: True solo si ESTE proceso consigue insertar
    la fila de la campaña. Si ya existe (envío hecho o en curso), False."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO email_envios (campana) VALUES ($1)
               ON CONFLICT (campana) DO NOTHING RETURNING campana""",
            campana,
        )
    return row is not None


@with_retry()
async def finalizar_envio_campana(pool: asyncpg.Pool, campana: str, n_enviados: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE email_envios SET enviado_at = now(), n_enviados = $2 WHERE campana = $1",
            campana, n_enviados,
        )


# =========================================================================
# Perfil de comunidad (v0.5.40)
# =========================================================================

_PERFIL_COLS = ("perfil_experiencia", "perfil_estilos", "perfil_publicado",
                "perfil_donde", "perfil_bio", "perfil_completo")


@with_retry()
async def get_perfil(pool: asyncpg.Pool, email: str) -> Optional[dict]:
    """Devuelve el perfil de comunidad del usuario (username + campos de perfil).
    `perfil_estilos` se devuelve ya como lista Python."""
    email = (email or "").strip().lower()
    if not email:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.username, u.perfil_experiencia, u.perfil_estilos, u.perfil_publicado,
                      u.perfil_donde, u.perfil_bio, u.perfil_completo, u.perfil_foto,
                      (SELECT COUNT(*) FROM comunidad_comentarios cc
                         WHERE cc.usuario_id = u.id AND cc.util AND cc.activo) AS utiles_recibidos
               FROM usuarios u WHERE LOWER(u.email) = $1""",
            email,
        )
    if not row:
        return None
    d = dict(row)
    estilos = d.get("perfil_estilos")
    if isinstance(estilos, str):
        try:
            estilos = json.loads(estilos)
        except (ValueError, TypeError):
            estilos = []
    d["perfil_estilos"] = estilos or []
    return d


@with_retry()
async def upsert_perfil(pool: asyncpg.Pool, email: str, datos: dict) -> bool:
    """Guarda el perfil de comunidad. `datos` admite: perfil_experiencia,
    perfil_estilos (lista), perfil_publicado, perfil_donde, perfil_bio.
    Marca perfil_completo = TRUE. Devuelve True si el usuario existía."""
    email = (email or "").strip().lower()
    if not email:
        return False
    estilos = datos.get("perfil_estilos") or []
    if not isinstance(estilos, list):
        estilos = []
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE usuarios SET
                 perfil_experiencia = $2,
                 perfil_estilos = $3::jsonb,
                 perfil_publicado = $4,
                 perfil_donde = $5,
                 perfil_bio = $6,
                 perfil_completo = TRUE
               WHERE LOWER(email) = $1""",
            email,
            (datos.get("perfil_experiencia") or None),
            json.dumps(estilos, ensure_ascii=False),
            (datos.get("perfil_publicado") or None),
            (datos.get("perfil_donde") or None),
            (datos.get("perfil_bio") or None),
        )
    return result.endswith(" 1")


@with_retry()
async def perfil_prefill_labels(pool: asyncpg.Pool, usuario_id) -> dict:
    """Sugerencias para pre-rellenar el perfil desde los análisis del usuario:
    el último valor de experiencia y los géneros distintos usados (labels en ES,
    el endpoint los mapea a values). Para que no rellene el perfil desde cero
    quien ya ha analizado tracks."""
    async with pool.acquire() as conn:
        exp = await conn.fetchval(
            """SELECT formulario->>'experiencia'
               FROM analisis
               WHERE usuario_id = $1 AND formulario->>'experiencia' IS NOT NULL
               ORDER BY timestamp DESC LIMIT 1""",
            usuario_id,
        )
        generos = await conn.fetch(
            """SELECT DISTINCT formulario->>'genero' AS g
               FROM analisis
               WHERE usuario_id = $1 AND formulario->>'genero' IS NOT NULL""",
            usuario_id,
        )
    return {
        "experiencia_label": exp,
        "genero_labels": [r["g"] for r in generos if r["g"]],
    }


# =========================================================================
# Comunidad — tracks compartidos (v0.5.41)
# =========================================================================


@with_retry()
async def crear_comunidad_post(pool: asyncpg.Pool, datos: dict) -> dict:
    """Inserta un post de la comunidad. `datos` debe traer las claves de la
    tabla (usuario_id, titulo, audio_file obligatorios). Devuelve la fila."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO comunidad_posts
                 (usuario_id, titulo, mensaje, estilo, estilo_custom, bpm, objetivo,
                  lufs, balance, mono_correlacion, mono_nivel, estado_track,
                  duracion_seg, waveform, audio_file, audio_mime, audio_bytes,
                  descargo_aceptado, analisis_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15,$16,$17,$18,$19)
               RETURNING id, timestamp""",
            datos["usuario_id"], datos["titulo"], datos.get("mensaje"),
            datos.get("estilo"), datos.get("estilo_custom"),
            datos.get("bpm"), datos.get("objetivo"),
            datos.get("lufs"), datos.get("balance"),
            datos.get("mono_correlacion"), datos.get("mono_nivel"),
            datos.get("estado_track"), datos.get("duracion_seg"),
            json.dumps(datos.get("waveform") or [], ensure_ascii=False),
            datos["audio_file"], datos.get("audio_mime"), datos.get("audio_bytes"),
            bool(datos.get("descargo_aceptado")), datos.get("analisis_id"),
        )
    return dict(row)


@with_retry()
async def list_comunidad_posts(
    pool: asyncpg.Pool, estilo: str | None = None, limit: int = 50
) -> list[dict]:
    """Posts activos, más recientes primero, con el distintivo del autor
    (username + perfil). NUNCA expone el email del autor."""
    where = "p.activo"
    args: list = []
    if estilo:
        where += " AND p.estilo = $1"
        args.append(estilo)
    args.append(min(limit, 100))
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT p.id, p.usuario_id, p.timestamp, p.titulo, p.mensaje, p.estilo, p.estilo_custom,
                       p.bpm, p.objetivo, p.lufs, p.balance, p.mono_correlacion,
                       p.mono_nivel, p.estado_track, p.duracion_seg, p.waveform, p.audio_mime,
                       u.username, u.perfil_foto,
                       u.perfil_experiencia, u.perfil_estilos,
                       u.perfil_publicado, u.perfil_donde, u.perfil_bio,
                       (SELECT COUNT(*) FROM comunidad_comentarios c
                          WHERE c.post_id = p.id AND c.activo) AS n_comentarios,
                       (SELECT COUNT(*) FROM comunidad_comentarios cu
                          WHERE cu.usuario_id = p.usuario_id AND cu.util AND cu.activo) AS autor_utiles
                FROM comunidad_posts p
                JOIN usuarios u ON u.id = p.usuario_id
                WHERE {where}
                ORDER BY p.timestamp DESC
                LIMIT ${len(args)}""",
            *args,
        )
    out = []
    for r in rows:
        d = dict(r)
        for k in ("waveform", "perfil_estilos"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = json.loads(d[k])
                except (ValueError, TypeError):
                    d[k] = []
        out.append(d)
    return out


@with_retry()
async def get_comunidad_post(pool: asyncpg.Pool, post_id) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM comunidad_posts WHERE id = $1 AND activo", post_id
        )
    return dict(row) if row else None


@with_retry()
async def editar_comunidad_post(pool: asyncpg.Pool, post_id, usuario_id, titulo: str, mensaje) -> bool:
    """Edita título y mensaje de un post (solo el dueño). El audio NO se toca."""
    async with pool.acquire() as conn:
        res = await conn.execute(
            """UPDATE comunidad_posts SET titulo = $3, mensaje = $4
               WHERE id = $1 AND usuario_id = $2 AND activo""",
            post_id, usuario_id, titulo, mensaje,
        )
    return res.endswith(" 1")


@with_retry()
async def editar_comunidad_post_mod(pool: asyncpg.Pool, post_id, titulo: str, mensaje) -> bool:
    """Moderación: edita título y mensaje de cualquier post (sin check de dueño).
    Solo lo invoca el backend tras verificar que el solicitante es moderador."""
    async with pool.acquire() as conn:
        res = await conn.execute(
            """UPDATE comunidad_posts SET titulo = $2, mensaje = $3
               WHERE id = $1 AND activo""",
            post_id, titulo, mensaje,
        )
    return res.endswith(" 1")


@with_retry()
async def desactivar_comunidad_post(pool: asyncpg.Pool, post_id, usuario_id) -> Optional[str]:
    """Soft-delete del post (solo el dueño). Devuelve el audio_file para
    borrar el archivo del disco, o None si no existía/no es suyo."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE comunidad_posts SET activo = FALSE
               WHERE id = $1 AND usuario_id = $2 AND activo
               RETURNING audio_file""",
            post_id, usuario_id,
        )
    return row["audio_file"] if row else None


@with_retry()
async def desactivar_comunidad_post_mod(pool: asyncpg.Pool, post_id) -> Optional[str]:
    """Moderación: retira un post sea de quien sea (sin comprobar propiedad).
    Solo lo invoca el backend tras verificar que el solicitante es moderador.
    Devuelve el audio_file para borrar el archivo, o None si no existía."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE comunidad_posts SET activo = FALSE
               WHERE id = $1 AND activo
               RETURNING audio_file""",
            post_id,
        )
    return row["audio_file"] if row else None


@with_retry()
async def contar_posts_activos(pool: asyncpg.Pool, usuario_id) -> int:
    """Posts activos de un usuario (cuota: máx 3 para cuidar el volumen)."""
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM comunidad_posts WHERE usuario_id = $1 AND activo",
            usuario_id,
        )
    return int(n or 0)


# =========================================================================
# Comunidad — comentarios + reciprocidad (v0.5.44)
# =========================================================================


@with_retry()
async def crear_comentario(pool: asyncpg.Pool, post_id, usuario_id, texto: str) -> Optional[dict]:
    """Inserta un comentario si el post existe y está activo. Devuelve la fila
    (id, timestamp) o None si el post no existe/está inactivo."""
    async with pool.acquire() as conn:
        existe = await conn.fetchval(
            "SELECT 1 FROM comunidad_posts WHERE id = $1 AND activo", post_id
        )
        if not existe:
            return None
        row = await conn.fetchrow(
            """INSERT INTO comunidad_comentarios (post_id, usuario_id, texto)
               VALUES ($1, $2, $3) RETURNING id, timestamp""",
            post_id, usuario_id, texto,
        )
    return dict(row)


@with_retry()
async def list_comentarios(pool: asyncpg.Pool, post_id) -> list[dict]:
    """Comentarios activos de un post, con el distintivo del autor. Los marcados
    como útiles flotan arriba; dentro de cada grupo, orden cronológico."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.id, c.timestamp, c.texto, c.util, c.usuario_id,
                      u.username, u.perfil_foto, u.perfil_experiencia, u.perfil_estilos,
                      u.perfil_publicado,
                      (SELECT COUNT(*) FROM comunidad_comentarios cc
                         WHERE cc.usuario_id = c.usuario_id AND cc.util AND cc.activo) AS autor_utiles
               FROM comunidad_comentarios c
               JOIN usuarios u ON u.id = c.usuario_id
               WHERE c.post_id = $1 AND c.activo
               ORDER BY c.util DESC, c.timestamp ASC""",
            post_id,
        )
    out = []
    for r in rows:
        d = dict(r)
        est = d.get("perfil_estilos")
        if isinstance(est, str):
            try:
                est = json.loads(est)
            except (ValueError, TypeError):
                est = []
        d["perfil_estilos"] = est or []
        out.append(d)
    return out


@with_retry()
async def borrar_comentario(pool: asyncpg.Pool, comentario_id, usuario_id) -> bool:
    """Soft-delete del comentario (solo el autor)."""
    async with pool.acquire() as conn:
        res = await conn.execute(
            """UPDATE comunidad_comentarios SET activo = FALSE
               WHERE id = $1 AND usuario_id = $2 AND activo""",
            comentario_id, usuario_id,
        )
    return res.endswith(" 1")


@with_retry()
async def borrar_comentario_mod(pool: asyncpg.Pool, comentario_id) -> bool:
    """Moderación: borra un comentario sea de quien sea (sin comprobar autoría).
    Solo lo invoca el backend tras verificar que el solicitante es moderador."""
    async with pool.acquire() as conn:
        res = await conn.execute(
            """UPDATE comunidad_comentarios SET activo = FALSE
               WHERE id = $1 AND activo""",
            comentario_id,
        )
    return res.endswith(" 1")


@with_retry()
async def marcar_comentario_util(pool: asyncpg.Pool, comentario_id, owner_id) -> Optional[bool]:
    """El DUEÑO del post marca/desmarca un comentario como útil (toggle).
    Verifica que `owner_id` es dueño del post del comentario. Devuelve el nuevo
    estado `util`, o None si no autorizado / no existe."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT c.util, p.usuario_id AS owner
               FROM comunidad_comentarios c
               JOIN comunidad_posts p ON p.id = c.post_id
               WHERE c.id = $1 AND c.activo""",
            comentario_id,
        )
        if not row or row["owner"] != owner_id:
            return None
        nuevo = not row["util"]
        await conn.execute(
            "UPDATE comunidad_comentarios SET util = $2 WHERE id = $1",
            comentario_id, nuevo,
        )
    return nuevo


@with_retry()
async def reciprocidad_stats(pool: asyncpg.Pool, usuario_id) -> dict:
    """Para el gate de compartir: nº de posts activos del usuario y nº de tracks
    DISTINTOS de OTROS en los que ha comentado (su 'dar' a la comunidad)."""
    async with pool.acquire() as conn:
        activos = await conn.fetchval(
            "SELECT COUNT(*) FROM comunidad_posts WHERE usuario_id = $1 AND activo",
            usuario_id,
        )
        comentados = await conn.fetchval(
            """SELECT COUNT(DISTINCT c.post_id)
               FROM comunidad_comentarios c
               JOIN comunidad_posts p ON p.id = c.post_id
               WHERE c.usuario_id = $1 AND c.activo AND p.usuario_id <> $1""",
            usuario_id,
        )
    return {"activos": int(activos or 0), "comentados": int(comentados or 0)}


@with_retry()
async def is_comunidad_beta(pool: asyncpg.Pool, email: str) -> bool:
    """¿Está este usuario habilitado a la comunidad por flag de DB (beta)?"""
    email = (email or "").strip().lower()
    if not email:
        return False
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT comunidad_beta FROM usuarios WHERE LOWER(email) = $1", email
        )
    return bool(v)


@with_retry()
async def is_pro(pool: asyncpg.Pool, email: str) -> bool:
    """¿Es el usuario Pro? (tier de pago: FLAC sin pérdida vs MP3)."""
    email = (email or "").strip().lower()
    if not email:
        return False
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT pro FROM usuarios WHERE LOWER(email) = $1", email
        )
    return bool(v)
