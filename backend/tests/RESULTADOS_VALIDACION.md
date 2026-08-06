# Validación del medidor de true peak — fase 1

**Fecha:** 2026-08-06 · **Versión del motor:** v0.5.71 (rama `feature/motor-picos-fase1`)
**Veredicto: FALLA.** `_TRUE_PEAK_VALIDATED` permanece en `False`.

Reproducir con:

```bash
python tests/validar_true_peak.py --json informe.json
```

---

## Entorno

| Componente | Local (venv 3.11) | Producción (Docker) |
|---|---|---|
| Python | 3.11.15 | 3.11 (`python:3.11-slim`) |
| numpy | 2.4.6 | sin pinear (`numpy>=1.24.0`) |
| scipy | 1.17.1 | sin pinear (`scipy>=1.10.0`) |
| soundfile | 0.14.0 | sin pinear (dep. transitiva de librosa) |
| libsndfile | 1.2.2 | `libsndfile1` de Debian bookworm |
| librosa | 0.11.0 | 0.11.0 (pineado) |
| soxr | 1.1.0 | sin pinear |
| pyloudnorm | 0.2.0 | sin pinear (`pyloudnorm>=0.1.0`) |
| ffmpeg | 8.1.1 | el de `apt` de bookworm |

**Riesgo abierto:** solo `librosa` está pineado. `soxr` es quien calcula el
sobremuestreo del true peak, y una versión distinta puede dar un valor
distinto. Recomendación para fase 2: pinear `soxr`, `soundfile` y `numpy`.

### Fiabilidad de ffmpeg como referencia

`ffmpeg version 8.1.1`. Comprobada la propagación del pico global de
`ebur128` — el problema conocido de que el `Peak` del resumen no recoja el
máximo real: en esta build el resumen **coincide** con el máximo de los `TPK`
por frame en los tres fixtures de control (`4.30 == 4.30`, `3.40 == 3.40`,
`-6.00 == -6.00`). La propagación es correcta.

Ahora bien, **la propagación correcta no implica medición correcta** (§2).

---

## Las tres referencias

1. **Valor analítico.** Sinusoide a `fs/4` desfasada 45°: las muestras caen
   siempre en `±A/√2`, así que el true peak está exactamente `20·log10(√2) =
   +3,0103 dB` sobre el sample peak. Y continua pura: true peak = sample peak.
   No depende de ninguna implementación.
2. **ffmpeg `ebur128=peak=true`.** Implementación en C independiente.
3. **Dos caminos propios en Python que no tocan soxr:** interpolación sinc
   exacta por FFT (32×, solo numpy) y sobremuestreo polifásico con
   `scipy.signal.resample_poly` (4×).

**Pendiente — comprobación manual:** contrastar 3-4 fixtures contra un medidor
profesional de escritorio (Youlean Loudness Meter 2, iZotope Insight o el
medidor de true peak del DAW). No está hecha. Es la única referencia realmente
ajena al ecosistema Python/ffmpeg y debería cerrarse antes de poner
`_TRUE_PEAK_VALIDATED = True`.

---

## Resultados

| fixture | Mentotrack | analítico | ffmpeg | fft 32× | poly 4× | Δ analít. | Δ ffmpeg |
|---|---|---|---|---|---|---|---|
| dc_menos6 | **−4,90** | −6,00 | −6,00 | −6,00 | −4,91 | **+1,10** | **+1,10** |
| isp_fs4_sobre_0 | 2,91 | 2,81 | 3,40 | 2,81 | 2,93 | +0,10 | −0,49 |
| isp_fs4_48000 | 2,91 | 2,81 | 3,40 | 2,81 | 2,93 | +0,10 | −0,49 |
| isp_fs4_96000 | 2,91 | 2,81 | 3,40 | 2,81 | 2,93 | +0,10 | −0,49 |
| wav24_pico_menos1 | 0,53 | — | 0,40 | 0,36 | 0,34 | — | +0,13 |
| wav16_pico_menos1 | 0,53 | — | 0,40 | 0,36 | 0,34 | — | +0,13 |
| wav64d_pico_menos1 | 0,53 | — | 0,40 | 0,36 | 0,34 | — | +0,13 |
| flac24_pico_menos1 | 0,53 | — | 0,40 | 0,36 | 0,34 | — | +0,13 |
| wav24_mono | 0,53 | — | 0,40 | 0,36 | 0,34 | — | +0,13 |
| wav32f_sobre_0 | 4,53 | — | 4,40 | 4,36 | 4,34 | — | +0,13 |
| wav24_muestras_0dbfs | 1,53 | — | 1,40 | 1,36 | 1,34 | — | +0,13 |
| wav24_tp_entre_m1_y_0 | 0,93 | — | 0,80 | 0,76 | 0,74 | — | +0,13 |
| wav24_clipping_evidente | 4,40 | — | 4,30 | 4,72 | 4,21 | — | +0,10 |
| wav24_clip_solo_L | 3,83 | — | 3,70 | 4,05 | 3,65 | — | +0,13 |
| wav24_limitado_sin_clip | 3,39 | — | 3,30 | 3,73 | 3,19 | — | +0,09 |
| wav24_clip_sostenido | 0,06 | — | 0,10 | 0,06 | 0,06 | — | −0,04 |
| wav24_clip_una_muestra | −0,00 | — | −0,00 | −0,00 | 0,01 | — | −0,00 |
| wav24_crest_bajo | −0,92 | — | −0,90 | −0,82 | −0,94 | — | −0,02 |
| wav24_48000_pico_menos1 | −1,00 | — | −1,00 | −0,99 | −0,99 | — | 0,00 |
| wav24_96000_pico_menos1 | −0,94 | — | −1,00 | −0,20 | −0,48 | — | +0,06 |
| mp3_320 | −0,01 | — | −0,00 | −0,01 | 0,01 | — | −0,01 |

---

## Desviación 1 — continua: +1,10 dB (FALLO)

Mentotrack mide −4,90 dBTP en una señal continua a −6,0 dBFS. El true peak de
una continua **es** su sample peak: no hay nada entre muestras. ffmpeg, la FFT
y el valor analítico coinciden los tres en −6,00.

### Causa, verificada experimentalmente

No es cosa de soxr: `scipy.signal.resample_poly` comete el mismo error
(−4,91). Es el **transitorio de borde** del filtro de sobremuestreo. El
archivo empieza y termina de golpe a amplitud plena; el FIR ve un escalón y
produce sobreoscilación de Gibbs en los primeros y últimos coeficientes.

Prueba directa — el mismo material con y sin fade de 50 ms:

| caso | Mentotrack | ffmpeg | fft 32× | poly 4× |
|---|---|---|---|---|
| continua **sin** fade | **−4,90** | −6,00 | −6,00 | −4,91 |
| continua **con** fade | **−6,00** | −6,00 | −6,00 | −5,99 |

Con fade, los cuatro métodos coinciden. Queda demostrado.

**Alcance real.** Afecta a archivos que empiezan o acaban abruptamente a
nivel alto: bounces cortados sin fade, loops, edits. Un track con fade-in o
que arranque en silencio no está afectado. El error siempre es **al alza**,
así que puede inflar la clasificación hacia "clipping".

**No se corrige en fase 1.** Arreglarlo cambia valores de true peak y por
tanto la clasificación, que está fuera de alcance. Propuesta para fase 2:
rellenar con ceros ~2.000 muestras a cada lado antes de sobremuestrear y
descartar esas zonas al buscar el máximo.

## Desviación 2 — material musical: +0,13 dB (dentro de tolerancia)

Constante en 8 fixtures distintos. **No** es efecto de borde: el fade no lo
cambia (0,53 con y sin fade).

Causa probable: rechazo imperfecto de las imágenes espectrales por parte de
soxr_hq. Los fixtures musicales llevan ráfagas de ruido (hats) con energía
hasta Nyquist; la FFT las elimina de forma ideal, soxr deja pasar un residuo
que suma al pico. Coherente con que `resample_poly` (filtro distinto) dé
−0,19 respecto a Mentotrack en la misma señal.

Está dentro de la tolerancia acordada (±0,30 vs ffmpeg) y el sesgo es
conservador (mide de más, avisa de más). Queda documentado, no se toca.

## Desviación 3 — ffmpeg se desvía +0,59 dB del valor analítico

En los tres fixtures `isp_fs4`, donde la respuesta correcta es +2,81 dBTP:

- Mentotrack: 2,91 → **+0,10** del valor correcto
- FFT sinc 32×: 2,81 → **exacto**
- ffmpeg: 3,40 → **+0,59** del valor correcto

En el caso donde se conoce la verdad, **Mentotrack acierta más que ffmpeg**.

Consecuencia metodológica: ffmpeg no puede arbitrar un caso en el que él
mismo falla. El validador lo comprueba ahora automáticamente — calcula la
desviación de ffmpeg respecto al analítico y, si supera la tolerancia
analítica, esa discrepancia se registra pero **no cuenta como fallo**, con
una nota explícita en el JSON. Las tolerancias acordadas **no se han tocado**.

---

## Conclusión

| | |
|---|---|
| Veredicto | **FALLA** (1 fallo real: continua, +1,10 dB) |
| `_TRUE_PEAK_VALIDATED` | `False` |
| Bloquea el despliegue | Según lo acordado, **sí** hasta decidir qué hacer |
| Precisión en música | ±0,13 dB frente a tres referencias — aceptable |
| Precisión en el caso analítico | +0,10 dB — mejor que ffmpeg |
| Fallo real | Solo con discontinuidad en los bordes del archivo |

El medidor es razonablemente bueno salvo por un artefacto acotado y bien
entendido. La decisión de si eso basta para desplegar la fase 1 —que **no
cambia ningún valor de true peak respecto a hoy**— es de Alex.

## Pendiente antes de poner `_TRUE_PEAK_VALIDATED = True`

1. Corregir el artefacto de borde (fase 2).
2. Cerrar la comprobación manual con un medidor profesional.
3. Pinear `soxr`, `soundfile` y `numpy` en `requirements.txt`.
4. Volver a ejecutar esta batería en el contenedor de producción.
