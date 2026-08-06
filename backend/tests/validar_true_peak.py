"""Validación del medidor de true peak contra referencias externas.

PASO OBLIGATORIO ANTES DE DESPLEGAR. Mientras este script no termine sin
fallos, `_TRUE_PEAK_VALIDATED` en engine/extractor.py debe seguir en False.

Tres referencias, deliberadamente de naturaleza distinta:

  1. VALOR ANALÍTICO — la teoría. No depende de ninguna implementación, así
     que es el juez cuando las otras dos discrepan.
  2. FFMPEG ebur128=peak=true — implementación en C, ampliamente usada.
     Se comprueba además que esta build propaga bien el pico global: el
     "Peak" del resumen tiene que coincidir con el máximo de los TPK por
     frame que aparecen en el log. Si no coincide, no se usa como referencia.
  3. IMPLEMENTACIONES INDEPENDIENTES EN PYTHON — dos caminos de DSP que no
     tocan soxr: interpolación sinc exacta por FFT (solo numpy) y
     sobremuestreo polifásico con scipy.signal.resample_poly. Comparten
     lenguaje pero no comparten código con el medidor auditado.

Una cuarta referencia — un medidor profesional de escritorio — queda como
comprobación MANUAL documentada en RESULTADOS_VALIDACION.md.

    python tests/validar_true_peak.py
    python tests/validar_true_peak.py --json informe.json

Tolerancias (acordadas 2026-08-06):
    analítico       objetivo ±0,05 dB   fallo > ±0,15 dB
    música/ffmpeg   objetivo ±0,10 dB   fallo > ±0,30 dB
    patológico ISP                      fallo > ±0,50 dB
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import capturar_golden as cg  # noqa: E402
from tests import fixtures as fx  # noqa: E402

TOL_ANALITICO_OBJETIVO = 0.05
TOL_ANALITICO_FALLO = 0.15
TOL_FFMPEG_OBJETIVO = 0.10
TOL_FFMPEG_FALLO = 0.30
TOL_PATOLOGICO_FALLO = 0.50


# ---------------------------------------------------------------------------
# Referencia 2 — ffmpeg
# ---------------------------------------------------------------------------
def ffmpeg_version() -> str:
    try:
        p = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        return p.stdout.splitlines()[0].strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def ffmpeg_true_peak(ruta: str):
    """Devuelve (peak_resumen, peak_max_frames) en dBFS, o (None, None).

    Devolver los dos permite comprobar que esta build propaga bien el pico
    global — el problema conocido de algunas versiones de `ebur128`.
    """
    try:
        p = subprocess.run(
            ["ffmpeg", "-i", ruta, "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None
    err = p.stderr

    resumen = None
    if "True peak:" in err:
        cola = err.split("True peak:", 1)[1]
        m = re.search(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS", cola)
        if m:
            resumen = -np.inf if m.group(1) == "-inf" else float(m.group(1))

    picos_frame = []
    for m in re.finditer(r"TPK:\s*((?:\s*-?[\d.]+|\s*-inf)+)\s*dBFS", err):
        for val in m.group(1).split():
            picos_frame.append(-np.inf if val == "-inf" else float(val))
    max_frames = max(picos_frame) if picos_frame else None
    return resumen, max_frames


# ---------------------------------------------------------------------------
# Referencia 3 — implementaciones independientes en Python
# ---------------------------------------------------------------------------
def tp_fft_sinc(ruta: str, oversampling: int = 32) -> float:
    """Interpolación sinc exacta por relleno de ceros en el espectro.

    Es la reconstrucción band-limited exacta de la extensión periódica de la
    señal. No usa soxr, ni scipy, ni filtros diseñados a mano: solo la FFT.
    """
    data, _sr = sf.read(ruta, always_2d=True, dtype="float64")
    picos = []
    for ch in range(data.shape[1]):
        x = data[:, ch]
        n = len(x)
        if n == 0:
            continue
        X = np.fft.rfft(x)
        m = n * oversampling
        Xp = np.zeros(m // 2 + 1, dtype=complex)
        Xp[:len(X)] = X
        # Nyquist: al ampliar la banda hay que repartir el bin de Nyquist
        if n % 2 == 0 and len(X) > 1:
            Xp[len(X) - 1] /= 2.0
        y = np.fft.irfft(Xp, m) * oversampling
        picos.append(float(np.max(np.abs(y))))
    if not picos:
        return -99.0
    pico = max(picos)
    return 20.0 * float(np.log10(pico)) if pico > 1e-9 else -99.0


def tp_resample_poly(ruta: str, oversampling: int = 4) -> float:
    """Sobremuestreo polifásico con scipy (filtro distinto al de soxr)."""
    try:
        from scipy.signal import resample_poly
    except ImportError:
        return None
    data, _sr = sf.read(ruta, always_2d=True, dtype="float64")
    picos = []
    for ch in range(data.shape[1]):
        up = resample_poly(data[:, ch], oversampling, 1)
        picos.append(float(np.max(np.abs(up))))
    if not picos:
        return -99.0
    pico = max(picos)
    return 20.0 * float(np.log10(pico)) if pico > 1e-9 else -99.0


# ---------------------------------------------------------------------------
def validar(destino_fixtures: str) -> dict:
    manifiesto = fx.generar(destino_fixtures)
    ver_ffmpeg = ffmpeg_version()

    # ¿Propaga bien esta build el pico global de ebur128?
    prop_ok, prop_detalle = True, []
    for nombre in ("wav24_clipping_evidente", "isp_fs4_sobre_0", "dc_menos6"):
        if nombre not in manifiesto:
            continue
        resumen, max_frames = ffmpeg_true_peak(manifiesto[nombre]["ruta"])
        if resumen is None or max_frames is None:
            prop_ok = False
            prop_detalle.append(f"{nombre}: no se pudo leer el pico de ffmpeg")
        elif abs(resumen - max_frames) > 0.05:
            prop_ok = False
            prop_detalle.append(
                f"{nombre}: resumen {resumen:.2f} != max por frame {max_frames:.2f}")
        else:
            prop_detalle.append(f"{nombre}: resumen {resumen:.2f} == max frames {max_frames:.2f}")

    filas, fallos = [], []
    for nombre, spec in sorted(manifiesto.items()):
        if nombre == "wav24_silencio":
            continue
        medido = cg.medir_completo(spec["ruta"])["true_peak_dbtp"]
        ref_ffmpeg, _ = ffmpeg_true_peak(spec["ruta"])
        ref_fft = tp_fft_sinc(spec["ruta"])
        ref_poly = tp_resample_poly(spec["ruta"])
        analitico = spec.get("tp_analitico")
        patologico = spec.get("patologico", False)

        # Señales con discontinuidad: el máximo GLOBAL no puede compararse
        # contra el valor analítico de régimen estable. Un escalón produce
        # sobreoscilación real en cualquier reconstrucción band-limited — está
        # medido en tests/estudio_continua.py, donde los cuatro métodos
        # (incluido ffmpeg) sobrepasan el sample peak sobre el mismo escalón.
        # Para estos fixtures la comprobación válida es la de régimen estable,
        # que hace estudio_continua.py; aquí solo se registra.
        if spec.get("regimen"):
            filas.append({
                "fixture": nombre, "mentotrack": round(medido, 3),
                "analitico": None,
                "objetivo_regimen_estable": spec.get("tp_regimen_estable"),
                "ffmpeg": None if ref_ffmpeg is None else round(ref_ffmpeg, 3),
                "fft_sinc_32x": round(ref_fft, 3),
                "resample_poly_4x": None if ref_poly is None else round(ref_poly, 3),
                "patologico": False,
                "nota": ("señal con discontinuidad: el máximo global no se "
                         "contrasta contra el analítico de régimen estable "
                         "(ver tests/estudio_continua.py)"),
            })
            continue

        fila = {
            "fixture": nombre, "mentotrack": round(medido, 3),
            "analitico": analitico,
            "ffmpeg": None if ref_ffmpeg is None else round(ref_ffmpeg, 3),
            "fft_sinc_32x": round(ref_fft, 3),
            "resample_poly_4x": None if ref_poly is None else round(ref_poly, 3),
            "patologico": patologico,
        }

        if analitico is not None:
            d = medido - analitico
            fila["delta_analitico"] = round(d, 3)
            limite = TOL_PATOLOGICO_FALLO if patologico else TOL_ANALITICO_FALLO
            if abs(d) > limite:
                fallos.append(f"{nombre}: {d:+.3f} dB vs analítico (límite ±{limite})")
            # Fiabilidad de la propia referencia externa: si ffmpeg se desvía
            # del valor analítico más que nosotros, no puede arbitrar ese caso.
            if ref_ffmpeg is not None and np.isfinite(ref_ffmpeg):
                fila["delta_ffmpeg_vs_analitico"] = round(ref_ffmpeg - analitico, 3)
            if ref_fft > -99:
                fila["delta_fft_vs_analitico"] = round(ref_fft - analitico, 3)

        if ref_ffmpeg is not None and prop_ok and np.isfinite(ref_ffmpeg):
            d = medido - ref_ffmpeg
            fila["delta_ffmpeg"] = round(d, 3)
            limite = TOL_PATOLOGICO_FALLO if patologico else TOL_FFMPEG_FALLO
            # ffmpeg solo arbitra donde se ha comprobado que él mismo acierta.
            ffmpeg_fiable = (analitico is None
                             or abs(ref_ffmpeg - analitico) <= TOL_ANALITICO_FALLO)
            fila["ffmpeg_fiable_en_este_caso"] = bool(ffmpeg_fiable)
            if abs(d) > limite and ffmpeg_fiable:
                fallos.append(f"{nombre}: {d:+.3f} dB vs ffmpeg (límite ±{limite})")
            elif abs(d) > limite:
                fila["nota"] = ("discrepancia con ffmpeg no contabilizada: ffmpeg se "
                                f"desvía {ref_ffmpeg - analitico:+.2f} dB del valor "
                                "analítico en este fixture")
        if ref_fft > -99:
            fila["delta_fft"] = round(medido - ref_fft, 3)
        filas.append(fila)

    return {
        "ffmpeg_version": ver_ffmpeg,
        "ffmpeg_propagacion_ok": prop_ok,
        "ffmpeg_propagacion_detalle": prop_detalle,
        "tolerancias": {
            "analitico_objetivo": TOL_ANALITICO_OBJETIVO,
            "analitico_fallo": TOL_ANALITICO_FALLO,
            "ffmpeg_objetivo": TOL_FFMPEG_OBJETIVO,
            "ffmpeg_fallo": TOL_FFMPEG_FALLO,
            "patologico_fallo": TOL_PATOLOGICO_FALLO,
        },
        "filas": filas,
        "fallos": fallos,
        "veredicto": "PASA" if not fallos else "FALLA",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=os.path.join(tempfile.gettempdir(),
                                                       "mentotrack_fixtures"))
    ap.add_argument("--json", dest="salida_json", default="")
    args = ap.parse_args()

    inf = validar(args.fixtures)

    print(f"ffmpeg: {inf['ffmpeg_version'] or 'NO DISPONIBLE'}")
    print(f"propagación del pico global de ebur128: "
          f"{'OK' if inf['ffmpeg_propagacion_ok'] else 'SOSPECHOSA — no se usa como referencia'}")
    for d in inf["ffmpeg_propagacion_detalle"]:
        print(f"   {d}")
    print()
    cab = f"{'fixture':26} {'mento':>8} {'analít':>8} {'ffmpeg':>8} {'fft32x':>8} {'poly4x':>8} {'Δanal':>7} {'Δffm':>7}"
    print(cab)
    print("-" * len(cab))
    for f in inf["filas"]:
        def s(v, w=8):
            return f"{v:>{w}.2f}" if isinstance(v, (int, float)) else f"{'—':>{w}}"
        print(f"{f['fixture']:26}{s(f['mentotrack'])}{s(f['analitico'])}{s(f['ffmpeg'])}"
              f"{s(f['fft_sinc_32x'])}{s(f['resample_poly_4x'])}"
              f"{s(f.get('delta_analitico'), 7)}{s(f.get('delta_ffmpeg'), 7)}")

    print()
    if inf["fallos"]:
        print(f"VEREDICTO: FALLA ({len(inf['fallos'])} desviaciones fuera de tolerancia)")
        for f_ in inf["fallos"]:
            print("  -", f_)
    else:
        print("VEREDICTO: PASA")

    if args.salida_json:
        with open(args.salida_json, "w", encoding="utf-8") as fh:
            json.dump(inf, fh, indent=2, ensure_ascii=False)
        print(f"\ninforme JSON: {args.salida_json}")
    return 0 if inf["veredicto"] == "PASA" else 1


if __name__ == "__main__":
    raise SystemExit(main())
