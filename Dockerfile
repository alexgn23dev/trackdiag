FROM python:3.11-slim

# Dependencias del sistema para librosa (audio processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Puerto (Railway asigna el suyo via $PORT)
ENV PORT=8000
EXPOSE 8000

# Arrancar desde el directorio backend para que los imports funcionen
WORKDIR /app/backend
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
