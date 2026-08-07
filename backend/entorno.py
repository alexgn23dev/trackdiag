"""Identidad del entorno y protección contra tocar producción desde preview.

El riesgo concreto: un entorno de preview mal configurado que herede
`DATABASE_URL`, `RESEND_API_KEY` o `SHEETS_WEBHOOK` de producción escribiría
en la base real, mandaría correos a usuarios reales y ensuciaría el espejo de
Sheets. Preferimos que la app **no arranque** a que arranque contra producción.

Cómo funciona sin exponer secretos: nunca se imprime ni se compara un valor
completo. Se comparan huellas SHA-256 truncadas, y para la base de datos se
compara además host+puerto+nombre, que no son secretos por sí solos.

Variables:

    MENTOTRACK_ENV          production | preview | development   (default: production)
    PROD_DB_FINGERPRINT     huella de la DATABASE_URL de producción (ver más abajo)
    PROD_RESEND_FINGERPRINT huella de la RESEND_API_KEY de producción
    PREVIEW_ALLOW_UNSAFE    "1" para saltarse la comprobación (romper el cristal)

Para obtener una huella sin revelar el secreto, en el entorno de producción:

    python -c "import backend.entorno as e; print(e.huella(os.environ['DATABASE_URL']))"

o más cómodo, con la app arrancada, `GET /api/tecnico/versiones` la incluye.
"""

import hashlib
import os
from urllib.parse import urlparse

ENV = (os.environ.get("MENTOTRACK_ENV") or "production").strip().lower()
ES_PREVIEW = ENV == "preview"
ES_PRODUCCION = ENV == "production"
ES_DESARROLLO = ENV == "development"


class ConfiguracionInsegura(RuntimeError):
    """Un entorno no productivo apunta a recursos de producción."""


def huella(valor: str) -> str:
    """SHA-256 truncado. No permite recuperar el valor original."""
    if not valor:
        return ""
    return hashlib.sha256(valor.strip().encode()).hexdigest()[:16]


def _identidad_db(url: str) -> str:
    """host:puerto/base — suficiente para detectar 'es la misma base' y
    sin exponer usuario ni contraseña."""
    if not url:
        return ""
    try:
        p = urlparse(url)
        return f"{p.hostname or ''}:{p.port or ''}{p.path or ''}"
    except Exception:
        return ""


def _flag(nombre: str, defecto: bool) -> bool:
    bruto = os.environ.get(nombre)
    if bruto is None:
        return defecto
    return bruto.strip().lower() in ("1", "true", "si", "sí", "yes", "on")


# --- Interruptores de servicios externos ----------------------------------
# En preview todo lo que sale al mundo viene APAGADO por defecto: hay que
# encenderlo a propósito, no apagarlo. Un olvido no manda correos reales.
SHEETS_ACTIVO = _flag("SHEETS_ACTIVO", defecto=not ES_PREVIEW)
EMAIL_ACTIVO = _flag("EMAIL_ACTIVO", defecto=not ES_PREVIEW)
WEBHOOKS_ACTIVOS = _flag("WEBHOOKS_ACTIVOS", defecto=not ES_PREVIEW)
ANALITICA_ACTIVA = _flag("ANALITICA_ACTIVA", defecto=not ES_PREVIEW)


def comprobar_aislamiento() -> list:
    """Verifica que un entorno no productivo no apunte a producción.

    Devuelve la lista de problemas. En preview, `proteger_arranque()` la
    convierte en una excepción que impide arrancar.
    """
    if ES_PRODUCCION:
        return []

    problemas = []

    db_url = os.environ.get("DATABASE_URL", "")
    prod_fp = os.environ.get("PROD_DB_FINGERPRINT", "").strip()
    if db_url and prod_fp:
        if huella(db_url) == prod_fp:
            problemas.append(
                "DATABASE_URL es idéntica a la de producción (coincide la huella)")
        elif huella(_identidad_db(db_url)) == prod_fp:
            problemas.append(
                "DATABASE_URL apunta al mismo host/puerto/base que producción")
    elif db_url and not prod_fp:
        problemas.append(
            "PROD_DB_FINGERPRINT no está definida: no se puede comprobar que la "
            "base no sea la de producción. Defínela o desactiva la comprobación "
            "a propósito con PREVIEW_ALLOW_UNSAFE=1")

    # Heurística adicional: la base interna de Railway en producción.
    if db_url and ES_PREVIEW:
        ident = _identidad_db(db_url)
        if "postgres.railway.internal" in ident and not os.environ.get("PREVIEW_DB_INTERNA_OK"):
            problemas.append(
                "DATABASE_URL usa el host interno de Railway sin marcar "
                "PREVIEW_DB_INTERNA_OK: probablemente sea la base de producción")

    resend = os.environ.get("RESEND_API_KEY", "")
    resend_fp = os.environ.get("PROD_RESEND_FINGERPRINT", "").strip()
    if resend and resend_fp and huella(resend) == resend_fp:
        problemas.append("RESEND_API_KEY es la de producción")

    if ES_PREVIEW and EMAIL_ACTIVO and resend:
        problemas.append(
            "EMAIL_ACTIVO=1 en preview: se enviarían correos de verdad. "
            "Déjalo apagado salvo que sea justo lo que quieres probar")

    if ES_PREVIEW and SHEETS_ACTIVO and os.environ.get("SHEETS_WEBHOOK"):
        problemas.append("SHEETS_ACTIVO=1 en preview con SHEETS_WEBHOOK definido")

    jwt = os.environ.get("JWT_SECRET", "")
    jwt_fp = os.environ.get("PROD_JWT_FINGERPRINT", "").strip()
    if jwt and jwt_fp and huella(jwt) == jwt_fp:
        problemas.append(
            "JWT_SECRET es el de producción: los tokens de preview servirían en prod")

    return problemas


def proteger_arranque() -> None:
    """Aborta el arranque si un entorno preview apunta a producción."""
    problemas = comprobar_aislamiento()
    if not problemas:
        if not ES_PRODUCCION:
            print(f"[ENTORNO] {ENV}: aislamiento verificado · "
                  f"sheets={SHEETS_ACTIVO} email={EMAIL_ACTIVO} "
                  f"webhooks={WEBHOOKS_ACTIVOS} analitica={ANALITICA_ACTIVA}")
        return

    detalle = "\n".join(f"  - {p}" for p in problemas)
    if _flag("PREVIEW_ALLOW_UNSAFE", defecto=False):
        print(f"[ENTORNO] AVISO — arrancando en {ENV} pese a:\n{detalle}\n"
              "         (PREVIEW_ALLOW_UNSAFE=1)")
        return
    raise ConfiguracionInsegura(
        f"El entorno '{ENV}' apunta a recursos de producción:\n{detalle}\n"
        "Corrige las variables o pon PREVIEW_ALLOW_UNSAFE=1 si sabes lo que haces.")


def resumen() -> dict:
    """Para el endpoint técnico y la banda de entorno del admin.
    Solo huellas y booleanos: ningún secreto."""
    return {
        "entorno": ENV,
        "es_preview": ES_PREVIEW,
        "servicios": {
            "sheets": SHEETS_ACTIVO,
            "email": EMAIL_ACTIVO,
            "webhooks": WEBHOOKS_ACTIVOS,
            "analitica": ANALITICA_ACTIVA,
        },
        "huellas": {
            "database_url": huella(os.environ.get("DATABASE_URL", "")),
            "database_identidad": huella(_identidad_db(os.environ.get("DATABASE_URL", ""))),
            "jwt_secret": huella(os.environ.get("JWT_SECRET", "")),
            "resend_api_key": huella(os.environ.get("RESEND_API_KEY", "")),
        },
        "aislamiento_ok": not comprobar_aislamiento(),
        "problemas_aislamiento": comprobar_aislamiento(),
    }
