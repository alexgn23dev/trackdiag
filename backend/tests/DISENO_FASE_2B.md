# Fase 2B — campos de muestras a fondo de escala

**Diseño. Nada de esto está implementado.**

---

## PRIORIDAD 0 — RETIRADA el 2026-08-07, antes de implementarse

> **Lo que decía este apartado era incorrecto.** Proponía sustituir
> `soxr_hq_4x` por el FIR 4× del anexo 2 de BS.1770-5, dando por hecho que
> soxr tenía un sesgo alto y que el FIR era la referencia buena. Al investigar
> las dos preguntas abiertas que el propio plan dejaba (el fixture 08 y el
> comportamiento a 96 kHz) resultó que **el FIR es el peor de los candidatos**
> y que hacer el cambio habría empeorado la medición.
>
> El texto original queda al final de esta sección, tachado, para que se vea
> de dónde salía. La evidencia completa está en `RESULTADOS_VALIDACION.md §8`
> y congelada en `tests/test_reconstruccion.py` (18 tests).

### Qué cambió

Apareció una referencia que no es otra implementación con sus propios
compromisos, sino la definición: `tests/reconstruccion_exacta.py`. La señal
continua detrás de un archivo muestreado es única, y su máximo se calcula sin
elegir filtro ni taps. Contra ella, medido:

| | material realista | con energía hasta Nyquist |
|---|---|---|
| FIR ITU 4× (lo que proponía el plan) | 0,100 | **0,850** |
| soxr_hq 4× (lo que hay en producción) | 0,114 | 0,387 |
| soxr_hq **8×** | **0,004** | 0,387 |

Las dos preguntas abiertas quedan contestadas:

1. **Fixture 08** — el FIR no "se descuelga" por un caso raro: un recorte duro
   llena el espectro hasta Nyquist y ahí el filtro de 12 taps cae 0,79 dB.
   Es su respuesta en frecuencia, medida tono a tono.
2. **96 kHz** — no hay nada que decidir. Con material realista a 88,2 o 96 kHz
   el pico entre muestras es menor de 0,05 dB y los dos medidores coinciden
   con la reconstrucción exacta. El fixture 05 es un tono de 24 kHz: por
   encima de lo audible.

Y aparece un hallazgo que el plan no contemplaba: **parte del error no es del
filtro, es de la rejilla.** 4× da cuatro puntos por muestra y el máximo cae
entre ellos.

### Lo que sí conviene hacer — PENDIENTE DE APROBACIÓN

**Subir el sobremuestreo de 4× a 8×, sin cambiar de filtro.** Con material
realista el error baja de 0,114 dB a 0,004 dB. Por encima de 8× no aporta
nada. Coste medido en una pista de 6 min estéreo: 0,40 s → 0,85 s.

Consecuencias, que son reales y hay que aceptarlas a propósito:

* Sube `PEAK_ALGORITHM_VERSION` a `peak-soxr_hq_8x-1`, y con ello los tres
  estados de validación caen a `False` solos: **hay que revalidar entero**,
  incluida otra ronda manual con el medidor externo.
* Los análisis nuevos leerán **hasta 0,11 dB más alto** que los anteriores, no
  más bajo. La dirección es la contraria a la que suponía el plan retirado:
  a 4× se estaba subestimando.
* Por tanto los 162 análisis entre 0 y +0,2 dBTP **no se "rescatan"**. Si
  acaso, algún análisis más cruzaría el 0. La comparabilidad con el histórico
  se rompe, que es justo para lo que cada fila guarda su
  `peak_algorithm_version`.

### Lo que queda irreducible

Con material que tiene energía por encima de 20 kHz (masters muy saturados),
soxr se queda 0,39 dB corto **y subir el factor no lo arregla**: ahí el error
es del filtro. Ningún medidor comercial acierta tampoco — Youlean se desvía
0,16 dB en la dirección opuesta sobre los mismos fixtures.

Eso no es un fallo que se pueda cerrar: es la incertidumbre de la medida. La
consecuencia de producto es que **la frontera de `true_peak_over` está clavada
en 0,0 dBTP, que es más fino de lo que la medición puede resolver en ese
material.** Opciones, para decidir aparte del cambio de factor:

* Una banda intermedia entre 0 y ~+0,3 dBTP con lenguaje de "está en el
  límite", en vez de afirmar que pasa del techo.
* Publicar la energía cerca de Nyquist como señal de confianza: cuando es
  alta, el true peak tiene más incertidumbre y el texto puede decirlo.

### Y qué hacer con la validación externa

El FAIL registrado en `VALIDACION_MANUAL.md` **se mantiene**: el criterio
acordado era coincidir con un medidor externo y no se cumplió. Lo que la
investigación demuestra es que ese criterio medía lo que no era — Youlean se
desvía de la verdad tanto como soxr, en sentido contrario.

Propuesta, que es más estricta que la que había y no más laxa: **juzgar contra
la reconstrucción exacta**, que sí es ground truth, con tolerancia ±0,05 dB en
material realista; y dejar la comparación con medidores comerciales como
documentación de la dispersión entre implementaciones, no como aprobado o
suspenso. No es tocar la tolerancia: es cambiar el árbitro por uno demostrable.

<details>
<summary>Texto original de la prioridad 0, retirado</summary>

> ~~La validación externa con Youlean Loudness Meter 2.5.14 confirmó lo que ya
> apuntaban la reconstrucción sinc por FFT y el FIR normativo: `soxr_hq_4x` lee
> entre 0,2 y 0,33 dB por encima del valor real en material con energía cerca
> de Nyquist. Cuatro referencias independientes coinciden en la dirección.
> Qué hacer: sustituir el sobremuestreo de producción por el FIR 4× del anexo 2
> de BS.1770-5. Sube `PEAK_ALGORITHM_VERSION` a `peak-itu_fir_4x-1`. Alrededor
> del 7% del histórico cambiaría de categoría si se recalculara.~~

El error de razonamiento, para no repetirlo: se tomó como "valor real" el
acuerdo entre dos medidores (Youlean y el FIR) sobre dos fixtures. Coincidían
porque ambos atenúan la zona alta del espectro, no porque acertaran.

</details>

---

La fase 2A dejó de llamar "clipping" a lo que no lo demuestra. La 2B es lo que
permitirá afirmarlo cuando de verdad lo sea: medir las muestras.

---

## Lo que se puede afirmar y lo que se infiere

Esta es la distinción que ordena toda la fase. Se propone que cada campo lleve
la etiqueta en el propio código.

### Mediciones objetivas

Salen de contar sobre el array de muestras. Dos personas con el mismo archivo
obtienen el mismo número. No dependen de ningún umbral discutible.

| Campo | Tipo | Qué es exactamente |
|---|---|---|
| `muestras_en_techo_por_canal` | `list[int]` | Cuántas muestras con `\|x\| >= 1 − 1 LSB` tiene cada canal. El margen de 1 LSB es lo que hace que el conteo no dependa del error de cuantización |
| `pct_muestras_en_techo` | `float` | El total anterior sobre el número de muestras. Un track de 6 min a 44,1 kHz tiene ~16 M por canal: el porcentaje es lo comparable, no el absoluto |
| `racha_maxima_muestras` | `int` | Muestras consecutivas en el techo, en el peor canal |
| `racha_maxima_ms` | `float` | La misma racha en milisegundos. **Es la que hay que usar en los umbrales**: 20 muestras son 0,45 ms a 44,1 kHz y 0,21 ms a 96 kHz |
| `canal_afectado` | `str` | `"L"`, `"R"`, `"ambos"` o `""` |
| `posicion_maximo_seg` | `float` | Segundo en el que está el máximo absoluto |
| `distancia_maximo_al_borde_seg` | `float` | Distancia del máximo al principio o al final, la menor de las dos |
| `true_peak_at_file_edge` | `bool` | El máximo cae dentro de la ventana de asentamiento del filtro (~512 muestras). **Se mide, pero no se corrige nada** |

`true_peak_at_file_edge` merece una nota. En la fase 1.1 se comprobó que la
sobreoscilación ante un escalón es real: los cuatro métodos la ven, y ffmpeg
coincide con soxr hasta la tercera cifra. **No es un artefacto que haya que
suprimir.** El campo sirve para que, si un track marca un pico alto, se sepa
si viene del contenido musical o del arranque abrupto del archivo — y para
poder matizar el texto, no para descontar dB.

### Inferencias

Salen de combinar mediciones con umbrales elegidos. Otro criterio da otro
resultado, así que el copy tiene que usar lenguaje de probabilidad.

| Campo | Tipo | Por qué es inferencia |
|---|---|---|
| `n_flat_tops` | `int` | Un flat top es "meseta con pendiente ≈ 0", y ese *≈* es un umbral. Propuesta: racha ≥ 3 muestras con `\|Δx\| < 2 LSB` |
| `concentracion_en_transitorios` | `float 0-1` | Fracción de muestras en techo que caen a menos de 50 ms de un onset detectado. Depende del detector de onsets, que ya tiene sus propios parámetros |
| `confianza_clipping_probable` | `float 0-1` | Combinación ponderada de todo lo anterior. **Es la más discutible del conjunto** y no debe presentarse nunca como un porcentaje al usuario |

## La gradación, ya acordada

De la corrección A.1 de la auditoría:

| Nivel | Criterio propuesto | Lenguaje |
|---|---|---|
| **A0 — techo tocado** | 1-2 muestras aisladas | "toca el máximo" — informativo |
| **A1 — muestras consecutivas** | rachas de 2-4 | "compatible con un limitador trabajando en el techo" |
| **A2 — flat tops cortos** | rachas de 5-20 y pendiente ≈ 0 | "probable recorte puntual" |
| **A3 — recorte sostenido** | racha > 1 ms **y** > 0,05 % de muestras **y** repetición del máximo exacto | "muy probablemente hay recorte" |
| **A4 — posiblemente intencional** | A2/A3 **con** `concentracion_en_transitorios > 0,8` | "hay recorte; si es un clipper en la batería, puede ser lo que buscabas" |

Ningún nivel usa la palabra "clipa" salvo A3, y ahí acompañada del dato.

## Cómo se cruza con lo que ya existe

La 2A dejó `true_peak_over` como "hay picos por encima del techo, pero esto no
demuestra recorte". La 2B es justo lo que cierra esa frase:

| `categoria_picos` (2A) | + medición de muestras (2B) | Conclusión |
|---|---|---|
| `true_peak_over` | A0 o ninguna | Over intersample puro. El máster está bien, el pico vive entre muestras |
| `true_peak_over` | A2 / A3 | Recorte probable **y** overs. Es el caso grave de verdad |
| `overs_float_recuperables` | (no aplica: en float no hay techo) | Sigue siendo recuperable |
| `ok` / `margen_streaming` | A3 | **El hallazgo que hoy es invisible**: techo correcto y recorte dentro, típico de un clipper antes del bounce |

Esa última fila es la que justifica la fase. Hoy un track así sale limpio.

## Coste estimado

Todo se calcula sobre el array `native` que ya se lee para el true peak. Es
una pasada de numpy sin allocations grandes:

```
en_techo   = np.abs(native) >= umbral        # bool (N, canales)
cambios    = np.diff(en_techo.astype(np.int8), axis=0)
# rachas por los índices de cambio; pendiente sobre native[en_techo]
```

Estimación: **10-30 ms** en un track de 6 minutos, frente a los ~600 ms que
tarda hoy el análisis de un track de 12 s. Despreciable.

## Qué hay que decidir antes de implementar

1. **El umbral de "en el techo".** ¿`1 − 1 LSB` del bit depth real, o un valor
   fijo como −0,1 dBFS? El primero es correcto pero exige conocer el bit
   depth, que solo tenemos desde v0.5.71 y solo en punto fijo.
2. **Qué hacer en 32-bit float.** No hay techo: no se puede contar "muestras a
   fondo de escala". ¿Se cuenta contra 0 dBFS por convenio, o se declara no
   aplicable?
3. **Qué hacer en MP3/OGG.** El decodificador puede pasarse de 0 aunque el
   original no lo hiciera. Probablemente: medir, marcar `archivo_lossy` y no
   emitir A2/A3 nunca sobre un lossy.
4. **Si `confianza_clipping_probable` llega a existir.** Es la más frágil de
   las once. Se puede implementar todo lo demás sin ella.
5. **Si esto entra en `reglas.py`.** Un A3 confirmado sí merece ser diagnóstico
   principal — es el problema más grave y más fácil de arreglar. Pero mover la
   jerarquía desplaza diagnósticos existentes y hay que medirlo antes con el
   endpoint de reanálisis.

## Lo que NO cubre la fase 2B

Recorte que ocurrió **antes** del bounce y luego se normalizó a la baja: no
deja muestras en el techo y es indetectable contando. Eso pide análisis de
forma de onda o espectral (armónicos de intermodulación), y no está en el
alcance de ninguna fase planificada.
