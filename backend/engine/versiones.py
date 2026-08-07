"""Versiones de los algoritmos de análisis y de las dependencias que los
determinan.

Por qué existe: dos análisis del mismo archivo pueden dar números distintos si
cambió el algoritmo o si cambió una librería por debajo (soxr es quien calcula
el sobremuestreo del true peak; numpy y pyloudnorm afectan al loudness).
Guardando estas versiones en cada análisis se puede saber después qué filas
son comparables entre sí sin tener que adivinarlo por la fecha.

Reglas para tocarlas:

* `PEAK_ALGORITHM_VERSION` — subir cuando cambie cómo se mide true peak o
  sample peak (método, oversampling, tratamiento de bordes, redondeo).
* `LOUDNESS_ALGORITHM_VERSION` — subir cuando cambie cómo se mide LUFS, LRA o
  short-term (sample rate de medición, gating, canales).
* `ANALYSIS_ENGINE_VERSION` — subir cuando cambie cualquier otra señal del
  extractor que altere el diagnóstico.
"""

import sys

# --- Algoritmos -----------------------------------------------------------
# soxr_hq a 4x sobre el archivo a sample rate nativo, máximo entre canales,
# con el sample peak como cota inferior. Sin recorte de bordes.
PEAK_ALGORITHM_VERSION = "peak-soxr_hq_8x-1"

# BS.1770 vía pyloudnorm sobre el audio remuestreado a 22.05 kHz.
# -2: v0.5.71 dejó de duplicar el canal en archivos mono (antes +3,01 LU).
LOUDNESS_ALGORITHM_VERSION = "loudness-pyloudnorm-22k-2"

# Conjunto de señales del extractor (espectro, estructura, armonía, harshness).
ANALYSIS_ENGINE_VERSION = "engine-2026.08.06-1"


def _v(nombre: str) -> str:
    try:
        import importlib.metadata as md
        return md.version(nombre)
    except Exception:
        return "desconocida"


def dependencias() -> dict:
    """Versiones reales en ejecución de lo que afecta a las mediciones."""
    info = {
        "python": sys.version.split()[0],
        "numpy": _v("numpy"),
        "scipy": _v("scipy"),
        "soundfile": _v("soundfile"),
        "soxr": _v("soxr"),
        "librosa": _v("librosa"),
        "pyloudnorm": _v("pyloudnorm"),
        "libsndfile": "desconocida",
    }
    try:
        import soundfile as sf
        info["libsndfile"] = sf.__libsndfile_version__
    except Exception:
        pass
    return info


def ffmpeg_version() -> str:
    """Solo informativo: ffmpeg no interviene en el análisis, se usa para
    validar el true peak contra una referencia externa."""
    import subprocess
    try:
        p = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                           text=True, timeout=10)
        return p.stdout.splitlines()[0].strip() if p.stdout else "no disponible"
    except Exception:
        return "no disponible"


def algoritmos() -> dict:
    return {
        "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
        "peak_algorithm_version": PEAK_ALGORITHM_VERSION,
        "loudness_algorithm_version": LOUDNESS_ALGORITHM_VERSION,
    }
