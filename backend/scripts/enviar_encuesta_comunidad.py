"""Envío de la encuesta de comunidad por email a los usuarios de Mentotrack.

Cada email lleva links personalizados (token JWT firmado con el JWT_SECRET de
prod) a https://www.mentotrack.com/encuesta — un clic registra el voto.

Uso (con las env vars de prod):
  DATABASE_URL=... JWT_SECRET=... RESEND_API_KEY=... python3 enviar_encuesta_comunidad.py            # dry-run
  ... python3 enviar_encuesta_comunidad.py --test alex@producciononline.com   # envía solo a esa dirección
  ... python3 enviar_encuesta_comunidad.py --send                             # envío real a todos (pide confirmación)

El destinatario sale de la tabla usuarios (email válido y sin email_opt_out).
JWT_SECRET DEBE ser el de producción — los links se validan en el servidor.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

import asyncpg
import httpx
import jwt

ENCUESTA = "comunidad-2026-06"

# El template y el copy viven en backend/encuesta_email.py (compartido con el
# envío programado del servidor). Este script solo orquesta el envío manual.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import encuesta_email  # noqa: E402


def token_para(email: str) -> str:
    secret = os.environ["JWT_SECRET"]
    payload = {
        "em": email.strip().lower(),
        "sc": "encuesta",
        "exp": datetime.utcnow() + timedelta(days=90),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def destinatarios() -> list[dict]:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        rows = await conn.fetch(
            """SELECT email, username FROM usuarios
               WHERE email LIKE '%@%' AND NOT email_opt_out
               ORDER BY fecha_registro ASC"""
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def enviar_batch(client: httpx.Client, lote: list[dict]) -> None:
    """Envía hasta 100 emails en una llamada al endpoint batch de Resend."""
    resp = client.post(
        "https://api.resend.com/emails/batch",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json=lote,
        timeout=30,
    )
    resp.raise_for_status()


def construir_payload(dest: dict) -> dict:
    return encuesta_email.payload_para(dest["email"], token_para(dest["email"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", metavar="EMAIL", help="envía solo a esta dirección")
    parser.add_argument("--send", action="store_true", help="envío real a todos los usuarios")
    args = parser.parse_args()

    for var in ("DATABASE_URL", "JWT_SECRET"):
        if not os.environ.get(var):
            sys.exit(f"Falta {var} en el entorno")

    if args.test:
        if not os.environ.get("RESEND_API_KEY"):
            sys.exit("Falta RESEND_API_KEY")
        payload = construir_payload({"email": args.test, "username": "Alex (prueba)"})
        with httpx.Client() as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            print(f"Email de prueba enviado a {args.test} — id: {resp.json().get('id')}")
        return

    dests = asyncio.run(destinatarios())
    print(f"Destinatarios (email válido, sin opt-out): {len(dests)}")

    if not args.send:
        # Dry-run: muestra resumen y guarda una preview del HTML
        preview = encuesta_email.email_html(token_para("preview@example.com"))
        path = "/tmp/encuesta_preview.html"
        with open(path, "w") as f:
            f.write(preview)
        print(f"DRY-RUN — no se ha enviado nada. Preview del email: {path}")
        print("Para enviar de verdad: --send (o --test EMAIL para una prueba)")
        return

    if not os.environ.get("RESEND_API_KEY"):
        sys.exit("Falta RESEND_API_KEY")
    confirm = input(f"¿Enviar a {len(dests)} usuarios? Escribe 'ENVIAR' para confirmar: ")
    if confirm.strip() != "ENVIAR":
        sys.exit("Cancelado.")

    enviados = 0
    with httpx.Client() as client:
        for i in range(0, len(dests), 100):
            lote = [construir_payload(d) for d in dests[i:i + 100]]
            enviar_batch(client, lote)
            enviados += len(lote)
            print(f"  {enviados}/{len(dests)} enviados")
            time.sleep(1.0)  # respeta el rate limit de Resend (2 req/s)
    print(f"Hecho — {enviados} emails enviados.")


if __name__ == "__main__":
    main()
