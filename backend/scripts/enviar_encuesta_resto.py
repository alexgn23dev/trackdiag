"""Envío de CONTINUACIÓN de la encuesta de comunidad.

El envío programado del 2026-06-12 alcanzó el límite diario de Resend tras
200 emails. Este script manda la encuesta a los usuarios RESTANTES sin
reenviarla a los 200 que ya la recibieron.

Reconstrucción de los 200 ya enviados (determinista, igual que hizo el
servidor): usuarios elegibles (email bien formado, sin opt-out) ordenados por
fecha_registro ASC; los primeros 200 ya la tienen. Este script salta esos 200
y envía al resto.

Uso (con env vars de prod — REQUIERE plan de Resend con cuota suficiente):
  DATABASE_URL=... JWT_SECRET=... RESEND_API_KEY=... python3 enviar_encuesta_resto.py            # dry-run (no envía)
  ... python3 enviar_encuesta_resto.py --test alexgn23@gmail.com   # 1 email de prueba (verifica que la cuota está activa)
  ... python3 enviar_encuesta_resto.py --send                      # envío real a los restantes
"""

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta

import asyncpg
import jwt
import resend

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import encuesta_email  # noqa: E402

CAMPANA = "comunidad-2026-06-resto"
YA_ENVIADOS = 200  # los 200 primeros (por fecha_registro) ya la recibieron el 12-jun
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def token_para(email: str) -> str:
    payload = {
        "em": email.strip().lower(),
        "sc": "encuesta",
        "exp": datetime.utcnow() + timedelta(days=90),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


async def _pool():
    return await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)


async def pendientes() -> tuple[list, list]:
    """Devuelve (pendientes_bien_formados, malformados). Los pendientes son los
    usuarios bien formados desde la posición YA_ENVIADOS en adelante."""
    pool = await _pool()
    try:
        rows = await pool.fetch(
            """SELECT email, username FROM usuarios
               WHERE email LIKE '%@%' AND NOT email_opt_out
               ORDER BY fecha_registro ASC"""
        )
    finally:
        await pool.close()
    bien = [dict(r) for r in rows if EMAIL_RE.match((r["email"] or "").strip())]
    mal = [dict(r) for r in rows if not EMAIL_RE.match((r["email"] or "").strip())]
    return bien[YA_ENVIADOS:], mal


async def claim() -> bool:
    """Candado: True solo si esta ejecución consigue insertar la campaña."""
    pool = await _pool()
    try:
        row = await pool.fetchrow(
            """INSERT INTO email_envios (campana) VALUES ($1)
               ON CONFLICT (campana) DO NOTHING RETURNING campana""",
            CAMPANA,
        )
        return row is not None
    finally:
        await pool.close()


async def finalizar(n: int) -> None:
    pool = await _pool()
    try:
        await pool.execute(
            "UPDATE email_envios SET enviado_at = now(), n_enviados = $2 WHERE campana = $1",
            CAMPANA, n,
        )
    finally:
        await pool.close()


def enviar_uno(dest: dict) -> None:
    params = encuesta_email.payload_para(dest["email"], token_para(dest["email"]))
    resend.Emails.send(params)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", metavar="EMAIL", help="envía 1 email de prueba")
    parser.add_argument("--send", action="store_true", help="envío real a los restantes")
    parser.add_argument("--force", action="store_true", help="ignora el candado (re-ejecutar tras fallo parcial)")
    args = parser.parse_args()

    for var in ("DATABASE_URL", "JWT_SECRET", "RESEND_API_KEY"):
        if not os.environ.get(var):
            sys.exit(f"Falta {var} en el entorno")
    resend.api_key = os.environ["RESEND_API_KEY"]

    if args.test:
        enviar_uno({"email": args.test})
        print(f"Prueba enviada a {args.test} — si llega, la cuota está activa.")
        return

    rest, mal = asyncio.run(pendientes())
    print(f"Pendientes bien formados: {len(rest)}")
    print(f"Malformados (se omiten, no entregan): {len(mal)} -> {[m['email'] for m in mal]}")

    if not args.send:
        print("\nDRY-RUN — no se ha enviado nada. Para enviar: --send")
        return

    if not args.force:
        if not asyncio.run(claim()):
            sys.exit(f"La campaña '{CAMPANA}' ya está reclamada (¿ya se envió?). Usa --force para reintentar.")

    enviados, fallos, fallos_detalle = 0, 0, []
    import time
    for d in rest:
        try:
            enviar_uno(d)
            enviados += 1
        except Exception as e:
            fallos += 1
            fallos_detalle.append((d["email"], f"{type(e).__name__}: {e}"))
            print(f"  fallo {d['email']}: {type(e).__name__}: {e}")
        time.sleep(0.6)  # rate limit Resend (~1.6/s)
        if enviados and enviados % 50 == 0:
            print(f"  {enviados}/{len(rest)}…")

    asyncio.run(finalizar(enviados))
    print(f"\nHecho — {enviados} enviados, {fallos} fallos.")
    if fallos_detalle:
        print("Detalle de fallos:")
        for em, err in fallos_detalle:
            print(f"  {em}: {err}")
    # confirmación a Alex
    try:
        resend.Emails.send({
            "from": encuesta_email.FROM,
            "to": ["alexgn23@gmail.com"],
            "subject": f"✅ Encuesta (resto) enviada — {enviados} emails",
            "html": f"<p>Continuación enviada: <strong>{enviados}</strong> de {len(rest)} pendientes · {fallos} fallos.</p>",
        })
    except Exception as e:
        print(f"(no se pudo enviar la confirmación: {e})")


if __name__ == "__main__":
    main()
