#!/bin/sh
set -e

# Railway monta el volumen (/data) como root. La app corre como appuser
# (no-root, por seguridad), así que al arrancar — aún como root — damos la
# propiedad del punto de montaje a appuser y después bajamos privilegios.
if [ -n "$RAILWAY_VOLUME_MOUNT_PATH" ] && [ -d "$RAILWAY_VOLUME_MOUNT_PATH" ]; then
    chown appuser:appuser "$RAILWAY_VOLUME_MOUNT_PATH" || true
fi

exec gosu appuser "$@"
