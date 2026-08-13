# Calibración de `enmascaramiento_bajo` (ago-2026)

Medición del diagnóstico que más se repetía en producción, contra música ya
editada. **La hipótesis de partida resultó equivocada** y la medición encontró
otra causa; se documenta con los dos resultados para que no se vuelva a
proponer el arreglo incorrecto.

## 1. Por qué se miró

| señal | dato |
|---|---|
| cuota del diagnóstico | **19 %** de los análisis (60 d), el 3.º más frecuente |
| satisfacción con este dx | **58 %** (n=13) |
| satisfacción con el resto | **79 %** (n=179) |
| usuarios que lo reciben en ≥60 % de sus análisis | 13 (de 290 con ≥3 análisis) |
| usuarios que lo reciben SIEMPRE | 4 |
| quejas textuales | *"SIEMPRE DA LA MISMA RESPUESTA DE EL BAJO Y EL KICK"*, *"SIEMPRE DICE LO MISMO"* |

Un usuario con 75 análisis recibió este mismo diagnóstico 31 veces.

## 2. Cómo se midió

La regla puntúa sobre `espectro_bandas`, que es **la media de dB por banda del
mel sobre el track entero** — no los tercios de octava en el drop. La primera
estimación (informe de feedback §3.1) usaba tercios y por tanto no servía para
mover un umbral. Aquí se mide con `extraer_senales` de verdad:

- **322 previews publicados** de 26 sellos (el corpus de `label-match`, mismo
  que el corredor espectral; ver `docs/corredor-referencia.md`).
- **32 tracks de usuario** de las carpetas de Alex, deduplicados por audio.

Métrica de calidad de cada componente: **ratio de discriminación** =
(% que dispara en tracks de usuario) / (% que dispara en música publicada).
Un componente con ratio ≈ 1 no distingue nada: marca a publicados y a usuarios
por igual, así que como evidencia de defecto no vale.

## 3. Qué se creía (y era falso)

**Hipótesis:** el umbral espectral `diff graves(60-200) − low_mid(200-800) >
12 dB → +2` estaba mal puesto y marcaba como defecto un rasgo del género.

**Medido:** es de los componentes que MEJOR funcionan.

| | publicado | usuario | ratio |
|---|---:|---:|---:|
| espectral > 12 dB (+2) | 9.3 % | 21.9 % | **2.35x** |
| espectral > 8 dB (+1) | 35.4 % | 56.2 % | 1.59x |

El corte de 12 dB cae en el **p90** de lo publicado. Subirlo a 14 dB (p95)
*empeora* las cosas: la discriminación baja a 1.55x y la elegibilidad total
apenas se mueve (22.0 % → 21.1 %). **No se toca.**

## 4. Lo que sí estaba roto: el bonus del sub

`diff_sub_low > 4 dB → +1`, con la razón *"posible rumble o sub descontrolado"*.

| | publicado | usuario | ratio |
|---|---:|---:|---:|
| sub > 4 dB (+1) | **38.8 %** | **37.5 %** | **0.97x** |

Dispara en cuatro de cada diez tracks, **publicados y de usuario por igual**.
Y no es cuestión del corte — ningún umbral lo salva:

| corte | publicado | usuario | ratio |
|---|---:|---:|---:|
| > 2 dB | 50.9 % | 46.9 % | 0.92x |
| > 4 dB | 39.8 % | 37.5 % | 0.94x |
| > 6 dB | 28.0 % | 28.1 % | 1.01x |
| > 8 dB | 17.4 % | 12.5 % | 0.72x |
| > 12 dB | 4.0 % | 3.1 % | 0.77x |

**La causa es de medida, no musical.** `diff_sub_low` resta dos *medias de dB*
entre bandas con muy distinto número de bins del mel: el sub (0-60 Hz) cubre
~2 bins y los graves (60-200 Hz) bastantes más. Promediar dB penaliza a la
banda ancha, así que la diferencia sale inflada por construcción. Es el mismo
motivo por el que existe `espectro_display` aparte para enseñar (ver el
comentario largo en `extractor.py`).

Además era **la vía número uno** por la que música ya editada alcanzaba el
umbral: la combinación `espectral+1 + sub+1` explica el **37 %** de los
previews publicados elegibles — dos señales flojas apilándose hasta cruzar el
listón.

## 5. El cambio (v0.5.96)

Se retira el bonus del sub de esta regla. `diff_sub_low` **sigue expuesto**
como señal informativa (el propio extractor lo declara así); simplemente deja
de puntuar.

Efecto medido:

| | antes | después |
|---|---:|---:|
| elegible en música publicada | 22.0 % | **14.0 %** |
| elegible en tracks de usuario | 40.6 % | 34.4 % |
| ratio de discriminación | 1.84x | **2.46x** |

**Dispara menos y discrimina más**: la evidencia retirada era ruido contado
como prueba.

## 6. Los otros componentes, para el registro

| componente | publicado | usuario | ratio | decisión |
|---|---:|---:|---:|---|
| espectral > 12 dB (+2) | 9.3 % | 21.9 % | 2.35x | se queda |
| espectral > 8 dB (+1) | 35.4 % | 56.2 % | 1.59x | se queda |
| densidad baja + > 10 dB (+1) | 12.1 % | 25.0 % | 2.06x | se queda |
| harshness severo (+1) | 0.6 % | 0.0 % | — | se queda (dispara en 2 de 322; inocuo) |
| eco del formulario | — | — | — | capado a +1 en v0.5.94 |

## 7. Límites de esta calibración

- **32 tracks de usuario es poco.** El resultado del sub aguanta igual: con
  n=322 en el lado publicado y un ratio de 0.97, no hay muestra de usuario
  que lo convierta en discriminador. Los ratios de los componentes que se
  quedan (1.6–2.4x) sí son más frágiles y conviene rehacerlos con más tracks.
- **"Publicado" no significa "sin problemas".** El corpus son previews de
  Beatport a 96 kbps, sobre todo progressive y house (ver
  `docs/corredor-referencia.md` §4). Lo que mide esta calibración es "esto no
  distingue a un track de usuario de uno editado", que es exactamente el
  listón que una regla de diagnóstico tiene que superar.
- **Nadie ha etiquetado "este track tiene enmascaramiento real".** Sin esa
  verdad no se puede medir precisión, solo discriminación. Si se quiere ir más
  lejos (por ejemplo, revisar el corte de 12 dB), hace falta pasar por
  `/calibrar` con tracks etiquetados a mano.

## 8. Cómo reproducirlo

`scratchpad/medir_masking.py` (no versionado) recorre corpus y usuarios con
`extraer_senales(..., omitir_armonia=True)` y vuelca `espectro_bandas` y las
señales derivadas. Los `scores` de cada análisis **sí se guardan en producción**
(`analisis.senales->'scores'`, 3170 filas), así que el reparto real por
puntuación se puede consultar sin reanalizar nada.
