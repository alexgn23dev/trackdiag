# Contraste contra un medidor comercial — registro manual

> ## ℹ️ INFORMATIVO. Ya no decide, y no hay que repetirlo (2026-08-09)
>
> Este documento nació como "validación externa": el aprobado final del
> medidor dependía de coincidir con un medidor profesional de escritorio.
> **Ese planteamiento era incorrecto y se retiró en la v0.5.73.**
>
> El motivo, medido: un medidor comercial no es un patrón. Frente al pico
> real, sobre los fixtures 01 y 06, **Youlean se desvía −0,16 dB y soxr
> +0,17 dB**. Los dos fallan, en direcciones opuestas y por la misma
> magnitud. Certificar contra Youlean era corregir un examen con las
> respuestas de otro alumno.
>
> **Quién decide ahora:** la capacidad de recuperar un pico *construido de
> antemano* — se fabrica una señal a 44100×64 limitada en banda, se anota su
> máximo real, se decima y se mide. Ver `RESULTADOS_VALIDACION.md §8b y §8c`.
>
> **Qué sigue valiendo de aquí abajo:** es la mejor medida que tenemos de
> cuánto se separan entre sí las implementaciones reales. Ese número es justo
> el que hace falta para hablarle al usuario de incertidumbre — y para no
> extrañarse cuando su medidor y Mentotrack no den lo mismo.
>
> **Los datos de abajo se tomaron con `peak-soxr_hq_4x-1`.** Desde la v0.5.72
> el algoritmo es `peak-soxr_hq_8x-1`. Si alguna vez se repite el contraste,
> hay que rehacer la tabla — pero **no bloquea nada**.

---

**Estado del registro histórico: EJECUTADA EL 2026-08-07 · RESULTADO: NO PASA.**

`TRUE_PEAK_EXTERNAL_VALIDATION_PASSED` permanece en `False`. **No se tocó
ninguna tolerancia ni el algoritmo para forzar el paso** — se investigó, y la
investigación acabó demostrando que el árbitro estaba mal elegido. Desde la
v0.5.73 este estado ya no arrastra a `_TRUE_PEAK_VALIDATED`.

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

## Por qué se montó así, y por qué era insuficiente

El razonamiento original: las cuatro referencias de `validar_true_peak.py`
(valor analítico, FIR de la ITU, sinc por FFT, ffmpeg) viven dentro del mismo
ecosistema Python/ffmpeg y comparten decodificador. Un medidor profesional de
escritorio es otro decodificador, otra implementación, otro fabricante.

Eso es cierto y sigue siendo útil. **El error fue confundir "ajeno" con
"correcto".** Un segundo medidor independiente detecta que discrepáis, pero no
dice quién acierta — y aquí resultó que no acertaba ninguno de los dos. Lo que
faltaba no era otra implementación, sino un **patrón**: un pico conocido de
antemano que el medidor tenga que recuperar. Eso es lo que hay ahora.

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

## Criterio de aprobación — RETIRADO

Estas eran las tolerancias con las que este documento decidía. **Ya no
deciden nada**; se conservan para poder leer la tabla de arriba.

| Tipo de fixture | Tolerancia que se usó |
|---|---|
| Con valor analítico conocido (`isp_fs4`, continua) | ±0,15 dB |
| Material musical | ±0,30 dB |
| Señales con discontinuidad (`dc_*`) | Solo se registraba |

La regla de "si alguna se sale, **no tocar la tolerancia**, investigar
primero" se cumplió — y la investigación es justo lo que acabó retirando el
criterio entero. Ver `RESULTADOS_VALIDACION.md §8b`.

## Medidor utilizado

| Campo | Valor |
|---|---|
| Software | *(por rellenar)* |
| Versión | *(por rellenar)* |
| Sistema operativo | *(por rellenar)* |
| Fecha de la medición | *(por rellenar)* |
| Persona | *(por rellenar)* |

## Al terminar

**Ya no hay nada que activar.** Este contraste no concede el aprobado desde la
v0.5.73 — ver el aviso del principio.

Si alguna vez se repite, lo único que hay que hacer es rehacer la tabla y
anotar la desviación observada en `RESULTADOS_VALIDACION.md`. Sirve para
saber cuánta distancia hay con lo que ve el usuario en su DAW, no para
decidir si el motor está bien.

**Lo que NO hay que hacer:** poner `_VALIDACION_EXTERNA_DECLARADA = True`
esperando que eso cambie `true_peak_validated`. Ya no entra en esa cuenta, y
`test_entorno.py::test_la_externa_es_informativa_y_no_decide` lo comprueba.
