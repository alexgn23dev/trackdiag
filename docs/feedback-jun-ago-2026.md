# Feedback jun–ago 2026: qué dice y qué tocar en el motor

Análisis de los 43 feedbacks con comentario de los últimos 60 días (17 jun –
13 ago 2026), leídos uno a uno y cruzados con las señales guardadas de cada
análisis, el código del motor y el corpus de referencia. Hecho el 2026-08-13
contra la DB de producción.

## 1. Los números

| | |
|---|---|
| análisis en 60 días | 1 537 |
| con feedback | 43 (2,8 % de respuesta) |
| reparto | Sí 23 · Parcial 11 · No 9 |
| satisfacción (Sí + ½·Parcial) | **66 %** |

Por mes, con la tasa de respuesta:

| mes | satisfacción | n | respuesta |
|---|---:|---:|---:|
| mayo | 81 % | 140 | 10 % |
| junio | 81 % | 26 | 3 % |
| julio | **52 %** | 21 | 3 % |
| agosto (parcial) | 75 % | 6 | 2 % |

**La caída de julio no la causó el motor**: entre v0.5.66 y v0.5.70 no hubo
ningún cambio en `backend/engine/` (solo CTAs y emails). Con n=21 el ruido
binomial es de ±20 puntos. Lo que sí es señal estable es el *contenido* de los
comentarios: los 9 "No" de los 60 días se explican, uno a uno, con las causas
del §3. Ojo también al colapso de la tasa de respuesta (10 % → 3 %) al retirar
la encuesta por email (v0.5.76): mayo y julio no midieron a la misma población.

## 2. Qué diagnostica el motor a escala (los 1 537)

| diagnóstico | % |
|---|---:|
| sin_diagnostico | 28 % |
| carencia_espectral | 20 % |
| **enmascaramiento_bajo** | **19 %** |
| exceso_densidad | 8 % |
| problema_arreglo | 6 % |
| harshness_mezcla | 4 % |
| exceso_lowend | 4 % |
| resto (5 dx) | 11 % |

Mono: excelente 1 247 · buena 203 · **problemática 85 (5,5 %)** · crítica 2.

## 3. Las causas de los Parcial/No, verificadas

### 3.1 `enmascaramiento_bajo` dispara de más y se retroalimenta — LA prioridad

Dos usuarios lo dicen con todas las letras ("SIEMPRE DA LA MISMA RESPUESTA DE
EL BAJO Y EL KICK", "SIEMPRE DICE LO MISMO") y el 19 % de todos los análisis lo
confirma. Verificado en `reglas.py`:

- **Eco del formulario**: mencionar "kick/bajo/bass/turbio…" en
  `bloqueo_percibido` suma **+2**, y `UMBRAL_MINIMO_CONFIANZA = 2` — las
  palabras del usuario BASTAN solas para alcanzar el umbral. El caso [32]
  (eurodance) salió con una única "evidencia": *"El usuario percibe problemas
  con el kick o el bajo"*. Le dijimos lo que él nos había dicho.
  Matices de la verificación adversarial: (a) el MISMO léxico con el MISMO +2
  existe también en `exceso_lowend` — el eco afecta a las dos reglas, y en
  empate a 2 gana exceso_lowend por orden de inserción; enmascaramiento sale
  como principal cuando además hay señal espectral (+1/+2), que es el caso
  común (ver punto siguiente); (b) el matching es por substring: "trabajo" o
  "abajo" también disparan "bajo". El arreglo tiene que cubrir ambas reglas y
  pasar a matching por palabra.
- **Umbral espectral dentro de lo normal**: `diff graves(60-200) −
  low_mid(200-800) > 12 dB` suma +2. Medido sobre los 322 previews publicados
  del corpus (aprox. por tercios de octava en el drop): mediana 8,7 dB, el
  **58 % supera 8 dB** (+1) y el **15 % supera 12 dB** (+2 → diagnóstico él
  solo). La regla marca como defecto un rasgo del género.

Arreglo propuesto (conservador): (a) el eco del formulario no puede puntuar
por sí solo — que sea desempate (+1 máx) y solo si ya hay ≥2 de señal física;
(b) recalibrar el umbral espectral contra el corpus (p. ej. exigir > p90 de lo
publicado ≈ 13-14 dB, y con densidad/harshness corroborando); (c) variedad en
el texto: si el mismo usuario repite diagnóstico en análisis consecutivos,
decirlo ("sigue siendo lo más prioritario") en vez de parecer un loop.

### 3.2 Mono "problemática" sin pérdida real — falso positivo confirmado

Caso [33]: correlación global 0,839, `perdida_mono_db = −0,4 dB` (nada) → aun
así "problemática" por correlación baja en la banda de medios. El usuario lo
comprobó en mono, no perdía nada, y tenía razón. Física del asunto: correlación
≈ 0 significa canales *independientes* (suman sin cancelarse); solo la
correlación *negativa* cancela. El nivel global se asigna por correlación de
banda **sin mirar la pérdida real que ya calculamos**.

Arreglo: exigir pérdida real para avisar — "problemática" solo si
`perdida_mono_db` (global o de la banda) supera ~1–1,5 dB; si la correlación es
baja pero no se pierde energía, es anchura estéreo, no un problema. Afecta al
5,5 % de los análisis. (Nota de la verificación: con la métrica usada, dos
canales totalmente independientes de igual energía dan como mucho −3 dB; la
banda descorrelacionada del caso [33] pesaba poco y la pérdida global quedó en
−0,4 dB — el aviso saltó igual.)

### 3.3 El LUFS del informe no cuadra con el del DAW del usuario

Casos [8]/[9]: su DAW marca −9,1; nosotros −15,4/−13,0 integrado. Medimos
`lufs_short_term_max` (−14,5/−12,1) pero **no se enseña**. Los medidores de
DAW suelen mostrar el máximo momentáneo/corto, no el integrado de todo el
track con intro y outro. El usuario no puede reconciliar las cifras → "esto
está mal" → No.

Arreglo: enseñar junto al integrado el short-term máximo ("en tu sección más
fuerte: −12,1 LUFS") + una línea de por qué tu DAW puede marcar más. Es
frontend + templates, cero riesgo de motor.

### 3.4 Géneros fuera del dominio club

Cumbia peruana [27], drone/ambient [26], blues rock [21], eurodance [32]… El
motor aplica normas de estructura de club (`arreglo_repetitivo`,
`problema_arreglo`) a materiales donde no aplican, y el usuario lo nota ("no
se acerca a la realidad del estilo"). Ya existe `aviso_genero` para género no
electrónico, pero el diagnóstico sigue jerarquizando con reglas de club.

Arreglo (acotar, como quiere Alex): con género fuera de la lista club (los
"Otro:" lejanos), bajar la autoridad — mantener las medidas físicas (espectro,
picos, mono) y **degradar las reglas de estructura a observaciones**, con el
aviso al frente: "las normas de estructura que usamos son de club; para tu
estilo tómalas como referencia, no como veredicto".

### 3.5 Quieren lo que no analizamos (composición, armonía, vocales)

[26] composición/armonía/idea, [36] uso de synths, [34]/[35] vocal
descompasado con la base, [24] elección de muestras. Es el punto ciego
conocido (CLAUDE.md §punto ciego) y NO se arregla sin ML/embeddings.

Arreglo barato y honesto: **declarar el alcance en el informe** — una línea
fija tipo "Analizamos señal: balance, dinámica, picos, estéreo y estructura
energética. No evaluamos armonía, melodía, composición ni afinación/timing de
voces". Gestiona la expectativa antes del feedback, no después.

### 3.6 La referencia subida a veces no aparece

[21] subió referencia y el informe SÍ la comparó (está en el texto guardado)
pero el usuario no la vio; [25] subió referencia y **no hay comparación en el
informe** (falló en silencio, sin mensaje de error). Además, verificado en el
frontend: **la vista v2 no pinta `comparacion_referencia` en ninguna
pestaña** — solo la clásica la enseña.

Arreglos: (a) si el usuario adjuntó referencia, el informe SIEMPRE dice algo de
ella, aunque sea "no pudimos procesarla" o "sin diferencias relevantes";
(b) portar la tarjeta de comparación a la v2; (c) los umbrales del comparador
siguen sin calibrar desde v0.5.32 — `sesiones.jsonl` guarda `senales_ref`
para eso.

### 3.7 Menores

- **True peak vs limitador** [40]: "si todo va limitado, ¿cómo hay picos sobre
  0?" → explicar inter-sample peaks en el aviso (pedagogía, templates).
- **Export roto** [10]: "exporté mal la canción" — poco que hacer, quizá avisar
  si la duración no cuadra con lo declarado.

## 4. El elefante: la v2 no la ve nadie

Verificado en el código: la vista v2 del diagnóstico solo se activa con
`?v2=1` escrito a mano en la URL. **Ningún flujo de producción la enlaza** —
la única mención pública es una línea de texto plano en el /changelog ("añade
?v2=1 a la dirección"), y los tests documentan que el flag es deliberado.
Todo el rediseño (balance espectral con corredor, cabecera nueva, tutoriales
visibles) está desplegado pero invisible: el 65 % de satisfacción es de la
vista clásica con el motor de siempre. Antes de rollout hay que cerrar §3.6b
(la comparación de referencia, que la clásica sí tiene y la v2 no).

## 5. Orden propuesto

| # | qué | tipo | riesgo | a quién afecta |
|---|---|---|---|---:|
| 1 | eco + umbral de enmascaramiento_bajo | motor (reglas) | medio — recalibrar con corpus y validar con /calibrar | 19 % de análisis |
| 2 | mono gateado por pérdida real | motor (extractor) | bajo — la señal ya existe | 5,5 % |
| 3 | LUFS short-term visible + explicación | frontend/templates | nulo | todos |
| 4 | declarar alcance (qué no analizamos) | frontend/templates | nulo | todos |
| 5 | referencia: nunca en silencio + tarjeta en v2 | frontend | bajo | subieron ref |
| 6 | acotar géneros fuera de club | motor (jerarquía) | medio | ~7 % (Otro:) |
| 7 | rollout v2 (decisión de producto) | producto | — | todos |

Regla de la casa que gobierna 1, 2 y 6: **la interfaz no puede sugerir un
problema que el análisis no haya detectado** — hoy el eco del formulario y el
mono por correlación la violan desde el motor.

## 6. Método y límites

- 43 feedbacks es poco (2,8 % de respuesta): sesgo de autoselección seguro.
  Los porcentajes de satisfacción se mueven ±15 pp con facilidad; las causas
  cualitativas son lo fiable.
- La medición del 58 %/15 % del §3.1 aproxima `espectro_bandas` (mel, track
  entero) con tercios de octava en el drop del corpus de previews — sirve para
  el orden de magnitud, no como umbral final. Recalibrar con el pipeline real
  antes de tocar la regla.
- `revision_alex`/`nota_alex` están vacíos en los 43: el circuito de revisión
  manual de /calibrar no se está usando para feedback reciente.
