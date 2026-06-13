FROM python:3.11-slim

# Dependencias del sistema para librosa (audio processing) + gosu (drop de
# privilegios en el entrypoint tras chownear el volumen)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    gosu \
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

# Entrypoint: arranca como root para chownear el volumen (/data lo monta
# Railway como root) y baja a appuser con gosu antes de ejecutar la app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Puerto (Railway asigna el suyo via $PORT)
ENV PORT=8000
# Logs de la app en tiempo real (sin buffer de stdout) — para ver prints/avisos
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Arrancar desde el directorio backend para que los imports funcionen
# --proxy-headers: detrás del proxy de Railway, request.client.host debe ser
# la IP real del cliente (X-Forwarded-For) — sin esto, los rate limits de
# slowapi comparten un único cubo global para todos los usuarios.
WORKDIR /app/backend
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips "*"
