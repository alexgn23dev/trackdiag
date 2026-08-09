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

---

## 8. Una referencia que sí es la verdad (2026-08-07)

Todo lo anterior compara implementaciones entre sí. Cuando discrepan no hay
forma de saber cuál acierta, y eso es lo que dejó bloqueada la fase 2B.

Ahora existe `tests/reconstruccion_exacta.py`, que **no es otra
implementación**: es la definición. El teorema de muestreo dice que la señal
continua detrás de un archivo es única; su máximo se obtiene rellenando de
ceros el espectro, sin elegir filtro ni número de taps. Los tests de
`test_reconstruccion.py` la verifican antes de usarla: reproduce el valor
analítico del seno a fs/4, converge al subir el factor, y nunca queda por
debajo del sample peak.

### Ningún medidor real es plano

Pico medido de un seno de amplitud 1,0, cuyo pico real es 0,000 dB a
cualquier frecuencia. Lo que se aparta de 0 es error del reconstructor:

| frecuencia | % Nyquist | exacta | FIR ITU 4× | soxr_hq 4× |
|---|---|---|---|---|
| 1 kHz | 4,5 % | 0,000 | +0,008 | 0,000 |
| 5 kHz | 22,7 % | 0,000 | **+0,115** | 0,000 |
| 10 kHz | 45,3 % | 0,000 | **+0,120** | 0,000 |
| 15 kHz | 68,0 % | 0,000 | +0,032 | 0,000 |
| 19 kHz | 86,2 % | 0,000 | −0,213 | 0,000 |
| 20 kHz | 90,7 % | 0,000 | −0,458 | 0,000 |
| 21 kHz | 95,2 % | 0,000 | −0,688 | −3,792 |
| 22 kHz | 99,8 % | 0,000 | **−0,791** | **−98,8** |

Los dos fallan, de formas distintas: **el FIR de 12 taps tiene rizado en toda
la banda de paso y cae cerca de Nyquist; soxr es exacto hasta el 90 % de
Nyquist y a partir de ahí borra el contenido.**

### Esto contesta las dos preguntas que bloqueaban la fase 2B

**Pregunta 1 — el fixture 08.** No es un caso raro ni un error de
transcripción: un recorte duro llena el espectro hasta Nyquist, justo donde el
FIR ya no llega. Frente a la reconstrucción exacta (+4,050 dBTP en el canal
izquierdo), el FIR se queda en −0,729 y soxr en −0,222.

**Pregunta 2 — 96 kHz.** El problema desaparece solo. Con material realista a
88,2 o 96 kHz, el pico entre muestras es menor de 0,05 dB y los dos medidores
coinciden con la reconstrucción exacta dentro de 0,05 dB. El fixture 05 es un
tono a fs/4 de 96 kHz, es decir **24 kHz**: por encima de lo audible y de lo
que produce cualquier instrumento. Que las implementaciones discrepen ahí no
dice nada sobre música real.

### El error de cada candidato, medido

Frente a la reconstrucción exacta. Material realista = el mismo bounce
limitado en banda a 8/12/16/18/19/20 kHz, que es lo que sale de un DAW:

| | material realista | con energía hasta Nyquist |
|---|---|---|
| FIR ITU 4× | 0,100 | **0,850** |
| soxr_hq 4× (producción) | 0,114 | 0,387 |
| soxr_hq **8×** | **0,004** | 0,387 |
| soxr_hq 16× | 0,004 | 0,387 |

### Dos conclusiones que invierten el plan de la fase 2B

**1. Cambiar a el FIR normativo empeoraría la medición.** El plan aprobado
partía de que soxr tenía un sesgo alto y el FIR era la referencia buena.
Medido contra la verdad, es al revés: el FIR es el peor de los candidatos.

**2. Parte del error de producción no es del filtro, es de la rejilla.**
Sobremuestrear 4× da cuatro puntos por muestra y el máximo real cae entre
ellos. Subiendo a **8×**, sin tocar el filtro, el error con material realista
baja de 0,114 dB a **0,004 dB**. Por encima de 8× ya no aporta nada. Coste
medido en una pista de 6 minutos estéreo: 0,40 s → 0,85 s.

Lo que **no** arregla subir el factor: el material con energía por encima de
20 kHz (masters muy saturados). Ahí el error es del filtro y se queda en
0,387 dB, suba lo que suba el sobremuestreo.

### Y por qué Youlean no puede ser el juez

La validación externa dio FAIL porque soxr leía 0,33 dB por encima de Youlean
en los fixtures 01 y 06. Con la referencia exacta en la mano, el reparto de
culpas es otro:

| fixture | exacto | soxr_hq 4× | Youlean |
|---|---|---|---|
| 01 | +0,360 | +0,531 (+0,17) | +0,20 (**−0,16**) |
| 06 | +1,360 | +1,531 (+0,17) | +1,20 (**−0,16**) |

**Los dos se desvían, en direcciones opuestas y por la misma magnitud.**
Youlean no es la verdad: es otro filtro finito, con su propio compromiso cerca
de Nyquist. Ambos fixtures tienen los hats hechos de ruido blanco hasta
Nyquist — energía que no tiene un bounce normal.

Esto **no** anula el FAIL registrado: el criterio que se acordó era coincidir
con un medidor externo, y no se cumplió. Lo que dice es que el criterio medía
lo que no era. La propuesta está en `DISENO_FASE_2B.md`.

---

## 8b. La referencia, comprobada contra una verdad construida (2026-08-08)

El §8 justificaba la referencia por teoría: "es la definición". Eso es poco, y
Alex lo señaló. Esta es la comprobación empírica.

**El método.** La verdad no se mide, se construye:

1. Se fabrica una señal a 44100 × 64 = **2,8 MHz** cuyo contenido no pasa de
   20 kHz. A ese rate está tan sobremuestreada que su máximo discreto ya es el
   continuo.
2. Se anota ese máximo. Es la verdad, conocida de antemano.
3. Se decima quedándose 1 de cada 64 muestras — sin filtrar, porque la señal
   ya venía limitada en banda. Eso es el archivo de 44,1 kHz.
4. Se le pide a cada medidor que recupere el número del paso 2 mirando solo el
   archivo del paso 3.

**Control del patrón:** reinterpolar la verdad 4× más fino la mueve
**0,00002 dB**. El patrón es sólido.

**Resultado** — error en dB frente al pico real, siete señales:

| señal | exacta 4× | exacta 8× | **exacta 16×** | FIR ITU 4× | soxr 4× | soxr 8× |
|---|---|---|---|---|---|---|
| hasta 20 kHz (s1) | −0,021 | −0,002 | −0,002 | +0,025 | −0,021 | −0,002 |
| hasta 20 kHz (s2) | −0,029 | −0,001 | −0,001 | −0,020 | −0,029 | −0,001 |
| hasta 16 kHz (s3) | −0,003 | −0,003 | −0,001 | −0,018 | −0,003 | −0,003 |
| hasta 10 kHz (s4) | −0,016 | −0,002 | −0,002 | **−0,113** | −0,016 | −0,002 |
| hasta 21,5 kHz (s5) | −0,006 | −0,003 | −0,000 | −0,004 | −0,033 | −0,034 |
| hasta 21,9 kHz (s6) | −0,012 | −0,006 | −0,000 | +0,012 | +0,073 | +0,085 |
| hasta 5 kHz (s7) | −0,001 | −0,001 | −0,000 | −0,010 | −0,001 | −0,001 |
| **máx \|error\|** | 0,029 | 0,006 | **0,002** | 0,113 | 0,073 | 0,085 |

### Qué queda demostrado

1. **La referencia acierta.** Recupera un pico que no conocía, con 0,002 dB de
   error, en siete señales de anchos de banda distintos. Deja de ser un
   argumento teórico.
2. **El error de rejilla es real y se ve solo.** La misma referencia perfecta
   pierde 0,029 dB a 4× y 0,006 a 8×. Es exactamente lo que corrigió la
   v0.5.72, medido sin ningún filtro de por medio.
3. **El FIR de la norma se equivoca 0,113 dB con una señal que no pasa de
   10 kHz.** No es la zona alta del espectro: es su rizado en la banda de
   paso, con material completamente benigno. Descartarlo fue lo correcto.

### Dos límites, declarados

* **Con energía pegada a Nyquist (s5, s6) el 8× no rescata nada**, y en un
  caso queda 0,012 dB por detrás del 4×. Ahí manda el filtro de soxr, no la
  rejilla. Es inaudible y está muy por debajo de la décima con la que se
  clasifica, pero el número no es cero y queda acotado en
  `test_con_energia_pegada_a_nyquist_el_8x_no_rescata_nada`.
* **Esta prueba valida la interpolación, no los bordes.** Las señales
  construidas son periódicas, que es el caso favorable para el método de la
  FFT. Lo que ocurre en el primer y último milisegundo de un archivo real
  sigue siendo terreno indefinido — ver §5b y el test del borde.

Congelado en `test_reconstruccion.py::TestContraUnaVerdadConstruida`.

---

## 8c. El árbitro cambia: la verdad construida, no un medidor comercial (v0.5.73)

Decidido por Alex el 2026-08-09, sobre la evidencia del §8b.

### Qué se cambia

`_TRUE_PEAK_VALIDATED` deja de depender del contraste manual con un medidor
de escritorio. Pasa a ser:

```python
_TRUE_PEAK_VALIDATED = (TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED
                        and TRUE_PEAK_INTERNAL_VALIDATION_PASSED)
```

| estado | valor | qué comprueba | ¿decide? |
|---|---|---|---|
| `true_peak_ground_truth_validation_passed` | **True** | Recuperar un pico construido de antemano | **Sí** |
| `true_peak_internal_validation_passed` | **True** | Batería contra analítico, ffmpeg, FIR, scipy | **Sí** |
| `true_peak_external_validation_passed` | False | Distancia a un medidor comercial | **No, informativa** |
| `true_peak_validated` | **True** | Las dos primeras | — |

### Por qué el medidor comercial deja de decidir

No es que Youlean mida mal. Es que **no es un patrón**. Sobre los fixtures 01
y 06, frente al pico real: Youlean −0,16 dB, soxr +0,17 dB. Los dos se
desvían, en direcciones opuestas y por la misma magnitud. Certificar contra
Youlean era corregir un examen con las respuestas de otro alumno.

El registro de `VALIDACION_MANUAL.md` **se conserva** y sigue siendo útil: 
documenta cuánto se separan entre sí las implementaciones reales, que es
exactamente el dato que hace falta para hablarle al usuario de incertidumbre.
Lo que ya no hace es conceder ni bloquear el aprobado.

### Lo que impide que esto sea un autoaprobado

`_VALIDACION_VERDAD_DECLARADA = True` es una constante que escribe una
persona. Sola no vale nada. Lo que la sostiene es
`test_picos.py::test_la_declaracion_de_validado_no_puede_mentir`, que
**vuelve a hacer la medición** con el medidor desplegado y exige que el
resultado coincida con lo declarado.

Comprobado que el seguro muerde en las dos direcciones:

```
declaración a False con la medida acertando  → FALLA
tolerancia imposible (0,0001 dB)             → FALLA
```

Error real del medidor desplegado contra la verdad construida: **0,0033 dB**,
frente a una tolerancia de 0,01.

---

## 9. Lo que se cambió: 4× → 8× (v0.5.72, 2026-08-07)

Aprobado por Alex tras el §8. **No se cambió el filtro** —el FIR de la norma
queda descartado por lo medido arriba— sino el factor de sobremuestreo.

| | |
|---|---|
| `PEAK_ALGORITHM_VERSION` | `peak-soxr_hq_4x-1` → **`peak-soxr_hq_8x-1`** |
| Validación interna | **re-ejecutada, PASA** (`tests/validar_true_peak.py`) |
| Validación externa | **`False`** — caducó al cambiar el algoritmo. Hay que repetirla |
| `_TRUE_PEAK_VALIDATED` | `False` |
| Error con material realista | 0,114 dB → **0,001 dB** |
| Coste, pista de 6 min estéreo | 0,40 s → 0,85 s |

### Cuánto se movió de verdad

De los 30 fixtures del golden, **solo 3 cambian a 1 decimal**:

| fixture | 4× | 8× | exacta | qué es |
|---|---|---|---|---|
| `wav24_96000_pico_menos1` | −0,9 | **−0,7** | −0,2 | Mejora real: se subestimaba 0,75 dB, ahora 0,53 |
| `dc_estable_menos6` | −4,9 | −4,5 | −4,9 | Borde del archivo: ni mejor ni peor, ver abajo |
| `dc_bordes_menos6` | −4,9 | −4,5 | −4,9 | Ídem |

**El resto de fixtures no se mueve.** Que el cambio sea casi invisible en el
golden y muy visible en material limitado en banda no es contradictorio: los
fixtures tienen los hats hechos de ruido blanco hasta Nyquist, y ahí manda el
filtro, no la rejilla.

### El aviso sobre los dos fixtures de continua

**No leerlos como una regresión.** Su máximo cae en el borde del archivo,
donde el valor depende de qué se asuma fuera y **no converge con el factor**:

```
x4 −4,90 · x8 −4,52 · x16 −4,84 · x24 −4,52 · x32 −4,89
```

Salta sin tendencia. En cambio un escalón **dentro** del archivo
(`dc_salto_interno_menos6`) da −4,94 con todos los factores, sin excepción.
La conclusión es la misma del §5b: en el borde no hay nada bien definido que
medir, y por eso esos fixtures son informativos y no deciden. Congelado en
`test_reconstruccion.py::test_en_el_borde_del_archivo_ningun_factor_converge`.

### Por qué 8 y no 16

Con material realista los dos dan 0,001 dB. 16× cuesta el doble (1,83 s
frente a 0,85 s en una pista de 6 minutos) y no compra nada. Los factores
intermedios no son monótonos —x6 da 0,020 y x12 da 0,009, ambos peores que
x8— porque por debajo de 8 el error de rejilla todavía depende de dónde caiga
el máximo respecto a la retícula.

### Lo que sigue sin arreglarse, y no se puede

Material con energía por encima de 20 kHz: soxr descarta esa zona y se queda
~0,39 dB corto, **suba lo que suba el sobremuestreo**. Es error del filtro.
Ningún medidor comercial acierta ahí tampoco. La consecuencia de producto
—que la frontera de `true_peak_over` en 0,0 dBTP es más fina de lo que la
medida resuelve en ese material— sigue abierta en `DISENO_FASE_2B.md`.
