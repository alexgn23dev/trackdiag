# Validación del medidor de true peak

**Última ejecución:** 2026-08-06 · **Motor:** v0.5.71 · rama `feature/motor-picos-fase1`

**Veredicto de la batería automática: PASA.**
**`_TRUE_PEAK_VALIDATED` sigue en `False`** — falta la comprobación manual
contra un medidor profesional (§6) y la ejecución en la imagen de producción.

```bash
python tests/validar_true_peak.py     # veredicto
python tests/estudio_continua.py      # estudio de señales con discontinuidad
python tests/reporte_entorno.py       # todo + versiones
```

---

## 1. Corrección respecto a la primera versión de este documento

La primera pasada concluyó que el motor tenía **un fallo de +1,10 dB** en
señales continuas. **Esa conclusión era incorrecta** y se retira.

Al implementar el FIR de referencia de la norma y comparar sobre un escalón
que está *dentro* del archivo —donde no hay ninguna ambigüedad sobre qué se
asume fuera— resulta que **los cuatro métodos sobrepasan el sample peak**, y
ffmpeg coincide con soxr hasta la tercera cifra:

| método | máx. sobre el escalón interno |
|---|---|
| soxr_hq_4x (producción) | **−4,900** |
| ffmpeg ebur128 | **−4,900** |
| FIR ITU-R BS.1770-5 | −5,048 |
| sinc por FFT 32× (ideal) | −4,854 |

El sample peak de esa señal es −6,000 dBFS. Que la reconstrucción supere el
sample peak ante un escalón **no es un artefacto: es la señal**. Una
discontinuidad tiene excursiones reales entre muestras, y cualquier medidor
de true peak correcto las reporta. La reconstrucción ideal es la que más
sobrepasa de las cuatro.

---

## 2. Entorno

| Componente | Local (venv 3.11) | Producción |
|---|---|---|
| Python | 3.11.15 | 3.11 (`python:3.11-slim`) |
| numpy | 2.4.6 | **pineada** en requirements.txt |
| scipy | 1.17.1 | **pineada** |
| soundfile | 0.14.0 | **pineada** |
| libsndfile | 1.2.2 | la que trae la wheel de soundfile |
| librosa | 0.11.0 | **pineada** |
| soxr | 1.1.0 | **pineada** |
| pyloudnorm | 0.2.0 | **pineada** |
| ffmpeg | 8.1.1 | el de apt (bookworm) |

Desde v0.5.71 las siete están fijadas con `==`. Antes solo lo estaba
`librosa`, así que dos deploys del mismo commit podían medir distinto — soxr
es quien calcula el sobremuestreo del true peak.

### Fiabilidad de ffmpeg como referencia

Comprobada la propagación del pico global de `ebur128`, el problema conocido
de que el `Peak` del resumen no recoja el máximo real. En esta build el
resumen **coincide** con el máximo de los `TPK` por frame en los fixtures de
control (`4.30 == 4.30`, `3.40 == 3.40`). La propagación es correcta.

Propagar bien no implica medir bien: ver §4.

---

## 3. Las cuatro referencias

1. **Valor analítico.** Seno a `fs/4` desfasado 45°: las muestras caen en
   `±A/√2`, así que el true peak está exactamente `20·log10(√2) = +3,0103 dB`
   por encima del sample peak. No depende de ninguna implementación.
2. **FIR de ITU-R BS.1770-5, anexo 2** (`tests/itu_bs1770.py`). Banco
   polifásico 4 fases × 12 taps, transcrito de la Tabla 3. Solo para tests.
3. **ffmpeg `ebur128=peak=true`.** Implementación en C independiente.
4. **Dos caminos propios en Python sin soxr:** interpolación sinc exacta por
   FFT (32×, solo numpy) y polifásico con `scipy.signal.resample_poly`.

**Pendiente — manual:** contrastar 3-4 fixtures contra un medidor profesional
de escritorio (Youlean Loudness Meter 2, iZotope Insight, o el del DAW). Es la
única referencia ajena al ecosistema Python/ffmpeg y **debe cerrarse antes de
poner `_TRUE_PEAK_VALIDATED = True`**.

### Verificación de los coeficientes del FIR

Los coeficientes están transcritos a mano de la norma, así que un error de
dígito no puede pasar inadvertido. `verificar_coeficientes()` comprueba las
propiedades estructurales que el banco debe cumplir, y los tests la ejecutan:

```
simetria_fase0_fase3   0.0        (el prototipo es de fase lineal)
simetria_fase1_fase2   0.0
ganancias_dc           [1.001587, 0.973022, 0.973022, 1.001587]
ganancia_dc_max_db     +0.0138 dB
ganancia_dc_min_db     −0.2375 dB
```

Simetría exacta y ganancia en continua próxima a 1 por fase. El +0,0138 dB de
la fase 0 explica que el FIR normativo mida una continua en −5,986 en vez de
−6,000: **es el error propio del filtro de la norma**.

---

## 4. Resultados

| fixture | Mentotrack | analítico | ffmpeg | fft 32× | poly 4× | Δ analít. | Δ ffmpeg |
|---|---|---|---|---|---|---|---|
| isp_fs4 (44,1/48/96 k) | 2,91 | 2,81 | 3,40 | 2,81 | 2,93 | **+0,10** | −0,49 |
| wav24_bandlimitada_15k | 0,15 | — | 0,10 | 0,16 | — | — | +0,05 |
| musicales banda completa (×8) | 0,53 | — | 0,40 | 0,36 | 0,34 | — | +0,13 |
| wav24_clipping_evidente | 4,40 | — | 4,30 | 4,72 | 4,21 | — | +0,10 |
| wav24_clip_una_muestra | −0,00 | — | −0,00 | −0,00 | 0,01 | — | −0,00 |
| wav24_48000 | −1,00 | — | −1,00 | −0,99 | −0,99 | — | 0,00 |
| mp3_320 | −0,01 | — | −0,00 | −0,01 | 0,01 | — | −0,01 |
| dc_estable / dc_bordes | −4,90 | — | −6,00 | −6,00 | −4,91 | — | (§5) |
| dc_salto_interno | −4,90 | — | −4,90 | −4,85 | −4,91 | — | 0,00 |

### En el caso donde se conoce la verdad, Mentotrack es el segundo más preciso

Sobre `isp_fs4`, cuyo valor correcto es +2,8103 dBTP:

| método | medido | error |
|---|---|---|
| sinc por FFT 32× | 2,810 | **exacto** |
| **soxr_hq_4x (producción)** | 2,910 | **+0,10** |
| FIR ITU (modo cero) | 2,893 | +0,08 |
| ffmpeg ebur128 | 3,400 | **+0,59** |

ffmpeg se desvía +0,59 dB del valor correcto en este caso, cinco veces más
que el algoritmo de producción. Por eso el validador comprueba ahora, de
forma automática, si la referencia externa acierta antes de dejar que arbitre:
calcula la desviación de ffmpeg respecto al analítico y, si se sale de la
tolerancia analítica, registra la discrepancia con una nota pero **no** la
cuenta como fallo. Las tolerancias acordadas no se han tocado.

---

## 5. La continua, en detalle

Tres variantes, dos regímenes de evaluación (`tests/estudio_continua.py`):

```
=== dc_salto_interno_menos6 (escalón DENTRO del archivo) ===
  método                   máx global   sin asentam.   Δ borde
  soxr_hq_4x                   -4.900         -4.900     0.000
  itu_fir_4x_cero              -5.048         -5.048     0.000
  fft_sinc_32x                 -4.854         -4.854     0.000
  ffmpeg                       -4.900              —         —

=== dc_estable_menos6 / dc_bordes_menos6 (escalón en el BORDE del archivo) ===
  soxr_hq_4x                   -4.900         -6.000     1.100
  itu_fir_4x_cero              -5.048         -5.986     0.938
  itu_fir_4x_extender          -5.986         -5.986     0.000
  fft_sinc_32x                 -6.000         -6.000     0.000
  ffmpeg                       -6.000              —         —
```

Dos lecturas distintas:

**(a) Escalón dentro del archivo.** Los cuatro métodos sobrepasan y coinciden
dentro de 0,2 dB. Es la respuesta real de la reconstrucción band-limited a
una discontinuidad. **No hay nada que corregir.**

**(b) Escalón en el borde del archivo.** Aquí el resultado depende por
completo de qué asume cada implementación fuera del archivo:

- soxr y el FIR en modo `cero` asumen silencio fuera → ven un escalón →
  sobreoscilan. Es lo que hace un DAC al reproducir el archivo.
- El FIR en modo `extender` asume que la señal continúa → sin escalón → −5,986.
- El sinc por FFT asume extensión periódica → sin escalón → −6,000.
- ffmpeg da −6,000: no ve escalón al arrancar.

**No hay una respuesta correcta**: son preguntas distintas. En régimen estable
—descartando el asentamiento— soxr da −6,000 exacto, mejor incluso que el FIR
normativo (−5,986, lastrado por su propia ganancia en continua).

Alcance práctico: solo afecta a archivos que arrancan o terminan de golpe a
nivel alto, y siempre al alza. **No se aplica ningún fade, recorte de primeras
o últimas muestras ni supresión de picos de borde en producción.**

---

## 6. Diferencias entre el FIR normativo y soxr_hq_4x

Medido variando el ancho de banda de la misma señal:

| señal | soxr − ideal | FIR ITU − ideal |
|---|---|---|
| banda completa (ruido hasta Nyquist) | **+0,171** | **−0,143** |
| paso-bajo a 15 kHz | −0,014 | −0,044 |
| paso-bajo a 10 kHz | −0,000 | +0,013 |

**Con el contenido lejos de Nyquist, los cuatro métodos coinciden dentro de
0,013 dB.** Toda la divergencia la produce la energía pegada a Nyquist, y los
dos se separan del ideal **en direcciones opuestas**:

- el FIR de la norma tiene 12 taps por fase: banda de transición ancha,
  atenúa la zona alta y **lee de menos**;
- soxr_hq tiene un filtro mucho más largo: conserva esa zona pero deja pasar
  algo de imagen espectral y **lee de más**.

Ninguno de los dos es un fallo. Consecuencia importante: el **+0,13 dB
sistemático frente a ffmpeg** que apareció en la primera pasada es un
artefacto de los fixtures (los hats son ruido blanco hasta Nyquist), no un
sesgo con música real. Sobre el fixture de banda limitada a 15 kHz la
diferencia con ffmpeg baja a **+0,05 dB**.

Casos extremos medidos, para que consten: con saturación `tanh` (armónicos
hasta Nyquist) el FIR normativo lee 0,91 dB por debajo del ideal; a 96 kHz con
ruido hasta 48 kHz, 0,30 dB por debajo. Los tests fijan el signo y una cota de
1,0 dB, para que un cambio de librería se note.

---

## 7. Conclusión

| | |
|---|---|
| Veredicto automático | **PASA** |
| `_TRUE_PEAK_VALIDATED` | **`False`** — falta la verificación manual y la ejecución en Docker |
| Precisión con música real | ±0,05 dB frente a cuatro referencias |
| Precisión en el caso analítico | +0,10 dB — cinco veces mejor que ffmpeg |
| Continua en régimen estable | −6,000 exacto |
| ¿Hay algún fallo demostrado? | **No.** Lo que parecía un fallo de +1,10 dB es la respuesta real ante una discontinuidad |

## Pendiente antes de `_TRUE_PEAK_VALIDATED = True`

1. Comprobación manual con un medidor profesional de escritorio.
2. Ejecutar `tests/reporte_entorno.py` dentro de la imagen de Docker.
3. Decidir qué se considera correcto en el borde del archivo (§5b): asumir
   silencio fuera, como ahora, o régimen estable. Es una decisión de producto,
   no de corrección.
