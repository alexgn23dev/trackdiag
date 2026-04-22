"""
TrackDiag API — Backend FastAPI
Endpoint principal: POST /api/diagnostico
"""

import os
import uuid
import json
import tempfile
from datetime import datetime

from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from engine.extractor import extraer_senales
from engine.diagnostico import generar_diagnostico

app = FastAPI(title="TrackDiag API", version="0.3.0")

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
    return {"status": "ok", "version": "0.2.0"}


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
            {"value": "terminar", "label": "Terminar y publicar"},
            {"value": "aprender", "label": "Practicar y aprender"},
            {"value": "sellos", "label": "Enviar a sellos / playlists"},
            {"value": "pinchar", "label": "Pincharlo en sesión"},
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
# Frontend — servir el SPA
# =========================================================================

@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/{full_path:path}")
def serve_catch_all(full_path: str):
    """Catch-all para SPA: si no es /api, devuelve index.html."""
    file_path = FRONTEND_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")
