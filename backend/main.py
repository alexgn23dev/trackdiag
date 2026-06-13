"""
Mentotrack API — Backend FastAPI
Endpoint principal: POST /api/diagnostico
"""

import os
import re
import asyncio
import signal
import uuid
import json
import secrets
import shutil
import tempfile
import httpx
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, HTMLResponse, StreamingResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Engine imports diferidos (lazy) — librosa/numpy/scipy solo se cargan
# cuando llega un diagnóstico, no al arrancar el servidor.
# Esto reduce el cold-start de ~8-12s a ~2-3s.
_extraer_senales = None
_generar_diagnostico = None
_comparar_senales = None


def _load_engine():
    """Carga los módulos pesados de análisis de audio bajo demanda."""
    global _extraer_senales, _generar_diagnostico, _comparar_senales
    if _extraer_senales is None:
        from engine.extractor import extraer_senales
        from engine.diagnostico import generar_diagnostico
        from engine.comparador import comparar_senales
        _extraer_senales = extraer_senales
        _generar_diagnostico = generar_diagnostico
        _comparar_senales = comparar_senales

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Mentotrack API", version="0.5.46")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Tarea de cron para reporte mensual
_reporte_task_handle = None
_encuesta_task_handle = None


def _run_alembic_upgrade() -> None:
    """Aplica las migraciones pendientes con `alembic upgrade head`.

    Se ejecuta al arrancar la app para que las tablas nuevas estén creadas
    antes de aceptar peticiones. Si la DB ya está al día, no hace nada.
    Si falla, lo logueamos pero seguimos arrancando: la app puede vivir
    con la DB desactualizada (los endpoints que necesiten lo nuevo darán
    503), preferible a no arrancar."""
    try:
        from alembic.config import Config
        from alembic import command
        backend_dir = Path(__file__).resolve().parent
        cfg = Config(str(backend_dir / "alembic.ini"))
        command.upgrade(cfg, "head")
        print("[STARTUP] alembic upgrade head: OK")
    except Exception as e:
        print(f"[STARTUP] alembic upgrade FALLÓ (la app sigue arrancando): {e}")


@app.on_event("startup")
async def _startup_db():
    """Inicializa el pool de Postgres si DATABASE_URL está disponible.
    Aplica migraciones pendientes antes de abrir el pool, para que las
    tablas nuevas existan al recibir la primera petición.
    En local sin DATABASE_URL, la app sigue arrancando (el motor de análisis
    no depende de la BD; los endpoints que sí dependan fallarán explícitos).
    Lanza también la tarea de cron del reporte mensual.
    """
    global _reporte_task_handle, _encuesta_task_handle
    if os.environ.get("DATABASE_URL"):
        # Migraciones primero (sync, rápido si no hay nada que aplicar).
        await asyncio.to_thread(_run_alembic_upgrade)
        from db import init_pool
        await init_pool()
        # Lanza la tarea de reporte mensual (no await, es long-running)
        _reporte_task_handle = asyncio.create_task(_task_monthly_reporte())
        # Envío programado de la encuesta de comunidad (one-shot, con candado en DB)
        _encuesta_task_handle = asyncio.create_task(_task_envio_encuesta())


@app.on_event("shutdown")
async def _shutdown_db():
    global _reporte_task_handle, _encuesta_task_handle
    if _reporte_task_handle:
        _reporte_task_handle.cancel()
        try:
            await _reporte_task_handle
        except asyncio.CancelledError:
            pass
    if _encuesta_task_handle:
        _encuesta_task_handle.cancel()
        try:
            await _encuesta_task_handle
        except asyncio.CancelledError:
            pass
    if os.environ.get("DATABASE_URL"):
        from db import close_pool
        await close_pool()

# Ruta al frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# CORS — solo orígenes confiables
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",") if os.environ.get("ALLOWED_ORIGINS") else [
    "https://mentotrack.com",
    "https://www.mentotrack.com",
    "http://localhost:8000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# GZip — comprime respuestas >500 bytes (~60-70% ahorro en JSON/HTML)
app.add_middleware(GZipMiddleware, minimum_size=500)


# Security headers — protección contra clickjacking, sniffing, XSS
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # CSP: permite CDNs usados por el frontend (React, Tailwind, fonts)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://www.googletagmanager.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://www.googletagmanager.com https://img.youtube.com https://i.ytimg.com https://i3.ytimg.com https://i1.sndcdn.com https://i2.sndcdn.com https://i3.sndcdn.com https://i4.sndcdn.com; "
            "connect-src 'self' https://www.google-analytics.com https://analytics.google.com https://*.google-analytics.com https://*.analytics.google.com; "
            "frame-src https://w.soundcloud.com https://www.youtube.com https://www.youtube-nocookie.com; "
            "frame-ancestors 'none';"
        )
        # HSTS solo en producción (cuando hay HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# =========================================================================
# JWT Configuration
# =========================================================================
JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    print("[WARN] JWT_SECRET no configurado — generando uno aleatorio (se perderá al reiniciar)")

JWT_EXPIRY_DAYS = int(os.environ.get("JWT_EXPIRY_DAYS", "7"))


def _create_token(email: str) -> str:
    """Genera un JWT token para el usuario."""
    payload = {
        "sub": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _verify_token(token: str) -> str | None:
    """Verifica un JWT token y devuelve el email o None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _get_token_from_request(request: Request) -> str | None:
    """Extrae el token del header Authorization: Bearer <token>."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


# Google Sheets webhook. Cutover B cerrado completamente el 2026-05-27:
# self-heal bulk copió 315 de 316 hashes residuales a Postgres, dejando
# 1 usuario residual sin hash real (no encontrado en Sheets). Postgres
# es la fuente única para auth normal. Esta variable SOLO la usan los
# endpoints admin de cutover-b (consulta y heal bulk) por si hay que
# repetir la operación con casos edge. Se puede desactivar en Railway
# cuando se confirme que no se va a necesitar más.
SHEETS_WEBHOOK = os.environ.get("SHEETS_WEBHOOK", "")

# Almacenamiento simple de sesiones (JSON lines)
SESIONES_PATH = os.environ.get("SESIONES_PATH", "sesiones.jsonl")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.5.46"}


# Validación compartida de uploads de audio (track principal y referencia)
_AUDIO_EXTENSIONES = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg"}
_AUDIO_SIGNATURES = {
    b"RIFF": "wav",       # WAV (RIFF header)
    b"fLaC": "flac",      # FLAC
    b"FORM": "aiff",      # AIFF
    b"OggS": "ogg",       # OGG Vorbis
    b"\xff\xfb": "mp3",   # MP3 (MPEG frame sync)
    b"\xff\xf3": "mp3",   # MP3 (MPEG 2.5)
    b"\xff\xf2": "mp3",   # MP3 (MPEG 2)
    b"ID3": "mp3",        # MP3 con ID3 tag
}
_MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB (previene OOM crashes)


def _validar_audio_upload(filename: str, content: bytes, etiqueta: str = ""):
    """Valida extensión, tamaño y magic bytes de un upload de audio.
    Devuelve (extension, None) si es válido o (extension, JSONResponse de error).
    Los magic bytes previenen que alguien renombre un ejecutable a .mp3."""
    pref = f"{etiqueta}: " if etiqueta else ""
    extension = os.path.splitext(filename or "")[1].lower()
    if extension not in _AUDIO_EXTENSIONES:
        return extension, JSONResponse(
            status_code=400,
            content={"error": f"{pref}Formato no soportado: {extension}. Usa MP3, WAV, FLAC o AIFF."}
        )
    if len(content) > _MAX_UPLOAD_BYTES:
        return extension, JSONResponse(
            status_code=413,
            content={"error": f"{pref}Archivo demasiado grande ({len(content) // (1024*1024)} MB). Máximo: 150 MB. Puedes convertir a MP3 para reducir el tamaño."}
        )
    header = content[:4]
    if not any(header.startswith(sig) for sig in _AUDIO_SIGNATURES):
        return extension, JSONResponse(
            status_code=415,
            content={"error": f"{pref}El archivo no parece ser audio válido. Asegúrate de subir un MP3, WAV, FLAC o AIFF real."}
        )
    return extension, None


@app.post("/api/diagnostico")
@limiter.limit("3/minute")
async def diagnosticar(
    request: Request,
    audio: UploadFile = File(...),
    genero: str = Form(...),
    genero_custom: str = Form(""),
    fase: str = Form(...),
    objetivo: str = Form(...),
    bloqueo_percibido: str = Form(""),
    experiencia: str = Form(...),
    dificultad_habitual: str = Form(...),
    referencia: str = Form(""),
    tiempo_disponible: str = Form(""),
    bpm_manual: str = Form(""),
    audio_ref: UploadFile | None = File(None),
):
    """
    Recibe un archivo de audio + contexto del cuestionario.
    Opcionalmente un track de referencia (audio_ref) para comparar.
    Retorna un diagnóstico estructurado.
    """
    # Si el usuario seleccionó "Otro", el campo libre es obligatorio.
    # 67% de usuarios "Otro" lo dejaban vacío en versiones previas — info perdida.
    if genero == "otro" and len((genero_custom or "").strip()) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": "Si seleccionas 'Otro' como género, escribe en el campo de texto qué género estás produciendo (mínimo 2 caracteres)."},
        )

    # Validar extensión, tamaño y magic bytes del track principal
    content = await audio.read()
    extension, err = _validar_audio_upload(audio.filename, content)
    if err:
        return err

    # Track de referencia (opcional): mismas validaciones, fail-fast antes de analizar nada
    content_ref = None
    extension_ref = None
    senales_ref = None
    comparacion_error = None
    tiene_ref = audio_ref is not None and (audio_ref.filename or "").strip() != ""
    if tiene_ref:
        content_ref = await audio_ref.read()
        if not content_ref:
            tiene_ref = False
            comparacion_error = "El track de referencia llegó vacío (0 bytes). Tu diagnóstico se generó igualmente, sin la comparación."
        else:
            extension_ref, err = _validar_audio_upload(audio_ref.filename, content_ref, "Track de referencia")
            if err:
                return err

    # Guardar archivo temporal
    session_id = str(uuid.uuid4())[:8]
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, f"{session_id}{extension}")

    try:
        with open(tmp_path, "wb") as f:
            f.write(content)
        tmp_ref_path = None
        if tiene_ref:
            tmp_ref_path = os.path.join(tmp_dir, f"{session_id}_ref{extension_ref}")
            with open(tmp_ref_path, "wb") as f:
                f.write(content_ref)
        # Liberar los bytes crudos: ya están en disco y pueden ser hasta 300 MB
        # que de otro modo seguirían vivos en RAM durante todo el análisis
        content = None
        content_ref = None

        # Validar duración mínima (8 seg) — audios más cortos dan diagnósticos sin sentido
        _load_engine()
        import librosa as _lr
        try:
            duracion_check = _lr.get_duration(path=tmp_path)
        except Exception:
            duracion_check = 0
        if duracion_check < 8:
            return JSONResponse(
                status_code=400,
                content={"error": "El audio es demasiado corto (mínimo 8 segundos). Sube un fragmento más largo de tu track."}
            )
        if tiene_ref:
            try:
                duracion_ref = _lr.get_duration(path=tmp_ref_path)
            except Exception:
                duracion_ref = 0
            if duracion_ref < 8:
                return JSONResponse(
                    status_code=400,
                    content={"error": "El track de referencia es demasiado corto (mínimo 8 segundos). Sube un track más largo o quítalo para analizar sin comparación."}
                )

        # Extraer señales con timeout de 90s (previene que archivos corruptos cuelguen el worker)
        bpm_int = None
        if bpm_manual and bpm_manual.strip():
            try:
                bpm_int = int(float(bpm_manual.strip()))
            except ValueError:
                pass

        loop = asyncio.get_event_loop()
        try:
            senales = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _extraer_senales(tmp_path, bpm_manual=bpm_int)),
                timeout=90
            )
        except asyncio.TimeoutError:
            print(f"[ERROR] diagnosticar: Timeout procesando audio ({session_id})")
            return JSONResponse(
                status_code=504,
                content={"error": "El análisis tardó demasiado. El archivo puede estar corrupto. Inténtalo con otro archivo."}
            )

        # Extraer señales de la referencia — EN SERIE (no en paralelo: el worker de
        # Railway comparte CPU) y sin armonía (~90% más rápido). Si falla, el
        # diagnóstico del usuario sale igual, solo se pierde la comparación.
        if tiene_ref:
            try:
                senales_ref = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: _extraer_senales(tmp_ref_path, omitir_armonia=True)),
                    timeout=60
                )
            except asyncio.TimeoutError:
                print(f"[ERROR] diagnosticar: Timeout en referencia ({session_id})")
                comparacion_error = "No se pudo analizar el track de referencia (tardó demasiado). Tu diagnóstico se generó igualmente, sin la comparación."
            except Exception as e:
                print(f"[ERROR] diagnosticar: referencia {type(e).__name__}: {e}")
                comparacion_error = "No se pudo analizar el track de referencia. Tu diagnóstico se generó igualmente, sin la comparación."

        # Construir contexto. genero_custom solo se usa cuando genero == "otro"
        # (texto libre que el usuario escribe para describir su género).
        contexto = {
            "genero": genero,
            "genero_custom": _sanitize(genero_custom, 60) if genero == "otro" else "",
            "fase": fase,
            "objetivo": objetivo,
            "bloqueo_percibido": bloqueo_percibido,
            "experiencia": experiencia,
            "dificultad_habitual": dificultad_habitual,
            "referencia": referencia,
            "tiempo_disponible": tiempo_disponible,
        }

        # Generar diagnóstico
        resultado = _generar_diagnostico(senales, contexto)

        # Comparación contra la referencia (si la hay)
        if senales_ref is not None:
            try:
                comp = _comparar_senales(senales, senales_ref, contexto)
                comp["ref_filename"] = (audio_ref.filename or "")[:120]
                resultado["comparacion_referencia"] = comp
            except Exception as e:
                print(f"[ERROR] diagnosticar: comparador {type(e).__name__}: {e}")
                comparacion_error = "No se pudo completar la comparación con la referencia. Tu diagnóstico se generó igualmente."
        if comparacion_error:
            resultado["comparacion_referencia"] = {"error": comparacion_error}

        # Guardar sesión para análisis futuro
        sesion = {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "contexto": contexto,
            "senales": {k: v for k, v in senales.items() if k != "bloques_rms"},
            "resultado": resultado,
        }
        if senales_ref is not None:
            # Para calibrar los umbrales del comparador con casos reales
            sesion["senales_ref"] = {k: v for k, v in senales_ref.items() if k != "bloques_rms"}
        with open(SESIONES_PATH, "a") as f:
            f.write(json.dumps(sesion, ensure_ascii=False) + "\n")

        return resultado

    except asyncio.TimeoutError:
        # Ya manejado arriba, pero por si acaso
        return JSONResponse(
            status_code=504,
            content={"error": "El análisis tardó demasiado. Inténtalo de nuevo."}
        )
    except Exception as e:
        # Log detallado para debug, mensaje genérico al cliente (no exponer internals)
        print(f"[ERROR] diagnosticar: {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error procesando el audio. Verifica que el archivo no esté corrupto e inténtalo de nuevo."}
        )
    finally:
        # Limpiar archivos temporales (rmtree maneja dir no vacío)
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.get("/api/opciones")
def opciones():
    """Retorna las opciones del cuestionario para el frontend."""
    return _OPCIONES


_OPCIONES = {
        "generos": [
            {"value": "tech_house", "label": "Tech House"},
            {"value": "house", "label": "House"},
            {"value": "techno", "label": "Techno"},
            {"value": "techno_acido", "label": "Techno ácido"},
            {"value": "hard_techno", "label": "Hard Techno"},
            {"value": "minimal", "label": "Minimal"},
            {"value": "dub_techno", "label": "Dub Techno"},
            {"value": "progressive_house", "label": "Progressive House"},
            {"value": "trance", "label": "Trance"},
            {"value": "psytrance", "label": "Psytrance"},
            {"value": "melodic_techno", "label": "Melodic Techno"},
            {"value": "deep_house", "label": "Deep House"},
            {"value": "afro_house", "label": "Afro House"},
            {"value": "indie_dance", "label": "Indie Dance"},
            {"value": "breaks", "label": "Breaks"},
            {"value": "hard_dance", "label": "Hard Dance / Bounce / Hardstyle"},
            {"value": "dnb", "label": "Drum & Bass / Jungle"},
            {"value": "organic_house", "label": "Organic / Melodic House"},
            {"value": "otro", "label": "Otro"},
        ],
        "fases": [
            {"value": "idea", "label": "Idea inicial / loop"},
            {"value": "arreglo_en_progreso", "label": "Arreglo en progreso"},
            {"value": "ajustando_mezcla", "label": "Arreglo cerrado, ajustando mezcla"},
            {"value": "casi_listo", "label": "Creo que está casi listo"},
        ],
        "objetivos": [
            {"value": "pinchar", "label": "Publicar y tocar en sesión"},
            {"value": "aprender", "label": "Practicar y aprender"},
            {"value": "sellos", "label": "Enviar demo a sellos"},
            {"value": "todo", "label": "Todo lo anterior"},
        ],
        "experiencia": [
            {"value": "menos_6m", "label": "Menos de 6 meses"},
            {"value": "6m_2a", "label": "6 meses a 2 años"},
            {"value": "2a_5a", "label": "2 a 5 años"},
            {"value": "mas_5a", "label": "Más de 5 años"},
        ],
        "dificultad_habitual": [
            {"value": "terminar", "label": "Terminar tracks"},
            {"value": "sonidos", "label": "Encontrar buenos sonidos"},
            {"value": "mezcla", "label": "Que la mezcla suene bien"},
            {"value": "estructura", "label": "Estructurar las ideas"},
            {"value": "todo", "label": "Todo me cuesta"},
        ],
        "tiempo_disponible": [
            {"value": "menos_1h", "label": "Menos de 1 hora"},
            {"value": "1h_2h", "label": "1 a 2 horas"},
            {"value": "mas_2h", "label": "Más de 2 horas"},
            {"value": "sin_prisa", "label": "No tengo prisa"},
        ],
}

# Mapas inversos label → value (para mapear el formulario guardado, que
# almacena labels en ES, de vuelta a values al pre-rellenar el perfil).
_LABEL_A_VALUE_GENERO = {o["label"].lower(): o["value"] for o in _OPCIONES["generos"]}
_LABEL_A_VALUE_EXPERIENCIA = {o["label"].lower(): o["value"] for o in _OPCIONES["experiencia"]}


# =========================================================================
# Feedback endpoints
# =========================================================================

FEEDBACK_FILE = Path(__file__).resolve().parent / "data" / "feedbacks.jsonl"
FEEDBACK_REQUESTS_FILE = Path(__file__).resolve().parent / "data" / "feedback_requests.jsonl"


def _sanitize(text: str, max_len: int = 500) -> str:
    """Sanitiza texto de entrada: strip, limit length, remove control chars."""
    if not isinstance(text, str):
        return ""
    return text.strip()[:max_len].replace("\x00", "")


@app.post("/api/feedback")
@limiter.limit("10/minute")
async def guardar_feedback(request: Request, data: dict):
    """Guarda feedback de utilidad del usuario (requiere JWT)."""
    token = _get_token_from_request(request)
    token_email = _verify_token(token) if token else None
    if not token_email:
        return JSONResponse(status_code=401, content={"error": "Autenticación requerida"})

    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "email": token_email,
        "util": _sanitize(str(data.get("util", "")), 20),
        "comentario": _sanitize(data.get("comentario", "")),
        "diagnostico": _sanitize(data.get("diagnostico", ""), 100),
    }
    with open(FEEDBACK_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.post("/api/feedback-request")
@limiter.limit("5/minute")
async def guardar_feedback_request(request: Request, data: dict):
    """Guarda solicitud de feedback real (requiere JWT)."""
    token = _get_token_from_request(request)
    token_email = _verify_token(token) if token else None
    if not token_email:
        return JSONResponse(status_code=401, content={"error": "Autenticación requerida"})

    FEEDBACK_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "email": token_email,
        "enlace": _sanitize(data.get("enlace", ""), 300),
        "diagnostico_id": _sanitize(data.get("diagnostico_id", ""), 100),
        "genero": _sanitize(data.get("genero", ""), 50),
        "objetivo": _sanitize(data.get("objetivo", ""), 50),
    }
    with open(FEEDBACK_REQUESTS_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}


# Log persistente de solicitudes de sesión 1:1 (consultoría). Apéndice
# rápido para tener historial sin tocar Postgres todavía. Si vemos volumen
# real, se migra a tabla con admin dashboard.
CONSULTORIA_REQUESTS_FILE = Path(__file__).resolve().parent / "data" / "consultoria_requests.jsonl"


# Embudo CTA — endpoint público para registrar eventos del usuario
# (impresión del CTA, clicks, visitas a /consultoria, form started/submit).
# No persiste IPs ni datos personales más allá del email opcional y un
# session_id anónimo generado por el cliente en localStorage.
@app.post("/api/cta-event")
@limiter.limit("60/minute")
async def cta_event(request: Request, data: dict):
    """Registra un evento del embudo. Acepta JSON con:
      evento (obligatorio), session_id, diagnostico_id, email."""
    evento = (data.get("evento") or "").strip()
    if not evento:
        return JSONResponse(status_code=400, content={"error": "Falta 'evento'"})
    session_id = _sanitize(data.get("session_id", ""), 64)
    diagnostico_id = _sanitize(data.get("diagnostico_id", ""), 50)
    email = _sanitize(data.get("email", ""), 180).lower()
    ua = (request.headers.get("user-agent") or "")[:500]

    if not _pg_available():
        # No bloqueamos al usuario por un fallo de tracking — solo logueamos.
        return {"ok": True, "stored": False}
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        row = await repo.create_cta_evento(
            pool,
            evento=evento,
            session_id=session_id or None,
            diagnostico_id=diagnostico_id or None,
            email=email or None,
            user_agent=ua or None,
        )
    except Exception as e:
        print(f"[CTA-EVENT] error: {type(e).__name__}: {e}")
        return {"ok": True, "stored": False}
    return {"ok": True, "stored": bool(row)}


@app.post("/api/consultoria/solicitud")
@limiter.limit("5/minute")
async def solicitud_consultoria(request: Request, data: dict):
    """Recibe la solicitud del formulario de la sesión 1:1, manda email a
    Alex con todos los datos y registra la entrada en jsonl local. No
    requiere auth — la página /consultoria es pública."""
    nombre = _sanitize(data.get("nombre", ""), 100)
    email = _sanitize(data.get("email", ""), 150).lower()
    soundcloud = _sanitize(data.get("soundcloud", ""), 500)

    if len(nombre) < 2:
        return JSONResponse(status_code=400, content={"error": "Indica tu nombre."})
    if "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse(status_code=400, content={"error": "El correo no parece válido."})
    if not (soundcloud.startswith("http://") or soundcloud.startswith("https://")):
        return JSONResponse(status_code=400, content={"error": "El enlace de tu track debe empezar por http:// o https://."})

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nombre": nombre,
        "email": email,
        "soundcloud": soundcloud,
        "ref_cancion": _sanitize(data.get("ref_cancion", ""), 300),
        "ref_artistas": _sanitize(data.get("ref_artistas", ""), 200),
        "ref_sellos": _sanitize(data.get("ref_sellos", ""), 200),
        "contexto": _sanitize(data.get("contexto", ""), 800),
    }

    # Persistencia primary: Postgres. Best-effort — si falla, igualmente
    # respondemos OK al usuario (el email a Alex y el jsonl de backup
    # garantizan que no se pierde la solicitud).
    if _pg_available():
        try:
            from db import get_pool
            import repositories as repo
            pool = get_pool()
            await repo.create_consultoria_solicitud(
                pool,
                nombre=entry["nombre"],
                email=entry["email"],
                soundcloud=entry["soundcloud"],
                ref_cancion=entry["ref_cancion"],
                ref_artistas=entry["ref_artistas"],
                ref_sellos=entry["ref_sellos"],
                contexto=entry["contexto"],
            )
        except Exception as e:
            print(f"[CONSULTORIA] Postgres falló: {type(e).__name__}: {e}")

    # Backup local en jsonl (filesystem efímero en Railway pero útil
    # para entornos donde sí persista — y por si Postgres está caído).
    try:
        CONSULTORIA_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONSULTORIA_REQUESTS_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[CONSULTORIA] no se pudo persistir en jsonl: {e}")

    # Email a Alex con los datos. Si falla, igualmente devolvemos OK al
    # usuario — Alex puede recuperar de Postgres / jsonl. Pero logueamos.
    _enviar_email_solicitud_consultoria(entry)

    # Marcar el último paso del embudo (form_submit) automáticamente desde
    # backend — el frontend no necesita disparar el evento explícitamente.
    if _pg_available():
        try:
            from db import get_pool
            import repositories as repo
            await repo.create_cta_evento(
                get_pool(),
                evento="consultoria_form_submit",
                session_id=_sanitize(data.get("session_id", ""), 64) or None,
                email=entry["email"],
            )
        except Exception as e:
            print(f"[CTA-EVENT] form_submit no se pudo registrar: {e}")

    return {"ok": True}


# Caché en memoria de IP → código de país ISO-2. Persiste hasta que el
# contenedor reinicia. Soporta valores None para no martillear ipapi.co
# ante IPs que ya fallaron una vez.
_IP_COUNTRY_CACHE: dict[str, str | None] = {}


def _client_ip(request: Request) -> str | None:
    """Extrae la IP del cliente final. Railway forwardea la IP real en
    X-Forwarded-For (primer elemento de la lista separada por comas);
    para entornos sin proxy intermedio usamos request.client.host."""
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


_PRIVATE_IP_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                        "172.20.", "172.21.", "172.22.", "172.23.",
                        "172.24.", "172.25.", "172.26.", "172.27.",
                        "172.28.", "172.29.", "172.30.", "172.31.",
                        "192.168.", "127.", "169.254.", "::1")


async def _country_from_request(request: Request) -> str | None:
    """Resuelve el país del cliente a código ISO-3166-1 alpha-2.

    Cadena de fuentes, en orden:
    1. Header CF-IPCountry — sólo si en algún momento se proxia por Cloudflare.
       Hoy mentotrack.com NO va detrás del proxy de CF (incompatible con
       uploads > 100 MB en plan Free), pero leemos el header por si cambia.
    2. Lookup contra ipapi.co usando la IP del cliente. Gratis hasta 30k
       req/mes sin API key. Cacheado en memoria por IP para no machacar el
       endpoint con el mismo usuario."""
    # Vía CF (no debería disparar hoy, pero es barato dejarlo).
    cf = (request.headers.get("CF-IPCountry") or "").strip().upper()
    if cf and len(cf) == 2 and cf not in ("XX", "T1", "EU"):
        return cf

    ip = _client_ip(request)
    if not ip:
        return None
    # IPs privadas o loopback: no merece la pena llamar al servicio.
    if any(ip.startswith(p) for p in _PRIVATE_IP_PREFIXES):
        return None
    if ip in _IP_COUNTRY_CACHE:
        return _IP_COUNTRY_CACHE[ip]

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"https://ipapi.co/{ip}/country/")
            country = (resp.text or "").strip().upper()
            if len(country) == 2 and country.isalpha():
                _IP_COUNTRY_CACHE[ip] = country
                return country
    except Exception as e:
        print(f"[GEO] ipapi.co falló para {ip}: {e}")

    # Negative cache para no reintentar en cada request del mismo usuario.
    _IP_COUNTRY_CACHE[ip] = None
    return None


def _parse_formulario_str_to_dict(s: str) -> dict:
    """'Tech House | Casi listo | Demo | 2-5 años | Estructura | Bloqueo: ...'
    → dict para JSONB."""
    if not s:
        return {}
    parts = [p.strip() for p in str(s).split("|")]
    keys = ["genero", "fase", "objetivo", "experiencia", "dificultad_habitual", "bloqueo"]
    out = {}
    for i, p in enumerate(parts):
        if i < len(keys):
            if keys[i] == "bloqueo" and p.lower().startswith("bloqueo:"):
                p = p[8:].strip()
            out[keys[i]] = p
    return out


@app.post("/api/sheets/registro")
@limiter.limit("5/minute")
async def proxy_sheets_registro(request: Request, data: dict):
    """Persiste un análisis. Postgres primary (cutover B cerrado 2026-05-20).
    El nombre del endpoint mantiene el prefijo `/api/sheets/` por
    compatibilidad con el frontend desplegado — internamente ya solo escribe
    a Postgres."""
    email = (data.get("email") or "").strip().lower()
    nombre_proyecto = (data.get("nombre_proyecto") or "").strip()
    formulario_str = data.get("formulario", "")
    diagnostico = data.get("diagnostico", "")
    senales_json_str = data.get("senales_json", "")
    genero_custom = (data.get("genero_custom") or "").strip()
    ts_str = data.get("timestamp", "")

    # Parse timestamp (acepta ISO con/sin Z)
    try:
        ts = ts_str.rstrip("Z") + "+00:00" if ts_str.endswith("Z") else ts_str
        timestamp = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
    except Exception:
        timestamp = datetime.now(timezone.utc)

    # Parse JSONB content
    try:
        senales_dict = json.loads(senales_json_str) if senales_json_str else {}
    except Exception:
        senales_dict = {}
    formulario_dict = _parse_formulario_str_to_dict(formulario_str)

    # Vinculación a proyecto + versionado automático
    proyecto_id_str = (data.get("proyecto_id") or "").strip()
    version_etiqueta = (data.get("version_etiqueta") or "").strip()[:80] or None

    # Postgres primary
    if _pg_available() and email and "@" in email:
        try:
            from db import get_pool
            import repositories as repo
            from uuid import UUID
            pool = get_pool()
            user = await repo.get_user_by_email(pool, email)
            usuario_id = user["id"] if user else None
            proyecto_id = None
            version_num = None

            if usuario_id:
                # Modo 1: el frontend pasa proyecto_id explícito (nuevo flujo).
                if proyecto_id_str:
                    try:
                        pid = UUID(proyecto_id_str)
                        proyecto_chk = await repo.get_proyecto(pool, pid, usuario_id)
                        if proyecto_chk:
                            proyecto_id = pid
                    except (ValueError, TypeError):
                        pass
                # Modo 2: legacy — frontend pasa nombre_proyecto string. Buscamos
                # un proyecto con ese nombre exact-match o creamos uno nuevo.
                elif nombre_proyecto:
                    proyecto = await repo.get_or_create_proyecto(pool, usuario_id, nombre_proyecto)
                    proyecto_id = proyecto["id"]

                if proyecto_id:
                    version_num = await repo.next_version_num(pool, proyecto_id)

            await repo.create_analisis(
                pool,
                usuario_id=usuario_id,
                proyecto_id=proyecto_id,
                version_num=version_num,
                version_etiqueta=version_etiqueta,
                timestamp=timestamp,
                email=email,
                nombre_proyecto_legacy=(nombre_proyecto or None),
                formulario=formulario_dict,
                diagnostico=diagnostico or "",
                senales=senales_dict,
                genero_custom=(genero_custom or None),
                pais=await _country_from_request(request),
                motor_version=app.version,
            )
        except Exception as e:
            print(f"[REGISTRO] Postgres falló: {e}")

    return {"ok": True}


@app.post("/api/sheets/feedback")
@limiter.limit("10/minute")
async def proxy_sheets_feedback(request: Request, data: dict):
    """Actualiza fue_util/comentario del análisis más reciente del usuario.
    Postgres primary (cutover B cerrado 2026-05-20)."""
    email = (data.get("email") or "").strip().lower()
    fue_util = data.get("fue_util", "")
    comentario = data.get("comentario", "")

    if _pg_available() and email:
        try:
            from db import get_pool
            import repositories as repo
            pool = get_pool()
            latest = await repo.find_latest_analisis_by_email(pool, email)
            if latest:
                await repo.update_analisis_feedback(
                    pool, latest["id"],
                    fue_util=(fue_util or None),
                    comentario=(comentario or None),
                )
        except Exception as e:
            print(f"[FEEDBACK] Postgres falló: {e}")
    return {"ok": True}


@app.post("/api/sheets/feedback-real")
@limiter.limit("5/minute")
async def proxy_sheets_feedback_real(request: Request, data: dict):
    """Actualiza feedback_real (enlace a SoundCloud / Dropbox / etc.) del
    análisis más reciente. Postgres primary (cutover B cerrado 2026-05-20)."""
    email = (data.get("email") or "").strip().lower()
    enlace = (data.get("enlace") or "").strip()

    if _pg_available() and email:
        try:
            from db import get_pool
            import repositories as repo
            pool = get_pool()
            latest = await repo.find_latest_analisis_by_email(pool, email)
            if latest and enlace:
                await repo.update_analisis_feedback_real(pool, latest["id"], enlace)
        except Exception as e:
            print(f"[FEEDBACK_REAL] Postgres falló: {e}")
    return {"ok": True}


@app.post("/api/sheets/tutorial-click")
@limiter.limit("20/minute")
async def proxy_sheets_tutorial_click(request: Request):
    """Registra qué tutorial de YouTube clickó el usuario. Postgres primary
    (cutover B cerrado 2026-05-20). Parsea body manualmente para soportar
    sendBeacon, que puede no enviar Content-Type: application/json."""
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
    except Exception:
        data = {}
    email = (data.get("email") or "").strip().lower()
    tutorial_url = (data.get("tutorial_clickado") or "").strip()

    if _pg_available() and email and tutorial_url:
        try:
            from db import get_pool
            import repositories as repo
            pool = get_pool()
            latest = await repo.find_latest_analisis_by_email(pool, email)
            if latest:
                await repo.update_tutorial_clickado(pool, latest["id"], tutorial_url)
        except Exception as e:
            print(f"[TUTORIAL_CLICK] Postgres falló: {e}")
    return {"ok": True}


@app.get("/api/sheets/datos")
@limiter.limit("5/minute")
async def proxy_sheets_datos(request: Request):
    """Devuelve todos los análisis para el dashboard admin.
    Postgres primary con fallback a Sheets. Mantiene el formato legacy
    que espera el dashboard (data: [...] con claves del Sheet)."""
    admin_cookie = request.cookies.get("admin_session", "")
    if not _verify_admin_token(admin_cookie):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})

    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        rows = await repo.list_all_analisis(pool)
        return {"ok": True, "data": [_pg_row_to_legacy_format(r) for r in rows]}
    except Exception as e:
        print(f"[ADMIN/DATOS] Postgres falló: {e}")
        return JSONResponse(status_code=503, content={"error": "Error consultando DB"})


# =========================================================================
# Auth — Registro/Login con contraseña (bcrypt + Google Sheets)
# =========================================================================


def _hash_password(password: str) -> str:
    """Genera un hash bcrypt de la contraseña."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verifica una contraseña contra su hash bcrypt."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# -------------------------------------------------------------------------
# Email transaccional vía Resend (resend.com)
# -------------------------------------------------------------------------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "Mentotrack <noreply@mentotrack.com>")
# Destinatario interno (Alex) para notificaciones operativas: solicitudes
# de consultoría, casos edge, etc. Si está vacío, las notificaciones fallan
# en silencio (se loguean) — no afecta al usuario.
ADMIN_NOTIFY_EMAIL = os.environ.get("ADMIN_NOTIFY_EMAIL", "alexgn23@gmail.com")
# Base URL del frontend para construir el link de reset. En local apunta a 8000
# (donde corre uvicorn), en prod a https://www.mentotrack.com.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://www.mentotrack.com")


def _resend_disponible() -> bool:
    """Devuelve True si Resend está configurado y la lib está instalada."""
    if not RESEND_API_KEY:
        return False
    try:
        import resend  # noqa: F401
        return True
    except ImportError:
        return False


def _enviar_email_reset_password(email: str, token: str) -> bool:
    """Envía el email de reset password vía Resend. Devuelve True si OK,
    False si falló (sin lanzar excepción al caller). El caller decide
    qué mensaje devolver al usuario."""
    if not _resend_disponible():
        print("[RESET] RESEND no disponible — no se envía email")
        return False
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        link = f"{APP_BASE_URL.rstrip('/')}/reset?token={token}"
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Restablece tu contraseña</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',sans-serif;background:#0a0a0b;color:#e5e5e5;padding:40px 20px;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#141416;border:1px solid #27272a;border-radius:12px;padding:32px;">
    <h1 style="color:#fff;font-size:20px;font-weight:600;margin:0 0 16px;">Restablece tu contraseña</h1>
    <p style="color:#a1a1aa;font-size:14px;line-height:1.6;margin:0 0 24px;">
      Has solicitado restablecer la contraseña de tu cuenta de Mentotrack.
      Pulsa el botón de abajo para elegir una nueva. El enlace caduca en 1 hora.
    </p>
    <a href="{link}" style="display:inline-block;background:#8b5cf6;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:600;font-size:14px;">Elegir nueva contraseña</a>
    <p style="color:#71717a;font-size:12px;line-height:1.6;margin:24px 0 0;">
      Si no has pedido este reset, ignora este email — tu contraseña no cambiará.
      Si ves comportamiento sospechoso en tu cuenta, escríbenos a
      <a href="mailto:soporte@producciononline.com" style="color:#a78bfa;">soporte@producciononline.com</a>.
    </p>
    <p style="color:#52525b;font-size:11px;margin:24px 0 0;word-break:break-all;">
      Si el botón no funciona, copia este enlace en tu navegador:<br>
      <span style="color:#71717a;">{link}</span>
    </p>
  </div>
  <p style="color:#52525b;font-size:11px;text-align:center;margin:24px 0 0;">
    Mentotrack · Producción Online · <a href="https://www.mentotrack.com" style="color:#71717a;">mentotrack.com</a>
  </p>
</body>
</html>"""
        text = (
            f"Has solicitado restablecer tu contraseña de Mentotrack.\n\n"
            f"Abre este enlace para elegir una nueva (caduca en 1 hora):\n{link}\n\n"
            f"Si no has pedido este reset, ignora este email.\n\n"
            f"Si necesitas ayuda, escribe a soporte@producciononline.com.\n"
        )
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": email,
            "subject": "Restablece tu contraseña de Mentotrack",
            "html": html,
            "text": text,
        })
        return True
    except Exception as e:
        print(f"[RESET] Resend falló: {type(e).__name__}: {e}")
        return False


def _enviar_email_solicitud_consultoria(datos: dict) -> bool:
    """Envía a ADMIN_NOTIFY_EMAIL los datos de la solicitud de sesión 1:1.
    Lo manda con reply-to al email del usuario para que Alex pueda
    contestar directamente sin copiar el correo. Si Resend no está
    disponible, lo logueamos y devolvemos False."""
    if not _resend_disponible():
        print("[CONSULTORIA] Resend no disponible — solicitud no enviada por email")
        return False
    try:
        import resend
        resend.api_key = RESEND_API_KEY

        def _row(label: str, value: str) -> str:
            if not value:
                value = "<em style='color:#9ca3af;'>(no indicado)</em>"
            else:
                # Escape básico
                value = (value.replace('&', '&amp;')
                              .replace('<', '&lt;').replace('>', '&gt;'))
            return (
                f"<tr><td style='padding:8px 12px;color:#71717a;font-size:13px;"
                f"vertical-align:top;width:130px;'>{label}</td>"
                f"<td style='padding:8px 12px;color:#1f2937;font-size:14px;'>{value}</td></tr>"
            )

        rows_html = "".join([
            _row("Nombre", datos.get("nombre", "")),
            _row("Email", datos.get("email", "")),
            _row("Track", datos.get("soundcloud", "")),
            _row("Canción ref.", datos.get("ref_cancion", "")),
            _row("Artistas ref.", datos.get("ref_artistas", "")),
            _row("Sellos ref.", datos.get("ref_sellos", "")),
            _row("Contexto", datos.get("contexto", "")),
        ])

        html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',sans-serif;background:#f5f1ea;padding:32px 16px;margin:0;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;">
    <p style="color:#9ca3af;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;margin:0 0 8px;">Sesión 1:1 · Solicitud nueva</p>
    <h1 style="color:#1f2937;font-size:18px;font-weight:600;margin:0 0 18px;">Nueva solicitud de {datos.get("nombre", "(sin nombre)")}</h1>
    <table style="border-collapse:collapse;width:100%;">
      <tbody>{rows_html}</tbody>
    </table>
    <p style="color:#9ca3af;font-size:12px;margin:18px 0 0;">
      Responde directamente a este email para contactar con quien lo envió.
    </p>
  </div>
</body></html>"""

        text = (
            f"Nueva solicitud de sesión 1:1\n\n"
            f"Nombre: {datos.get('nombre', '')}\n"
            f"Email: {datos.get('email', '')}\n"
            f"Track: {datos.get('soundcloud', '')}\n"
            f"Canción ref.: {datos.get('ref_cancion', '') or '(no indicado)'}\n"
            f"Artistas ref.: {datos.get('ref_artistas', '') or '(no indicado)'}\n"
            f"Sellos ref.: {datos.get('ref_sellos', '') or '(no indicado)'}\n\n"
            f"Contexto:\n{datos.get('contexto', '') or '(no indicado)'}\n"
        )

        params = {
            "from": RESEND_FROM,
            "to": ADMIN_NOTIFY_EMAIL,
            "subject": f"Sesión 1:1 — Solicitud de {datos.get('nombre', '(sin nombre)')}",
            "html": html,
            "text": text,
        }
        # Reply-to al email del usuario para que Alex pueda contestar al hilo
        user_email = (datos.get("email") or "").strip()
        if user_email:
            params["reply_to"] = user_email
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"[CONSULTORIA] Resend falló: {type(e).__name__}: {e}")
        return False


async def _sheets_get(params: dict) -> dict:
    """Envía operaciones al Apps Script via POST (datos sensibles en body, no en URL).
    Devuelve la respuesta JSON del Apps Script.
    Si hay error de conexión, devuelve {"_connection_error": "descripción"}
    para distinguirlo de respuestas válidas del script que contengan "error"."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEETS_WEBHOOK, json=params, timeout=15)
            data = resp.json()
            # Si el Apps Script devuelve un array (no actualizado), es error de config
            if isinstance(data, list):
                print(f"[SHEETS] Apps Script devolvió array en vez de objeto — ¿falta actualizar el script?")
                return {"_connection_error": "Apps Script no actualizado"}
            return data
    except Exception as e:
        print(f"[SHEETS] Error: {e}")
        return {"_connection_error": str(e)}


# -------------------------------------------------------------------------
# Helpers de Postgres con fallback a Sheets
# -------------------------------------------------------------------------

def _pg_available() -> bool:
    """True si DATABASE_URL está configurada (en producción siempre, en local
    solo si el dev lo ha pasado explícitamente)."""
    return bool(os.environ.get("DATABASE_URL"))


def _pg_row_to_legacy_format(row: dict) -> dict:
    """Convierte una fila de la tabla analisis al mismo formato que devuelve
    el Apps Script (action=get_all), para que el frontend no note el cambio.

    Frontend espera claves planas con los nombres del Sheet:
      timestamp, email, nombre_proyecto, formulario (string), diagnostico,
      senales_json (string), fue_util, comentario, feedback_real,
      revision_alex, nota_alex, tutoriales_sugeridos, tutorial_clickado,
      genero_custom.
    """
    formulario = row.get("formulario") or {}
    senales = row.get("senales") or {}
    # formulario en Postgres es dict (JSONB), pero el frontend lo recibe como
    # string "Género | Fase | Objetivo | Experiencia | Dificultad | Bloqueo: ...".
    if isinstance(formulario, str):
        formulario_str = formulario
    else:
        partes = [
            formulario.get("genero", ""),
            formulario.get("fase", ""),
            formulario.get("objetivo", ""),
            formulario.get("experiencia", ""),
            formulario.get("dificultad_habitual", ""),
        ]
        bloqueo = formulario.get("bloqueo", "")
        if bloqueo:
            partes.append(f"Bloqueo: {bloqueo}")
        formulario_str = " | ".join(p for p in partes if p)
    # senales en Postgres es dict (JSONB), el frontend espera el JSON serializado
    if isinstance(senales, str):
        senales_str = senales
    else:
        senales_str = json.dumps(senales, ensure_ascii=False)
    ts = row.get("timestamp")
    # tutoriales_sugeridos: el frontend lo trata como string. Si viene como
    # dict/list desde JSONB lo serializamos.
    tut_sug = row.get("tutoriales_sugeridos")
    if isinstance(tut_sug, (dict, list)):
        tut_sug = json.dumps(tut_sug, ensure_ascii=False)
    elif tut_sug is None:
        tut_sug = ""
    nota_alex = row.get("nota_alex")
    rid = row.get("id")
    pid = row.get("proyecto_id")
    return {
        # IDs (sólo presentes en filas Postgres; ausentes en filas Sheets legacy)
        "id": str(rid) if rid is not None else "",
        "proyecto_id": str(pid) if pid is not None else "",
        "version_num": row.get("version_num"),
        "version_etiqueta": row.get("version_etiqueta") or "",
        "nombre_proyecto_legacy": row.get("nombre_proyecto_legacy") or "",
        "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else (ts or ""),
        "email": row.get("email") or "",
        "nombre_proyecto": row.get("nombre_proyecto_legacy") or "",
        "formulario": formulario_str,
        "diagnostico": row.get("diagnostico") or "",
        "senales_json": senales_str,
        "fue_util": row.get("fue_util") or "",
        "comentario": row.get("comentario") or "",
        "feedback_real": row.get("feedback_real") or "",
        "revision_alex": row.get("revision_alex") or "",
        "nota_alex": float(nota_alex) if nota_alex is not None else "",
        "tutoriales_sugeridos": tut_sug or "",
        "tutorial_clickado": row.get("tutorial_clickado") or "",
        "pais": (row.get("pais") or "").strip() or "",
        "genero_custom": row.get("genero_custom") or "",
    }


async def _obtener_historial(email: str) -> list:
    """Devuelve historial del usuario desde Postgres en el formato legacy
    esperado por el frontend (cutover B cerrado 2026-05-20)."""
    if not _pg_available():
        return []
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return []
        rows = await repo.list_analisis_usuario(pool, user["id"])
        return [_pg_row_to_legacy_format(r) for r in rows]
    except Exception as e:
        print(f"[HISTORIAL] Postgres falló: {e}")
        return []


async def _get_user_for_auth(email: str) -> dict | None:
    """Busca usuario para autenticación en Postgres (cutover B cerrado 2026-05-20).
    Devuelve dict con keys: found, email, password_hash, username (formato
    compatible con el flujo legacy)."""
    if not _pg_available():
        return None
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        u = await repo.get_user_by_email(pool, email)
        if u:
            return {
                "found": True,
                "email": u["email"],
                "password_hash": u["password_hash"],
                "username": u.get("username") or "",
                "_from": "postgres",
            }
    except Exception as e:
        print(f"[AUTH] Postgres get_user falló: {e}")
    return None


_USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def _valid_username(u: str) -> bool:
    """Valida formato de username (3-20 chars, letras/números/_/-)."""
    return bool(u and _USERNAME_REGEX.match(u))


def _looks_like_email(s: str) -> bool:
    return "@" in s and "." in s.split("@")[-1]


# -------------------------------------------------------------------------
# /api/auth/login — login con email O username + password
# -------------------------------------------------------------------------
@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def auth_login(request: Request, data: dict):
    identifier = (data.get("identifier") or data.get("email") or "").strip()
    password = (data.get("password") or "").strip()

    if not identifier:
        return JSONResponse(status_code=400, content={"error": "Email o nombre de usuario requerido"})
    if len(password) < 8:
        return JSONResponse(status_code=400, content={"error": "La contraseña debe tener al menos 8 caracteres"})

    # Normalizar identifier
    is_email = _looks_like_email(identifier)
    if is_email:
        identifier = identifier.lower()
    else:
        identifier = identifier.lstrip("@")
        if not _valid_username(identifier):
            return JSONResponse(status_code=400, content={"error": "Nombre de usuario inválido"})

    # Postgres es la única fuente desde el cierre del cutover B (2026-05-27).
    # Los usuarios residuales con password_hash = '__MIGRATED__' no pueden
    # autenticarse y caen en "credenciales incorrectas" — recuperan via
    # /api/auth/forgot (escribiendo a soporte para reset manual).
    user_data = None
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "No se pudo conectar con la base de datos."})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        u = await repo.get_user_by_identifier(pool, identifier)
        if u:
            user_data = {
                "found": True,
                "email": u["email"],
                "password_hash": u["password_hash"],
                "username": u.get("username") or "",
            }
    except Exception as e:
        print(f"[LOGIN] Postgres falló: {e}")
        return JSONResponse(status_code=503, content={"error": "No se pudo conectar con la base de datos."})

    if not user_data or not user_data.get("found"):
        return JSONResponse(status_code=401, content={"error": "Credenciales incorrectas"})
    if not _verify_password(password, user_data.get("password_hash", "")):
        return JSONResponse(status_code=401, content={"error": "Credenciales incorrectas"})

    email = user_data.get("email", "").strip().lower()
    username = (user_data.get("username") or "").strip()
    historial = await _obtener_historial(email)
    token = _create_token(email)
    return {
        "ok": True,
        "email": email,
        "username": username,
        "token": token,
        "historial": historial,
        "needs_username": not bool(username),
    }


# -------------------------------------------------------------------------
# /api/auth/register — registro con email + username + password
# -------------------------------------------------------------------------
@app.post("/api/auth/register")
@limiter.limit("3/minute")
async def auth_register(request: Request, data: dict):
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip().lstrip("@")
    password = (data.get("password") or "").strip()

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Email inválido"})
    if not _valid_username(username):
        return JSONResponse(status_code=400, content={
            "error": "Nombre de usuario inválido. Usa 3-20 caracteres: letras, números, guion bajo o guion."
        })
    if len(password) < 8:
        return JSONResponse(status_code=400, content={"error": "La contraseña debe tener al menos 8 caracteres"})

    hashed = _hash_password(password)

    # Postgres primary
    if _pg_available():
        try:
            from db import get_pool
            import repositories as repo
            pool = get_pool()
            # Comprobar email duplicado
            existing_email = await repo.get_user_by_email(pool, email)
            if existing_email and existing_email["password_hash"] != "__MIGRATED__":
                return JSONResponse(status_code=409, content={"error": "Ese email ya está registrado."})
            # Comprobar username duplicado
            existing_username = await repo.get_user_by_username(pool, username)
            if existing_username and (not existing_email or existing_username["id"] != existing_email["id"]):
                return JSONResponse(status_code=409, content={"error": "Ese nombre de usuario ya está cogido."})
            if existing_email and existing_email["password_hash"] == "__MIGRATED__":
                # Usuario migrado completando registro: actualizamos hash y username
                await repo.update_user_password(pool, existing_email["id"], hashed)
                if username:
                    await repo.update_user_username(pool, existing_email["id"], username)
            else:
                await repo.create_user(pool, email, hashed, username)
        except Exception as e:
            print(f"[REGISTER] Postgres falló: {e}")
            return JSONResponse(status_code=503, content={"error": "No se pudo conectar con la base de datos."})

    token = _create_token(email)
    return {
        "ok": True,
        "email": email,
        "username": username,
        "token": token,
        "historial": [],
        "nuevo": True,
    }


# -------------------------------------------------------------------------
# /api/auth/check_username — comprueba disponibilidad
# -------------------------------------------------------------------------
@app.post("/api/auth/check_username")
@limiter.limit("20/minute")
async def auth_check_username(request: Request, data: dict):
    username = (data.get("username") or "").strip().lstrip("@")
    if not _valid_username(username):
        return {"ok": False, "available": False, "error": "Formato inválido"}

    if not _pg_available():
        return {"ok": False, "available": False, "error": "Servicio no disponible"}
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        available = await repo.is_username_available(pool, username)
        return {"ok": True, "available": bool(available)}
    except Exception as e:
        print(f"[CHECK_USERNAME] Postgres falló: {e}")
        return {"ok": False, "available": False, "error": "Error de conexión"}


# -------------------------------------------------------------------------
# /api/auth/set_username — JWT required (migración de usuarios viejos)
# -------------------------------------------------------------------------
@app.post("/api/auth/set_username")
@limiter.limit("5/minute")
async def auth_set_username(request: Request, data: dict):
    token = _get_token_from_request(request)
    if not token:
        return JSONResponse(status_code=401, content={"error": "Token requerido"})
    email = _verify_token(token)
    if not email:
        return JSONResponse(status_code=401, content={"error": "Token inválido o expirado"})

    username = (data.get("username") or "").strip().lstrip("@")
    if not _valid_username(username):
        return JSONResponse(status_code=400, content={
            "error": "Nombre de usuario inválido. Usa 3-20 caracteres: letras, números, guion bajo o guion."
        })

    # Postgres primary
    if _pg_available():
        try:
            from db import get_pool
            import repositories as repo
            pool = get_pool()
            user = await repo.get_user_by_email(pool, email)
            if not user:
                # Fallback: usuario no está en Postgres todavía. Caer a Sheets.
                pass
            else:
                # Comprobar disponibilidad del username
                otro = await repo.get_user_by_username(pool, username)
                if otro and otro["id"] != user["id"]:
                    return JSONResponse(status_code=409, content={"error": "Ese nombre de usuario ya está cogido."})
                await repo.update_user_username(pool, user["id"], username)
                return {"ok": True, "username": username}
        except Exception as e:
            print(f"[SET_USERNAME] Postgres falló: {e}")
            return JSONResponse(status_code=503, content={"error": "No se pudo conectar con la base de datos."})

    return JSONResponse(status_code=503, content={"error": "Servicio no disponible."})


# -------------------------------------------------------------------------
# /api/auth/forgot — genera token + manda email vía Resend
# -------------------------------------------------------------------------
_MENSAJE_FORGOT_MANUAL = (
    "Para recuperar el acceso, escríbenos a soporte@producciononline.com "
    "indicando el email con el que te registraste. Te ayudaremos manualmente."
)
_MENSAJE_FORGOT_OK = (
    "Si ese email corresponde a una cuenta, te hemos enviado un enlace para "
    "elegir nueva contraseña. Revisa tu bandeja (y la carpeta de spam). El "
    "enlace caduca en 1 hora."
)


@app.post("/api/auth/forgot")
@limiter.limit("3/minute")
async def auth_forgot(request: Request, data: dict):
    """Pide reset de contraseña. Si Resend está configurado, genera token
    de un solo uso (1h de vida), invalida tokens activos previos del usuario
    y envía email con el enlace de reset. Si Resend no está configurado,
    fallback al mensaje manual (contactar soporte).

    Siempre devuelve OK aunque el email no exista — para no leakear si una
    cuenta está registrada o no."""
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Email inválido"})

    # Si no hay Resend configurado, fallback al mensaje manual (sin tocar DB)
    if not _resend_disponible():
        return {"ok": True, "message": _MENSAJE_FORGOT_MANUAL,
                "contact_email": "soporte@producciononline.com"}

    if not _pg_available():
        return JSONResponse(status_code=503, content={
            "error": "No se pudo conectar con la base de datos. Inténtalo en unos segundos."
        })

    # Buscar usuario y generar token solo si existe — pero respondemos lo
    # mismo en ambos casos para no leakear existencia de cuentas.
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if user:
            # Anular cualquier token activo previo del mismo usuario antes
            # de generar uno nuevo (evita acumulación si pide varios resets).
            await repo.invalidate_active_tokens_for_user(pool, user["id"])
            token = secrets.token_urlsafe(48)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            await repo.create_password_reset_token(pool, user["id"], token, expires_at)
            _enviar_email_reset_password(user["email"], token)
            # Aunque falle el envío del email, respondemos OK al usuario
            # (queda registrado en logs). El usuario puede pedir otro reset.
    except Exception as e:
        print(f"[FORGOT] error: {type(e).__name__}: {e}")
        # Aún así, respondemos OK para no leakear

    return {"ok": True, "message": _MENSAJE_FORGOT_OK}


# -------------------------------------------------------------------------
# /api/auth/reset — consume token y actualiza contraseña
# -------------------------------------------------------------------------
@app.post("/api/auth/reset")
@limiter.limit("5/minute")
async def auth_reset(request: Request, data: dict):
    """Recibe { token, password }. Valida el token (no usado, no expirado),
    actualiza el hash bcrypt del usuario en Postgres, marca el token como
    usado. Devuelve un JWT al usuario para login automático."""
    token = (data.get("token") or "").strip()
    password = (data.get("password") or "").strip()

    if not token:
        return JSONResponse(status_code=400, content={"error": "Token requerido"})
    if len(password) < 8:
        return JSONResponse(status_code=400, content={
            "error": "La contraseña debe tener al menos 8 caracteres"
        })

    if not _pg_available():
        return JSONResponse(status_code=503, content={
            "error": "No se pudo conectar con la base de datos."
        })

    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        token_row = await repo.get_password_reset_token(pool, token)
        if not token_row:
            return JSONResponse(status_code=400, content={
                "error": "Este enlace ya no es válido (caducado o usado). Pide otro reset."
            })

        # Actualizar hash y marcar token usado en operaciones separadas;
        # si el update_user_password falla, el token sigue siendo válido
        # para reintentar.
        new_hash = _hash_password(password)
        await repo.update_user_password(pool, token_row["usuario_id"], new_hash)
        await repo.mark_password_reset_token_used(pool, token_row["id"])
    except Exception as e:
        print(f"[RESET] error: {type(e).__name__}: {e}")
        return JSONResponse(status_code=503, content={
            "error": "Error al cambiar la contraseña. Inténtalo de nuevo."
        })

    # Login automático tras reset
    email = token_row["email"]
    historial = await _obtener_historial(email)
    jwt_token = _create_token(email)
    return {"ok": True, "email": email, "token": jwt_token, "historial": historial}


async def _heal_postgres_user_password(email: str, real_hash: str) -> None:
    """Si Postgres tiene un hash placeholder, sobrescribirlo con el hash real
    obtenido de Sheets. Self-healing progresivo de la migración inicial."""
    if not _pg_available():
        return
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        u = await repo.get_user_by_email(pool, email)
        if u:
            await repo.update_user_password(pool, u["id"], real_hash)
    except Exception as e:
        print(f"[AUTH] heal_postgres falló: {e}")


async def _create_user(email: str, password_hash: str) -> tuple[bool, str | None]:
    """Crea usuario en Postgres. Devuelve (ok, error_msg). Si existe un
    placeholder '__MIGRATED__' para ese email (residual del cutover B),
    actualiza el hash en lugar de fallar — el usuario está estableciendo
    su contraseña por primera vez."""
    email = (email or "").strip().lower()
    if not _pg_available():
        return False, "No se pudo conectar con la base de datos."
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        existing = await repo.get_user_by_email(pool, email)
        if existing and existing["password_hash"] != "__MIGRATED__":
            return False, "El usuario ya existe"
        if existing and existing["password_hash"] == "__MIGRATED__":
            await repo.update_user_password(pool, existing["id"], password_hash)
        else:
            await repo.create_user(pool, email, password_hash)
    except Exception as e:
        print(f"[AUTH] Postgres create_user falló: {e}")
        return False, "No se pudo crear el usuario."
    return True, None


@app.post("/api/auth/acceder")
@limiter.limit("5/minute")
async def acceder(request: Request, data: dict):
    """
    Endpoint unificado login/registro.
    - Postgres primary con fallback a Sheets para usuarios migrados.
    - Cuando un usuario migrado autentica correctamente vía Sheets, su hash
      real se copia a Postgres (self-healing progresivo).
    """
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Email inválido"})
    if len(password) < 8:
        return JSONResponse(status_code=400, content={"error": "La contraseña debe tener al menos 8 caracteres"})

    user_data = await _get_user_for_auth(email)

    if user_data:
        # Los usuarios residuales con hash '__MIGRATED__' (sin hash real en
        # Postgres tras el cutover B) fallan aquí: bcrypt no puede verificar
        # contra ese placeholder. Recuperan via /api/auth/forgot (manual).
        if not _verify_password(password, user_data.get("password_hash", "")):
            return JSONResponse(status_code=401, content={"error": "Contraseña incorrecta"})
        historial = await _obtener_historial(email)
        token = _create_token(email)
        return {"ok": True, "email": email, "token": token, "historial": historial, "nuevo": False}

    # Usuario nuevo → registrar en Postgres
    hashed = _hash_password(password)
    ok, err = await _create_user(email, hashed)
    if not ok and err == "El usuario ya existe":
        return JSONResponse(status_code=409, content={"error": "El email ya está registrado. Prueba con tu contraseña."})
    historial = await _obtener_historial(email)
    token = _create_token(email)
    return {"ok": True, "email": email, "token": token, "historial": historial, "nuevo": True}


@app.post("/api/auth/historial")
@limiter.limit("10/minute")
async def obtener_historial(request: Request, data: dict):
    """Refresca historial de un usuario autenticado (requiere JWT token)."""
    token = _get_token_from_request(request)
    if not token:
        return JSONResponse(status_code=401, content={"error": "Token requerido"})

    token_email = _verify_token(token)
    if not token_email:
        return JSONResponse(status_code=401, content={"error": "Token inválido o expirado"})

    # El email del token debe coincidir con el solicitado
    email = (data.get("email") or "").strip().lower()
    if email and email != token_email:
        return JSONResponse(status_code=403, content={"error": "No autorizado"})

    historial = await _obtener_historial(token_email)
    return {"ok": True, "historial": historial}


# =========================================================================
# Proyectos — agrupación de análisis por canción
# =========================================================================

def _require_auth_user(request: Request) -> tuple[str | None, JSONResponse | None]:
    """Devuelve (email_token, None) si todo OK, o (None, JSONResponse) con error.
    Endpoints de proyectos requieren login obligatorio."""
    token = _get_token_from_request(request)
    if not token:
        return None, JSONResponse(status_code=401, content={"error": "Token requerido"})
    email = _verify_token(token)
    if not email:
        return None, JSONResponse(status_code=401, content={"error": "Token inválido o expirado"})
    return email, None


def _optional_auth_user(request: Request) -> str | None:
    """Email del usuario si trae un token válido, None si no. Para endpoints
    de lectura pública que enriquecen la respuesta cuando hay sesión (p.ej.
    marcar qué comentarios son tuyos / si eres dueño del post)."""
    token = _get_token_from_request(request)
    if not token:
        return None
    return _verify_token(token)


async def _get_usuario_id_from_email(email: str):
    """Resuelve usuario_id desde un email. Requiere Postgres disponible."""
    from db import get_pool
    import repositories as repo
    pool = get_pool()
    user = await repo.get_user_by_email(pool, email)
    return (user["id"] if user else None), pool


def _serialize_proyecto(p: dict) -> dict:
    return {
        "id": str(p["id"]),
        "nombre": p["nombre"],
        "fecha_creacion": p["fecha_creacion"].isoformat() if p.get("fecha_creacion") else None,
        "archivado": bool(p.get("archivado", False)),
        "n_versiones": int(p.get("n_versiones", 0)) if "n_versiones" in p else None,
        "fecha_ultima_version": (
            p["fecha_ultima_version"].isoformat()
            if p.get("fecha_ultima_version") else None
        ),
    }


@app.get("/api/proyectos")
@limiter.limit("30/minute")
async def get_proyectos(request: Request):
    """Lista los proyectos del usuario logueado con resumen mínimo
    (id, nombre, n_versiones, fecha de última versión, archivado).
    Soporta ?archivados=1 para incluir los archivados."""
    email, err = _require_auth_user(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return {"proyectos": []}
        include_archivados = request.query_params.get("archivados") in ("1", "true")
        rows = await repo.list_proyectos_con_resumen(pool, user["id"], include_archivados)
        return {"proyectos": [_serialize_proyecto(p) for p in rows]}
    except Exception as e:
        print(f"[PROYECTOS GET] {e}")
        return JSONResponse(status_code=500, content={"error": "Error obteniendo proyectos"})


@app.post("/api/proyectos")
@limiter.limit("10/minute")
async def post_proyecto(request: Request, data: dict):
    """Crea un proyecto nuevo. Body: {nombre}.
    Si ya existe uno con el mismo nombre (case-insensitive), devuelve el existente."""
    email, err = _require_auth_user(request)
    if err:
        return err
    nombre = (data.get("nombre") or "").strip()[:120]
    if not nombre:
        return JSONResponse(status_code=400, content={"error": "Nombre requerido"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        proyecto = await repo.get_or_create_proyecto(pool, user["id"], nombre)
        return {"ok": True, "proyecto": _serialize_proyecto(proyecto)}
    except Exception as e:
        print(f"[PROYECTOS POST] {e}")
        return JSONResponse(status_code=500, content={"error": "Error creando proyecto"})


@app.get("/api/proyectos/{proyecto_id}")
@limiter.limit("30/minute")
async def get_proyecto_detalle(request: Request, proyecto_id: str):
    """Detalle de un proyecto + sus versiones (análisis) ordenadas."""
    email, err = _require_auth_user(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from uuid import UUID
        pid = UUID(proyecto_id)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "ID inválido"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        proyecto = await repo.get_proyecto(pool, pid, user["id"])
        if not proyecto:
            return JSONResponse(status_code=404, content={"error": "Proyecto no encontrado"})
        versiones = await repo.list_analisis_proyecto(pool, pid)
        # Serializar versiones en formato accesible al frontend
        versiones_out = []
        for v in versiones:
            versiones_out.append({
                "id": str(v["id"]),
                "version_num": v.get("version_num"),
                "version_etiqueta": v.get("version_etiqueta") or "",
                "timestamp": v["timestamp"].isoformat() if v.get("timestamp") else None,
                "formulario": v.get("formulario") or {},
                "diagnostico": v.get("diagnostico") or "",
                "senales": v.get("senales") or {},
                "fue_util": v.get("fue_util") or "",
                "comentario": v.get("comentario") or "",
                "feedback_real": v.get("feedback_real") or "",
                "genero_custom": v.get("genero_custom") or "",
            })
        return {
            "proyecto": _serialize_proyecto(proyecto),
            "versiones": versiones_out,
        }
    except Exception as e:
        print(f"[PROYECTO DETALLE] {e}")
        return JSONResponse(status_code=500, content={"error": "Error obteniendo proyecto"})


@app.post("/api/proyectos/{proyecto_id}/archivar")
@limiter.limit("10/minute")
async def post_archivar_proyecto(request: Request, proyecto_id: str, data: dict):
    """Archiva o desarchiva un proyecto. Body opcional: {archivar: true/false}.
    Por defecto archiva (true)."""
    email, err = _require_auth_user(request)
    if err:
        return err
    try:
        from uuid import UUID
        pid = UUID(proyecto_id)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "ID inválido"})
    archivar = bool(data.get("archivar", True))
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        ok = await repo.archivar_proyecto(pool, pid, user["id"], archivar)
        if not ok:
            return JSONResponse(status_code=404, content={"error": "Proyecto no encontrado"})
        return {"ok": True, "archivado": archivar}
    except Exception as e:
        print(f"[PROYECTOS ARCHIVAR] {e}")
        return JSONResponse(status_code=500, content={"error": "Error archivando proyecto"})


@app.post("/api/proyectos/{proyecto_id}/renombrar")
@limiter.limit("10/minute")
async def post_renombrar_proyecto(request: Request, proyecto_id: str, data: dict):
    """Renombra un proyecto. Body: {nombre}."""
    email, err = _require_auth_user(request)
    if err:
        return err
    nuevo = (data.get("nombre") or "").strip()[:120]
    if not nuevo:
        return JSONResponse(status_code=400, content={"error": "Nombre requerido"})
    try:
        from uuid import UUID
        pid = UUID(proyecto_id)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "ID inválido"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        ok = await repo.renombrar_proyecto(pool, pid, user["id"], nuevo)
        if not ok:
            return JSONResponse(status_code=404, content={"error": "Proyecto no encontrado"})
        return {"ok": True, "nombre": nuevo}
    except Exception as e:
        print(f"[PROYECTOS RENOMBRAR] {e}")
        return JSONResponse(status_code=500, content={"error": "Error renombrando proyecto"})


@app.get("/api/analisis-sueltos")
@limiter.limit("30/minute")
async def get_analisis_sueltos(request: Request):
    """Lista los análisis del usuario sin proyecto asignado, para reasignar."""
    email, err = _require_auth_user(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return {"analisis": []}
        rows = await repo.list_analisis_sueltos_usuario(pool, user["id"])
        out = []
        for a in rows:
            out.append({
                "id": str(a["id"]),
                "timestamp": a["timestamp"].isoformat() if a.get("timestamp") else None,
                "nombre_proyecto_legacy": a.get("nombre_proyecto_legacy") or "",
                "diagnostico": (a.get("diagnostico") or "")[:300],  # truncado para listado
            })
        return {"analisis": out}
    except Exception as e:
        print(f"[ANALISIS SUELTOS] {e}")
        return JSONResponse(status_code=500, content={"error": "Error obteniendo análisis"})


@app.post("/api/analisis/{analisis_id}/asignar-proyecto")
@limiter.limit("10/minute")
async def post_asignar_analisis(request: Request, analisis_id: str, data: dict):
    """Asigna un análisis suelto a un proyecto. Body: {proyecto_id}.
    Calcula version_num automático."""
    email, err = _require_auth_user(request)
    if err:
        return err
    proyecto_id_str = data.get("proyecto_id", "")
    try:
        from uuid import UUID
        aid = UUID(analisis_id)
        pid = UUID(proyecto_id_str)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "ID inválido"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        ok = await repo.asignar_analisis_a_proyecto(pool, aid, pid, user["id"])
        if not ok:
            return JSONResponse(status_code=404, content={"error": "Análisis o proyecto no encontrado"})
        return {"ok": True}
    except Exception as e:
        print(f"[ASIGNAR ANALISIS] {e}")
        return JSONResponse(status_code=500, content={"error": "Error asignando análisis"})


@app.post("/api/analisis/{analisis_id}/etiqueta")
@limiter.limit("10/minute")
async def post_etiqueta_version(request: Request, analisis_id: str, data: dict):
    """Renombra la etiqueta de una versión (campo version_etiqueta).
    Body: {etiqueta}. Pasa vacío para borrar la etiqueta."""
    email, err = _require_auth_user(request)
    if err:
        return err
    etiqueta = (data.get("etiqueta") or "").strip()[:80]
    try:
        from uuid import UUID
        aid = UUID(analisis_id)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "ID inválido"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        user = await repo.get_user_by_email(pool, email)
        if not user:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        ok = await repo.update_version_etiqueta(pool, aid, user["id"], etiqueta)
        if not ok:
            return JSONResponse(status_code=404, content={"error": "Análisis no encontrado"})
        return {"ok": True, "etiqueta": etiqueta}
    except Exception as e:
        print(f"[ETIQUETA VERSION] {e}")
        return JSONResponse(status_code=500, content={"error": "Error actualizando etiqueta"})


# =========================================================================
# Ideas — sistema de votación de ideas de usuarios
# =========================================================================

@app.get("/api/ideas")
@limiter.limit("30/minute")
async def get_ideas(request: Request):
    """Obtiene todas las ideas ordenadas por votos. Postgres primary,
    Sheets fallback si Postgres está caído."""
    if _pg_available():
        try:
            from db import get_pool
            import repositories as repo
            pool = get_pool()
            rows = await repo.list_ideas(pool)
            ideas = [{
                "id": str(r["id"]),
                "nombre": r.get("nombre") or "",
                "titulo": r.get("titulo") or "",
                "descripcion": r.get("descripcion") or "",
                "fecha": r["fecha"].strftime("%d %b %Y") if r.get("fecha") else "",
                "votos": int(r.get("votos") or 0),
            } for r in rows]
            return {"ideas": ideas}
        except Exception as e:
            print(f"[IDEAS GET] Postgres falló: {e}")
            return JSONResponse(status_code=503, content={"error": "Error de conexión"})
    return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})


@app.post("/api/ideas")
@limiter.limit("5/minute")
async def create_idea(request: Request, data: dict):
    """Crea una nueva idea (cutover B cerrado 2026-05-20, solo Postgres)."""
    nombre = (data.get("nombre") or "").strip()
    titulo = (data.get("titulo") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()

    if not nombre or not titulo or not descripcion:
        return JSONResponse(status_code=400, content={"error": "Todos los campos son obligatorios"})
    if len(titulo) > 100:
        return JSONResponse(status_code=400, content={"error": "El título no puede superar 100 caracteres"})
    if len(descripcion) > 500:
        return JSONResponse(status_code=400, content={"error": "La descripción no puede superar 500 caracteres"})

    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        row = await repo.create_idea(pool, nombre=nombre, titulo=titulo, descripcion=descripcion)
        return {"ok": True, "id": str(row["id"])}
    except Exception as e:
        print(f"[IDEAS CREATE] Postgres falló: {e}")
        return JSONResponse(status_code=503, content={"error": "No se pudo guardar la idea"})


@app.post("/api/ideas/{idea_id}/vote")
@limiter.limit("20/minute")
async def vote_idea(request: Request, idea_id: str, data: dict):
    """Vota una idea. Solo se aceptan UUIDs ahora (cutover B cerrado 2026-05-20).
    Los IDs cortos legacy de Sheets ya no se procesan; en su día se migraron."""
    delta = data.get("delta")
    if delta is None:
        voto = data.get("voto", "")
        if voto not in ("up", "down"):
            return JSONResponse(status_code=400, content={"error": "Voto debe ser 'up' o 'down'"})
        delta = 1 if voto == "up" else -1
    try:
        delta = max(-2, min(2, int(delta)))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "Delta inválido"})

    try:
        from uuid import UUID as _UUID
        idea_uuid = _UUID(idea_id)
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"error": "ID de idea inválido"})

    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        new_votos = await repo.vote_idea(pool, idea_uuid, delta)
        if new_votos is not None:
            return {"ok": True, "votos": new_votos}
        return JSONResponse(status_code=404, content={"error": "Idea no encontrada"})
    except Exception as e:
        print(f"[IDEAS VOTE] Postgres falló: {e}")
        return JSONResponse(status_code=503, content={"error": "Error de conexión"})


# Ruta para servir la página de ideas
@app.get("/ideas")
def serve_ideas():
    ideas_path = FRONTEND_DIR / "ideas.html"
    if not ideas_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(ideas_path, headers={"Cache-Control": "no-cache"})


@app.get("/comunidad")
def serve_comunidad():
    page = FRONTEND_DIR / "comunidad.html"
    if not page.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


# =========================================================================
# Calibración — Alex etiqueta análisis con feedback_real para calibrar el motor
# =========================================================================

# Email canónico del único admin actual. Si el día de mañana hay multi-admin
# se reemplaza por un mapping cookie → email.
_ADMIN_EMAIL_CANONICO = "alex@producciononline.com"


def _admin_email_from_cookie(request: Request):
    """Devuelve el email del admin si la cookie es válida, None si no."""
    cookie = request.cookies.get("admin_session", "")
    if not _verify_admin_token(cookie):
        return None
    return _ADMIN_EMAIL_CANONICO


# Cache en memoria de URLs cortas → canónicas. Se llena al primer acceso al
# endpoint /api/calibrar/tracks y persiste hasta que el contenedor reinicia.
_SC_RESOLVED_CACHE: dict[str, str] = {}


async def _resolver_url_audio(url: str) -> str:
    """Convierte URLs cortas de SoundCloud (on.soundcloud.com/XYZ) a su forma
    canónica, que es la que entiende el widget oficial. También limpia los
    tracking params (?si=…, ?utm_*). Si no es SoundCloud o falla la
    resolución, devuelve la URL original."""
    if not url:
        return ""
    if url in _SC_RESOLVED_CACHE:
        return _SC_RESOLVED_CACHE[url]

    resolved = url
    try:
        if url.startswith("https://on.soundcloud.com/"):
            async with httpx.AsyncClient(follow_redirects=False, timeout=3.0) as client:
                resp = await client.head(url)
                location = resp.headers.get("location") or ""
                if "soundcloud.com/" in location:
                    resolved = location.split("?", 1)[0]
        elif "soundcloud.com/" in url:
            # Strip tracking params para SC normales
            resolved = url.split("?", 1)[0]
    except Exception as e:
        print(f"[CALIBRAR] resolución de URL falló para {url}: {e}")
        resolved = url

    _SC_RESOLVED_CACHE[url] = resolved
    return resolved


def _serializar_track_calibracion(row: dict) -> dict:
    """Serializa una fila de list_analisis_con_feedback_real a JSON."""
    ts = row.get("timestamp")
    fecha_etiqueta = row.get("fecha_etiqueta")
    return {
        "id": str(row["id"]),
        "timestamp": ts.isoformat() if ts else None,
        "email": row.get("email"),
        "nombre_proyecto_legacy": row.get("nombre_proyecto_legacy"),
        "formulario": row.get("formulario") or {},
        "diagnostico": row.get("diagnostico") or "",
        "senales": row.get("senales") or {},
        "feedback_real": row.get("feedback_real") or "",
        "feedback_real_resuelto": row.get("feedback_real_resuelto") or row.get("feedback_real") or "",
        "genero_custom": row.get("genero_custom"),
        "proyecto_id": str(row["proyecto_id"]) if row.get("proyecto_id") else None,
        "version_num": row.get("version_num"),
        "etiqueta": (
            {
                "id": str(row["etiqueta_id"]),
                "veredicto": row.get("veredicto"),
                "comentario": row.get("comentario"),
                "descartado": bool(row.get("descartado")),
                "fecha": fecha_etiqueta.isoformat() if fecha_etiqueta else None,
            }
            if row.get("etiqueta_id")
            else None
        ),
    }


# Stopwords ES + EN básicas para análisis de palabras frecuentes en comentarios.
_STOPWORDS_CALIBRAR = {
    # ES
    "para","como","pero","esta","este","esto","esos","esas","muy","más","mas","sin",
    "sobre","entre","cuando","donde","porque","aunque","desde","hasta","mientras",
    "todo","toda","todos","todas","otro","otra","otros","otras","cada","algún","alguna",
    "algunos","algunas","mucho","mucha","muchos","muchas","poco","poca","pocos","pocas",
    "siempre","nunca","tambien","también","solo","sólo","mismo","misma","mismos","mismas",
    "puede","pueden","tiene","tienen","hace","hacer","hecho","hace","tan","tanto",
    "según","aquí","ahí","allí","ahora","luego","antes","despues","después",
    "hola","creo","veo","oigo","suena","track","tema","mezcla","master","máster","mix",
    # EN
    "the","and","with","this","that","from","into","over","under","just","very",
    "have","has","had","not","but","for","you","your","its","not",
}


def _palabras_significativas(texto: str) -> list[str]:
    """Extrae palabras de un comentario, en minúsculas, sin stopwords, len>=4."""
    if not texto:
        return []
    # Sustituye signos por espacios para no juntar palabras
    limpio = re.sub(r"[^a-záéíóúñü0-9\s-]", " ", texto.lower())
    return [
        w for w in limpio.split()
        if len(w) >= 4 and w not in _STOPWORDS_CALIBRAR
    ]


def _color_motor_desde_diagnostico(diagnostico: str) -> str:
    """Mapea el estado libre del motor a verde/amarillo/rojo. Heurístico:
    listo/lista → verde; casi/pendiente → amarillo; iteración/construcción/
    prematura/necesita → rojo. Lo desconocido se etiqueta como 'desconocido'."""
    if not diagnostico:
        return "desconocido"
    m = re.search(r"ESTADO:\s*(.+)", diagnostico, re.IGNORECASE)
    if not m:
        return "desconocido"
    estado = m.group(1).strip().lower()
    if any(s in estado for s in ("construc", "iteración", "iteracion", "prematura", "necesita iter", "buena base")):
        return "rojo"
    if any(s in estado for s in ("casi", "pendiente", "punto")):
        return "amarillo"
    if "listo" in estado or "lista" in estado:
        return "verde"
    return "desconocido"


def _calcular_stats_calibracion(etiquetas: list[dict], total_disponibles: int) -> dict:
    """Stats sobre los comentarios libres del admin. Sin veredicto color
    (decisión: el admin escribe texto libre, no marca color, para no sesgar
    el análisis posterior). Las palabras frecuentes se bucketean por color
    que sacó el MOTOR — así se ven divergencias estilo \"en tracks que el
    motor llamó verde, en tus comentarios aparece N veces 'harshness'\"."""
    from collections import Counter

    palabras_por_motor: dict[str, Counter] = {
        "verde": Counter(), "amarillo": Counter(), "rojo": Counter(),
        "desconocido": Counter(),
    }
    longitudes: list[int] = []
    descartados = 0
    comentados = 0  # etiquetas no descartadas con comentario no vacío

    for e in etiquetas:
        if bool(e.get("descartado")):
            descartados += 1
            continue
        comentario = (e.get("comentario") or "").strip()
        if not comentario:
            continue
        comentados += 1
        longitudes.append(len(comentario))

        motor = _color_motor_desde_diagnostico(e.get("diagnostico") or "")
        if motor not in palabras_por_motor:
            motor = "desconocido"
        for w in _palabras_significativas(comentario):
            palabras_por_motor[motor][w] += 1

    pendientes = max(total_disponibles - comentados - descartados, 0)
    longitud_media = (sum(longitudes) // len(longitudes)) if longitudes else 0

    top_palabras_por_motor = {
        c: [{"palabra": p, "n": n} for p, n in cnt.most_common(10)]
        for c, cnt in palabras_por_motor.items()
    }

    return {
        "total_disponibles": total_disponibles,
        "total_etiquetados": comentados,
        "descartados": descartados,
        "pendientes": pendientes,
        "longitud_media_comentario": longitud_media,
        "palabras_por_color_motor": top_palabras_por_motor,
    }


@app.get("/api/calibrar/tracks")
@limiter.limit("30/minute")
async def calibrar_listar_tracks(request: Request):
    """Lista análisis con feedback_real y, si existe, la etiqueta del admin.
    Resuelve en paralelo las URLs cortas de SoundCloud para que el widget
    pueda embeber el reproductor (las short URLs `on.soundcloud.com/...` no
    son aceptadas directamente por el widget)."""
    email = _admin_email_from_cookie(request)
    if not email:
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        rows = await repo.list_analisis_con_feedback_real(pool, email, limit=500)
        urls = [r.get("feedback_real") or "" for r in rows]
        resueltas = await asyncio.gather(*(_resolver_url_audio(u) for u in urls))
        for r, ru in zip(rows, resueltas):
            r["feedback_real_resuelto"] = ru
        return {"ok": True, "tracks": [_serializar_track_calibracion(r) for r in rows]}
    except Exception as e:
        print(f"[CALIBRAR] error listando tracks: {e}")
        return JSONResponse(status_code=503, content={"error": "Error consultando DB"})


@app.get("/api/calibrar/stats")
@limiter.limit("30/minute")
async def calibrar_obtener_stats(request: Request):
    """Estadísticas de calibración del admin: distribución, matriz de
    concordancia motor↔admin y palabras frecuentes por veredicto."""
    email = _admin_email_from_cookie(request)
    if not email:
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        raw = await repo.get_stats_calibracion_raw(pool, email)
        stats = _calcular_stats_calibracion(raw["etiquetas"], raw["total_disponibles"])
        return {"ok": True, **stats}
    except Exception as e:
        print(f"[CALIBRAR] error calculando stats: {e}")
        return JSONResponse(status_code=503, content={"error": "Error calculando estadísticas"})


@app.post("/api/calibrar/etiqueta")
@limiter.limit("60/minute")
async def calibrar_guardar_etiqueta(request: Request, data: dict):
    """Upsert de una etiqueta del admin sobre un análisis.
    Si veredicto, comentario y descartado quedan todos vacíos/False,
    borra la etiqueta."""
    email = _admin_email_from_cookie(request)
    if not email:
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    analisis_id_raw = (data.get("analisis_id") or "").strip()
    veredicto = (data.get("veredicto") or "").strip().lower() or None
    comentario = (data.get("comentario") or "").strip() or None
    descartado = bool(data.get("descartado"))
    if veredicto and veredicto not in ("verde", "amarillo", "rojo"):
        return JSONResponse(status_code=400, content={"error": "Veredicto inválido"})
    if comentario and len(comentario) > 5000:
        comentario = comentario[:5000]
    try:
        analisis_id = uuid.UUID(analisis_id_raw)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "ID de análisis inválido"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        if not veredicto and not comentario and not descartado:
            ok = await repo.delete_etiqueta_calibracion(pool, analisis_id, email)
            return {"ok": True, "deleted": ok}
        etiqueta_row = await repo.upsert_etiqueta_calibracion(
            pool,
            analisis_id=analisis_id,
            etiquetador_email=email,
            veredicto=veredicto,
            comentario=comentario,
            descartado=descartado,
        )
        ts = etiqueta_row.get("timestamp")
        return {
            "ok": True,
            "etiqueta": {
                "id": str(etiqueta_row["id"]),
                "veredicto": etiqueta_row.get("veredicto"),
                "comentario": etiqueta_row.get("comentario"),
                "descartado": bool(etiqueta_row.get("descartado")),
                "fecha": ts.isoformat() if ts else None,
            },
        }
    except Exception as e:
        print(f"[CALIBRAR] error guardando etiqueta: {e}")
        return JSONResponse(status_code=503, content={"error": "Error guardando"})


# =========================================================================
# Reanálisis histórico — pasa señales guardadas por el motor actual
# =========================================================================
#
# Las señales se guardan en la columna JSONB `analisis.senales` en formato
# *flat* (key→valor) tal y como las arma el frontend. El motor de reglas
# espera un dict *anidado* (con sub-dicts `distribucion`, `armonia`,
# `loudness`, `mono_compat`, `harshness`). Reconstruimos el anidado a partir
# del flat para poder re-evaluar el motor sin tener que re-subir el WAV.
# Algunos campos no están en el flat (max_seccion_baja, notas_dominantes…);
# se rellenan con defaults seguros. Para la decisión de score esto basta —
# son campos cosméticos para los mensajes, no thresholds.

_FORMULARIO_LABEL_TO_VALUE = {
    "genero": {
        "Tech House": "tech_house", "House": "house", "Techno": "techno",
        "Techno ácido": "techno_acido", "Hard Techno": "hard_techno",
        "Minimal": "minimal", "Dub Techno": "dub_techno",
        "Progressive House": "progressive_house", "Trance": "trance",
        "Psytrance": "psytrance", "Melodic Techno": "melodic_techno",
        "Deep House": "deep_house", "Afro House": "afro_house",
        "Indie Dance": "indie_dance", "Breaks": "breaks", "Otro": "otro",
    },
    "fase": {
        "Idea inicial / loop": "idea",
        "Arreglo en progreso": "arreglo_en_progreso",
        "Arreglo cerrado, ajustando mezcla": "ajustando_mezcla",
        "Creo que está casi listo": "casi_listo",
    },
    "objetivo": {
        "Publicar y tocar en sesión": "pinchar",
        "Practicar y aprender": "aprender",
        "Enviar demo a sellos": "sellos",
        "Todo lo anterior": "todo",
    },
    "experiencia": {
        "Menos de 6 meses": "menos_6m",
        "6 meses a 2 años": "6m_2a",
        "2 a 5 años": "2a_5a",
        "Más de 5 años": "mas_5a",
    },
    "dificultad_habitual": {
        "Terminar tracks": "terminar",
        "Encontrar buenos sonidos": "sonidos",
        "Que la mezcla suene bien": "mezcla",
        "Estructurar las ideas": "estructura",
        "Todo me cuesta": "todo",
    },
}


def _duracion_seg_from_fmt(fmt: str) -> int:
    """'4:32' → 272. Acepta MM:SS o HH:MM:SS. 0 si no parsea."""
    if not isinstance(fmt, str):
        return 0
    parts = fmt.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, TypeError):
        return 0
    return 0


def _reconstruir_senales_nested(flat: dict) -> dict:
    """Flat (frontend snapshot) → nested (lo que esperan reglas.py / diagnostico.py).
    Lossy en campos que el flat no captura (max_seccion_baja, etc.); rellena
    con defaults que no alteran las decisiones del motor."""
    if not isinstance(flat, dict):
        return {}
    duracion_fmt = flat.get("duracion") or ""
    return {
        "bpm": flat.get("bpm", 0) or 0,
        "duracion_fmt": duracion_fmt,
        "duracion_seg": _duracion_seg_from_fmt(duracion_fmt),
        "balance_grave": flat.get("balance_grave", "ok"),
        "diff_grave_media": flat.get("diff_grave_media", 0) or 0,
        "diff_sub_low": flat.get("diff_sub_low", 0) or 0,
        "db_grave": flat.get("db_grave", 0) or 0,
        "db_media": flat.get("db_media", 0) or 0,
        "db_aguda": flat.get("db_aguda", 0) or 0,
        "densidad_global": flat.get("densidad", "media") or "media",
        "densidad_espectral": flat.get("densidad_espectral", 0) or 0,
        "contraste_energetico": flat.get("contraste", "medio") or "medio",
        "varianza_energia": flat.get("varianza_energia", 0) or 0,
        "rango_dinamico": flat.get("rango_dinamico", 2.0) or 2.0,
        "tiene_desarrollo": bool(flat.get("tiene_desarrollo", False)),
        "cambios_significativos": flat.get("cambios_significativos", 0) or 0,
        "n_bloques": flat.get("n_bloques", 0) or 0,
        "madurez_estimada": flat.get("madurez", "en_desarrollo") or "en_desarrollo",
        "carencia_medios": bool(flat.get("carencia_medios", False)),
        "carencia_agudos": bool(flat.get("carencia_agudos", False)),
        "distribucion": {
            "break_desproporcionado": bool(flat.get("break_largo", False)),
            "drop_corto": bool(flat.get("drop_corto", False)),
            "inicio_abrupto": bool(flat.get("sin_intro", False)),
            "sin_outro": bool(flat.get("sin_outro", False)),
            "estructura_problematica": bool(flat.get("estructura_problematica", False)),
            "max_seccion_baja": 0,
            "max_seccion_alta": 0,
        },
        "armonia": {
            "key": flat.get("key", "?") or "?",
            "modo": flat.get("modo", "") or "",
            "key_confidence": flat.get("key_confidence", 0) or 0,
            "contenido_tonal": flat.get("contenido_tonal", 0.5) or 0.5,
            # consistencia_armonica es float 0-1, complejidad_armonica es string
            "consistencia_armonica": flat.get("consistencia_armonica", 0.5) if isinstance(flat.get("consistencia_armonica"), (int, float)) else 0.5,
            "complejidad_armonica": flat.get("complejidad_armonica") or "moderada",
            "ratio_tonal_percusivo": flat.get("ratio_tonal_percusivo", 1.0) or 1.0,
            "n_notas_activas": flat.get("n_notas_activas", 0) or 0,
            "notas_dominantes": [],
        },
        "loudness": {
            "lufs_integrado": flat.get("lufs_integrado", -14) or -14,
            "lufs_short_term_max": flat.get("lufs_short_term_max", -14) or -14,
            "rango_loudness": flat.get("rango_loudness", 0) or 0,
            "nivel": flat.get("nivel_loudness", "moderado") or "moderado",
            "true_peak_dbtp": flat.get("true_peak_dbtp", -99.0) or -99.0,
            "nivel_true_peak": flat.get("nivel_true_peak", "") or "",
            "referencia": "",
        },
        "mono_compat": {
            "es_stereo": bool(flat.get("es_stereo", True)),
            "correlacion_lr": flat.get("correlacion_lr", 1.0) or 1.0,
            "perdida_mono_db": flat.get("perdida_mono_db", 0) or 0,
            "nivel_compatibilidad": flat.get("nivel_mono", "compatible") or "compatible",
            "fase_invertida": bool(flat.get("fase_invertida", False)),
            "bandas": {
                "graves": {"estado": flat.get("mono_graves", "ok") or "ok"},
                "medios": {"estado": flat.get("mono_medios", "ok") or "ok"},
                "agudos": {"estado": flat.get("mono_agudos", "ok") or "ok"},
            },
        },
        "harshness": {
            "tiene_harshness": bool(flat.get("tiene_harshness", False)),
            "nivel": flat.get("harshness_nivel", "no") or "no",
            "pico_p95": flat.get("harshness_p95", 0) or 0,
            "pct_frames_harsh": flat.get("harshness_pct", 0) or 0,
            "zona_problema": "",
            "peak_freq_hz": 0,
            "caracter": "",
        },
    }


def _formulario_to_contexto(formulario: dict, genero_custom: str = "") -> dict:
    """Formulario guardado (con labels en ES) → contexto (con slugs) que
    espera el motor de reglas. `bloqueo` se reexporta como
    `bloqueo_percibido` porque ese es el nombre que usan las reglas."""
    if not isinstance(formulario, dict):
        return {}
    contexto: dict = {}
    for campo, valor in formulario.items():
        if not isinstance(valor, str):
            contexto[campo] = valor
            continue
        mapa = _FORMULARIO_LABEL_TO_VALUE.get(campo, {})
        slug = mapa.get(valor.strip())
        contexto[campo] = slug if slug else valor.strip()
    contexto["bloqueo_percibido"] = contexto.get("bloqueo", "")
    if genero_custom:
        contexto["genero_custom"] = genero_custom
    return contexto


_DX_PRINCIPAL_ID_RE = re.compile(
    r"DIAGNÓSTICO PRINCIPAL:.*?\(([a-zA-Z0-9_]+)\)", re.IGNORECASE
)


def _extraer_dx_principal_id(diagnostico_str: str) -> str:
    """Extrae el id (entre paréntesis) del diagnóstico principal del informe
    de texto que se guarda en analisis.diagnostico."""
    if not diagnostico_str:
        return ""
    m = _DX_PRINCIPAL_ID_RE.search(diagnostico_str)
    return m.group(1) if m else ""


def _replay_motor_sobre_analisis(row: dict) -> dict | None:
    """Re-evalúa el motor actual sobre las señales guardadas. Lectura: no
    toca la DB. Devuelve None si no se pudo procesar (señales vacías o
    el motor lanzó excepción)."""
    flat = row.get("senales") or {}
    if not flat:
        return None
    # asyncpg devuelve JSONB como dict; si por lo que sea viene str, parseamos.
    if isinstance(flat, str):
        try:
            flat = json.loads(flat)
        except Exception:
            return None
    senales = _reconstruir_senales_nested(flat)
    contexto = _formulario_to_contexto(
        row.get("formulario") or {},
        genero_custom=(row.get("genero_custom") or "") or "",
    )
    try:
        from engine.reglas import evaluar_diagnosticos, aplicar_jerarquia
        scores, _ = evaluar_diagnosticos(senales, contexto)
        principal_id, secundario_id, _, _ = aplicar_jerarquia(scores, senales, contexto)
    except Exception as e:
        print(f"[REANALISIS] motor falló sobre {row.get('id')}: {e}")
        return None
    return {
        "id": str(row.get("id")),
        "timestamp": row.get("timestamp"),
        "email": row.get("email") or "",
        "old_id": _extraer_dx_principal_id(row.get("diagnostico") or ""),
        "new_id": principal_id,
        "new_secundario_id": secundario_id,
        "new_score": int(scores.get(principal_id, 0)),
        "scores": {k: int(v) for k, v in scores.items()},
        "genero_label": (row.get("formulario") or {}).get("genero", "") or "",
        "genero_slug": contexto.get("genero", "") or "",
    }


# =========================================================================
# Admin: embudo CTA (impresiones / clicks / visitas / form / submit)
# =========================================================================
@app.get("/api/admin/embudo")
@limiter.limit("60/minute")
async def admin_embudo(request: Request):
    """Agregados del embudo CTA para el tab Embudo del dashboard."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    dias = 30
    try:
        dias_param = request.query_params.get("dias")
        if dias_param:
            dias = max(1, min(365, int(dias_param)))
    except (TypeError, ValueError):
        pass
    try:
        from db import get_pool
        import repositories as repo
        stats = await repo.stats_embudo_cta(get_pool(), dias=dias)
    except Exception as e:
        print(f"[EMBUDO-ADMIN] error: {type(e).__name__}: {e}")
        return JSONResponse(status_code=503, content={"error": "Error consultando DB"})
    return {"ok": True, **stats}


# =========================================================================
# Admin: solicitudes de Consultoría (sesión 1:1)
# =========================================================================
@app.get("/api/admin/consultoria/solicitudes")
@limiter.limit("60/minute")
async def admin_consultoria_solicitudes(request: Request):
    """Lista todas las solicitudes recibidas vía /consultoria, más recientes
    primero. Solo accesible con cookie admin."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        rows = await repo.list_consultoria_solicitudes(pool, limit=500)
    except Exception as e:
        print(f"[CONSULTORIA-ADMIN] error listando: {e}")
        return JSONResponse(status_code=503, content={"error": "Error consultando DB"})

    out = []
    for r in rows:
        out.append({
            "id": str(r["id"]),
            "timestamp": r["timestamp"].isoformat() if r["timestamp"] else None,
            "nombre": r["nombre"],
            "email": r["email"],
            "soundcloud": r["soundcloud"],
            "ref_cancion": r["ref_cancion"] or "",
            "ref_artistas": r["ref_artistas"] or "",
            "ref_sellos": r["ref_sellos"] or "",
            "contexto": r["contexto"] or "",
            "estado": r["estado"],
            "notas_admin": r["notas_admin"] or "",
            "actualizada_en": r["actualizada_en"].isoformat() if r["actualizada_en"] else None,
        })
    return {"ok": True, "solicitudes": out}


@app.post("/api/admin/consultoria/solicitudes/{solicitud_id}")
@limiter.limit("60/minute")
async def admin_consultoria_actualizar(request: Request, solicitud_id: str, data: dict):
    """Actualiza estado y/o notas de una solicitud. Estados válidos:
    nueva, aceptada, rechazada, completada, reembolsada."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    estado = (data.get("estado") or "").strip().lower() or None
    notas_raw = data.get("notas")
    notas = notas_raw.strip() if isinstance(notas_raw, str) else None
    # Si notas viene como cadena vacía explícita, persistimos cadena vacía.
    # Si viene como None / no se manda, no se toca el campo.
    estados_validos = ("nueva", "aceptada", "rechazada", "completada", "reembolsada")
    if estado is not None and estado not in estados_validos:
        return JSONResponse(status_code=400, content={"error": "Estado inválido"})
    if estado is None and notas is None:
        return JSONResponse(status_code=400, content={"error": "Nada que actualizar"})
    try:
        sid = uuid.UUID(solicitud_id)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "ID inválido"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        ok = await repo.update_consultoria_solicitud_estado(pool, sid, estado, notas)
    except Exception as e:
        print(f"[CONSULTORIA-ADMIN] error update: {e}")
        return JSONResponse(status_code=503, content={"error": "Error actualizando"})
    return {"ok": ok}


@app.get("/api/admin/cutover-b")
@limiter.limit("30/minute")
async def admin_cutover_b(request: Request):
    """Inventario del cierre del cutover B: cuántos usuarios todavía usan
    el placeholder __MIGRATED__ (= dependen de Sheets para autenticar) y
    cuántos siguen activos. Decisión de eliminar el fallback Sheets se
    basa en este dato."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        stats = await repo.stats_usuarios_migrated(pool)
    except Exception as e:
        print(f"[CUTOVER-B] error: {e}")
        return JSONResponse(status_code=503, content={"error": "Error consultando DB"})
    return {"ok": True, "sheets_webhook_activo": bool(SHEETS_WEBHOOK), **stats}


@app.post("/api/admin/cutover-b/heal")
@limiter.limit("3/hour")
async def admin_cutover_b_heal(request: Request):
    """Self-heal bulk: pasa cada usuario __MIGRATED__ por Sheets, obtiene su
    hash real y lo copia a Postgres. Soporta dry-run vía query ?dry_run=1.

    Iteración en batches paralelos pequeños (5 a la vez) para no saturar el
    Apps Script de Sheets. Devuelve resumen con counts por categoría."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    if not SHEETS_WEBHOOK:
        return JSONResponse(
            status_code=503,
            content={"error": "SHEETS_WEBHOOK no configurado — no se puede pedir hashes a Sheets"},
        )

    dry_run = request.query_params.get("dry_run") in ("1", "true", "yes")

    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        emails = await repo.list_emails_migrated(pool)
    except Exception as e:
        print(f"[CUTOVER-B-HEAL] listado falló: {e}")
        return JSONResponse(status_code=503, content={"error": "Error listando usuarios"})

    print(f"[CUTOVER-B-HEAL] iniciando heal sobre {len(emails)} usuarios (dry_run={dry_run})")

    counters = {
        "total": len(emails),
        "healed": 0,                      # Hash real copiado a Postgres
        "sheets_not_found": 0,            # Sheets dice que ese email no existe
        "sheets_still_migrated": 0,       # Sheets también tiene __MIGRATED__
        "sheets_empty_hash": 0,           # Sheets responde pero sin hash usable
        "sheets_error": 0,                # Sheets no respondió o dio error
    }

    async def heal_one(email: str) -> str:
        try:
            sheets_resp = await _sheets_get({"action": "get_user", "email": email})
        except Exception as e:
            print(f"[CUTOVER-B-HEAL] {email}: error Sheets: {e}")
            return "sheets_error"
        if sheets_resp.get("_connection_error"):
            return "sheets_error"
        if not sheets_resp.get("found"):
            return "sheets_not_found"
        sheets_hash = (sheets_resp.get("password_hash") or "").strip()
        if not sheets_hash:
            return "sheets_empty_hash"
        if sheets_hash == "__MIGRATED__":
            return "sheets_still_migrated"
        # Tenemos un hash real — actualizamos Postgres (salvo dry-run)
        if not dry_run:
            try:
                await _heal_postgres_user_password(email, sheets_hash)
            except Exception as e:
                print(f"[CUTOVER-B-HEAL] {email}: update Postgres falló: {e}")
                return "sheets_error"
        return "healed"

    # Batches de 5 para limitar concurrencia contra Sheets.
    BATCH_SIZE = 5
    for i in range(0, len(emails), BATCH_SIZE):
        chunk = emails[i:i + BATCH_SIZE]
        results = await asyncio.gather(*(heal_one(e) for e in chunk), return_exceptions=False)
        for r in results:
            counters[r] = counters.get(r, 0) + 1

    print(f"[CUTOVER-B-HEAL] resumen: {counters}")
    return {"ok": True, "dry_run": dry_run, **counters}


@app.get("/api/admin/reanalisis")
@limiter.limit("10/minute")
async def admin_reanalisis(request: Request):
    """Pasa cada análisis guardado por el motor actual y devuelve un resumen
    de matches vs cambios. SOLO LECTURA — no modifica DB. Útil para medir
    impacto de recalibraciones sin tener que re-subir tracks."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})

    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        rows = await repo.list_all_analisis(pool, limit=5000)
    except Exception as e:
        print(f"[REANALISIS] error listando análisis: {e}")
        return JSONResponse(status_code=503, content={"error": "Error consultando DB"})

    total_procesados = 0
    errores = 0
    matches = 0
    cambios = 0
    sin_old_id = 0  # análisis donde el informe guardado no permite extraer el id
    transitions: dict[str, int] = {}
    cambios_samples: list[dict] = []
    por_genero: dict[str, dict] = {}

    for row in rows:
        res = _replay_motor_sobre_analisis(row)
        if not res:
            errores += 1
            continue
        total_procesados += 1
        old_id = res["old_id"]
        new_id = res["new_id"]
        if not old_id:
            sin_old_id += 1
            es_match = False
        else:
            es_match = (old_id == new_id)
        if es_match:
            matches += 1
        else:
            cambios += 1
            key = f"{old_id or '?'} → {new_id}"
            transitions[key] = transitions.get(key, 0) + 1
            cambios_samples.append({
                "id": res["id"],
                "timestamp": res["timestamp"].isoformat() if res["timestamp"] else None,
                "email": res["email"],
                "old_id": old_id,
                "new_id": new_id,
                "new_secundario_id": res["new_secundario_id"],
                "new_score": res["new_score"],
                "genero": res["genero_label"],
                "scores": res["scores"],
            })
        # Por género (label tal cual lo guardó el frontend)
        g = res["genero_label"] or "—"
        bucket = por_genero.setdefault(g, {"total": 0, "matches": 0, "cambios": 0})
        bucket["total"] += 1
        if es_match:
            bucket["matches"] += 1
        else:
            bucket["cambios"] += 1

    # Muestras: más recientes primero, capadas a 100 para no inflar el payload
    cambios_samples.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    cambios_samples = cambios_samples[:100]

    transitions_ordenadas = sorted(
        ({"transition": k, "n": v} for k, v in transitions.items()),
        key=lambda x: x["n"], reverse=True,
    )
    por_genero_lista = [
        {"genero": g, **bucket}
        for g, bucket in sorted(por_genero.items(), key=lambda x: -x[1]["total"])
    ]

    return {
        "ok": True,
        "motor_version": app.version,
        "total_en_db": len(rows),
        "total_procesados": total_procesados,
        "errores": errores,
        "sin_old_id": sin_old_id,
        "matches": matches,
        "cambios": cambios,
        "transitions": transitions_ordenadas,
        "cambios_samples": cambios_samples,
        "por_genero": por_genero_lista,
    }


@app.get("/calibrar")
def serve_calibrar(request: Request):
    """Página de calibración. Protegida por cookie admin (misma que /dashboard).
    Si no hay sesión, redirige a /dashboard para que el admin entre con la key."""
    admin_cookie = request.cookies.get("admin_session", "")
    if not _verify_admin_token(admin_cookie):
        return RedirectResponse(url="/dashboard", status_code=303)
    calibrar_path = FRONTEND_DIR / "calibrar.html"
    if not calibrar_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(calibrar_path, headers={"Cache-Control": "no-cache"})


# =========================================================================
# Métricas públicas — página /metricas
# =========================================================================
# Cache en memoria de las métricas (recalcular cada 6h es suficiente para
# una página pública orientativa).
_PUBLIC_METRICS_CACHE: dict = {"data": None, "fetched_at": None}
_PUBLIC_METRICS_TTL = timedelta(hours=6)


@app.get("/api/metricas/public")
@limiter.limit("30/minute")
async def public_metrics(request: Request):
    """Métricas agregadas para la página pública /metricas. SOLO aggregates,
    sin PII. Cacheado 6h en memoria — la página marca cuándo se generó."""
    now = datetime.now(timezone.utc)
    cached = _PUBLIC_METRICS_CACHE.get("data")
    fetched_at = _PUBLIC_METRICS_CACHE.get("fetched_at")
    if cached and fetched_at and (now - fetched_at) < _PUBLIC_METRICS_TTL:
        return cached

    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        data = await repo.get_public_metrics(pool)
    except Exception as e:
        print(f"[METRICAS] error: {type(e).__name__}: {e}")
        # Si tenemos cache antiguo lo devolvemos antes de fallar
        if cached:
            return cached
        return JSONResponse(status_code=503, content={"error": "Error calculando métricas"})

    data["generated_at"] = now.isoformat()
    _PUBLIC_METRICS_CACHE["data"] = data
    _PUBLIC_METRICS_CACHE["fetched_at"] = now
    return data


@app.get("/metricas")
def serve_metricas():
    """Página pública con gráficas de crecimiento."""
    metricas_path = FRONTEND_DIR / "metricas.html"
    if not metricas_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(metricas_path, headers={"Cache-Control": "public, max-age=300"})


@app.get("/consultoria")
def serve_consultoria():
    """Landing de la sesión 1:1 con Alex (200€/60min).
    Mientras CAL_LINK siga vacío en el HTML, la sección de agenda muestra
    placeholder con email de contacto. Cambiar 1 línea en consultoria.html
    para activar el embed cuando Cal.com esté listo."""
    path = FRONTEND_DIR / "consultoria.html"
    if not path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


# Changelog: HTML lee el JSON y renderiza las entradas en cliente
@app.get("/changelog")
def serve_changelog():
    changelog_path = FRONTEND_DIR / "changelog.html"
    if not changelog_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(changelog_path, headers={"Cache-Control": "no-cache"})


@app.get("/changelog.json")
def serve_changelog_json():
    json_path = FRONTEND_DIR / "changelog.json"
    if not json_path.is_file():
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    # no-cache: los cambios de versión deben verse inmediatamente
    return FileResponse(json_path, headers={"Cache-Control": "no-cache"}, media_type="application/json")


# =========================================================================
# Páginas legales (servidas en URLs sin extensión)
# =========================================================================

# Mapeo URL pública → archivo HTML en frontend
_LEGAL_PAGES = {
    "aviso-legal": "aviso-legal.html",
    "privacidad": "privacidad.html",
    "cookies": "cookies.html",
    "terminos": "terminos.html",
}


def _serve_legal(slug: str):
    """Sirve una página legal estática con cache moderado."""
    filename = _LEGAL_PAGES.get(slug)
    if not filename:
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    page_path = FRONTEND_DIR / filename
    if not page_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    # Cache 1h en navegador (textos legales cambian poco pero deben poder actualizarse)
    return FileResponse(page_path, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/reset")
def serve_reset(request: Request):
    """Página de reset de contraseña. Sirve siempre el HTML — el token se
    valida en POST /api/auth/reset. Sin cache para evitar problemas si
    abren un link viejo y vuelven al actual."""
    reset_path = FRONTEND_DIR / "reset.html"
    if not reset_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(reset_path, headers={"Cache-Control": "no-cache, no-store"})


@app.get("/aviso-legal")
def serve_aviso_legal():
    return _serve_legal("aviso-legal")


@app.get("/privacidad")
def serve_privacidad():
    return _serve_legal("privacidad")


@app.get("/cookies")
def serve_cookies():
    return _serve_legal("cookies")


@app.get("/terminos")
def serve_terminos():
    return _serve_legal("terminos")


# =========================================================================
# Dashboard admin — ruta protegida con clave
# =========================================================================

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
if not ADMIN_KEY:
    ADMIN_KEY = secrets.token_hex(16)
    print("[WARN] ADMIN_KEY no configurado — generando uno aleatorio (configura ADMIN_KEY en env vars)")

ADMIN_SESSION_SECRET = os.environ.get("ADMIN_SESSION_SECRET", secrets.token_hex(16))


def _create_admin_token() -> str:
    """Genera un token de sesión admin."""
    payload = {
        "role": "admin",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, ADMIN_SESSION_SECRET, algorithm="HS256")


def _verify_admin_token(token: str) -> bool:
    """Verifica un token de sesión admin."""
    try:
        payload = jwt.decode(token, ADMIN_SESSION_SECRET, algorithms=["HS256"])
        return payload.get("role") == "admin"
    except Exception:
        return False


@app.post("/api/admin/login")
@limiter.limit("3/minute")
async def admin_login(request: Request, data: dict):
    """Login admin: recibe clave, devuelve cookie HttpOnly con sesión."""
    key = data.get("key", "")
    if key != ADMIN_KEY:
        return JSONResponse(status_code=403, content={"error": "Clave incorrecta"})

    token = _create_admin_token()
    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=43200,  # 12 horas
    )
    return response


@app.post("/api/admin/logout")
async def admin_logout():
    """Logout admin: borra la cookie de sesión."""
    response = JSONResponse(content={"ok": True})
    response.delete_cookie("admin_session")
    return response


@app.get("/dashboard")
def serve_dashboard(request: Request, key: str = ""):
    """Dashboard admin protegido por cookie de sesión.
    El parámetro ?key= solo se acepta para el primer login:
    setea la cookie y redirige a /dashboard (sin key en URL)."""
    # Check cookie first — acceso normal
    admin_cookie = request.cookies.get("admin_session", "")
    if _verify_admin_token(admin_cookie):
        dashboard_path = FRONTEND_DIR / "dashboard.html"
        if not dashboard_path.is_file():
            return JSONResponse(status_code=404, content={"error": "Dashboard no encontrado"})
        return FileResponse(dashboard_path)

    # Primer login con key: setear cookie y REDIRIGIR para quitar key de la URL
    if key and key == ADMIN_KEY:
        token = _create_admin_token()
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=43200,
        )
        return response

    # Sin cookie ni key válida → mostrar formulario de login inline
    login_html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MentoTrack Admin — Login</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="manifest" href="/manifest-admin.json">
<meta name="theme-color" content="#09090b">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; background: #09090b; color: #e5e5e5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .login-box { width: 100%; max-width: 360px; padding: 24px; }
  .logo { text-align: center; margin-bottom: 32px; font-size: 18px; font-weight: 600; letter-spacing: -0.02em; color: #fff; }
  .logo .dot { color: #8b5cf6; }
  h1 { font-size: 14px; font-weight: 500; color: #9ca3af; text-align: center; margin-bottom: 24px; }
  form { display: flex; flex-direction: column; gap: 12px; }
  input { background: #141414; border: 1px solid #333; border-radius: 10px; padding: 14px 16px; color: #e5e5e5; font-size: 15px; outline: none; transition: border-color 0.15s; -webkit-appearance: none; }
  input:focus { border-color: #8b5cf6; }
  button { background: #8b5cf6; color: #fff; border: none; border-radius: 10px; padding: 14px; font-size: 15px; font-weight: 600; cursor: pointer; transition: background 0.15s; -webkit-appearance: none; }
  button:active { background: #7c3aed; }
  .error { color: #f87171; font-size: 13px; text-align: center; display: none; }
</style>
</head>
<body>
<div class="login-box">
  <div class="logo">mentotrack<span class="dot">●</span></div>
  <h1>Panel de administración</h1>
  <form method="GET" action="/dashboard">
    <input type="password" name="key" placeholder="Admin key" required autocomplete="off" autofocus>
    <button type="submit">Entrar</button>
  </form>
</div>
</body>
</html>"""
    return HTMLResponse(content=login_html, status_code=200)


# ---- PWA assets para dashboard admin ----

@app.get("/manifest-admin.json")
def serve_admin_manifest():
    return FileResponse(
        FRONTEND_DIR / "manifest-admin.json",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/sw-admin.js")
def serve_admin_sw():
    """Service Worker — necesita Service-Worker-Allowed para scope /dashboard."""
    return FileResponse(
        FRONTEND_DIR / "sw-admin.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/dashboard",
        },
    )


@app.get("/pwa-admin-192.png")
def serve_pwa_icon_192():
    return FileResponse(FRONTEND_DIR / "pwa-admin-192.png", headers={"Cache-Control": "public, max-age=604800, immutable"})


@app.get("/pwa-admin-512.png")
def serve_pwa_icon_512():
    return FileResponse(FRONTEND_DIR / "pwa-admin-512.png", headers={"Cache-Control": "public, max-age=604800, immutable"})


# =========================================================================
# Admin: Reporte Mensual
# =========================================================================

def _generate_reporte_html(stats_generales: dict, stats_embudo: dict, mes_str: str) -> str:
    """Genera HTML bonito del reporte mensual."""
    mes_display = f"{mes_str.split('-')[0]}-{mes_str.split('-')[1]}"
    mes_nombre = {
        "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
        "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
        "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre",
    }[mes_str.split('-')[1]]

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1f2937; border-bottom: 2px solid #0ea5e9; padding-bottom: 10px; }}
        h2 {{ color: #374151; margin-top: 30px; }}
        .kpi {{ display: inline-block; width: 32%; margin: 1%; text-align: center; padding: 15px; background: #f3f4f6; border-radius: 8px; }}
        .kpi-value {{ font-size: 24px; font-weight: bold; color: #0ea5e9; }}
        .kpi-label {{ font-size: 12px; color: #6b7280; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f9fafb; font-weight: 600; }}
        .funnel-row {{ display: flex; gap: 10px; margin: 10px 0; }}
        .funnel-bar {{ height: 30px; background: #0ea5e9; border-radius: 4px; display: flex; align-items: center; padding: 0 8px; color: white; font-size: 12px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>📊 Reporte Mensual — {mes_nombre} {mes_str.split('-')[0]}</h1>

    <h2>Análisis</h2>
    <div class="kpi">
        <div class="kpi-value">{stats_generales['analisis']['total_mes']}</div>
        <div class="kpi-label">Este mes</div>
    </div>
    <div class="kpi">
        <div class="kpi-value">{stats_generales['analisis']['total_all_time']}</div>
        <div class="kpi-label">Total histórico</div>
    </div>
    <div class="kpi">
        <div class="kpi-value">{stats_generales['analisis'].get('con_referencia_mes', 0)}</div>
        <div class="kpi-label">Con track de referencia</div>
    </div>
    <p style="font-size: 13px; color: #6b7280;">
        Track de referencia: {stats_generales['analisis'].get('con_referencia_mes', 0)} de {stats_generales['analisis']['total_mes']} análisis este mes
        ({(stats_generales['analisis'].get('con_referencia_mes', 0) / stats_generales['analisis']['total_mes'] * 100) if stats_generales['analisis']['total_mes'] else 0:.0f}%)
        · {stats_generales['analisis'].get('con_referencia_all_time', 0)} en total desde el lanzamiento (v0.5.32, jun 2026).
    </p>

    <h3>Desglose por semana</h3>
    <table>
        <tr><th>Semana</th><th>Análisis</th></tr>
"""
    for semana in stats_generales['analisis']['por_semana']:
        html += f"<tr><td>Semana {semana['semana']}</td><td>{semana['count']}</td></tr>\n"

    html += f"""
    </table>

    <h2>Usuarios</h2>
    <div class="kpi">
        <div class="kpi-value">{stats_generales['usuarios']['total']}</div>
        <div class="kpi-label">Total usuarios</div>
    </div>
    <div class="kpi">
        <div class="kpi-value">{stats_generales['usuarios']['nuevos_mes']}</div>
        <div class="kpi-label">Nuevos este mes</div>
    </div>

    <h3>Usuarios nuevos por semana</h3>
    <table>
        <tr><th>Semana</th><th>Nuevos</th></tr>
"""
    for semana in stats_generales['usuarios']['nuevos_por_semana']:
        html += f"<tr><td>Semana {semana['semana']}</td><td>{semana['count']}</td></tr>\n"

    html += f"""
    </table>

    <h2>Análisis por Persona</h2>
    <h3>Histórico (desde el inicio)</h3>
    <table>
        <tr><th>Métrica</th><th>Valor</th></tr>
        <tr><td>Usuarios con análisis</td><td>{stats_generales['analisis_por_persona']['all_time']['usuarios_con_analisis']}</td></tr>
        <tr><td>Promedio análisis/usuario</td><td>{stats_generales['analisis_por_persona']['all_time']['promedio']:.1f}</td></tr>
        <tr><td>Mediana</td><td>{stats_generales['analisis_por_persona']['all_time']['mediana']:.1f}</td></tr>
        <tr><td>Máximo</td><td>{stats_generales['analisis_por_persona']['all_time']['maximo']}</td></tr>
    </table>

    <h3>Este mes</h3>
    <table>
        <tr><th>Métrica</th><th>Valor</th></tr>
        <tr><td>Usuarios con análisis</td><td>{stats_generales['analisis_por_persona']['mes']['usuarios_con_analisis']}</td></tr>
        <tr><td>Promedio análisis/usuario</td><td>{stats_generales['analisis_por_persona']['mes']['promedio']:.1f}</td></tr>
        <tr><td>Mediana</td><td>{stats_generales['analisis_por_persona']['mes']['mediana']:.1f}</td></tr>
        <tr><td>Máximo</td><td>{stats_generales['analisis_por_persona']['mes']['maximo']}</td></tr>
    </table>

    <h2>Embudo CTA — Auditorías 1:1</h2>
    <table>
        <tr><th>Evento</th><th>Sesiones únicas</th><th>% vs paso anterior</th></tr>
"""

    embudo_steps = [
        ("CTA Visto", "cta_visto"),
        ("CTA Clickado", "cta_clicked"),
        ("Visita /consultoria", "consultoria_visit"),
        ("Form iniciado", "consultoria_form_started"),
        ("Form enviado", "consultoria_form_submit"),
    ]

    totales = stats_embudo.get('totales_recientes', {})
    prev_count = None
    for label, event_key in embudo_steps:
        data = totales.get(event_key)
        if data:
            count = data.get('sesiones', 0)
            pct = ""
            if prev_count and prev_count > 0:
                pct = f"{(count / prev_count * 100):.1f}%"
            html += f"<tr><td>{label}</td><td>{count}</td><td>{pct}</td></tr>\n"
            prev_count = count

    html += """
    </table>

    <p style="margin-top: 40px; font-size: 12px; color: #9ca3af;">
        Reporte generado automáticamente por Mentotrack.<br>
        <a href="https://www.mentotrack.com/dashboard">Ver dashboard completo</a>
    </p>
</div>
</body>
</html>"""
    return html


async def _send_reporte_email(html_content: str, mes_str: str, email_dest: str) -> bool:
    """Envía el reporte via Resend. Retorna True si tuvo éxito."""
    resend_key = os.environ.get("RESEND_API_KEY")
    if not resend_key:
        print("[REPORTE] RESEND_API_KEY no configurada")
        return False

    mes_nombre = {
        "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
        "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
        "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre",
    }[mes_str.split('-')[1]]
    ano = mes_str.split('-')[0]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {resend_key}"},
                json={
                    "from": "Mentotrack <noreply@mentotrack.com>",
                    "to": email_dest,
                    "subject": f"📊 Reporte Mentotrack — {mes_nombre} {ano}",
                    "html": html_content,
                    "reply_to": "hola@mentotrack.com",
                }
            )
            if resp.status_code == 200:
                print(f"[REPORTE] Email enviado a {email_dest}")
                return True
            else:
                print(f"[REPORTE] Fallo enviando email: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        print(f"[REPORTE] Error al enviar: {e}")
        return False


@app.get("/api/admin/reporte-mensual")
@limiter.limit("10/minute")
async def admin_reporte_mensual(request: Request):
    """Genera y envía (o retorna) el reporte mensual.
    Parámetros opcionativos: year=2026&month=5
    Si no se especifican, usa el mes anterior al actual.
    Solo accesible con cookie admin."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})

    try:
        today = datetime.now(timezone.utc)
        year = request.query_params.get("year")
        month = request.query_params.get("month")

        if year and month:
            year, month = int(year), int(month)
        else:
            # Mes anterior al actual
            if today.month == 1:
                year, month = today.year - 1, 12
            else:
                year, month = today.year, today.month - 1

        mes_str = f"{year}-{month:02d}"

        from db import get_pool
        import repositories as repo
        pool = get_pool()

        stats_gen = await repo.stats_reporte_mensual(pool, year, month)
        stats_emb = await repo.stats_embudo_cta(pool, dias=30)

        html = _generate_reporte_html(stats_gen, stats_emb, mes_str)

        return HTMLResponse(content=html)
    except Exception as e:
        print(f"[REPORTE] error: {type(e).__name__}: {e}")
        return JSONResponse(status_code=503, content={"error": "Error generando reporte"})


@app.post("/api/admin/enviar-reporte-email")
@limiter.limit("3/minute")
async def admin_enviar_reporte_email(request: Request, data: dict):
    """Genera y envía el reporte por email. Parámetros: year, month, email (opcional)."""
    if not _admin_email_from_cookie(request):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Postgres no disponible"})

    try:
        today = datetime.now(timezone.utc)
        year = data.get("year")
        month = data.get("month")
        email_dest = data.get("email", _ADMIN_EMAIL_CANONICO)

        if year and month:
            year, month = int(year), int(month)
        else:
            if today.month == 1:
                year, month = today.year - 1, 12
            else:
                year, month = today.year, today.month - 1

        mes_str = f"{year}-{month:02d}"

        from db import get_pool
        import repositories as repo
        pool = get_pool()

        stats_gen = await repo.stats_reporte_mensual(pool, year, month)
        stats_emb = await repo.stats_embudo_cta(pool, dias=30)
        html = _generate_reporte_html(stats_gen, stats_emb, mes_str)

        # Enviar email
        await _send_reporte_email(html, mes_str, email_dest)

        return JSONResponse(content={"ok": True, "mensaje": f"Reporte enviado a {email_dest}"})
    except Exception as e:
        print(f"[ENVIAR-EMAIL] error: {type(e).__name__}: {e}")
        return JSONResponse(status_code=503, content={"error": f"Error enviando email: {str(e)}"})


async def _task_monthly_reporte():
    """Tarea de cron que se ejecuta cada hora y chequea si es el día 1 del mes a las 09:00.
    Si es, calcula el reporte del mes anterior y lo envía por email."""
    try:
        while True:
            await asyncio.sleep(3600)  # Chequea cada hora
            now = datetime.now(timezone.utc)

            # Ejecuta si es día 1, hora 09:00 (ventana de 1 minuto)
            if now.day == 1 and now.hour == 9 and now.minute < 1:
                if not _pg_available():
                    print("[REPORTE-CRON] Postgres no disponible")
                    continue

                try:
                    from db import get_pool
                    import repositories as repo

                    # Calcula reporte del mes anterior
                    if now.month == 1:
                        year, month = now.year - 1, 12
                    else:
                        year, month = now.year, now.month - 1

                    mes_str = f"{year}-{month:02d}"
                    pool = get_pool()

                    stats_gen = await repo.stats_reporte_mensual(pool, year, month)
                    stats_emb = await repo.stats_embudo_cta(pool, dias=30)

                    html = _generate_reporte_html(stats_gen, stats_emb, mes_str)

                    # Envía email
                    email_dest = os.environ.get("ADMIN_EMAIL", "alexgn23@gmail.com")
                    await _send_reporte_email(html, mes_str, email_dest)

                    print(f"[REPORTE-CRON] Reporte {mes_str} enviado exitosamente")
                except Exception as e:
                    print(f"[REPORTE-CRON] error generando reporte: {e}")
    except asyncio.CancelledError:
        pass


# -------------------------------------------------------------------------
# Envío programado de la encuesta de comunidad — UNA SOLA VEZ
# 2026-06-12 06:03 UTC = 08:03 hora peninsular española (CEST, UTC+2)
# -------------------------------------------------------------------------
_ENVIO_ENCUESTA_UTC = datetime(2026, 6, 12, 6, 3, tzinfo=timezone.utc)


async def _enviar_encuesta_masiva(campana: str, destinatarios: list | None = None) -> int:
    """Envía la encuesta a todos los usuarios (sin opt-out). El candado en
    email_envios garantiza que la campaña solo se envía una vez aunque haya
    redeploys o varios workers."""
    from db import get_pool
    import repositories as repo
    import encuesta_email
    import resend

    pool = get_pool()
    if not await repo.claim_envio_campana(pool, campana):
        print(f"[ENCUESTA-ENVIO] {campana}: ya enviada o en curso — no se repite")
        return 0
    if destinatarios is None:
        destinatarios = await repo.emails_para_envio(pool)
    print(f"[ENCUESTA-ENVIO] {campana}: enviando a {len(destinatarios)} usuarios…")
    resend.api_key = RESEND_API_KEY
    enviados = 0
    fallos = 0
    for d in destinatarios:
        try:
            token = _encuesta_token(d["email"])
            params = encuesta_email.payload_para(d["email"], token)
            await asyncio.to_thread(resend.Emails.send, params)
            enviados += 1
        except Exception as e:
            fallos += 1
            print(f"[ENCUESTA-ENVIO] fallo con {d['email']}: {type(e).__name__}: {e}")
        await asyncio.sleep(0.6)  # rate limit de Resend (2 req/s)
        if enviados and enviados % 100 == 0:
            print(f"[ENCUESTA-ENVIO] {enviados}/{len(destinatarios)}…")
    await repo.finalizar_envio_campana(pool, campana, enviados)
    print(f"[ENCUESTA-ENVIO] {campana}: hecho — {enviados} enviados, {fallos} fallos")
    # Confirmación a Alex (a gmail: el buzón de producciononline filtra los Resend)
    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": encuesta_email.FROM,
            "to": ["alexgn23@gmail.com"],
            "subject": f"✅ Encuesta '{campana}' enviada — {enviados} emails",
            "html": (
                f"<p>Envío completado a las {datetime.now(timezone.utc).strftime('%H:%M')} UTC.</p>"
                f"<p><strong>{enviados}</strong> enviados · {fallos} fallos · "
                f"{len(destinatarios)} destinatarios.</p>"
                "<p>Para ver respuestas: pregunta a Claude o abre "
                "<a href='https://www.mentotrack.com/api/admin/encuesta'>/api/admin/encuesta</a> "
                "con tu sesión de admin abierta.</p>"
            ),
        })
    except Exception as e:
        print(f"[ENCUESTA-ENVIO] no se pudo enviar la confirmación: {e}")
    return enviados


async def _task_envio_encuesta():
    """Tarea one-shot: duerme hasta la hora programada y lanza el envío.
    Si el deploy llega tarde (caída, redeploy), envía igualmente dentro de
    una ventana de 48 h; pasada la ventana no hace nada."""
    try:
        ahora = datetime.now(timezone.utc)
        if ahora > _ENVIO_ENCUESTA_UTC + timedelta(hours=48):
            return
        espera = (_ENVIO_ENCUESTA_UTC - ahora).total_seconds()
        if espera > 0:
            print(f"[ENCUESTA-ENVIO] programado para {_ENVIO_ENCUESTA_UTC.isoformat()} (en {espera/3600:.1f} h)")
            await asyncio.sleep(espera)
        if not _pg_available():
            print("[ENCUESTA-ENVIO] Postgres no disponible — abortado")
            return
        if not _resend_disponible():
            print("[ENCUESTA-ENVIO] Resend no disponible — abortado")
            return
        await _enviar_encuesta_masiva(ENCUESTA_ACTUAL)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[ENCUESTA-ENVIO] error en la tarea: {type(e).__name__}: {e}")


# =========================================================================
# Encuesta por email — un clic desde el email registra el voto (v0.5.34)
# =========================================================================

ENCUESTA_ACTUAL = "comunidad-2026-06"
_ENCUESTA_OPCIONES = {
    "todo": "Sí — compartiría mis tracks y comentaría los de otros",
    "solo_compartir": "Compartiría mis tracks, pero no me veo comentando los de otros",
    "solo_comentar": "Comentaría los de otros, pero aún no compartiría los míos",
    "no": "No me interesa",
}


def _encuesta_token(email: str, dias: int = 90) -> str:
    """Token firmado que identifica al destinatario en los links del email.
    Scope propio ('encuesta') para que no sirva como token de sesión."""
    payload = {
        "em": (email or "").strip().lower(),
        "sc": "encuesta",
        "exp": datetime.utcnow() + timedelta(days=dias),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _email_desde_token_encuesta(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("sc") != "encuesta":
            return None
        return (payload.get("em") or "").strip().lower() or None
    except Exception:
        return None


@app.get("/encuesta")
@limiter.limit("30/minute")
async def encuesta_page(request: Request, t: str = "", o: str = ""):
    """Página de voto de la encuesta. Llega desde el email con ?t=token&o=opcion.
    El voto se registra vía POST desde JS (los scanners de email siguen los GET
    pero no ejecutan JS — evita falsos votos)."""
    email = _email_desde_token_encuesta(t)
    if not email:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;background:#111;color:#eee;"
            "display:flex;align-items:center;justify-content:center;min-height:100vh'>"
            "<p>Este enlace no es válido o ha caducado.</p></body></html>",
            status_code=400,
        )
    o_valida = o if o in _ENCUESTA_OPCIONES else ""
    botones = "".join(
        f"""<button class="opt" data-o="{clave}" onclick="votar('{clave}')">{texto}</button>"""
        for clave, texto in _ENCUESTA_OPCIONES.items()
    )
    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Encuesta — Mentotrack</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0c0c0e; color: #e5e5e5; margin: 0; display: flex; justify-content: center; padding: 40px 16px; }}
  .box {{ max-width: 560px; width: 100%; }}
  h1 {{ font-size: 20px; color: #fff; }}
  p {{ line-height: 1.55; color: #b8b8bd; font-size: 15px; }}
  .opt {{ display: block; width: 100%; text-align: left; margin: 10px 0; padding: 14px 16px; border-radius: 10px; border: 1px solid #2e2e33; background: #18181c; color: #e5e5e5; font-size: 15px; cursor: pointer; }}
  .opt:hover {{ border-color: #25F464; }}
  .opt.sel {{ border-color: #25F464; background: rgba(37,244,100,0.08); }}
  #gracias {{ display: none; color: #25F464; font-weight: 600; margin-top: 14px; }}
  textarea {{ width: 100%; box-sizing: border-box; margin-top: 16px; padding: 12px; border-radius: 10px; border: 1px solid #2e2e33; background: #18181c; color: #e5e5e5; font-size: 14px; min-height: 90px; font-family: inherit; }}
  #enviarCom {{ margin-top: 8px; padding: 10px 18px; border-radius: 8px; border: none; background: #25F464; color: #0c0c0e; font-weight: 600; cursor: pointer; font-size: 14px; }}
  #comOk {{ display: none; color: #25F464; font-size: 13px; margin-left: 10px; }}
  .baja {{ margin-top: 36px; font-size: 12px; }} .baja a {{ color: #6b6b70; }}
</style></head>
<body><div class="box">
  <h1>¿Comunidad de feedback dentro de Mentotrack?</h1>
  <p>La idea: compartir públicamente tu idea inacabada o tu track casi terminado con otros
  productores que usan Mentotrack —con tu nombre, no anónimo— y daros feedback entre vosotros.</p>
  <p><strong style="color:#fff">Elige la opción que mejor te describa:</strong></p>
  {botones}
  <div id="gracias">✓ Respuesta registrada. Puedes cambiarla con otro clic.</div>
  <textarea id="comentario" maxlength="2000" placeholder="¿Quieres matizar tu respuesta? ¿Qué te animaría o te frenaría? (opcional)"></textarea>
  <div><button id="enviarCom" onclick="enviarComentario()">Enviar comentario</button><span id="comOk">✓ Guardado</span></div>
  <p class="baja"><a href="/email/baja?t={t}">No quiero recibir más emails como este</a></p>
</div>
<script>
  const T = {json.dumps(t)};
  let votado = false;
  function marcar(o) {{
    document.querySelectorAll('.opt').forEach(b => b.classList.toggle('sel', b.dataset.o === o));
    document.getElementById('gracias').style.display = 'block';
  }}
  function votar(o) {{
    fetch('/api/encuesta/voto', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ t: T, o: o }})
    }}).then(r => {{ if (r.ok) {{ votado = true; marcar(o); }} }}).catch(() => {{}});
  }}
  function enviarComentario() {{
    const c = document.getElementById('comentario').value.trim();
    if (!c) return;
    fetch('/api/encuesta/comentario', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ t: T, comentario: c }})
    }}).then(r => {{ if (r.ok) document.getElementById('comOk').style.display = 'inline'; }}).catch(() => {{}});
  }}
  const oInicial = {json.dumps(o_valida)};
  if (oInicial) votar(oInicial);
</script>
</body></html>"""
    return HTMLResponse(html)


@app.post("/api/encuesta/voto")
@limiter.limit("10/minute")
async def encuesta_voto(request: Request, data: dict):
    email = _email_desde_token_encuesta(data.get("t", ""))
    opcion = data.get("o", "")
    if not email or opcion not in _ENCUESTA_OPCIONES:
        return JSONResponse(status_code=400, content={"error": "Token u opción no válidos"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "DB no disponible"})
    from db import get_pool
    import repositories as repo
    await repo.upsert_encuesta_respuesta(get_pool(), ENCUESTA_ACTUAL, email, opcion)
    return {"ok": True}


@app.post("/api/encuesta/comentario")
@limiter.limit("5/minute")
async def encuesta_comentario(request: Request, data: dict):
    email = _email_desde_token_encuesta(data.get("t", ""))
    comentario = _sanitize(data.get("comentario", ""), 2000)
    if not email or not comentario:
        return JSONResponse(status_code=400, content={"error": "Token o comentario no válidos"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "DB no disponible"})
    from db import get_pool
    import repositories as repo
    ok = await repo.set_encuesta_comentario(get_pool(), ENCUESTA_ACTUAL, email, comentario)
    if not ok:
        return JSONResponse(status_code=400, content={"error": "Elige primero una opción"})
    return {"ok": True}


@app.get("/email/baja")
@limiter.limit("10/minute")
async def email_baja(request: Request, t: str = ""):
    """Baja de emails no transaccionales (encuestas/novedades)."""
    email = _email_desde_token_encuesta(t)
    if not email:
        return HTMLResponse("<p>Enlace no válido o caducado.</p>", status_code=400)
    if not _pg_available():
        return HTMLResponse("<p>Servicio no disponible, inténtalo más tarde.</p>", status_code=503)
    from db import get_pool
    import repositories as repo
    await repo.set_email_opt_out(get_pool(), email)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;background:#111;color:#eee;"
        "display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center'>"
        "<div><p>Listo — no volverás a recibir emails de encuestas o novedades de Mentotrack.</p>"
        "<p style='color:#888;font-size:13px'>Los emails operativos (como recuperar tu contraseña) no se ven afectados.</p></div>"
        "</body></html>"
    )


@app.get("/api/admin/encuesta")
@limiter.limit("10/minute")
async def admin_encuesta(request: Request, encuesta: str = ""):
    """Resultados de la encuesta (requiere cookie admin)."""
    admin_cookie = request.cookies.get("admin_session", "")
    if not _verify_admin_token(admin_cookie):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "DB no disponible"})
    from db import get_pool
    import repositories as repo
    stats = await repo.stats_encuesta(get_pool(), encuesta or ENCUESTA_ACTUAL)
    stats["opciones_texto"] = _ENCUESTA_OPCIONES
    return stats


# =========================================================================
# Perfil de comunidad (v0.5.40)
# =========================================================================

# Opciones de trayectoria publicada. El frontend pregunta Sí/No y, si Sí,
# despliega autoeditado/sellos ("no" es el value de la respuesta No).
PERFIL_PUBLICADO_OPCIONES = {
    "no": "Aún no he publicado música",
    "autoeditado": "Autoeditado (Bandcamp, DistroKid, Triple Point…)",
    "sellos": "Firmado por sellos",
}


@app.get("/api/perfil")
@limiter.limit("30/minute")
async def get_perfil(request: Request):
    """Perfil de comunidad del usuario logueado."""
    email, err = _require_auth_user(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        from db import get_pool
        import repositories as repo
        pool = get_pool()
        perfil = await repo.get_perfil(pool, email)
        if perfil is None:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        # Si el perfil aún no se ha completado, sugerir valores desde los análisis
        prefill = {}
        if not perfil.get("perfil_completo"):
            user = await repo.get_user_by_email(pool, email)
            if user:
                labels = await repo.perfil_prefill_labels(pool, user["id"])
                exp_label = (labels.get("experiencia_label") or "").strip().lower()
                exp_value = _LABEL_A_VALUE_EXPERIENCIA.get(exp_label)
                estilos = []
                for gl in labels.get("genero_labels", []):
                    v = _LABEL_A_VALUE_GENERO.get((gl or "").strip().lower())
                    if v and v != "otro" and v not in estilos:
                        estilos.append(v)
                prefill = {"perfil_experiencia": exp_value, "perfil_estilos": estilos}
        return {
            "perfil": perfil,
            "prefill": prefill,
            "publicado_opciones": PERFIL_PUBLICADO_OPCIONES,
        }
    except Exception as e:
        print(f"[PERFIL GET] {e}")
        return JSONResponse(status_code=500, content={"error": "Error obteniendo el perfil"})


@app.post("/api/perfil")
@limiter.limit("15/minute")
async def post_perfil(request: Request, data: dict):
    """Guarda el perfil de comunidad. Body: perfil_experiencia, perfil_estilos
    (lista de values), perfil_publicado, perfil_donde, perfil_bio."""
    email, err = _require_auth_user(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    # Saneado: estilos máximo 8, cada uno corto; textos acotados
    estilos = data.get("perfil_estilos") or []
    if not isinstance(estilos, list):
        estilos = []
    estilos = [str(e)[:40] for e in estilos][:8]
    publicado = data.get("perfil_publicado") or None
    if publicado and publicado not in PERFIL_PUBLICADO_OPCIONES:
        publicado = None
    datos = {
        "perfil_experiencia": (data.get("perfil_experiencia") or None),
        "perfil_estilos": estilos,
        "perfil_publicado": publicado,
        "perfil_donde": _sanitize(data.get("perfil_donde", ""), 200) or None,
        "perfil_bio": _sanitize(data.get("perfil_bio", ""), 500) or None,
    }
    try:
        from db import get_pool
        import repositories as repo
        ok = await repo.upsert_perfil(get_pool(), email, datos)
        if not ok:
            return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
        return {"ok": True}
    except Exception as e:
        print(f"[PERFIL POST] {e}")
        return JSONResponse(status_code=500, content={"error": "Error guardando el perfil"})


# =========================================================================
# Comunidad — compartir tracks para feedback entre productores (v0.5.41)
# =========================================================================

# PRUEBAS PRIVADAS: la comunidad solo está activa para los emails de esta
# allowlist (env COMUNIDAD_EMAILS, coma-separada; default solo Alex). Quita la
# variable o pon "*" para abrirla a todos cuando esté lista.
_COMUNIDAD_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("COMUNIDAD_EMAILS", "alexgn23@gmail.com").split(",")
    if e.strip()
}


def _comunidad_habilitada(email: str | None) -> bool:
    if "*" in _COMUNIDAD_EMAILS:
        return True
    return bool(email) and email.strip().lower() in _COMUNIDAD_EMAILS


def _require_comunidad(request: Request) -> tuple[str | None, JSONResponse | None]:
    """Auth + allowlist de la comunidad. Mientras esté en pruebas privadas,
    solo los emails permitidos pasan; el resto recibe 403 'comunidad_oculta'."""
    email, err = _require_auth_user(request)
    if err:
        return None, err
    if not _comunidad_habilitada(email):
        return None, JSONResponse(
            status_code=403,
            content={"error": "La comunidad está en pruebas privadas todavía.", "codigo": "comunidad_oculta"},
        )
    return email, None


# Referencias vivas a las tareas de aviso (evita que el GC las cancele)
_AVISO_TASKS: set = set()


async def _notificar_comentario(dueno_email: str, autor_username: str, titulo: str, texto: str) -> None:
    """Avisa por email al dueño de un track de que ha recibido un comentario.
    Fire-and-forget: cualquier fallo se loguea sin afectar al comentario."""
    if not _resend_disponible():
        return
    try:
        import resend
        import html as _html
        resend.api_key = RESEND_API_KEY
        autor = _html.escape(_sanitize(autor_username, 40))
        titulo_s = _html.escape(_sanitize(titulo, 120))
        # recorte del comentario para el preview del email
        extracto = texto if len(texto) <= 400 else texto[:400] + "…"
        extracto_html = _html.escape(extracto)
        url = f"{APP_BASE_URL}/comunidad"
        html = f"""<!DOCTYPE html><html lang="es"><body style="margin:0;background:#f4f4f5;padding:24px 12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="540" style="max-width:540px;background:#fff;border-radius:14px;padding:30px 28px" cellpadding="0" cellspacing="0"><tr><td>
  <p style="margin:0 0 14px;font-size:16px;color:#18181b"><strong>{autor}</strong> ha comentado tu track en la comunidad 🎧</p>
  <p style="margin:0 0 6px;font-size:14px;color:#71717a">Tu track: <strong style="color:#3f3f46">{titulo_s}</strong></p>
  <div style="margin:14px 0;padding:14px 16px;border-left:3px solid #25F464;background:#fafafa;border-radius:8px;font-size:15px;color:#3f3f46;line-height:1.55;white-space:pre-wrap">{extracto_html}</div>
  <a href="{url}" style="display:inline-block;margin-top:8px;padding:11px 20px;background:#18181b;color:#fff;border-radius:10px;text-decoration:none;font-size:14px;font-weight:600">Ver y responder en la comunidad</a>
  <p style="margin:24px 0 0;font-size:12px;color:#a1a1aa;border-top:1px solid #e4e4e7;padding-top:14px">Recibes este aviso porque compartiste un track en la comunidad de Mentotrack.</p>
</td></tr></table></td></tr></table></body></html>"""
        text = (f"{autor} ha comentado tu track \"{titulo_s}\" en la comunidad de Mentotrack.\n\n"
                f"\"{extracto}\"\n\nVer y responder: {url}\n")
        await asyncio.to_thread(resend.Emails.send, {
            "from": RESEND_FROM,
            "to": dueno_email,
            "subject": f"💬 {autor} ha comentado tu track en la comunidad",
            "html": html,
            "text": text,
        })
        print(f"[COMUNIDAD] aviso de comentario enviado a {dueno_email}")
    except Exception as e:
        print(f"[COMUNIDAD] aviso de comentario falló: {type(e).__name__}: {e}")


# Cap propio para audio compartido: 80 MB cabe un WAV 16-bit de ~7,5 min y
# cualquier MP3. (El análisis admite 150 MB, pero el audio compartido se
# almacena en el volumen de 5 GB — el cap cuida el espacio.)
_AUDIO_COMUNIDAD_MAX = 80 * 1024 * 1024
_MIME_AUDIO = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
    ".aiff": "audio/aiff", ".aif": "audio/aiff", ".ogg": "audio/ogg",
}


def _audio_comunidad_dir() -> Path:
    """Directorio de audio compartido: el volumen persistente de Railway en
    prod (RAILWAY_VOLUME_MOUNT_PATH=/data), tmp en local."""
    base = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.environ.get("AUDIO_DIR") or tempfile.gettempdir()
    d = Path(base) / "comunidad"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _calcular_waveform(path: str, n_picos: int = 240):
    """Picos RMS normalizados 0-1 (para pintar la forma de onda en cliente)
    + duración en segundos. Carga a 11 kHz mono — rápido y suficiente."""
    import librosa as _lr
    import numpy as _np
    y, sr = _lr.load(path, sr=11025, mono=True)
    if len(y) == 0:
        return [], 0.0
    dur = float(len(y)) / sr
    bloque = max(1, len(y) // n_picos)
    picos = []
    for i in range(0, min(len(y), bloque * n_picos), bloque):
        seg = y[i:i + bloque]
        if len(seg) == 0:
            break
        picos.append(float(_np.sqrt(_np.mean(seg ** 2))))
    mx = max(picos) if picos else 1.0
    if mx <= 0:
        mx = 1.0
    return [round(p / mx, 3) for p in picos], dur


# Un MP3 ya pequeño se guarda tal cual (no re-comprimir lossy→lossy);
# todo lo demás (WAV/FLAC/AIFF/OGG o MP3 enorme) se transcodifica a MP3 320,
# ~10x menos peso en el volumen y mejor streaming. Umbral: 30 MB.
_MP3_PASSTHROUGH_MAX = 30 * 1024 * 1024


def _transcodificar_mp3(origen: str, destino: str) -> bool:
    """Convierte `origen` a MP3 320 kbps en `destino` con ffmpeg (ya está en
    el contenedor para librosa). Devuelve True si generó un MP3 válido."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", origen, "-vn", "-map", "a:0",
             "-codec:a", "libmp3lame", "-b:a", "320k", destino],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180,
        )
        return r.returncode == 0 and os.path.isfile(destino) and os.path.getsize(destino) > 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def _parse_float(s, lo=None, hi=None):
    try:
        v = float(str(s).strip())
    except (ValueError, TypeError):
        return None
    # NaN/inf pasarían los límites (NaN < x es False) y romperían el JSON del listado
    if v != v or v in (float("inf"), float("-inf")):
        return None
    if lo is not None and v < lo:
        return None
    if hi is not None and v > hi:
        return None
    return v


@app.get("/api/comunidad/habilitada")
@limiter.limit("60/minute")
async def comunidad_habilitada_endpoint(request: Request):
    """¿Puede el usuario actual ver/usar la comunidad? (pruebas privadas).
    El frontend oculta toda la UI de comunidad si devuelve false."""
    email = _optional_auth_user(request)
    return {"habilitada": _comunidad_habilitada(email)}


@app.post("/api/comunidad/compartir")
@limiter.limit("10/hour")
async def comunidad_compartir(
    request: Request,
    audio: UploadFile = File(...),
    titulo: str = Form(...),
    estilo: str = Form(""),
    estilo_custom: str = Form(""),
    bpm: str = Form(""),
    objetivo: str = Form(""),
    lufs: str = Form(""),
    balance: str = Form(""),
    mono_correlacion: str = Form(""),
    mono_nivel: str = Form(""),
    estado_track: str = Form(""),
    descargo: str = Form(""),
):
    """Comparte un track con la comunidad. Requiere sesión + perfil completo
    + aceptar el descargo de autoría. El audio queda en el volumen y los
    datos objetivos del análisis acompañan al post."""
    email, err = _require_comunidad(request)
    if err:
        return err
    if descargo not in ("si", "true", "1"):
        return JSONResponse(status_code=400, content={"error": "Debes aceptar las condiciones para compartir."})
    titulo = _sanitize(titulo, 120)
    if len(titulo) < 2:
        return JSONResponse(status_code=400, content={"error": "Ponle un título al track (mínimo 2 caracteres)."})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})

    from db import get_pool
    import repositories as repo
    pool = get_pool()
    user = await repo.get_user_by_email(pool, email)
    if not user:
        return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
    perfil = await repo.get_perfil(pool, email)
    if not perfil or not perfil.get("perfil_completo"):
        return JSONResponse(
            status_code=403,
            content={"error": "Completa tu perfil de productor antes de compartir — es lo que da credibilidad a tu track y a tu feedback.", "codigo": "perfil_incompleto"},
        )

    # Reciprocidad + cuota: 1 track gratis siempre; para tener 2-3 a la vez
    # hay que haber dado feedback en tantos tracks de otros como tracks tengas
    # publicados. Da-para-recibir, y acota el volumen (máx 3).
    recip = await repo.reciprocidad_stats(pool, user["id"])
    if recip["activos"] >= 3:
        return JSONResponse(
            status_code=400,
            content={"error": "Ya tienes 3 tracks en la comunidad (el máximo). Retira alguno para compartir uno nuevo."},
        )
    if recip["comentados"] < recip["activos"]:
        faltan = recip["activos"] - recip["comentados"]
        return JSONResponse(
            status_code=403,
            content={
                "error": f"Ya tienes {recip['activos']} track(s) en la comunidad. Para compartir otro a la vez, primero deja feedback en {faltan} track(s) más de otros productores — aquí se da para recibir.",
                "codigo": "reciprocidad",
            },
        )

    content = await audio.read()
    extension, errv = _validar_audio_upload(audio.filename, content)
    if errv:
        return errv
    if len(content) > _AUDIO_COMUNIDAD_MAX:
        return JSONResponse(
            status_code=413,
            content={"error": f"Para compartir, el archivo puede pesar máximo 80 MB (el tuyo: {len(content) // (1024*1024)} MB). Expórtalo en MP3 320 y listo."},
        )

    # Directorio del volumen: si no está disponible (permisos/montaje),
    # responder claro en vez de un 500 sin gestionar
    try:
        destino = _audio_comunidad_dir()
        libre = shutil.disk_usage(destino).free
    except OSError as e:
        print(f"[COMUNIDAD] volumen no disponible: {type(e).__name__}: {e}")
        return JSONResponse(status_code=503, content={"error": "El almacenamiento de la comunidad no está disponible ahora mismo. Inténtalo en un rato."})
    # Espacio libre: si queda poco, parar ANTES de escribir
    # (un volumen lleno rompería la feature para todos)
    if libre < max(len(content) * 2, 250 * 1024 * 1024):
        print(f"[COMUNIDAD] volumen casi lleno ({libre // (1024*1024)} MB libres) — upload rechazado")
        return JSONResponse(status_code=503, content={"error": "El almacenamiento de la comunidad está temporalmente lleno. Inténtalo más tarde."})

    # Escribir el original en un tmp EFÍMERO (no en el volumen) para validar
    # duración y transcodificar. El volumen solo recibirá el MP3 final.
    tmp_dir = tempfile.mkdtemp()
    tmp_orig = os.path.join(tmp_dir, f"orig{extension}")
    try:
        with open(tmp_orig, "wb") as f:
            f.write(content)
    except OSError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[COMUNIDAD] error guardando tmp: {e}")
        return JSONResponse(status_code=500, content={"error": "No se pudo procesar el audio. Inténtalo de nuevo."})
    orig_bytes = len(content)
    content = None  # liberar RAM

    fname = audio_mime = None
    audio_bytes = orig_bytes
    try:
        # Duración razonable (8 s – 20 min): acota el coste de transcode/waveform
        # y evita que un MP3/OGG de horas (cabe en 80 MB) cuelgue el worker
        try:
            import librosa as _lr
            dur_chk = _lr.get_duration(path=tmp_orig)
        except Exception:
            dur_chk = 0
        if dur_chk < 8 or dur_chk > 20 * 60:
            return JSONResponse(
                status_code=400,
                content={"error": "La duración del track debe estar entre 8 segundos y 20 minutos."},
            )

        loop = asyncio.get_event_loop()
        fname = f"{uuid.uuid4().hex}.mp3"
        fpath = destino / fname
        # MP3 ya pequeño → tal cual. Resto → transcode a MP3 320.
        if extension == ".mp3" and orig_bytes <= _MP3_PASSTHROUGH_MAX:
            shutil.move(tmp_orig, fpath)
            audio_mime = "audio/mpeg"
        else:
            ok = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _transcodificar_mp3(tmp_orig, str(fpath))),
                timeout=200,
            )
            if ok:
                audio_mime = "audio/mpeg"
                audio_bytes = fpath.stat().st_size
            else:
                # Fallback: guardar el original (su extensión real) para no
                # bloquear al usuario por un fallo de ffmpeg (raro)
                print(f"[COMUNIDAD] transcode falló, guardando original ({extension})")
                fname = f"{uuid.uuid4().hex}{extension}"
                fpath = destino / fname
                shutil.move(tmp_orig, fpath)
                audio_mime = _MIME_AUDIO.get(extension, "application/octet-stream")
                audio_bytes = fpath.stat().st_size
    except asyncio.TimeoutError:
        print("[COMUNIDAD] transcode timeout")
        return JSONResponse(status_code=400, content={"error": "El audio tardó demasiado en procesarse. Prueba con un archivo más corto o ya en MP3."})
    except OSError as e:
        print(f"[COMUNIDAD] error de E/S guardando audio: {e}")
        return JSONResponse(status_code=500, content={"error": "No se pudo guardar el audio. Inténtalo de nuevo."})
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Forma de onda sobre el archivo final (si falla, el post sale sin onda)
    waveform, dur = [], None
    try:
        loop = asyncio.get_event_loop()
        waveform, dur = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _calcular_waveform(str(fpath))),
            timeout=60,
        )
    except Exception as e:
        print(f"[COMUNIDAD] waveform falló ({fname}): {type(e).__name__}: {e}")

    bpm_v = _parse_float(bpm, 40, 300)
    datos = {
        "usuario_id": user["id"],
        "titulo": titulo,
        "estilo": _sanitize(estilo, 40) or None,
        "estilo_custom": _sanitize(estilo_custom, 60) or None,
        "bpm": int(bpm_v) if bpm_v else None,
        "objetivo": _sanitize(objetivo, 20) or None,
        "lufs": _parse_float(lufs, -60, 0),
        "balance": _sanitize(balance, 30) or None,
        "mono_correlacion": _parse_float(mono_correlacion, -1, 1),
        "mono_nivel": _sanitize(mono_nivel, 30) or None,
        "estado_track": _sanitize(estado_track, 40) or None,
        "duracion_seg": dur,
        "waveform": waveform,
        "audio_file": fname,
        "audio_mime": audio_mime,
        "audio_bytes": audio_bytes,
        "descargo_aceptado": True,
        "analisis_id": None,
    }
    try:
        row = await repo.crear_comunidad_post(pool, datos)
    except Exception as e:
        print(f"[COMUNIDAD] error insertando post: {type(e).__name__}: {e}")
        fpath.unlink(missing_ok=True)  # no dejar audio huérfano
        return JSONResponse(status_code=500, content={"error": "No se pudo publicar el track. Inténtalo de nuevo."})
    return {"ok": True, "post_id": str(row["id"])}


@app.get("/api/comunidad/posts")
@limiter.limit("30/minute")
async def comunidad_posts(request: Request, estilo: str = "", limit: int = 50):
    """Muro de la comunidad: posts activos con el distintivo del autor.
    En pruebas privadas: solo la allowlist (el resto, lista vacía)."""
    if not _comunidad_habilitada(_optional_auth_user(request)):
        return {"posts": [], "oculta": True}
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    from db import get_pool
    import repositories as repo
    rows = await repo.list_comunidad_posts(get_pool(), estilo.strip() or None, max(1, min(limit, 100)))
    posts = []
    for r in rows:
        posts.append({
            "id": str(r["id"]),
            "timestamp": r["timestamp"].isoformat() if r.get("timestamp") else None,
            "titulo": r["titulo"],
            "estilo": r.get("estilo"),
            "estilo_custom": r.get("estilo_custom"),
            "bpm": r.get("bpm"),
            "objetivo": r.get("objetivo"),
            "lufs": r.get("lufs"),
            "balance": r.get("balance"),
            "mono_correlacion": r.get("mono_correlacion"),
            "mono_nivel": r.get("mono_nivel"),
            "estado_track": r.get("estado_track"),
            "duracion_seg": r.get("duracion_seg"),
            "waveform": r.get("waveform") or [],
            "n_comentarios": int(r.get("n_comentarios") or 0),
            "autor": {
                "username": r.get("username") or "productor",
                "experiencia": r.get("perfil_experiencia"),
                "estilos": r.get("perfil_estilos") or [],
                "publicado": r.get("perfil_publicado"),
                "donde": r.get("perfil_donde"),
                "bio": r.get("perfil_bio"),
                "utiles": int(r.get("autor_utiles") or 0),
            },
        })
    return {"posts": posts}


@app.get("/api/comunidad/audio/{post_id}")
@limiter.limit("120/minute")
async def comunidad_audio(request: Request, post_id: str):
    """Sirve el audio de un post con soporte de rangos HTTP (Safari/iOS lo
    exigen para reproducir, y permite hacer seek sin descargar todo)."""
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        pid = uuid.UUID(post_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    from db import get_pool
    import repositories as repo
    post = await repo.get_comunidad_post(get_pool(), pid)
    if not post:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    try:
        fpath = _audio_comunidad_dir() / post["audio_file"]
        if not fpath.is_file():
            return JSONResponse(status_code=404, content={"error": "Audio no disponible"})
    except OSError:
        return JSONResponse(status_code=503, content={"error": "Almacenamiento no disponible"})

    file_size = fpath.stat().st_size
    media_type = post.get("audio_mime") or "application/octet-stream"
    range_header = request.headers.get("range", "")
    start, end, status = 0, file_size - 1, 200
    if range_header.startswith("bytes="):
        # RFC 7233: un Range sintácticamente inválido se IGNORA (200 completo);
        # solo un rango bien formado pero fuera del archivo devuelve 416.
        rng = range_header[6:].split(",")[0].strip()
        s, _, e = rng.partition("-")
        try:
            if s:
                rs = int(s)
                re_ = int(e) if e else file_size - 1
                if rs >= file_size:
                    return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
                if rs <= re_:
                    start, end, status = rs, min(re_, file_size - 1), 206
            elif e:
                n = int(e)
                if n > 0:
                    start, status = max(0, file_size - n), 206
        except ValueError:
            start, end, status = 0, file_size - 1, 200

    total = end - start + 1

    def iterfile(s=start, restante=total):
        with open(fpath, "rb") as f:
            f.seek(s)
            while restante > 0:
                data = f.read(min(256 * 1024, restante))
                if not data:
                    break
                restante -= len(data)
                yield data

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(total),
        "Cache-Control": "private, max-age=3600",
        # identity evita que GZipMiddleware comprima el stream (rompería la
        # semántica de Content-Range/Content-Length para el reproductor)
        "Content-Encoding": "identity",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return StreamingResponse(iterfile(), status_code=status, media_type=media_type, headers=headers)


@app.delete("/api/comunidad/posts/{post_id}")
@limiter.limit("10/minute")
async def comunidad_borrar(request: Request, post_id: str):
    """El autor retira su track de la comunidad (soft-delete + borra el audio)."""
    email, err = _require_comunidad(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        pid = uuid.UUID(post_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    from db import get_pool
    import repositories as repo
    pool = get_pool()
    user = await repo.get_user_by_email(pool, email)
    if not user:
        return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
    audio_file = await repo.desactivar_comunidad_post(pool, pid, user["id"])
    if audio_file is None:
        return JSONResponse(status_code=404, content={"error": "No encontrado o no es tuyo"})
    try:
        (_audio_comunidad_dir() / audio_file).unlink(missing_ok=True)
    except OSError as e:
        print(f"[COMUNIDAD] no se pudo borrar el audio {audio_file}: {e}")
    return {"ok": True}


# ---- Comentarios (feedback entre productores) -------------------------------

def _comentario_autor_dict(r: dict, viewer_id=None, post_owner_id=None) -> dict:
    """Serializa un comentario con el distintivo del autor. Marca es_autor
    (el viewer lo escribió → puede borrar) y la respuesta del endpoint indica
    a nivel de post si el viewer puede marcar útil (es dueño del track)."""
    return {
        "id": str(r["id"]),
        "timestamp": r["timestamp"].isoformat() if r.get("timestamp") else None,
        "texto": r["texto"],
        "util": bool(r.get("util")),
        "es_autor": viewer_id is not None and r.get("usuario_id") == viewer_id,
        "autor": {
            "username": r.get("username") or "productor",
            "experiencia": r.get("perfil_experiencia"),
            "estilos": r.get("perfil_estilos") or [],
            "publicado": r.get("perfil_publicado"),
            "utiles": int(r.get("autor_utiles") or 0),
        },
    }


@app.get("/api/comunidad/posts/{post_id}/comentarios")
@limiter.limit("60/minute")
async def comunidad_listar_comentarios(request: Request, post_id: str):
    """Comentarios de un track. En pruebas privadas: solo la allowlist.
    Con sesión, marca cuáles son tuyos y si eres el dueño del track."""
    if not _comunidad_habilitada(_optional_auth_user(request)):
        return JSONResponse(status_code=403, content={"error": "La comunidad está en pruebas privadas.", "codigo": "comunidad_oculta"})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        pid = uuid.UUID(post_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    from db import get_pool
    import repositories as repo
    pool = get_pool()
    post = await repo.get_comunidad_post(pool, pid)
    if not post:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    viewer_id = None
    email = _optional_auth_user(request)
    if email:
        u = await repo.get_user_by_email(pool, email)
        viewer_id = u["id"] if u else None
    es_dueno = viewer_id is not None and viewer_id == post["usuario_id"]
    rows = await repo.list_comentarios(pool, pid)
    return {
        "comentarios": [_comentario_autor_dict(r, viewer_id, post["usuario_id"]) for r in rows],
        "puedo_marcar_util": es_dueno,
        "es_mi_track": es_dueno,
    }


@app.post("/api/comunidad/posts/{post_id}/comentarios")
@limiter.limit("20/hour")
async def comunidad_crear_comentario(request: Request, post_id: str, data: dict):
    """Deja feedback en un track. Requiere sesión + perfil completo (tu
    distintivo da credibilidad). No puedes comentar tu propio track."""
    email, err = _require_comunidad(request)
    if err:
        return err
    texto = _sanitize(data.get("texto", ""), 1500)
    if len(texto) < 3:
        return JSONResponse(status_code=400, content={"error": "Escribe un comentario (mínimo 3 caracteres)."})
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        pid = uuid.UUID(post_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    from db import get_pool
    import repositories as repo
    pool = get_pool()
    user = await repo.get_user_by_email(pool, email)
    if not user:
        return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
    perfil = await repo.get_perfil(pool, email)
    if not perfil or not perfil.get("perfil_completo"):
        return JSONResponse(
            status_code=403,
            content={"error": "Completa tu perfil de productor antes de comentar — da credibilidad a tu feedback.", "codigo": "perfil_incompleto"},
        )
    post = await repo.get_comunidad_post(pool, pid)
    if not post:
        return JSONResponse(status_code=404, content={"error": "Este track ya no está disponible."})
    if post["usuario_id"] == user["id"]:
        return JSONResponse(status_code=400, content={"error": "No puedes comentar tu propio track."})
    row = await repo.crear_comentario(pool, pid, user["id"], texto)
    if row is None:
        return JSONResponse(status_code=404, content={"error": "Este track ya no está disponible."})
    # Avisar al dueño del track por email (fire-and-forget: no bloquea la respuesta).
    # Guardamos referencia a la tarea para que el GC no la cancele antes de tiempo.
    try:
        dueno = await repo.get_user_by_id(pool, post["usuario_id"])
        if dueno and dueno.get("email"):
            _t = asyncio.create_task(_notificar_comentario(
                dueno["email"], (user.get("username") or "Un productor"),
                post.get("titulo") or "tu track", texto,
            ))
            _AVISO_TASKS.add(_t)
            _t.add_done_callback(_AVISO_TASKS.discard)
    except Exception as e:
        print(f"[COMUNIDAD] no se pudo programar el aviso de comentario: {e}")
    return {"ok": True, "comentario_id": str(row["id"])}


@app.delete("/api/comunidad/comentarios/{comentario_id}")
@limiter.limit("20/minute")
async def comunidad_borrar_comentario(request: Request, comentario_id: str):
    """El autor borra su comentario."""
    email, err = _require_comunidad(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        cid = uuid.UUID(comentario_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    from db import get_pool
    import repositories as repo
    pool = get_pool()
    user = await repo.get_user_by_email(pool, email)
    if not user:
        return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
    ok = await repo.borrar_comentario(pool, cid, user["id"])
    if not ok:
        return JSONResponse(status_code=404, content={"error": "No encontrado o no es tuyo"})
    return {"ok": True}


@app.post("/api/comunidad/comentarios/{comentario_id}/util")
@limiter.limit("60/minute")
async def comunidad_marcar_util(request: Request, comentario_id: str):
    """El dueño del track marca/desmarca un comentario como 'me ayudó'."""
    email, err = _require_comunidad(request)
    if err:
        return err
    if not _pg_available():
        return JSONResponse(status_code=503, content={"error": "Base de datos no disponible"})
    try:
        cid = uuid.UUID(comentario_id)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "No encontrado"})
    from db import get_pool
    import repositories as repo
    pool = get_pool()
    user = await repo.get_user_by_email(pool, email)
    if not user:
        return JSONResponse(status_code=404, content={"error": "Usuario no encontrado"})
    nuevo = await repo.marcar_comentario_util(pool, cid, user["id"])
    if nuevo is None:
        return JSONResponse(status_code=403, content={"error": "Solo el dueño del track puede marcar útil un comentario."})
    return {"ok": True, "util": nuevo}


# =========================================================================
# Frontend — servir el SPA
# =========================================================================

@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


# Extensiones de assets inmutables → cache largo (7 días)
_CACHEABLE_EXT = {".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".png", ".jpg", ".svg", ".ico", ".webp"}


def _file_response_with_cache(file_path: Path) -> FileResponse:
    """FileResponse con Cache-Control según extensión."""
    ext = file_path.suffix.lower()
    if ext in _CACHEABLE_EXT:
        # Assets estáticos: 7 días de cache en navegador
        return FileResponse(file_path, headers={"Cache-Control": "public, max-age=604800, immutable"})
    # HTML y otros: no cachear (siempre fresco)
    return FileResponse(file_path, headers={"Cache-Control": "no-cache"})


@app.get("/{full_path:path}")
def serve_catch_all(full_path: str):
    """Catch-all para SPA: si no es /api, devuelve index.html."""
    # Bloquear acceso a archivos/directorios ocultos (.git, .env, etc.)
    if any(part.startswith('.') for part in full_path.split('/')):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    # Bloquear paths peligrosos (wp-*, etc.)
    if full_path.startswith(('wp-', 'wp/', 'xmlrpc', 'admin', 'phpmyadmin')):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    # Proteger acceso directo al archivo dashboard.html y calibrar.html
    if "dashboard" in full_path.lower() or "calibrar" in full_path.lower():
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    file_path = (FRONTEND_DIR / full_path).resolve()
    # Path traversal protection: must stay within frontend dir
    if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if file_path.is_file():
        return _file_response_with_cache(file_path)
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})
