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
    """Configura cada conexión nueva del pool: codec para JSONB → dict."""
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


async def init_pool() -> asyncpg.Pool:
    """Crea el pool global. Llamar al arrancar la app."""
    global _pool
    if _pool is not None:
        return _pool
    _pool = await asyncpg.create_pool(
        dsn=_get_dsn(),
        min_size=1,
        max_size=10,
        command_timeout=15,
        init=_init_conn,
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
