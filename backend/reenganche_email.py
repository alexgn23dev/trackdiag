"""Template del email de re-enganche — la vuelta tras el primer análisis.

Por qué existe: medido sobre 781 usuarios con cohorte madura, el 69% se va
tras un solo día de uso y de los que vuelven la mediana son 5 días. Este email
entra en esa ventana (día 3-6) con lo único que tenemos y que le importa al
usuario: su bloqueo concreto y lo que ya le dijimos que hiciera.

Decisión consciente: NO se miden aperturas. Apple Mail Privacy Protection
precarga las imágenes y falsea el grueso de las aperturas — un píxel daría una
métrica bonita que invita a decisiones malas. Se mide el clic (redirect propio)
y la vuelta real (¿hay análisis nuevo en los 7 días siguientes?).
"""

import os
import re

# main.py usa APP_BASE_URL y encuesta_email.py usa BASE_URL: se aceptan ambas
# para no depender de cuál esté puesta en Railway.
BASE_URL = (
    os.environ.get("BASE_URL")
    or os.environ.get("APP_BASE_URL")
    or "https://www.mentotrack.com"
).rstrip("/")
FROM = os.environ.get("RESEND_FROM", "Mentotrack <noreply@mentotrack.com>")
# Ojo: alex@producciononline.com NO recibe correo de Resend (problema conocido).
# El re-enganche invita a responder, así que la respuesta tiene que llegar.
REPLY_TO = os.environ.get("ADMIN_EMAIL", "alexgn23@gmail.com")

# Frase corta del bloqueo, para el asunto. Los `titulo` de engine/templates.py
# son frases completas y no caben en una línea de asunto.
BLOQUEOS_CORTOS = {
    "problema_arreglo": "la estructura del arreglo",
    "poco_contraste": "la curva de energía",
    "falta_impacto": "el impacto del drop",
    "mezcla_prematura": "cerrar el arreglo antes de mezclar",
    "exceso_lowend": "el exceso de graves",
    "exceso_densidad": "el exceso de elementos a la vez",
    "track_verde": "hacer crecer la idea",
    "carencia_espectral": "el cuerpo en medios y agudos",
    "conflicto_armonico": "los conflictos armónicos",
    "pobreza_armonica": "el contenido melódico",
    "harshness_mezcla": "las zonas duras en medios-altos",
    "break_sin_payoff": "el contraste del break",
    "arreglo_repetitivo": "la falta de variaciones",
    "enmascaramiento_bajo": "el bajo tapando al kick",
    "sin_diagnostico": None,
}


def _linea(informe: str, etiqueta: str) -> str:
    """Extrae una línea con prefijo del informe en texto plano guardado en
    `analisis.diagnostico` (formato construido por el frontend)."""
    if not informe:
        return ""
    m = re.search(rf"^{etiqueta}:\s*(.+)$", informe, re.M)
    return m.group(1).strip() if m else ""


def contexto_desde_fila(fila: dict) -> dict:
    """Normaliza una fila de `candidatos_reenganche` en lo que necesita el copy."""
    informe = fila.get("diagnostico") or ""
    senales = fila.get("senales") or {}
    if isinstance(senales, str):
        import json
        try:
            senales = json.loads(senales)
        except (ValueError, TypeError):
            senales = {}
    diag_id = senales.get("diag_principal") or ""
    titulo = _linea(informe, "DIAGNÓSTICO PRINCIPAL")
    # El título viene con el id entre paréntesis al final: se quita.
    titulo = re.sub(r"\s*\([a-z_]+\)\s*$", "", titulo).strip()
    version = fila.get("version_num") or 0
    # Sin bloqueo detectado el encuadre cambia por completo: no se le puede
    # decir "tu bloqueo principal era: no hay bloqueos".
    sin_bloqueo = diag_id in ("", "sin_diagnostico")
    return {
        "email": fila.get("email") or "",
        "username": (fila.get("username") or "").strip(),
        "proyecto": (fila.get("proyecto_nombre") or "").strip(),
        "proyecto_id": str(fila["proyecto_id"]) if fila.get("proyecto_id") else "",
        "version_actual": version,
        "version_siguiente": (version + 1) if version else 0,
        "diag_id": diag_id,
        "diag_titulo": "" if sin_bloqueo else titulo,
        "bloqueo_corto": BLOQUEOS_CORTOS.get(diag_id),
        "sin_bloqueo": sin_bloqueo,
        "siguiente_sesion": _linea(informe, "SIGUIENTE SESIÓN"),
        "estado": senales.get("estado") or "",
    }


def asunto(ctx: dict) -> str:
    """Tres variantes. Sin emojis, sin exclamaciones, sin urgencia falsa."""
    proyecto = ctx.get("proyecto")
    corto = ctx.get("bloqueo_corto")
    if corto and proyecto:
        return f"{proyecto}: sigue pendiente {corto}"
    if corto:
        return f"Lo que quedó pendiente en tu track: {corto}"
    if proyecto:
        return f"¿Has vuelto a tocar {proyecto}?"
    return "¿Has vuelto a tocar ese track?"


def _etiqueta_version(ctx: dict) -> str:
    """Etiqueta que va SIEMPRE precedida del artículo "la" en el copy
    ("la v3" / "la nueva versión") — no incluirlo aquí."""
    n = ctx.get("version_siguiente") or 0
    return f"v{n}" if n else "nueva versión"


def url_boton(ctx: dict, t: str) -> str:
    """Pasa por el redirect propio para poder medir el clic (el cliente de
    correo no ejecuta JS, así que no hay otra forma fiable)."""
    pid = ctx.get("proyecto_id") or ""
    extra = f"&p={pid}" if pid else ""
    return f"{BASE_URL}/r/reenganche?t={t}{extra}"


def url_master(ctx: dict, t: str) -> str:
    """CTA secundario al Máster. También por el redirect propio, para poder
    separar en el embudo quién viene del email y con qué bloqueo."""
    cat = ctx.get("diag_id") or "general"
    return f"{BASE_URL}/r/reenganche?t={t}&d=master&c={cat}"


def email_html(ctx: dict, t: str) -> str:
    proyecto = ctx.get("proyecto")
    nombre_track = f"<strong>{proyecto}</strong>" if proyecto else "tu track"
    vsig = _etiqueta_version(ctx)
    saludo = f"Hola {ctx['username']}," if ctx.get("username") else "Hola,"

    if ctx.get("sin_bloqueo"):
        intro = (f"{saludo} hace unos días analizaste {nombre_track} en Mentotrack "
                 "y el análisis salió limpio: no había ningún bloqueo claro que resolver.")
    else:
        intro = (f"{saludo} hace unos días analizaste {nombre_track} en Mentotrack. "
                 "El bloqueo principal era este:")

    bloque_diag = ""
    if ctx.get("diag_titulo"):
        bloque_diag = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px">
      <tr><td style="border-left:3px solid #25F464;padding:2px 0 2px 14px">
        <p style="margin:0;font-size:15px;line-height:1.55;color:#18181b">{ctx['diag_titulo']}</p>
      </td></tr>
    </table>"""

    bloque_sesion = ""
    if ctx.get("siguiente_sesion"):
        bloque_sesion = f"""
    <p style="margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#71717a">
      Lo que el análisis te propuso:
    </p>
    <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#3f3f46">{ctx['siguiente_sesion']}</p>"""

    if ctx.get("sin_bloqueo"):
        cierre = (f"Si le has seguido dando vueltas, sube la <strong>{vsig}</strong>: comparo las dos "
                  "versiones y te digo qué ha cambiado — también sirve para confirmar que no has roto "
                  "nada por el camino.")
    else:
        cierre = (f"Si ya le has metido mano, súbela: comparo la <strong>{vsig}</strong> con la versión que "
                  "analizaste y te digo punto por punto qué has arreglado, qué se ha movido de sitio y qué "
                  "sigue igual. Si no la has tocado, tampoco pasa nada — esto es solo para que no se te "
                  "quede en la carpeta de siempre.")

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f4f5;padding:24px 12px;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center">
<table role="presentation" width="560" style="max-width:560px;background:#ffffff;border-radius:14px;padding:32px 28px" cellpadding="0" cellspacing="0">
  <tr><td>
    <p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#3f3f46">
      {intro}
    </p>{bloque_diag}{bloque_sesion}
    <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#3f3f46">
      {cierre}
    </p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 8px">
      <tr><td>
        <a href="{url_boton(ctx, t)}"
           style="display:inline-block;padding:12px 22px;background:#6D10FF;color:#ffffff;
                  text-decoration:none;border-radius:10px;font-size:15px;font-weight:600">
          Subir la {vsig}{f" de {proyecto}" if proyecto else ""}
        </a>
      </td></tr>
    </table>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:26px 0 0">
      <tr><td style="border-top:1px solid #e4e4e7;padding-top:18px">
        <p style="margin:0 0 10px;font-size:15px;line-height:1.6;color:#3f3f46">
          Si notas que siempre te atascas en lo mismo, es que falta método. El Máster de
          Producción Online es un programa paso a paso y desde cero para
          <strong>terminar temas al nivel que pide el mercado</strong> junto a 16 profesores
          especializados.
        </p>
        <a href="{url_master(ctx, t)}" style="font-size:15px;color:#6D10FF;font-weight:600;text-decoration:underline">
          Ver el Máster →
        </a>
      </td></tr>
    </table>
    <p style="margin:22px 0 0;font-size:15px;color:#3f3f46">
      <strong>Alex</strong> · Mentotrack — Producción Online
    </p>
    <p style="margin:28px 0 0;font-size:12px;color:#a1a1aa;border-top:1px solid #e4e4e7;padding-top:14px">
      Recibes este email porque analizaste un track en mentotrack.com ·
      <a href="{BASE_URL}/email/baja?t={t}" style="color:#a1a1aa">No quiero recibir más emails como este</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def email_texto(ctx: dict, t: str) -> str:
    """Texto plano — los filtros penalizan el HTML sin alternativa."""
    proyecto = ctx.get("proyecto")
    nombre_track = proyecto if proyecto else "tu track"
    vsig = _etiqueta_version(ctx)
    saludo = f"Hola {ctx['username']}," if ctx.get("username") else "Hola,"
    if ctx.get("sin_bloqueo"):
        partes = [f"{saludo} hace unos días analizaste {nombre_track} en Mentotrack y el análisis "
                  "salió limpio: no había ningún bloqueo claro que resolver."]
    else:
        partes = [f"{saludo} hace unos días analizaste {nombre_track} en Mentotrack."]
        if ctx.get("diag_titulo"):
            partes.append(f"El bloqueo principal era este:\n\n  {ctx['diag_titulo']}")
    if ctx.get("siguiente_sesion"):
        partes.append(f"LO QUE EL ANÁLISIS TE PROPUSO:\n{ctx['siguiente_sesion']}")
    if ctx.get("sin_bloqueo"):
        partes.append(
            f"Si le has seguido dando vueltas, sube la {vsig}: comparo las dos versiones y te digo "
            "qué ha cambiado — también sirve para confirmar que no has roto nada por el camino."
        )
    else:
        partes.append(
            f"Si ya le has metido mano, súbela: comparo la {vsig} con la versión que analizaste "
            "y te digo punto por punto qué has arreglado, qué se ha movido de sitio y qué sigue "
            "igual. Si no la has tocado, tampoco pasa nada — esto es solo para que no se te quede "
            "en la carpeta de siempre."
        )
    partes.append(f"Subir la {vsig}: {url_boton(ctx, t)}")
    partes.append(
        "Si notas que siempre te atascas en lo mismo, es que falta método. El Máster de "
        "Producción Online es un programa paso a paso y desde cero para terminar temas al "
        "nivel que pide el mercado junto a 16 profesores especializados."
        f"\nVer el Máster: {url_master(ctx, t)}"
    )
    partes.append("Alex · Mentotrack — Producción Online")
    partes.append(f"--\nRecibes este email porque analizaste un track en mentotrack.com.\nDarte de baja: {BASE_URL}/email/baja?t={t}")
    return "\n\n".join(partes) + "\n"


def payload_para(ctx: dict, t: str, destinatario: str = "") -> dict:
    """Payload para la API de Resend. `destinatario` permite enviar una prueba
    a otra dirección sin tocar el resto del contenido."""
    baja = f"<{BASE_URL}/email/baja?t={t}>"
    return {
        "from": FROM,
        "to": [destinatario or ctx["email"]],
        "reply_to": REPLY_TO,
        "subject": asunto(ctx),
        "html": email_html(ctx, t),
        "text": email_texto(ctx, t),
        "headers": {
            "List-Unsubscribe": baja,
            # Hace que Gmail muestre su botón nativo de "Cancelar suscripción".
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }
