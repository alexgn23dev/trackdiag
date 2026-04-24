"""
Mentotrack API — Backend FastAPI
Endpoint principal: POST /api/diagnostico
"""

import os
import uuid
import json
import secrets
import tempfile
import httpx
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from engine.extractor import extraer_senales
from engine.diagnostico import generar_diagnostico

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Mentotrack API", version="0.4.0")
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
    return {"status": "ok", "version": "0.4.0"}


@app.post("/api/diagnostico")
@limiter.limit("3/minute")
async def diagnosticar(
    request: Request,
    audio: UploadFile = File(...),
    genero: str = Form(...),
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
    # Validar formato
    extension = os.path.splitext(audio.filename or "")[1].lower()
    if extension not in [".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg"]:
        return JSONResponse(
            status_code=400,
            content={"error": f"Formato no soportado: {extension}. Usa MP3, WAV, FLAC o AIFF."}
        )

    # Guardar archivo temporal
    session_id = str(uuid.uuid4())[:8]
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, f"{session_id}{extension}")

    try:
        content = await audio.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        # Extraer señales (con BPM manual si se proporcionó)
        bpm_int = None
        if bpm_manual and bpm_manual.strip():
            try:
                bpm_int = int(float(bpm_manual.strip()))
            except ValueError:
                pass
        senales = extraer_senales(tmp_path, bpm_manual=bpm_int)

        # Construir contexto
        contexto = {
            "genero": genero,
            "fase": fase,
            "objetivo": objetivo,
            "bloqueo_percibido": bloqueo_percibido,
            "experiencia": experiencia,
            "dificultad_habitual": dificultad_habitual,
            "referencia": referencia,
            "tiempo_disponible": tiempo_disponible,
        }

        # Generar diagnóstico
        resultado = generar_diagnostico(senales, contexto)

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

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando el audio: {str(e)}"}
        )
    finally:
        # Limpiar archivo temporal
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if os.path.exists(tmp_dir):
            os.rmdir(tmp_dir)


@app.get("/api/opciones")
def opciones():
    """Retorna las opciones del cuestionario para el frontend."""
    return {
        "generos": [
            {"value": "tech_house", "label": "Tech House"},
            {"value": "house", "label": "House"},
            {"value": "techno", "label": "Techno"},
            {"value": "techno_acido", "label": "Techno ácido"},
            {"value": "minimal", "label": "Minimal"},
            {"value": "progressive_house", "label": "Progressive House"},
            {"value": "trance", "label": "Trance"},
            {"value": "progressive_trance", "label": "Progressive Trance"},
            {"value": "melodic_techno", "label": "Melodic Techno"},
            {"value": "deep_house", "label": "Deep House"},
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
            data = resp.json()
            return data
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


@app.get("/api/sheets/datos")
@limiter.limit("5/minute")
async def proxy_sheets_datos(request: Request, key: str = ""):
    """Proxy: obtiene todos los datos de Sheets para el dashboard admin."""
    admin_cookie = request.cookies.get("admin_session", "")
    if not _verify_admin_token(admin_cookie) and key != ADMIN_KEY:
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(SHEETS_WEBHOOK, timeout=15)
            return resp.json()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})


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
    """Envía operaciones al Apps Script via POST (datos sensibles en body, no en URL)."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(SHEETS_WEBHOOK, json=params, timeout=15)
            data = resp.json()
            # Si el Apps Script devuelve un array (no actualizado), tratarlo como error
            if isinstance(data, list):
                print(f"[SHEETS] Apps Script devolvió array en vez de objeto — ¿falta actualizar el script?")
                return {"error": "Apps Script no actualizado"}
            return data
    except Exception as e:
        print(f"[SHEETS] Error: {e}")
        return {"error": str(e)}


async def _obtener_historial_sheets(email: str) -> list:
    """Obtiene el historial del usuario desde Google Sheets."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(SHEETS_WEBHOOK, timeout=15)
            all_rows = resp.json()
    except Exception:
        all_rows = []
    return [r for r in all_rows if (r.get("email") or "").strip().lower() == email]


@app.post("/api/auth/acceder")
@limiter.limit("5/minute")
async def acceder(request: Request, data: dict):
    """
    Login/Registro unificado:
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
    user_data = await _sheets_get({"action": "get_user", "email": email})

    if user_data.get("error"):
        return JSONResponse(status_code=503, content={
            "error": "No se pudo conectar con la base de datos. Verifica que el Apps Script esté actualizado."
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
# Dashboard admin — ruta protegida con clave
# =========================================================================

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
if not ADMIN_KEY:
    ADMIN_KEY = secrets.token_hex(16)
    print(f"[WARN] ADMIN_KEY no configurado — generando uno aleatorio: {ADMIN_KEY}")

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
    """Dashboard admin protegido por cookie de sesión o clave inicial."""
    # Check cookie first
    admin_cookie = request.cookies.get("admin_session", "")
    if _verify_admin_token(admin_cookie):
        dashboard_path = FRONTEND_DIR / "dashboard.html"
        if not dashboard_path.is_file():
            return JSONResponse(status_code=404, content={"error": "Dashboard no encontrado"})
        return FileResponse(dashboard_path)

    # Fallback: check key param (only for initial login, will set cookie)
    if key == ADMIN_KEY:
        token = _create_admin_token()
        dashboard_path = FRONTEND_DIR / "dashboard.html"
        if not dashboard_path.is_file():
            return JSONResponse(status_code=404, content={"error": "Dashboard no encontrado"})
        response = FileResponse(dashboard_path)
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=43200,
        )
        return response

    return JSONResponse(status_code=403, content={"error": "Acceso denegado"})


# =========================================================================
# Frontend — servir el SPA
# =========================================================================

@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{full_path:path}")
def serve_catch_all(full_path: str):
    """Catch-all para SPA: si no es /api, devuelve index.html."""
    # Proteger acceso directo al archivo dashboard.html
    if "dashboard" in full_path.lower():
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    file_path = (FRONTEND_DIR / full_path).resolve()
    # Path traversal protection: must stay within frontend dir
    if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")
