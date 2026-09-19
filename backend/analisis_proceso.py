"""El análisis de audio corre en un proceso aparte.

Por qué: cada extracción de señales (librosa/numpy/scipy) reserva cientos de
MB que, dentro del proceso del servidor, no vuelven al sistema al terminar:
glibc los deja fragmentados entre los hilos del executor. En Railway se veía
como una RAM que subía de ~0,8 GB recién desplegado a más de 2 GB en un mes y
solo bajaba al redesplegar; la factura de septiembre de 2026 (96 % memoria) lo
reflejó. Con cada análisis en un proceso hijo que muere al acabar, el sistema
recupera toda la memoria, y un timeout mata el análisis de verdad (con un hilo
seguía consumiendo CPU después de haber respondido 504).

Uso desde un endpoint:

    senales = await analisis_proceso.ejecutar(
        analisis_proceso.EXTRAER_SENALES, ruta, bpm_manual=120, timeout=90)

El hijo es `python -m analisis_proceso`, importa solo la función pedida (nunca
main.py) y deja el resultado en un archivo pickle; las excepciones del motor
vuelven al padre con su clase, así que `AudioSinSenalAnalizable` se sigue
capturando igual en los endpoints (vive en engine/excepciones.py para que el
padre la reconstruya sin importar librosa). Los `print` del hijo salen por los
mismos stdout/stderr del servidor (logs de Railway).

Regla: el proceso del servidor nunca importa librosa. Todo lo que la necesite
va por aquí; tests/test_servidor_sin_librosa.py lo comprueba.

Variables de entorno:
    ANALISIS_PROCESOS   análisis simultáneos como máximo (por defecto 2); el
                        resto espera su hueco. Acota el pico de memoria: dos
                        análisis largos a la vez ya rondan los 4 GB.
"""

import asyncio
import importlib
import json
import os
import pickle
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

# Tareas que los endpoints ejecutan en el hijo, como "modulo:funcion".
EXTRAER_SENALES = "engine.extractor:extraer_senales"
CALCULAR_WAVEFORM = "analisis_proceso:calcular_waveform"
VALIDACION_TRUE_PEAK = "analisis_proceso:validacion_true_peak"

_MAX_SIMULTANEOS = max(1, int(os.environ.get("ANALISIS_PROCESOS", "2") or 2))
_hueco = threading.BoundedSemaphore(_MAX_SIMULTANEOS)


class AnalisisFallido(RuntimeError):
    """El proceso hijo murió sin dejar resultado (por ejemplo, sin memoria) o
    devolvió algo que no se puede transportar al padre."""


# ---------------------------------------------------------------- padre ----

def ejecutar_sync(tarea: str, *args, timeout: float = 90.0, **kwargs):
    """Ejecuta `tarea` ("modulo:funcion") con esos argumentos en un proceso
    hijo y devuelve su resultado. Bloquea el hilo que la llama: desde el
    servidor usar `ejecutar()`.

    Lanza TimeoutError (== asyncio.TimeoutError) si el hijo supera `timeout`
    segundos — y lo mata —, la excepción original si la función la lanzó, y
    AnalisisFallido si el proceso desapareció sin responder."""
    fd, salida = tempfile.mkstemp(prefix="mentotrack_hijo_", suffix=".pkl")
    os.close(fd)
    carga = json.dumps({"args": list(args), "kwargs": kwargs, "salida": salida})
    cmd = [sys.executable, "-m", "analisis_proceso", tarea, carga]
    env = dict(os.environ)
    # numba (dentro de librosa) compila al vuelo y guarda el resultado en disco:
    # con un directorio escribible, ese coste se paga una vez por contenedor y
    # no en cada proceso hijo.
    env.setdefault("NUMBA_CACHE_DIR", os.path.join(tempfile.gettempdir(), "mentotrack-numba"))
    try:
        t0 = time.monotonic()
        with _hueco:
            espera = time.monotonic() - t0
            if espera > 1.0:
                print(f"[ANALISIS] {tarea} esperó {espera:.1f}s por un hueco "
                      f"(máximo {_MAX_SIMULTANEOS} simultáneos)")
            try:
                proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=env, timeout=timeout)
            except subprocess.TimeoutExpired:
                # subprocess.run ya ha matado al hijo y esperado a que muera.
                raise TimeoutError(f"{tarea} superó los {timeout:.0f} s; proceso matado") from None
        paquete = _leer(salida)
    finally:
        try:
            os.unlink(salida)
        except OSError:
            pass
    if paquete is None:
        raise AnalisisFallido(f"el proceso de {tarea} terminó con código {proc.returncode} "
                              "sin dejar resultado")
    if not paquete["ok"]:
        raise paquete["excepcion"]
    return paquete["resultado"]


async def ejecutar(tarea: str, *args, timeout: float = 90.0, **kwargs):
    """Versión asíncrona de `ejecutar_sync`: no bloquea el event loop."""
    return await asyncio.to_thread(ejecutar_sync, tarea, *args, timeout=timeout, **kwargs)


def _leer(salida: str):
    try:
        with open(salida, "rb") as f:
            datos = f.read()
    except OSError:
        return None
    if not datos:
        return None
    return pickle.loads(datos)


# ----------------------------------------------------------------- hijo ----

def _escribir(salida: str, paquete: dict) -> None:
    try:
        datos = pickle.dumps(paquete, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        # Resultado o excepción que no viaja por pickle: se cuenta como fallo,
        # con el motivo, en vez de dejar al padre sin respuesta. La clase se
        # toma del módulo importable: en el hijo este archivo es `__main__` y
        # el padre no podría resolver `__main__.AnalisisFallido`.
        from analisis_proceso import AnalisisFallido as _Fallido
        exc = paquete.get("excepcion")
        motivo = (f"{type(exc).__name__}: {exc}" if exc is not None
                  else f"resultado no serializable ({type(e).__name__}: {e})")
        datos = pickle.dumps({"ok": False, "excepcion": _Fallido(motivo)})
    tmp = salida + ".tmp"
    with open(tmp, "wb") as f:
        f.write(datos)
    os.replace(tmp, salida)   # atómico: el padre nunca lee un archivo a medias


def _main(argv: list) -> int:
    tarea, carga = argv[1], json.loads(argv[2])
    try:
        modulo, nombre = tarea.split(":")
        fn = getattr(importlib.import_module(modulo), nombre)
        paquete = {"ok": True, "resultado": fn(*carga["args"], **carga["kwargs"])}
    except Exception as e:
        paquete = {"ok": False, "excepcion": e}
    _escribir(carga["salida"], paquete)
    return 0


# ------------------------------------------- tareas que corren en el hijo ----

def calcular_waveform(path: str, n_picos: int = 400):
    """Picos RMS normalizados 0-1 (para pintar la forma de onda en cliente)
    + duración en segundos. Carga a 11 kHz mono — rápido y suficiente.
    Resolución 400: en electrónica el RMS (no el peak, que el kick 4/4 deja
    plano) refleja la dinámica del arreglo; más puntos = más detalle del muro.
    Vive aquí, y no en main.py, para que el hijo no tenga que importar la app."""
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


def validacion_true_peak() -> dict:
    """Estados de validación del medidor de true peak, para
    /api/tecnico/versiones. Son constantes de engine.extractor: se leen aquí,
    en el hijo, para que el servidor no importe librosa por consultarlas."""
    from engine import extractor as e
    return {
        "true_peak_ground_truth_validation_passed": e.TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED,
        "true_peak_internal_validation_passed": e.TRUE_PEAK_INTERNAL_VALIDATION_PASSED,
        "true_peak_external_validation_passed": e.TRUE_PEAK_EXTERNAL_VALIDATION_PASSED,
        "true_peak_validated": e._TRUE_PEAK_VALIDATED,
    }


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
