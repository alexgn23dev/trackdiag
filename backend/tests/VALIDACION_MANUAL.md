# Validación externa del true peak — registro manual

**Estado: PENDIENTE.** Ninguna fila tiene datos reales.

Mientras esta tabla no esté completa,
`TRUE_PEAK_EXTERNAL_VALIDATION_PASSED` sigue en `False` en
`backend/engine/extractor.py`, y por tanto `_TRUE_PEAK_VALIDATED` también.

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

## Tabla

Las columnas «Mentotrack», «FIR ITU» y «FFmpeg» salen de `auto.json`. Las
demás se rellenan a mano.

| # | Archivo | SR | Formato | SP Mentotrack (dBFS) | TP Mentotrack (dBTP) | FIR ITU | FFmpeg | Medidor externo | Δ ext−Mento | Δ ext−ITU | Resultado | Observaciones |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `wav24_pico_menos1.wav` | 44100 | WAV PCM_24 | −1,00 | +0,53 | +0,22 | +0,40 | | | | ⬜ | Material musical de banda completa |
| 2 | `wav24_bandlimitada_15k.wav` | 44100 | WAV PCM_24 | −1,00 | +0,15 | +0,12 | +0,10 | | | | ⬜ | **El más representativo de música real** |
| 3 | `isp_fs4_sobre_0.wav` | 44100 | WAV PCM_24 | −0,20 | +2,91 | +2,89 | +3,40 | | | | ⬜ | Analítico: **+2,81**. Decide |
| 4 | `isp_fs4_48000.wav` | 48000 | WAV PCM_24 | −0,20 | +2,91 | +2,89 | +3,40 | | | | ⬜ | Analítico: **+2,81**. Decide |
| 5 | `isp_fs4_96000.wav` | 96000 | WAV PCM_24 | −0,20 | +2,91 | +2,89 | +3,40 | | | | ⬜ | Analítico: **+2,81**. Decide |
| 6 | `wav24_muestras_0dbfs.wav` | 44100 | WAV PCM_24 | 0,00 | +1,53 | +1,22 | +1,40 | | | | ⬜ | Normalizado exacto a fondo de escala |
| 7 | `wav32f_sobre_0.wav` | 44100 | WAV FLOAT 32 | +3,00 | +4,53 | +4,22 | +4,40 | | | | ⬜ | Comprobar que el medidor lee el float sin recortar a 0 |
| 8 | `wav24_clip_solo_L.wav` | 44100 | WAV PCM_24 | 0,00 | +3,83 | — | +3,70 | | | | ⬜ | Anotar si el medidor distingue L de R |
| 9 | `mp3_320.mp3` | 44100 | MP3 320 | — | −0,01 | — | −0,00 | | | | ⬜ | Decodificadores distintos: informativo |
| 10 | `dc_salto_interno_menos6.wav` | 44100 | WAV PCM_24 | −6,00 | −4,90 | −5,05 | −4,90 | | | | ⬜ | Escalón interno. **No decide**, solo se registra |

Resultado: ⬜ pendiente · ✅ dentro de tolerancia · ⚠️ fuera (investigar) · ➖ no decide

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
