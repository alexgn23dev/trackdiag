"""
Mentotrack API — Backend FastAPI
Endpoint principal: POST /api/diagnostico
"""

import os
import uuid
import json
import tempfile
import httpx
import bcrypt
from datetime import datetime
from urllib.parse import urlencode

from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from engine.extractor import extraer_senales
from engine.diagnostico import generar_diagnostico

app = FastAPI(title="Mentotrack API", version="0.3.0")

# Ruta al frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento simple de sesiones (JSON lines)
SESIONES_PATH = os.environ.get("SESIONES_PATH", "sesiones.jsonl")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.3.1"}


@app.post("/api/diagnostico")
async def diagnosticar(
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


@app.post("/api/feedback")
async def guardar_feedback(data: dict):
    """Guarda feedback de utilidad del usuario."""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
        "util": data.get("util"),
        "comentario": data.get("comentario", ""),
        "diagnostico": data.get("diagnostico", ""),
    }
    with open(FEEDBACK_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.post("/api/feedback-request")
async def guardar_feedback_request(data: dict):
    """Guarda solicitud de feedback real por Alex."""
    FEEDBACK_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
        "enlace": data.get("enlace", ""),
        "diagnostico_id": data.get("diagnostico_id", ""),
        "genero": data.get("genero", ""),
        "objetivo": data.get("objetivo", ""),
    }
    with open(FEEDBACK_REQUESTS_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}


# =========================================================================
# Auth — Registro/Login con contraseña (bcrypt + Google Sheets)
# =========================================================================

SHEETS_WEBHOOK = os.environ.get(
    "SHEETS_WEBHOOK",
    "https://script.google.com/macros/s/AKfycby-LFa0ztbqPMD_E-zkRfAfSKLmiTjPjVXdAn44E_rHRHq3XYLCygZqoTlhhT8yT_Mh/exec",
)


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
    """Hace GET al Apps Script con parámetros."""
    try:
        url = f"{SHEETS_WEBHOOK}?{urlencode(params)}"
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=15)
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
async def acceder(data: dict):
    """
    Login/Registro unificado:
    - Si el email existe → verifica contraseña → devuelve historial
    - Si el email no existe → registra con la contraseña → devuelve historial vacío
    """
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"error": "Email inválido"})
    if len(password) < 4:
        return JSONResponse(status_code=400, content={"error": "La contraseña debe tener al menos 4 caracteres"})

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
        return {"ok": True, "email": email, "historial": historial, "nuevo": False}
    else:
        # Usuario nuevo → registrar
        hashed = _hash_password(password)
        result = await _sheets_get({"action": "register", "email": email, "hash": hashed})

        if not result.get("ok") and result.get("error") == "El usuario ya existe":
            return JSONResponse(status_code=409, content={"error": "El email ya está registrado. Prueba con tu contraseña."})

        historial = await _obtener_historial_sheets(email)
        return {"ok": True, "email": email, "historial": historial, "nuevo": True}


@app.post("/api/auth/historial")
async def obtener_historial(data: dict):
    """Refresca historial de un usuario ya autenticado (no requiere contraseña)."""
    email = (data.get("email") or "").strip().lower()
    if not email:
        return JSONResponse(status_code=400, content={"error": "Email requerido"})
    historial = await _obtener_historial_sheets(email)
    return {"ok": True, "historial": historial}


# =========================================================================
# Dashboard admin — ruta protegida con clave
# =========================================================================

ADMIN_KEY = os.environ.get("ADMIN_KEY", "mentotrack2024")


@app.get("/dashboard")
def serve_dashboard(key: str = ""):
    """Dashboard admin protegido por clave en query param."""
    if key != ADMIN_KEY:
        return JSONResponse(status_code=403, content={"error": "Acceso denegado"})
    dashboard_path = FRONTEND_DIR / "dashboard.html"
    if not dashboard_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Dashboard no encontrado"})
    return FileResponse(dashboard_path)


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
    if full_path == "dashboard.html":
        return JSONResponse(status_code=403, content={"error": "Usa /dashboard?key=..."})
    file_path = FRONTEND_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")
