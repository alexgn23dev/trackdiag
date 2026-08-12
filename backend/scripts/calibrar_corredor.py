"""Regenera el corredor de referencia del gráfico de balance espectral.

    python backend/scripts/calibrar_corredor.py --corpus "ruta/a/audio_samples"

Imprime el bloque `V2_CORREDOR` listo para pegar en `frontend/index.html`.

## Qué es el corredor

La banda sombreada que se dibuja detrás de la curva del usuario: **dónde cae el
espectro de la música que ya está editada**. Sin ella, el usuario ve su curva
pero no tiene con qué compararla, y "equilibrado" es una palabra sin respaldo.

Son los percentiles 5 y 95 por banda de tercio de octava, medidos con el MISMO
código que mide el track del usuario (`_espectro_tercios_octava`), en la misma
ventana (el drop), con la misma inclinación de dibujo y anclados igual que la curva que se pinta
encima. Si alguna de esas cuatro cosas divergiera, la comparación dejaría de
significar nada.

## Por qué el anclaje es el CUERPO del tema y no su banda más alta

Anclar al pico parecía natural ("dB bajo el pico") pero tenía un punto ciego
grave: el 87 % de los temas pica entre 50 y 80 Hz, así que en esa banda todo el
mundo vale 0 por construcción y **el corredor no puede detectar exceso de grave
justo donde más importa**. Medido: en 50 Hz la mediana y el p95 valían los dos
0.0, margen cero por arriba.

Anclando a la media de 200 Hz - 2 kHz (el cuerpo del tema) el corredor recupera
6.6 dB de margen ahí, y el numero que sale es ademas mas facil de explicar: "tu
grave esta X dB por encima del cuerpo del tema".

## Los límites, que hay que declarar

1. **Se corta en 12.5 kHz.** El corpus son MP3 y por encima de ahí el corredor
   describe al compresor, no a los sellos: en 16 kHz se ensancha a 20.7 dB y en
   20 kHz a 64.
2. **Es house melódico, progressive y deep.** No hay techno ni tech house, que
   es una parte del público de Mentotrack.
3. **Separa poco.** Con la regla de rachas calibrada aquí, el 87 % de los temas
   editados sale "equilibrado" y también el 73 % de los tracks de usuario. Por
   eso el corredor se presenta como contexto y no como aprobado/suspenso: como
   clasificador es débil, como referencia visual es útil.
4. **El estilo del sello pesa.** En 50 Hz, la diferencia entre el sello con más
   grave y el que menos es de 2.9 dB sobre un corredor de 15.8: el 18 %.

## Por qué la regla es de rachas y no de "no salirse"

Con 29 bandas y un corredor del 5 al 95, salirse en alguna banda es lo normal:
medido, solo el 26 % de los discos publicados se queda dentro en TODAS. Una
banda suelta fuera es la textura del tema; lo que describe una zona es una racha
de bandas seguidas. Con rachas de 4 el reparto sale como dice el punto 3.

El ancho mediano del corredor es de 11.1 dB.
"""

import argparse
import glob
import json
import os
import sys
import warnings

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
warnings.filterwarnings("ignore")

from engine.extractor import _CENTROS_TERCIO, _espectro_tercios_octava  # noqa: E402

TILT = 1.5          # la misma inclinación de dibujo que usa el frontend
CUERPO = (200.0, 2000.0)   # la referencia de nivel, igual que en el gráfico
TOPE_CORREDOR = 12500  # ver §"límites" arriba
VENTANA_SEG = 10.0
PCT_LO, PCT_HI = 5, 95


def sin_ponderar(f):
    return np.zeros_like(np.asarray(f, dtype=float))


def espectro_del_drop(ruta):
    """Mismo criterio de ventana que el motor: los 10 s de más energía."""
    import librosa
    y, sr = librosa.load(ruta, sr=22050, mono=True)
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    frames = max(1, int(VENTANA_SEG * sr / 512))
    if len(rms) > frames:
        acum = np.concatenate([[0.0], np.cumsum(rms)])
        ini = int(np.argmax(acum[frames:] - acum[:-frames])) * 512 / sr
    else:
        ini = 0.0
    e = _espectro_tercios_octava(ruta, ini, ini + VENTANA_SEG, sin_ponderar)
    if not e:
        return None
    vals = [b["db"] for b in e["bandas"]]
    # Si falta alguna banda por debajo de 16 kHz el tema no sirve de referencia.
    return None if any(v is None for v in vals[:27]) else vals


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", required=True,
                    help="carpeta con subcarpetas por sello y audio dentro")
    ap.add_argument("--limite", type=int, default=0,
                    help="analizar solo los N primeros (para probar rápido)")
    args = ap.parse_args()

    rutas = sorted(glob.glob(os.path.join(args.corpus, "*", "*.mp3"))
                   + glob.glob(os.path.join(args.corpus, "*", "*.wav")))
    if args.limite:
        rutas = rutas[:args.limite]
    if not rutas:
        raise SystemExit(f"No hay audio en {args.corpus}")

    print(f"Midiendo {len(rutas)} temas…", file=sys.stderr)
    filas, sellos = [], []
    for i, r in enumerate(rutas, 1):
        try:
            v = espectro_del_drop(r)
        except Exception:
            v = None
        if v:
            filas.append(v)
            sellos.append(os.path.basename(os.path.dirname(r)))
        if i % 40 == 0:
            print(f"  {i}/{len(rutas)} · {len(filas)} válidos", file=sys.stderr)

    if len(filas) < 30:
        raise SystemExit(f"Solo {len(filas)} temas válidos: muy pocos para calibrar.")

    hz = np.array(_CENTROS_TERCIO, dtype=float)
    M = np.array([[np.nan if x is None else x for x in f] for f in filas], dtype=float)
    cuerpo = (hz >= CUERPO[0]) & (hz <= CUERPO[1])
    # Inclinar y anclar al cuerpo, exactamente como hace el gráfico.
    T = M + TILT * np.log2(hz / 1000.0)
    S = T - np.nanmean(T[:, cuerpo], axis=1, keepdims=True)

    lo = np.nanpercentile(S, PCT_LO, axis=0)
    med = np.nanpercentile(S, 50, axis=0)
    hi = np.nanpercentile(S, PCT_HI, axis=0)

    dentro = hz <= TOPE_CORREDOR
    print(f"\n    // {len(filas)} temas de {len(set(sellos))} sellos · "
          f"percentiles {PCT_LO}-{PCT_HI} · generado por "
          f"backend/scripts/calibrar_corredor.py")
    print("    const V2_CORREDOR = [")
    for i, h in enumerate(hz):
        if dentro[i]:
            print(f"        {{ hz: {h:g}, lo: {lo[i]:.1f}, med: {med[i]:.1f}, "
                  f"hi: {hi[i]:.1f} }},")
    print("    ];")

    # Y el reparto que produce la regla, que es lo que hay que vigilar.
    def racha_max(fila):
        m = c = 0
        for v in fila:
            c = c + 1 if v else 0
            m = max(m, c)
        return m

    fuera = ((S < lo) | (S > hi))[:, dentro]
    rachas = np.array([racha_max(f) for f in fuera])
    print(f"\n// Reparto sobre el propio corpus (temas ya editados):", file=sys.stderr)
    for k in (3, 4, 5):
        print(f"//   racha >= {k} bandas -> 'equilibrado' el "
              f"{(rachas < k).mean() * 100:.0f} %", file=sys.stderr)
    print(f"// Ancho mediano del corredor: "
          f"{np.nanmedian((hi - lo)[dentro]):.1f} dB", file=sys.stderr)
    print(f"// Se queda dentro en TODAS las bandas: "
          f"{(fuera.sum(axis=1) == 0).mean() * 100:.0f} %", file=sys.stderr)


if __name__ == "__main__":
    main()
