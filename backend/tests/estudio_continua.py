"""Estudio de la continua: ¿el +1,10 dB es un fallo o la respuesta del filtro?

Compara cuatro métodos sobre las tres variantes de señal continua, en dos
regímenes de evaluación:

  * máximo GLOBAL — todo el archivo, incluidos los bordes
  * máximo SIN ASENTAMIENTO — descartando la zona donde el filtro arranca

Métodos:
  soxr_hq_4x   el de producción (engine/extractor.py)
  itu_fir_4x   implementación de referencia del Anexo 2 de BS.1770-5
  fft_sinc_32x interpolación sinc exacta (numpy)
  ffmpeg       ebur128=peak=true

    python tests/estudio_continua.py
"""

import os
import sys
import tempfile

import librosa
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import fixtures as fx  # noqa: E402
from tests import itu_bs1770 as itu  # noqa: E402
from tests import validar_true_peak as vtp  # noqa: E402

# Ventana de asentamiento para soxr. El filtro de soxr_hq es bastante más
# largo que los 12 taps por fase del FIR de la ITU; 512 muestras de entrada a
# cada lado cubren su respuesta impulsional con margen de sobra.
ASENTAMIENTO_SOXR_ENTRADA = 512


def _db(lineal: float) -> float:
    return 20.0 * float(np.log10(lineal)) if lineal > 1e-12 else -99.0


def tp_soxr(ruta: str, descartar_asentamiento: bool = False) -> float:
    """Mismo camino que producción; opcionalmente descarta los bordes.

    El descarte es SOLO para este estudio: producción no recorta nada.
    """
    native, sr = sf.read(ruta, always_2d=True, dtype="float32")
    picos = []
    for ch in range(native.shape[1]):
        up = librosa.resample(native[:, ch], orig_sr=sr, target_sr=sr * 4,
                              res_type="soxr_hq")
        if descartar_asentamiento:
            r = ASENTAMIENTO_SOXR_ENTRADA * 4
            if len(up) > 2 * r:
                up = up[r:-r]
        picos.append(float(np.max(np.abs(up))))
    return _db(max(picos)) if picos else -99.0


def tp_fft(ruta: str, descartar_asentamiento: bool = False) -> float:
    if not descartar_asentamiento:
        return vtp.tp_fft_sinc(ruta)
    data, _sr = sf.read(ruta, always_2d=True, dtype="float64")
    os_ = 32
    picos = []
    for ch in range(data.shape[1]):
        x = data[:, ch]
        n = len(x)
        X = np.fft.rfft(x)
        m = n * os_
        Xp = np.zeros(m // 2 + 1, dtype=complex)
        Xp[:len(X)] = X
        if n % 2 == 0 and len(X) > 1:
            Xp[len(X) - 1] /= 2.0
        y = np.fft.irfft(Xp, m) * os_
        r = ASENTAMIENTO_SOXR_ENTRADA * os_
        if len(y) > 2 * r:
            y = y[r:-r]
        picos.append(float(np.max(np.abs(y))))
    return _db(max(picos)) if picos else -99.0


def estudiar(destino: str) -> list:
    manifiesto = fx.generar(destino)
    objetivo = [n for n in manifiesto if n.startswith("dc_")]
    filas = []
    for nombre in sorted(objetivo):
        spec = manifiesto[nombre]
        ruta = spec["ruta"]
        data, _sr = sf.read(ruta, always_2d=True, dtype="float64")
        ffm, _ = vtp.ffmpeg_true_peak(ruta)
        filas.append({
            "fixture": nombre,
            "regimen": spec.get("regimen", ""),
            "sample_peak": _db(float(np.max(np.abs(data)))),
            "objetivo_estable": spec.get("tp_regimen_estable"),
            "global": {
                "soxr_hq_4x": tp_soxr(ruta, False),
                "itu_fir_4x_cero": itu.true_peak_desde_archivo(ruta, "cero", False),
                "itu_fir_4x_extender": itu.true_peak_desde_archivo(ruta, "extender", False),
                "fft_sinc_32x": tp_fft(ruta, False),
                "ffmpeg": ffm,
            },
            "sin_asentamiento": {
                "soxr_hq_4x": tp_soxr(ruta, True),
                "itu_fir_4x_cero": itu.true_peak_desde_archivo(ruta, "cero", True),
                "itu_fir_4x_extender": itu.true_peak_desde_archivo(ruta, "extender", True),
                "fft_sinc_32x": tp_fft(ruta, True),
                "ffmpeg": None,   # ffmpeg no permite acotar la región medida
            },
        })
    return filas


def main():
    destino = os.path.join(tempfile.gettempdir(), "mentotrack_fixtures")
    filas = estudiar(destino)
    metodos = ["soxr_hq_4x", "itu_fir_4x_cero", "itu_fir_4x_extender",
               "fft_sinc_32x", "ffmpeg"]
    for f in filas:
        print(f"\n=== {f['fixture']}  ({f['regimen']}) ===")
        print(f"    sample peak: {f['sample_peak']:.3f} dBFS"
              f" · objetivo en régimen estable: {f['objetivo_estable']} dBTP")
        print(f"    {'método':22} {'máx global':>12} {'sin asentam.':>14} {'Δ borde':>9}")
        for m in metodos:
            g = f["global"].get(m)
            s = f["sin_asentamiento"].get(m)
            gs = f"{g:12.3f}" if isinstance(g, float) else f"{'—':>12}"
            ss = f"{s:14.3f}" if isinstance(s, float) else f"{'—':>14}"
            ds = f"{g - s:9.3f}" if isinstance(g, float) and isinstance(s, float) else f"{'—':>9}"
            print(f"    {m:22} {gs} {ss} {ds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
