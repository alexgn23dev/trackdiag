# Fase 2B — campos de muestras a fondo de escala

**Diseño. Nada de esto está implementado.**

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
