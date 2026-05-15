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
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, HTMLResponse
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


def _load_engine():
    """Carga los módulos pesados de análisis de audio bajo demanda."""
    global _extraer_senales, _generar_diagnostico
    if _extraer_senales is None:
        from engine.extractor import extraer_senales
        from engine.diagnostico import generar_diagnostico
        _extraer_senales = extraer_senales
        _generar_diagnostico = generar_diagnostico

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Mentotrack API", version="0.4.1")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    allow_methods=["GET", "POST"],
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
            "img-src 'self' data: https://www.googletagmanager.com https://img.youtube.com https://i.ytimg.com https://i3.ytimg.com; "
            "connect-src 'self' https://www.google-analytics.com https://analytics.google.com https://*.google-analytics.com https://*.analytics.google.com; "
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


# Google Sheets webhook (env var only, no hardcoded URL)
SHEETS_WEBHOOK = os.environ.get("SHEETS_WEBHOOK", "")
if not SHEETS_WEBHOOK:
    print("[WARN] SHEETS_WEBHOOK no configurado — las funciones de Google Sheets no funcionarán")

# Almacenamiento simple de sesiones (JSON lines)
SESIONES_PATH = os.environ.get("SESIONES_PATH", "sesiones.jsonl")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.4.2"}


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
):
    """
    Recibe un archivo de audio + contexto del cuestionario.
    Retorna un diagnóstico estructurado.
    """
    # Validar extensión
    extension = os.path.splitext(audio.filename or "")[1].lower()
    if extension not in [".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg"]:
        return JSONResponse(
            status_code=400,
            content={"error": f"Formato no soportado: {extension}. Usa MP3, WAV, FLAC o AIFF."}
        )

    # Leer contenido y validar tamaño (máx 100 MB para prevenir OOM crashes)
    MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
    content = await audio.read()
    if len(content) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": f"Archivo demasiado grande ({len(content) // (1024*1024)} MB). Máximo: 100 MB. Puedes convertir a MP3 para reducir el tamaño."}
        )

    # Validar magic bytes — confirmar que el archivo es audio real, no solo extensión
    # Previene que alguien renombre un ejecutable a .mp3
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
    header = content[:4]
    is_valid_audio = any(header.startswith(sig) for sig in _AUDIO_SIGNATURES)
    if not is_valid_audio:
        return JSONResponse(
            status_code=415,
            content={"error": "El archivo no parece ser audio válido. Asegúrate de subir un MP3, WAV, FLAC o AIFF real."}
        )

    # Guardar archivo temporal
    session_id = str(uuid.uuid4())[:8]
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, f"{session_id}{extension}")

    try:
        with open(tmp_path, "wb") as f:
            f.write(content)

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

        # Guardar sesión para análisis futuro
        sesion = {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "contexto": contexto,
            "senales": {k: v for k, v in senales.items() if k != "bloques_rms"},
            "resultado": resultado,
        }
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
    return {
        "generos": [
            {"value": "tech_house", "label": "Tech House"},
            {"value": "house", "label": "House"},
            {"value": "techno", "label": "Techno"},
            {"value": "techno_acido", "label": "Techno ácido"},
            {"value": "hard_techno", "label": "Hard Techno"},
            {"value": "minimal", "label": "Minimal"},
            {"value": "progressive_house", "label": "Progressive House"},
            {"value": "trance", "label": "Trance"},
            {"value": "psytrance", "label": "Psytrance"},
            {"value": "melodic_techno", "label": "Melodic Techno"},
            {"value": "deep_house", "label": "Deep House"},
            {"value": "afro_house", "label": "Afro House"},
            {"value": "indie_dance", "label": "Indie Dance"},
            {"value": "breaks", "label": "Breaks"},
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


# =========================================================================
# Proxy de Google Sheets — el frontend NUNCA debe conocer la URL del script
# =========================================================================

async def _sheets_post(payload: dict) -> dict:
    """Hace POST al Apps Script con datos en el body (no en query params)."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEETS_WEBHOOK, json=payload, timeout=15)
            try:
                return resp.json()
            except Exception:
                # Apps Script legacy devuelve texto plano "ok", no JSON
                return {"ok": True, "raw": resp.text[:100]}
    except Exception as e:
        print(f"[SHEETS POST] Error: {e}")
        return {"error": str(e)}


@app.post("/api/sheets/registro")
@limiter.limit("5/minute")
async def proxy_sheets_registro(request: Request, data: dict):
    """Proxy: envía datos de registro/diagnóstico a Google Sheets."""
    payload = {
        "tipo": "registro",
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
        "email": data.get("email", ""),
        "nombre_proyecto": data.get("nombre_proyecto", ""),
        "formulario": data.get("formulario", ""),
        "diagnostico": data.get("diagnostico", ""),
        "senales_json": data.get("senales_json", ""),
        "genero_custom": data.get("genero_custom", ""),
    }
    result = await _sheets_post(payload)
    return {"ok": True}


@app.post("/api/sheets/feedback")
@limiter.limit("10/minute")
async def proxy_sheets_feedback(request: Request, data: dict):
    """Proxy: envía feedback de utilidad a Google Sheets."""
    payload = {
        "tipo": "feedback_util",
        "email": data.get("email", ""),
        "fue_util": data.get("fue_util", ""),
        "comentario": data.get("comentario", ""),
    }
    result = await _sheets_post(payload)
    return {"ok": True}


@app.post("/api/sheets/feedback-real")
@limiter.limit("5/minute")
async def proxy_sheets_feedback_real(request: Request, data: dict):
    """Proxy: envía enlace de feedback real a Google Sheets."""
    payload = {
        "tipo": "feedback_real",
        "email": data.get("email", ""),
        "enlace": data.get("enlace", ""),
    }
    result = await _sheets_post(payload)
    return {"ok": True}


@app.post("/api/sheets/tutorial-click")
@limiter.limit("20/minute")
async def proxy_sheets_tutorial_click(request: Request):
    """Proxy: registra click en tutorial de YouTube en Google Sheets.
    Parsea body manualmente para soportar sendBeacon (que puede no
    enviar Content-Type: application/json correctamente)."""
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
    except Exception:
        data = {}
    payload = {
        "tipo": "tutorial_click",
        "email": data.get("email", ""),
        "diagnostico_id": data.get("diagnostico_id", ""),
        "tutorial_clickado": data.get("tutorial_clickado", ""),
        "tutoriales_sugeridos": data.get("tutoriales_sugeridos", ""),
    }
    result = await _sheets_post(payload)
    return {"ok": True}


@app.get("/api/sheets/datos")
@limiter.limit("5/minute")
async def proxy_sheets_datos(request: Request):
    """Proxy: obtiene todos los datos de Sheets para el dashboard admin.
    Solo acepta auth via cookie HttpOnly (no query params para evitar leaks)."""
    admin_cookie = request.cookies.get("admin_session", "")
    if not _verify_admin_token(admin_cookie):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    try:
        result = await _sheets_get({"action": "get_all"})
        if result.get("_connection_error"):
            return JSONResponse(status_code=503, content={"error": "Error conectando con la base de datos"})
        return result
    except Exception as e:
        print(f"[ERROR] sheets datos: {e}")
        return JSONResponse(status_code=503, content={"error": "Error conectando con la base de datos"})


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


async def _obtener_historial_sheets(email: str) -> list:
    """Obtiene el historial del usuario desde Google Sheets via POST."""
    try:
        result = await _sheets_get({"action": "get_all"})
        if result.get("_connection_error"):
            print(f"[HISTORIAL] Error de conexión: {result['_connection_error']}")
            return []
        all_rows = result.get("data", [])
    except Exception as e:
        print(f"[HISTORIAL] Error: {e}")
        all_rows = []
    return [r for r in all_rows if (r.get("email") or "").strip().lower() == email]


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

    if not SHEETS_WEBHOOK:
        return JSONResponse(status_code=503, content={"error": "Servicio no configurado."})

    # Normalizar identifier: si es email, lowercase; si es username, validar formato
    is_email = _looks_like_email(identifier)
    if is_email:
        identifier = identifier.lower()
    else:
        identifier = identifier.lstrip("@")
        if not _valid_username(identifier):
            return JSONResponse(status_code=400, content={"error": "Nombre de usuario inválido"})

    user_data = await _sheets_get({"action": "get_user_by_identifier", "identifier": identifier})
    if user_data.get("_connection_error"):
        return JSONResponse(status_code=503, content={"error": "No se pudo conectar con la base de datos."})

    if not user_data.get("found"):
        # Mensaje genérico para no revelar si existe o no
        return JSONResponse(status_code=401, content={"error": "Credenciales incorrectas"})

    if not _verify_password(password, user_data.get("password_hash", "")):
        return JSONResponse(status_code=401, content={"error": "Credenciales incorrectas"})

    email = user_data.get("email", "").strip().lower()
    username = (user_data.get("username") or "").strip()
    historial = await _obtener_historial_sheets(email)
    token = _create_token(email)
    return {
        "ok": True,
        "email": email,
        "username": username,
        "token": token,
        "historial": historial,
        "needs_username": not bool(username),  # migración: usuario sin username
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

    if not SHEETS_WEBHOOK:
        return JSONResponse(status_code=503, content={"error": "Servicio no configurado."})

    hashed = _hash_password(password)
    result = await _sheets_get({
        "action": "register",
        "email": email,
        "username": username,
        "hash": hashed,
    })

    if result.get("_connection_error"):
        return JSONResponse(status_code=503, content={"error": "No se pudo conectar con la base de datos."})

    if not result.get("ok"):
        err = result.get("error", "")
        if err == "El usuario ya existe":
            return JSONResponse(status_code=409, content={"error": "Ese email ya está registrado."})
        if err == "Username no disponible":
            return JSONResponse(status_code=409, content={"error": "Ese nombre de usuario ya está cogido."})
        return JSONResponse(status_code=400, content={"error": err or "No se pudo registrar"})

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
    if not SHEETS_WEBHOOK:
        return {"ok": False, "available": False, "error": "Servicio no configurado"}
    result = await _sheets_get({"action": "check_username", "username": username})
    if result.get("_connection_error"):
        return {"ok": False, "available": False, "error": "Error de conexión"}
    return {"ok": True, "available": bool(result.get("available"))}


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

    result = await _sheets_get({
        "action": "set_username",
        "email": email,
        "username": username,
    })
    if result.get("_connection_error"):
        return JSONResponse(status_code=503, content={"error": "No se pudo conectar con la base de datos."})
    if not result.get("ok"):
        err = result.get("error", "")
        if err == "Username no disponible":
            return JSONResponse(status_code=409, content={"error": "Ese nombre de usuario ya está cogido."})
        return JSONResponse(status_code=400, content={"error": err or "No se pudo asignar"})

    return {"ok": True, "username": username}


# -------------------------------------------------------------------------
# /api/auth/forgot — placeholder (recuperación manual por email)
# -------------------------------------------------------------------------
@app.post("/api/auth/forgot")
@limiter.limit("3/minute")
async def auth_forgot(request: Request, data: dict):
    """Placeholder: dirige al usuario a contactar por email para reset manual.
    Iteración futura: token único + email transaccional."""
    return {
        "ok": True,
        "message": (
            "Para recuperar el acceso, escríbenos a soporte@producciononline.com "
            "indicando el email con el que te registraste. Te ayudaremos manualmente."
        ),
        "contact_email": "soporte@producciononline.com",
    }


@app.post("/api/auth/acceder")
@limiter.limit("5/minute")
async def acceder(request: Request, data: dict):
    """
    DEPRECATED: endpoint unificado login/registro original.
    Mantenido para compatibilidad con frontend antiguo. Nuevos clientes deben usar
    /api/auth/login y /api/auth/register.

    - Si el email existe → verifica contraseña → devuelve historial
    - Si el email no existe → registra con la contraseña → devuelve historial vacío
    """
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Email inválido"})
    if len(password) < 8:
        return JSONResponse(status_code=400, content={"error": "La contraseña debe tener al menos 8 caracteres"})

    # Buscar si el usuario existe en el Sheet
    if not SHEETS_WEBHOOK:
        print("[ERROR] acceder: SHEETS_WEBHOOK no configurado")
        return JSONResponse(status_code=503, content={
            "error": "Servicio no configurado. Contacta al administrador."
        })

    user_data = await _sheets_get({"action": "get_user", "email": email})
    # Distinguir errores de conexión vs respuestas válidas del Apps Script
    # El Apps Script puede devolver {"found": false, "error": "No existe la pestaña usuarios"}
    # — eso no es un error de conexión, es que la pestaña aún no se ha creado
    if user_data.get("_connection_error"):
        print(f"[ERROR] acceder: Connection error = {user_data['_connection_error']}")
        return JSONResponse(status_code=503, content={
            "error": "No se pudo conectar con la base de datos. Inténtalo de nuevo en unos segundos."
        })

    if user_data.get("found"):
        # Usuario existe → verificar contraseña
        if not _verify_password(password, user_data.get("password_hash", "")):
            return JSONResponse(status_code=401, content={"error": "Contraseña incorrecta"})

        historial = await _obtener_historial_sheets(email)
        token = _create_token(email)
        return {"ok": True, "email": email, "token": token, "historial": historial, "nuevo": False}
    else:
        # Usuario nuevo → registrar
        hashed = _hash_password(password)
        result = await _sheets_get({"action": "register", "email": email, "hash": hashed})

        if not result.get("ok") and result.get("error") == "El usuario ya existe":
            return JSONResponse(status_code=409, content={"error": "El email ya está registrado. Prueba con tu contraseña."})

        historial = await _obtener_historial_sheets(email)
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

    historial = await _obtener_historial_sheets(token_email)
    return {"ok": True, "historial": historial}


# =========================================================================
# Ideas — sistema de votación de ideas de usuarios
# =========================================================================

@app.get("/api/ideas")
@limiter.limit("30/minute")
async def get_ideas(request: Request):
    """Obtiene todas las ideas ordenadas por votos."""
    result = await _sheets_get({"action": "get_ideas"})
    if result.get("_connection_error"):
        return JSONResponse(status_code=503, content={"error": "Error de conexión"})
    ideas = result.get("ideas", [])
    # Ordenar por votos descendente
    ideas.sort(key=lambda x: x.get("votos", 0), reverse=True)
    return {"ideas": ideas}


@app.post("/api/ideas")
@limiter.limit("5/minute")
async def create_idea(request: Request, data: dict):
    """Crea una nueva idea."""
    nombre = (data.get("nombre") or "").strip()
    titulo = (data.get("titulo") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()

    if not nombre or not titulo or not descripcion:
        return JSONResponse(status_code=400, content={"error": "Todos los campos son obligatorios"})
    if len(titulo) > 100:
        return JSONResponse(status_code=400, content={"error": "El título no puede superar 100 caracteres"})
    if len(descripcion) > 500:
        return JSONResponse(status_code=400, content={"error": "La descripción no puede superar 500 caracteres"})

    idea_id = str(uuid.uuid4())[:8]
    payload = {
        "action": "create_idea",
        "id": idea_id,
        "nombre": nombre,
        "titulo": titulo,
        "descripcion": descripcion,
        "fecha": datetime.now(timezone.utc).strftime("%d %b %Y"),
        "votos": 0,
    }
    result = await _sheets_get(payload)
    if result.get("_connection_error"):
        return JSONResponse(status_code=503, content={"error": "Error de conexión"})
    return {"ok": True, "id": idea_id}


@app.post("/api/ideas/{idea_id}/vote")
@limiter.limit("20/minute")
async def vote_idea(request: Request, idea_id: str, data: dict):
    """Vota una idea (up o down)."""
    delta = data.get("delta")
    if delta is None:
        voto = data.get("voto", "")
        if voto not in ("up", "down"):
            return JSONResponse(status_code=400, content={"error": "Voto debe ser 'up' o 'down'"})
        delta = 1 if voto == "up" else -1
    delta = max(-2, min(2, int(delta)))  # Limitar a [-2, 2]
    result = await _sheets_get({"action": "vote_idea", "id": idea_id, "delta": delta})
    if result.get("_connection_error"):
        return JSONResponse(status_code=503, content={"error": "Error de conexión"})
    return {"ok": True, "votos": result.get("votos", 0)}


# Ruta para servir la página de ideas
@app.get("/ideas")
def serve_ideas():
    ideas_path = FRONTEND_DIR / "ideas.html"
    if not ideas_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Página no encontrada"})
    return FileResponse(ideas_path, headers={"Cache-Control": "no-cache"})


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
    # Proteger acceso directo al archivo dashboard.html
    if "dashboard" in full_path.lower():
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    file_path = (FRONTEND_DIR / full_path).resolve()
    # Path traversal protection: must stay within frontend dir
    if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if file_path.is_file():
        return _file_response_with_cache(file_path)
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})
