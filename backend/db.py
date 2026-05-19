"""
Conexión a Postgres.
Pool global de asyncpg, inicializado al arrancar la app y cerrado al apagarla.
"""
import json
import os
import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


def _get_dsn() -> str:
    """Lee DATABASE_URL del entorno y normaliza el prefijo si hace falta."""
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("DATABASE_URL no está definida en el entorno")
    # asyncpg acepta 'postgres://' y 'postgresql://' indistintamente, pero
    # algunas libs/SQLAlchemy prefieren 'postgresql://'. Normalizamos.
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    return dsn


async def _init_conn(conn: asyncpg.Connection):
    """Configura cada conexión NUEVA del pool: codecs JSONB."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def _setup_conn(conn: asyncpg.Connection):
    """Se ejecuta en CADA acquire(): valida que la conexión está viva.
    Si el ping falla, asyncpg descarta la conexión y crea una nueva.
    Necesario porque el proxy TCP de Railway corta conexiones idle sin
    avisar al cliente — sin este check, la primera query falla con
    'connection was closed in the middle of operation'."""
    await conn.fetchval("SELECT 1")


async def init_pool() -> asyncpg.Pool:
    """Crea el pool global. Llamar al arrancar la app.

    Configuración para Railway: el proxy TCP de la URL pública corta
    conexiones idle agresivamente. Mitigamos con:
    - max_inactive_connection_lifetime=60s: pool recicla conexiones
      antes que Railway las mate.
    - setup ping en cada acquire: valida que la conexión está viva antes
      de devolverla; si está muerta, el pool la descarta y crea otra.
    - min_size=0: no mantiene conexiones idle entre peticiones.
    """
    global _pool
    if _pool is not None:
        return _pool
    # ssl='prefer': intenta SSL primero (necesario en Railway proxy público).
    # Si el servidor no lo soporta, cae a TCP plano. En la URL interna de
    # Railway el TCP plano funciona y prefer lo respeta.
    _pool = await asyncpg.create_pool(
        dsn=_get_dsn(),
        min_size=0,
        max_size=10,
        command_timeout=15,
        max_inactive_connection_lifetime=30.0,
        init=_init_conn,
        setup=_setup_conn,
        ssl="prefer",
    )
    return _pool


async def close_pool() -> None:
    """Cierra el pool. Llamar al apagar la app."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Devuelve el pool ya inicializado. Lanza si no está listo."""
    if _pool is None:
        raise RuntimeError("Pool de Postgres no inicializado. Llama a init_pool() primero.")
    return _pool
