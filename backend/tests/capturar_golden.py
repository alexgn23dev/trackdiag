"""Congela el comportamiento del motor de picos/loudness en un JSON.

Se ejecutó por primera vez ANTES de tocar nada (fase 1, 2026-08-06) para
tener una referencia contra la que comprobar que los cambios de esa fase no
alteran ninguna clasificación ni ningún texto visible.

    python tests/capturar_golden.py            # compara contra el golden
    python tests/capturar_golden.py --escribir # regenera el golden

Regenerar el golden es una decisión consciente: solo se hace cuando el cambio
de comportamiento está aprobado y documentado.
"""

import argparse
import json
import os
import sys

import librosa
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import _analizar_loudness  # noqa: E402
from tests import fixtures as fx  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_loudness.json")

# Campos cuyo valor NO puede cambiar en la fase 1.
CAMPOS_CONGELADOS = [
    "lufs_integrado", "lufs_short_term_max", "rango_loudness",
    "nivel", "nivel_true_peak", "aviso_true_peak",
    "saturacion_dinamica", "aviso_saturacion", "referencia", "consejo_master",
]


# Divergencias APROBADAS respecto al golden original (capturado en v0.5.70).
# El golden se mantiene tal cual se capturó antes de tocar nada; los cambios
# de comportamiento que sí están autorizados se declaran aquí, uno a uno, con
# su motivo. Cualquier otra divergencia hace fallar el test.
CAMBIOS_AUTORIZADOS = {
    ("wav24_mono", "lufs_integrado"): (
        "v0.5.71 — LUFS de archivos mono. Antes se duplicaba el canal a estéreo, "
        "lo que sumaba la energía dos veces (+3,01 LU). Verificado con ffmpeg "
        "ebur128: mono real = -20,7 LUFS; el golden decía -17,8."),
    ("wav24_mono", "nivel"): (
        "Consecuencia directa del anterior: -20,8 cruza el umbral de -20 y "
        "pasa de 'bajo' a 'muy_bajo'."),
    ("wav24_mono", "referencia"): "Texto asociado al cambio de `nivel`.",
    ("wav24_mono", "consejo_master"): "Texto asociado al cambio de `nivel`.",
    ("wav24_silencio", "lufs_integrado"): (
        "v0.5.71 — pyloudnorm devuelve -inf con silencio absoluto y ese -inf "
        "llegaba a la respuesta, donde Starlette (allow_nan=False) provocaba "
        "un HTTP 500. Ahora se sustituye por el centinela -99.0. En el flujo "
        "real este archivo ni siquiera llega hasta aquí: extraer_senales lo "
        "corta antes con AudioSinSenalAnalizable → HTTP 422."),

    # --- v0.5.72: sobremuestreo 4x → 8x --------------------------------------
    # Solo tres fixtures se mueven a 1 decimal. Los dos primeros son el mismo
    # fenómeno y NO son una mejora ni un empeoramiento: son la zona donde la
    # medida no está definida.
    ("dc_estable_menos6", "true_peak_dbtp_1dec"): (
        "v0.5.72 — sobremuestreo 8x. El máximo de este fixture cae en el BORDE "
        "del archivo, donde el valor depende de qué se asuma fuera y no "
        "converge con el factor: x4 -4,9 · x8 -4,5 · x16 -4,8 · x24 -4,5. Un "
        "escalón DENTRO del archivo (dc_salto_interno) da -4,94 con todos los "
        "factores. No es una regresión: es que ahí no hay nada bien definido "
        "que medir. Ver RESULTADOS_VALIDACION.md §5b y §8."),
    ("dc_bordes_menos6", "true_peak_dbtp_1dec"): (
        "Mismo caso que dc_estable_menos6: el máximo está en el borde."),

    ("wav24_96000_pico_menos1", "true_peak_dbtp_1dec"): (
        "v0.5.72 — sobremuestreo 8x: -0,9 → -0,7. Aquí sí es una mejora real. "
        "La reconstrucción exacta da -0,2: a 4x se estaba subestimando 0,75 dB "
        "y a 8x la subestimación baja a 0,53. El resto lo causa el filtro de "
        "soxr, que descarta el contenido por encima del 90% de Nyquist — este "
        "fixture tiene los hats de ruido blanco hasta 48 kHz."),
    ("wav24_96000_pico_menos1", "aviso_true_peak"): (
        "Texto asociado: lleva el valor dentro."),
}


def medir_completo(ruta: str) -> dict:
    """Reproduce exactamente la llamada que hace extraer_senales() y devuelve
    el dict de loudness entero."""
    y_stereo, sr = librosa.load(ruta, sr=22050, mono=False)
    es_stereo = y_stereo.ndim == 2 and y_stereo.shape[0] == 2
    y = np.mean(y_stereo, axis=0) if es_stereo else (
        y_stereo if y_stereo.ndim == 1 else y_stereo[0])
    from engine.extractor import _analizar_formato, _clasificar_recorte
    formato = _analizar_formato(ruta)
    try:
        onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
    except Exception:
        onsets = None
    res = _analizar_loudness(ruta, y_preloaded=y, sr_preloaded=sr,
                             y_stereo_preloaded=y_stereo if es_stereo else None,
                             formato=formato, onsets_seg=onsets)
    res.update(_clasificar_recorte(res, formato))
    return res


def medir(ruta: str) -> dict:
    """Solo los campos congelados, para comparar contra el golden."""
    res = medir_completo(ruta)
    salida = {k: res.get(k) for k in CAMPOS_CONGELADOS}
    # true_peak se guarda aparte y siempre redondeado a 1 decimal: en la fase 1
    # el valor interno pasa a tener precisión completa, pero la CLASIFICACIÓN
    # y lo que se enseña siguen saliendo del redondeado.
    tp = res.get("true_peak_dbtp")
    salida["true_peak_dbtp_1dec"] = round(float(tp), 1) if tp is not None else None
    return salida


def capturar(destino_fixtures: str) -> dict:
    manifiesto = fx.generar(destino_fixtures)
    return {nombre: medir(spec["ruta"]) for nombre, spec in sorted(manifiesto.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--escribir", action="store_true")
    ap.add_argument("--fixtures", default="/tmp/mentotrack_fixtures")
    args = ap.parse_args()

    actual = capturar(args.fixtures)

    if args.escribir or not os.path.exists(GOLDEN):
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(actual, f, indent=2, ensure_ascii=False, sort_keys=True)
        print(f"golden escrito: {GOLDEN} ({len(actual)} fixtures)")
        return 0

    with open(GOLDEN, encoding="utf-8") as f:
        esperado = json.load(f)

    fallos, autorizados = comparar(esperado, actual)

    for nombre, campo, motivo in autorizados:
        print(f"cambio autorizado — {nombre}.{campo}: {motivo}")
    if fallos:
        print(f"\nDIVERGE del golden sin autorización ({len(fallos)}):")
        for f_ in fallos:
            print("  -", f_)
        return 1
    print(f"\nOK: {len(actual)} fixtures, sin divergencias no autorizadas")
    return 0


def comparar(esperado: dict, actual: dict):
    """Devuelve (fallos, cambios_autorizados)."""
    fallos, autorizados = [], []
    for nombre in sorted(set(esperado) | set(actual)):
        e, a = esperado.get(nombre), actual.get(nombre)
        if e is None or a is None:
            fallos.append(f"{nombre}: presente solo en {'actual' if e is None else 'golden'}")
            continue
        for campo in sorted(set(e) | set(a)):
            if e.get(campo) == a.get(campo):
                continue
            motivo = CAMBIOS_AUTORIZADOS.get((nombre, campo))
            if motivo:
                autorizados.append((nombre, campo, motivo))
            else:
                fallos.append(f"{nombre}.{campo}: golden={e.get(campo)!r} actual={a.get(campo)!r}")
    return fallos, autorizados


if __name__ == "__main__":
    raise SystemExit(main())
