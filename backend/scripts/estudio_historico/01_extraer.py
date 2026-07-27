#!/usr/bin/env python3
"""Paso 1 del estudio histórico: extrae las tablas `analisis` y `usuarios` de
Postgres (Railway) a un SQLite local (`estudio.db`, gitignored) para poder
iterar las queries sin machacar el proxy TCP.

Requisitos: Railway CLI logueado y linkado al proyecto (railway link),
psycopg2 instalado. La URL pública de la DB se obtiene del CLI y no se
imprime nunca.

Uso:  python3 01_extraer.py
"""
import json
import os
import sqlite3
import subprocess

import psycopg2

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(AQUI, "..", "..", ".."))
# El volcado contiene emails: por defecto queda junto al script (gitignored);
# se puede sacar del repo del todo con ESTUDIO_DB=/ruta/estudio.db.
DB_PATH = os.environ.get("ESTUDIO_DB", os.path.join(AQUI, "estudio.db"))


def get_url():
    out = subprocess.run(
        ["railway", "variables", "--service", "Postgres", "--json"],
        capture_output=True, text=True, cwd=REPO)
    return json.loads(out.stdout)["DATABASE_PUBLIC_URL"]


def main():
    conn = psycopg2.connect(get_url())
    cur = conn.cursor()

    db = sqlite3.connect(DB_PATH)
    db.execute("DROP TABLE IF EXISTS analisis")
    db.execute("""CREATE TABLE analisis (
        id TEXT PRIMARY KEY, usuario_id TEXT, proyecto_id TEXT, version_num INTEGER,
        ts TEXT, email TEXT, formulario TEXT, senales TEXT, diagnostico TEXT,
        fue_util TEXT, comentario TEXT, feedback_real TEXT, motor_version TEXT, pais TEXT)""")
    cur.execute("""SELECT id, usuario_id, proyecto_id, version_num, timestamp, email,
        formulario, senales, diagnostico, fue_util, comentario, feedback_real,
        motor_version, pais FROM analisis""")
    n = 0
    for row in cur:
        db.execute("INSERT INTO analisis VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            str(row[0]), str(row[1]) if row[1] else None, str(row[2]) if row[2] else None,
            row[3], row[4].isoformat() if row[4] else None, row[5],
            json.dumps(row[6], ensure_ascii=False) if row[6] else None,
            json.dumps(row[7], ensure_ascii=False) if row[7] else None,
            row[8], row[9], row[10], row[11], row[12], row[13]))
        n += 1

    db.execute("DROP TABLE IF EXISTS usuarios")
    db.execute("""CREATE TABLE usuarios (
        id TEXT PRIMARY KEY, email TEXT, username TEXT, fecha_registro TEXT,
        perfil_experiencia TEXT, pro INTEGER)""")
    cur.execute("SELECT id, email, username, fecha_registro, perfil_experiencia, pro FROM usuarios")
    m = 0
    for row in cur:
        db.execute("INSERT INTO usuarios VALUES (?,?,?,?,?,?)", (
            str(row[0]), row[1], row[2], row[3].isoformat() if row[3] else None,
            row[4], 1 if row[5] else 0))
        m += 1
    db.commit()
    conn.close()
    print(f"Extraídos {n} análisis y {m} usuarios -> {DB_PATH}")


if __name__ == "__main__":
    main()
