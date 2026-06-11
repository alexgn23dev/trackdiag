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
BASE_URL = os.environ.get("BASE_URL", "https://www.mentotrack.com")
FROM = os.environ.get("RESEND_FROM", "Alex de Mentotrack <noreply@mentotrack.com>")
REPLY_TO = "alex@producciononline.com"
SUBJECT = "¿Quieres feedback entre productores?"

OPCIONES = [
    ("todo", "Sí — compartiría mis tracks y comentaría los de otros"),
    ("solo_compartir", "Compartiría mis tracks, pero no me veo comentando"),
    ("solo_comentar", "Comentaría los de otros, pero aún no compartiría los míos"),
    ("no", "No me interesa"),
]


def token_para(email: str) -> str:
    secret = os.environ["JWT_SECRET"]
    payload = {
        "em": email.strip().lower(),
        "sc": "encuesta",
        "exp": datetime.utcnow() + timedelta(days=90),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def email_html(username: str, t: str) -> str:
    # `username` ya no se usa en el saludo (copy de Alex, sin saludo personalizado)
    botones = "".join(
        f"""<tr><td style="padding:6px 0">
              <a href="{BASE_URL}/encuesta?t={t}&amp;o={clave}"
                 style="display:block;padding:13px 16px;border:1px solid #d4d4d8;border-radius:10px;
                        color:#18181b;text-decoration:none;font-size:15px;background:#fafafa">
                {texto}</a>
            </td></tr>"""
        for clave, texto in OPCIONES
    )
    return f"""<!DOCTYPE html>
<html lang="es"><body style="margin:0;background:#f4f4f5;padding:24px 12px;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center">
<table role="presentation" width="560" style="max-width:560px;background:#ffffff;border-radius:14px;padding:32px 28px" cellpadding="0" cellspacing="0">
  <tr><td>
    <p style="margin:0 0 16px;font-size:13px;color:#16a34a;font-weight:600">MENTOTRACK</p>
    <p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#3f3f46">
      Soy Alex, de Mentotrack. Estoy pensando en transformar esta plataforma en algo más
      interactivo, con comunidad, donde podáis ayudaros entre todos.
    </p>
    <p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#3f3f46">
      ¿Cómo lo haríamos? Creando una sección donde compartas públicamente tu idea inacabada
      o tu track casi terminado —con tu nombre, no anónimo— junto a otros productores que
      también usan la plataforma, para daros feedback entre vosotros.
    </p>
    <p style="margin:0 0 6px;font-size:15px;color:#18181b;font-weight:600">
      Responde con un clic:
    </p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{botones}</table>
    <p style="margin:14px 0 0;font-size:13px;color:#71717a">
      Tras el clic podrás añadir un comentario si quieres matizar tu respuesta.
    </p>
    <p style="margin:22px 0 0;font-size:15px;color:#3f3f46">
      Gracias por tu colaboración.<br>
      <strong>Alex</strong> · Mentotrack — Producción Online
    </p>
    <p style="margin:28px 0 0;font-size:12px;color:#a1a1aa;border-top:1px solid #e4e4e7;padding-top:14px">
      Recibes este email porque tienes cuenta en mentotrack.com ·
      <a href="{BASE_URL}/email/baja?t={t}" style="color:#a1a1aa">No quiero recibir más emails como este</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


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
    t = token_para(dest["email"])
    return {
        "from": FROM,
        "to": [dest["email"]],
        "reply_to": REPLY_TO,
        "subject": SUBJECT,
        "html": email_html(dest.get("username") or "", t),
        "headers": {"List-Unsubscribe": f"<{BASE_URL}/email/baja?t={t}>"},
    }


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
        preview = email_html("productor_ejemplo", token_para("preview@example.com"))
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
