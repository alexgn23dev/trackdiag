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

# Instalar dependencias Python DESDE EL LOCK.
#
# El lock (`requirements.lock.txt`) es el `pip freeze` de una imagen ya
# validada: incluye las transitivas, que sin él pueden resolverse distinto
# entre dos builds del mismo commit. En este motor eso importa — `soxr`
# calcula el sobremuestreo del true peak y `numba` afecta al rendimiento.
#
# `--no-deps` es la parte que de verdad hace reproducible el build: sin él,
# pip volvería a resolver el árbol y podría traer versiones distintas de las
# congeladas. Con él, se instala exactamente lo que dice el lock.
COPY backend/requirements.txt backend/requirements.lock.txt ./
RUN pip install --no-cache-dir --no-deps -r requirements.lock.txt

# Verificación de reproducibilidad. Falla el build si:
#   1. lo instalado no coincide con el lock;
#   2. el lock no cubre alguna dependencia declarada en requirements.txt;
#   3. una dependencia directa está declarada sin `==`.
COPY backend/scripts/verificar_lock.py ./scripts/verificar_lock.py
RUN python scripts/verificar_lock.py

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
