# Validación externa del true peak — registro manual

**Estado: EJECUTADA EL 2026-08-07 · RESULTADO: NO PASA.**

`TRUE_PEAK_EXTERNAL_VALIDATION_PASSED` permanece en `False` en
`backend/engine/extractor.py`, y por tanto `_TRUE_PEAK_VALIDATED` también.
**No se ha tocado ninguna tolerancia ni el algoritmo para forzar el paso.**

## Resultado

| Campo | Valor |
|---|---|
| Medidor | Youlean Loudness Meter 2, versión 2.5.14 |
| Cadena | Ableton Live 12.4.3 · macOS Sonoma 14.0 |
| Métrica | True Peak / dBTP |
| Fecha | 2026-08-07 |
| Persona | Alex Gonzalez |
| `peak_algorithm_version` evaluada | **`peak-soxr_hq_4x-1`** |
| Fixtures evaluados | 8 decisivos + 2 informativos |
| Resultado | **4 PASS · 3 FAIL · 1 sin medir** |
| Desviación máxima | **−0,33 dB** (fixtures 01 y 06) |
| Desviación media (filas limpias) | **−0,20 dB** — Mentotrack lee sistemáticamente alto |

| # | Archivo | Mentotrack | Youlean | Δ | Tolerancia | Resultado |
|---|---|---|---|---|---|---|
| 1 | `01_wav24_pico_menos1.wav` | +0,53 | +0,20 | **−0,33** | ±0,30 | **FAIL** |
| 2 | `02_wav24_bandlimitada_15k.wav` | +0,14 | +0,10 | −0,04 | ±0,30 | PASS |
| 3 | `03_isp_fs4_sobre_0.wav` (44,1 nativo) | +2,91 | +2,80 | −0,11 | ±0,15 | PASS |
| 4 | `04_isp_fs4_48000.wav` | +2,91 | — | — | ±0,15 | sin medir a 48 kHz nativo |
| 5 | `05_isp_fs4_96000.wav` (96 nativo) | +2,91 | +2,70 | **−0,21** | ±0,15 | **FAIL** |
| 6 | `06_wav24_muestras_0dbfs.wav` | +1,53 | +1,20 | **−0,33** | ±0,30 | **FAIL** |
| 7 | `07_wav32f_sobre_0.wav` | +4,53 | +4,30 | −0,23 | ±0,30 | PASS |
| 8 | `08_wav24_clip_solo_L.wav` | +3,83 | +3,70 | −0,13 | ±0,30 | PASS |
| 9 | `09_mp3_320.mp3` | −0,01 | −0,10 | −0,09 | informativo | — |
| 10 | `10_dc_salto_interno_menos6.wav` | −4,90 | −4,80 | +0,10 | informativo | — |

## Interpretación

**Los fallos 01 y 06 son el hallazgo.** Material de banda completa con energía
hasta Nyquist. Youlean y el FIR normativo (`tests/itu_bs1770.py`) coinciden
dentro de **0,02 dB** (+0,20 vs +0,22 · +1,20 vs +1,22); soxr_hq_4x está 0,33
por encima de ambos. Es la tercera y cuarta referencia independiente que
apuntan en la misma dirección: la reconstrucción sinc por FFT ya daba +0,17.

Comparativa sobre las filas limpias:

```
Youlean vs soxr_hq_4x : media −0,195 · máx 0,33
Youlean vs FIR ITU    : media −0,012 · máx 0,09   (excluyendo el fixture 08)
```

**El fallo 05 es otro fenómeno.** Contra la verdad analítica (+2,8103):
Youlean −0,11, Mentotrack +0,10. Se desvían los dos, en direcciones opuestas
y por magnitudes parecidas; su suma (0,21) revienta la tolerancia estrecha.
No demuestra que soxr esté mal, sino que a 96 kHz las implementaciones
divergen en señales patológicas — BS.1770 especifica el sobremuestreo 4×
pensando en 44,1 y 48 kHz. La misma señal a 44,1 nativo (fixture 03) da
−0,01 en Youlean.

**Los fixtures 04 y 05 no son medibles a través de un DAW salvo a su rate
nativo.** Son tonos a exactamente fs/4: al reconvertir el sample rate, el
tono deja de estar en fs/4 del nuevo rate, cambia el patrón de muestreo y con
él el pico entre muestras. Medido, el 04 dio +2,70 y +2,90 según el rate del
proyecto — con el mismo archivo.

## Consecuencia y decisión tomada

El sesgo afecta a los análisis con true peak entre 0 y +0,2 dBTP: **162 del
histórico (7,4%)**, que hoy se clasifican por encima de 0 y probablemente no
lo están.

**El sesgo es preexistente**: está en producción desde mayo de 2026 y la
versión v0.5.71 no altera ningún valor de true peak (lo garantiza el golden).
Decisión de Alex el 2026-08-07: desplegar v0.5.71, que arregla otros cinco
problemas reales, dejando `true_peak_validated=false` registrado en cada
análisis, y atacar el sesgo en la fase 2B.

## Para repetir la validación

Los 10 fixtures se generan con `python tests/fixtures.py <destino>`; el
script `preparar_validacion.py` del histórico de trabajo los deja numerados.
Al repetirla hay que medir cada archivo **a su sample rate nativo**.

## Por qué hace falta

Las cuatro referencias de `validar_true_peak.py` (valor analítico, FIR de la
ITU, sinc por FFT, ffmpeg) viven todas dentro del mismo ecosistema
Python/ffmpeg y comparten decodificador de archivo. Un medidor profesional de
escritorio es la única referencia realmente ajena: otro decodificador, otra
implementación, otro fabricante.

## Cómo rellenarla

1. Generar los fixtures:

   ```bash
   cd backend && python tests/fixtures.py /ruta/donde/quieras
   ```

2. Obtener las columnas automáticas (Mentotrack, FIR ITU, ffmpeg):

   ```bash
   python tests/validar_true_peak.py --fixtures /ruta/donde/quieras --json auto.json
   ```

3. Abrir cada archivo en el medidor externo y anotar su true peak. Medidores
   válidos: **Youlean Loudness Meter 2**, **iZotope Insight 2**, **NUGEN
   MasterCheck**, o el medidor de true peak del DAW (Ableton, Logic, Cubase,
   Studio One). Anotar cuál se usó y su versión.

   Importante: poner el medidor en **true peak / dBTP**, no en sample peak, y
   dejar que procese el archivo entero.

4. Rellenar la tabla, calcular las diferencias y marcar el resultado.

## Criterio de aprobación

| Tipo de fixture | Tolerancia frente al medidor externo |
|---|---|
| Con valor analítico conocido (`isp_fs4`, continua) | ±0,15 dB |
| Material musical | ±0,30 dB |
| Señales con discontinuidad (`dc_*`) | Solo se registra; **no** decide, porque cada implementación asume algo distinto fuera del archivo |

Aprueba si **todas** las filas que deciden quedan dentro de tolerancia. Si
alguna se sale: **no tocar la tolerancia**. Investigar primero, igual que se
hizo con el falso positivo de la continua (ver `RESULTADOS_VALIDACION.md`).

## Medidor utilizado

| Campo | Valor |
|---|---|
| Software | *(por rellenar)* |
| Versión | *(por rellenar)* |
| Sistema operativo | *(por rellenar)* |
| Fecha de la medición | *(por rellenar)* |
| Persona | *(por rellenar)* |

## Al terminar

Si todas las filas que deciden salen ✅:

1. Rellenar la sección «Medidor utilizado».
2. Poner en `backend/engine/extractor.py`:
   ```python
   TRUE_PEAK_EXTERNAL_VALIDATION_PASSED = True   # ver tests/VALIDACION_MANUAL.md
   ```
   `_TRUE_PEAK_VALIDATED` pasará a `True` solo, porque se deriva de las dos.
3. Actualizar `test_entorno.py::test_externa_no_pasa_todavia`, que hoy
   comprueba justo lo contrario y fallará a propósito.
4. Anotarlo en `RESULTADOS_VALIDACION.md`.
