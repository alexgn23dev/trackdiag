"""Template del email de la encuesta de comunidad.

Módulo compartido entre el envío programado del servidor (main.py) y el
script manual (scripts/enviar_encuesta_comunidad.py) — una sola fuente
del copy para que no diverjan.
"""

import os

BASE_URL = os.environ.get("BASE_URL", "https://www.mentotrack.com")
FROM = os.environ.get("RESEND_FROM", "Mentotrack <noreply@mentotrack.com>")
REPLY_TO = "alex@producciononline.com"
SUBJECT = "¿Quieres feedback entre productores?"

OPCIONES = [
    ("todo", "Sí — compartiría mis tracks y comentaría los de otros"),
    ("solo_compartir", "Compartiría mis tracks, pero no me veo comentando"),
    ("solo_comentar", "Comentaría los de otros, pero aún no compartiría los míos"),
    ("no", "No me interesa"),
]


def email_html(t: str) -> str:
    """HTML del email. `t` es el token JWT personalizado del destinatario."""
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
    <p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#3f3f46">
      Soy Alex, de Mentotrack. Estoy pensando en transformar esta plataforma en algo más
      interactivo, con comunidad, donde podáis ayudaros entre todos.
    </p>
    <p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#3f3f46">
      ¿Cómo lo haríamos? Creando una sección donde compartas públicamente tu idea inacabada
      o tu track casi terminado —con tu nombre, no anónimo— junto a otros productores que
      también usan la plataforma, para daros feedback entre vosotros y ayudaros a terminar
      los proyectos.
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


def email_texto(t: str) -> str:
    """Versión texto plano (mejora la entregabilidad: los filtros penalizan
    los emails que solo llevan HTML)."""
    lineas_opciones = "\n".join(
        f"- {texto}:\n  {BASE_URL}/encuesta?t={t}&o={clave}\n"
        for clave, texto in OPCIONES
    )
    return f"""Soy Alex, de Mentotrack. Estoy pensando en transformar esta plataforma en algo más interactivo, con comunidad, donde podáis ayudaros entre todos.

¿Cómo lo haríamos? Creando una sección donde compartas públicamente tu idea inacabada o tu track casi terminado —con tu nombre, no anónimo— junto a otros productores que también usan la plataforma, para daros feedback entre vosotros y ayudaros a terminar los proyectos.

Responde con un clic (abre el enlace de la opción que mejor te describa):

{lineas_opciones}
Tras el clic podrás añadir un comentario si quieres matizar tu respuesta.

Gracias por tu colaboración.
Alex · Mentotrack — Producción Online

--
Recibes este email porque tienes cuenta en mentotrack.com.
Darte de baja: {BASE_URL}/email/baja?t={t}
"""


def payload_para(email: str, t: str) -> dict:
    """Payload completo para la API de Resend (send o batch)."""
    return {
        "from": FROM,
        "to": [email],
        "reply_to": REPLY_TO,
        "subject": SUBJECT,
        "html": email_html(t),
        "text": email_texto(t),
        "headers": {"List-Unsubscribe": f"<{BASE_URL}/email/baja?t={t}>"},
    }
