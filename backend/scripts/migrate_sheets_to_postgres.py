"""
Migración one-time: Google Sheets → Postgres.

Fuentes soportadas:
  --csv PATH          Lee análisis de un export CSV local. Para testar.
                      No incluye usuarios reales ni ideas (faltan en el CSV).
  --webhook URL       Llama al Apps Script desplegado.
                      Lee análisis (action=list), usuarios e ideas (action=get_ideas).
                      Fuente preferida para la migración de verdad.

Comportamiento:
  - Idempotente vía TRUNCATE: vacía las 4 tablas al inicio.
  - Crea usuarios → proyectos → análisis → ideas en ese orden (respeta FKs).
  - Agrupa análisis por (email, LOWER(TRIM(nombre_proyecto))) para inferir proyectos.
  - Asigna version_num cronológico dentro de cada proyecto.
  - Análisis sin nombre_proyecto quedan con proyecto_id=NULL ("sueltos").
  - Para usuarios sin password_hash conocido (modo CSV), genera un hash placeholder
    que NO permite login — el usuario tendrá que pasar por /forgot.

Uso:
  DATABASE_URL=postgresql://... python migrate_sheets_to_postgres.py --csv ../../TrackDiag....csv
  DATABASE_URL=postgresql://... python migrate_sheets_to_postgres.py --webhook https://script.google.com/.../exec
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg


# -----------------------------------------------------------------------------
# Lectura desde CSV
# -----------------------------------------------------------------------------

def read_from_csv(path: str) -> dict:
    """Lee un export del Sheet en formato CSV. Devuelve {analisis: [...]}.
    No tiene usuarios ni ideas (esa info no está en el CSV principal).
    """
    import pandas as pd
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    analisis = df.to_dict(orient="records")
    return {"analisis": analisis, "usuarios": [], "ideas": []}


# -----------------------------------------------------------------------------
# Lectura desde Apps Script
# -----------------------------------------------------------------------------

def read_from_webhook(url: str) -> dict:
    """Llama al Apps Script con action=list (análisis), action=get_all sobre
    pestaña usuarios (vía workaround) y action=get_ideas."""
    import httpx
    # 1) análisis (pestaña principal)
    r = httpx.get(url, params={"action": "list"}, timeout=60.0)
    r.raise_for_status()
    analisis = r.json()
    if not isinstance(analisis, list):
        raise RuntimeError(f"action=list devolvió formato inesperado: {type(analisis)}")
    # 2) ideas
    r = httpx.post(url, json={"action": "get_ideas"}, timeout=60.0)
    r.raise_for_status()
    ideas_resp = r.json()
    ideas = ideas_resp.get("ideas", []) if isinstance(ideas_resp, dict) else []
    # 3) usuarios — el Apps Script actual no expone listado masivo de usuarios
    #    por seguridad (tiene get_user/get_user_by_identifier por email/username).
    #    Devolvemos vacío y los usuarios se "inferirán" de los emails que aparecen
    #    en los análisis (sin password_hash real).
    print("AVISO: el Apps Script no expone listado de usuarios.")
    print("       Se crearán usuarios a partir de emails únicos de los análisis,")
    print("       con password_hash placeholder. Tendrán que pasar por /forgot.")
    return {"analisis": analisis, "usuarios": [], "ideas": ideas}


# -----------------------------------------------------------------------------
# Parsing helpers
# -----------------------------------------------------------------------------

def parse_timestamp(ts: str) -> datetime:
    """Acepta ISO con Z, ISO sin TZ, '30 Apr 2026', etc. Devuelve UTC aware."""
    if not ts:
        return datetime.now(timezone.utc)
    ts = str(ts).strip()
    # ISO con Z
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    # "30 Apr 2026"
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"No puedo parsear timestamp: {ts!r}")


def parse_formulario(s: str) -> dict:
    """'Tech House | Casi listo | Demo | 2-5 años | Estructura | Bloqueo: ...'
    → dict con campos nombrados."""
    if not s:
        return {}
    parts = [p.strip() for p in str(s).split("|")]
    keys = ["genero", "fase", "objetivo", "experiencia", "dificultad_habitual", "bloqueo"]
    fields = {}
    for i, p in enumerate(parts):
        if i < len(keys):
            # "Bloqueo: texto" → quitar prefijo
            if keys[i] == "bloqueo" and p.lower().startswith("bloqueo:"):
                p = p[8:].strip()
            fields[keys[i]] = p
    return fields


def parse_senales_json(s: str) -> dict:
    if not s:
        return {}
    if isinstance(s, dict):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def normalize_email(e: str) -> str:
    return str(e or "").strip().lower()


def normalize_proyecto_name(s: str) -> str:
    return str(s or "").strip().lower()


# -----------------------------------------------------------------------------
# Lógica de migración
# -----------------------------------------------------------------------------

PASSWORD_PLACEHOLDER = "__MIGRATED__"  # No es un hash válido de bcrypt → no permite login


async def migrar(conn: asyncpg.Connection, data: dict, dry_run: bool = False):
    analisis_raw = data.get("analisis", [])
    ideas_raw = data.get("ideas", [])

    print(f"\n→ Filas crudas leídas: {len(analisis_raw)} análisis, {len(ideas_raw)} ideas")

    # 1) Vaciar tablas (idempotente)
    if not dry_run:
        print("→ TRUNCATE tablas existentes...")
        await conn.execute("TRUNCATE TABLE analisis, ideas, proyectos, usuarios CASCADE")

    # 2) Extraer emails únicos para crear usuarios
    emails_unicos = set()
    for row in analisis_raw:
        e = normalize_email(row.get("email"))
        if e and "@" in e:
            emails_unicos.add(e)
    print(f"→ Emails únicos a crear como usuarios: {len(emails_unicos)}")

    # 3) Insertar usuarios (con password_hash placeholder)
    email_to_id = {}
    if not dry_run:
        for e in emails_unicos:
            uid = await conn.fetchval(
                "INSERT INTO usuarios (email, password_hash) VALUES ($1, $2) RETURNING id",
                e, PASSWORD_PLACEHOLDER,
            )
            email_to_id[e] = uid
    else:
        # En dry-run simulamos los ids
        import uuid
        for e in emails_unicos:
            email_to_id[e] = uuid.uuid4()

    # 4) Agrupar por (email, nombre_proyecto normalizado) para crear proyectos
    #    Solo los análisis con nombre_proyecto no vacío forman proyectos.
    proyectos_map = {}  # (email, nombre_normalizado) -> proyecto_id
    proyecto_nombres_originales = {}  # para usar el primer nombre original encontrado
    for row in analisis_raw:
        e = normalize_email(row.get("email"))
        nombre_proyecto = str(row.get("nombre_proyecto") or "").strip()
        if not e or not nombre_proyecto or e not in email_to_id:
            continue
        key = (e, normalize_proyecto_name(nombre_proyecto))
        if key not in proyectos_map:
            # Reservamos slot, asignamos id real abajo
            proyectos_map[key] = None
            proyecto_nombres_originales[key] = nombre_proyecto

    print(f"→ Proyectos únicos detectados: {len(proyectos_map)}")

    if not dry_run:
        for key in proyectos_map:
            email, _norm = key
            nombre = proyecto_nombres_originales[key]
            pid = await conn.fetchval(
                """INSERT INTO proyectos (usuario_id, nombre)
                   VALUES ($1, $2) RETURNING id""",
                email_to_id[email], nombre,
            )
            proyectos_map[key] = pid
    else:
        import uuid
        for key in proyectos_map:
            proyectos_map[key] = uuid.uuid4()

    # 5) Insertar análisis. Calcular version_num cronológico por proyecto.
    #    Pre-ordenamos por (proyecto_key, timestamp) para asignar versiones secuenciales.
    enriched = []
    for row in analisis_raw:
        e = normalize_email(row.get("email"))
        if not e or "@" not in e:
            continue
        nombre_proyecto = str(row.get("nombre_proyecto") or "").strip()
        proyecto_key = (e, normalize_proyecto_name(nombre_proyecto)) if nombre_proyecto else None
        proyecto_id = proyectos_map.get(proyecto_key) if proyecto_key else None
        try:
            ts = parse_timestamp(row.get("timestamp", ""))
        except ValueError as ex:
            print(f"   AVISO: timestamp inválido, salto fila: {ex}")
            continue
        enriched.append({
            "email": e,
            "usuario_id": email_to_id.get(e),
            "proyecto_id": proyecto_id,
            "proyecto_key": proyecto_key,
            "timestamp": ts,
            "row": row,
        })

    # Ordenar por (proyecto_key, timestamp)
    enriched.sort(key=lambda x: (str(x["proyecto_key"] or ""), x["timestamp"]))

    # Asignar version_num
    contador_por_proyecto = {}
    for a in enriched:
        pk = a["proyecto_key"]
        if pk is None:
            a["version_num"] = None
        else:
            contador_por_proyecto[pk] = contador_por_proyecto.get(pk, 0) + 1
            a["version_num"] = contador_por_proyecto[pk]

    # Insertar análisis
    print(f"→ Insertando {len(enriched)} análisis...")
    skipped_invalid_json = 0
    if not dry_run:
        for a in enriched:
            row = a["row"]
            nota_alex_raw = str(row.get("nota_alex", "") or "").strip()
            try:
                nota_alex = float(nota_alex_raw) if nota_alex_raw else None
            except ValueError:
                nota_alex = None
            tutoriales = row.get("tutoriales_sugeridos", "")
            try:
                tutoriales_json = json.loads(tutoriales) if tutoriales else None
            except (json.JSONDecodeError, TypeError):
                tutoriales_json = tutoriales if tutoriales else None

            try:
                await conn.execute(
                    """INSERT INTO analisis (
                        usuario_id, proyecto_id, version_num, version_etiqueta,
                        timestamp, email, nombre_proyecto_legacy,
                        formulario, diagnostico, senales,
                        fue_util, comentario, feedback_real,
                        revision_alex, nota_alex,
                        tutoriales_sugeridos, tutorial_clickado,
                        genero_custom
                    ) VALUES (
                        $1, $2, $3, NULL,
                        $4, $5, $6,
                        $7, $8, $9,
                        $10, $11, $12,
                        $13, $14,
                        $15, $16,
                        $17
                    )""",
                    a["usuario_id"], a["proyecto_id"], a["version_num"],
                    a["timestamp"], a["email"],
                    (str(row.get("nombre_proyecto") or "").strip() or None),
                    json.dumps(parse_formulario(row.get("formulario", ""))),
                    str(row.get("diagnostico") or ""),
                    json.dumps(parse_senales_json(row.get("senales_json", ""))),
                    (str(row.get("fue_util") or "").strip() or None),
                    (str(row.get("comentario") or "").strip() or None),
                    (str(row.get("feedback_real") or "").strip() or None),
                    (str(row.get("revision_alex") or "").strip() or None),
                    nota_alex,
                    json.dumps(tutoriales_json) if tutoriales_json is not None else None,
                    (str(row.get("tutorial_clickado") or "").strip() or None),
                    (str(row.get("genero_custom") or "").strip() or None),
                )
            except Exception as ex:
                skipped_invalid_json += 1
                print(f"   AVISO: fallo en INSERT analisis ({a['email']} @ {a['timestamp']}): {ex}")

    if skipped_invalid_json:
        print(f"   Saltadas {skipped_invalid_json} filas por errores de INSERT.")

    # 6) Insertar ideas
    if ideas_raw and not dry_run:
        print(f"→ Insertando {len(ideas_raw)} ideas...")
        for idea in ideas_raw:
            try:
                ts = parse_timestamp(idea.get("fecha", ""))
            except ValueError:
                ts = datetime.now(timezone.utc)
            await conn.execute(
                """INSERT INTO ideas (nombre, titulo, descripcion, fecha, votos)
                   VALUES ($1, $2, $3, $4, $5)""",
                (str(idea.get("nombre") or "").strip() or None),
                str(idea.get("titulo") or "").strip(),
                (str(idea.get("descripcion") or "").strip() or None),
                ts,
                int(idea.get("votos") or 0),
            )

    # 7) Verificación final
    print("\n→ Verificación:")
    n_usuarios = await conn.fetchval("SELECT COUNT(*) FROM usuarios")
    n_proyectos = await conn.fetchval("SELECT COUNT(*) FROM proyectos")
    n_analisis = await conn.fetchval("SELECT COUNT(*) FROM analisis")
    n_ideas = await conn.fetchval("SELECT COUNT(*) FROM ideas")
    n_sueltos = await conn.fetchval("SELECT COUNT(*) FROM analisis WHERE proyecto_id IS NULL")
    n_sin_user = await conn.fetchval("SELECT COUNT(*) FROM analisis WHERE usuario_id IS NULL")
    max_versions = await conn.fetchval(
        "SELECT MAX(version_num) FROM analisis WHERE version_num IS NOT NULL"
    )
    print(f"   usuarios:           {n_usuarios}")
    print(f"   proyectos:          {n_proyectos}")
    print(f"   análisis:           {n_analisis}")
    print(f"     - sueltos (sin proyecto):  {n_sueltos}")
    print(f"     - sin usuario:             {n_sin_user}")
    print(f"     - max version_num:         {max_versions}")
    print(f"   ideas:              {n_ideas}")


async def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="Path a CSV exportado del Sheet")
    g.add_argument("--webhook", help="URL del Apps Script desplegado")
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL no definida en el entorno.")
        sys.exit(1)
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    print(f"DSN: {dsn[:50]}...")
    print(f"Modo: {'CSV' if args.csv else 'WEBHOOK'}{'  [DRY-RUN]' if args.dry_run else ''}")

    if args.csv:
        data = read_from_csv(args.csv)
    else:
        data = read_from_webhook(args.webhook)

    conn = await asyncpg.connect(dsn=dsn)
    try:
        async with conn.transaction():
            await migrar(conn, data, dry_run=args.dry_run)
        print("\nOK — migración completada.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
