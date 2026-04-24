FROM python:3.11-slim

# Dependencias del sistema para librosa (audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root (seguridad: no correr como root)
RUN useradd -m -r appuser

WORKDIR /app

# Instalar dependencias Python
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Dar permisos al usuario para escribir archivos temporales y sesiones
RUN chown -R appuser:appuser /app

# Cambiar a usuario no-root
USER appuser

# Puerto (Railway asigna el suyo via $PORT)
ENV PORT=8000
EXPOSE 8000

# Arrancar desde el directorio backend para que los imports funcionen
WORKDIR /app/backend
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
