# Por qué el informe no enseña el BPM

Decisión de Alex, 14-ago-2026, tras medirlo: **si no podemos acertar casi
siempre, es mejor no dar el dato**. El BPM aporta poco al diagnóstico y una
cifra mal puesta arriba del informe tira por tierra la credibilidad de todo lo
demás.

Se escribe esta nota porque el impulso de volver a enseñarlo es fuerte: es un
dato que todo el mundo espera ver.

## 1. Cómo se detecta, y por qué falla

`librosa.beat.beat_track` estima el tempo sobre un **tempograma de bins
discretos**. A 22 050 Hz con hop 512, esos bins caen en:

    112.3 · 117.5 · 123.0 · 129.2 · 136.0 · 143.6 · 152.0 · 161.5 · 172.3

No hay nada entre 123.0 y 129.2: cualquier track entre ~126 y ~132 BPM sale
como **129**. Es decir, **128 y 130 —los dos tempos más comunes del género—
daban el mismo número**, y ese número no lo usa nadie.

Medido sobre los BPM que había en producción:

| | |
|---|---|
| caían en un bin del detector | **95 %** |
| caían en un BPM "de productor" (120, 124, 128, 132, 140…) | **0 %** |
| valor más frecuente | **129 BPM**, en el 40 % de los análisis |

## 2. El refinado, y hasta dónde llega

Se puede quitar la cuantización sin tocar la detección: los beats que
`beat_track` devuelve ya están donde están, así que **ajustando una recta a
sus tiempos**, la pendiente da el periodo real. Está implementado
(`_refinar_tempo` en `extractor.py`) y funciona muy bien... cuando funciona.

Con tempo perfectamente constante (13 loops sintéticos de BPM conocido, de
extremo a extremo por el motor real): **13 de 13 exactos**, cuando antes
fallaban 8 de 13 con hasta 3.6 BPM de error.

El problema es la cobertura, que depende del material:

| material | pasa el filtro de confianza |
|---|---:|
| previews publicados y masterizados (120) | 42 % |
| **tracks de usuario reales (33)** | **15 %** |

En los tracks de usuario —bounces, mezclas a medias, cosas con tempo no
perfectamente rígido— **solo 5 de 33** dan una medida en la que se pueda
confiar. Los otros 28 se quedan con el valor del bin: 13 de ellos mostraban
"129", 8 mostraban "123".

Y el filtro no es opcional: en el 58 % de la música real donde el ajuste NO
pasa, el refinado acierta 4 de 58 — es decir, forzarlo empeoraría el dato.

## 3. Y además hay fallos gruesos: el caso 140 → 112, resuelto

Un usuario reportó un track a 140 que Mentotrack dio como **112**. Con su
archivo delante (ago-2026) el mecanismo quedó claro, y merece escribirse
porque es contraintuitivo.

### Por qué 140 es el peor caso posible

El detector mide el pulso en frames. A 22 050 Hz con hop 512 hay 43,07
frames/s, así que **el periodo del beat solo se puede representar en frames
enteros**:

| BPM | frames por beat | distancia al entero |
|---|---:|---:|
| 112 | 23,07 | **0,07** ← casi clavado |
| 128 | 20,19 | 0,19 |
| 130 | 19,88 | 0,12 |
| **140** | **18,46** | **0,46** ← justo entre dos lags |
| 145 | 17,82 | 0,18 |

140 cae en el punto más ambiguo que existe, y 112 en uno de los más limpios.
El detector no puede engancharse a 140 y se va al candidato "fácil". La
relación 140 → 112 **no es musical** (no es mitad, ni doble, ni tresillo): es
aritmética de la rejilla, y por eso el ratio sale en 5/4.

Que el track *sí* es 140 se confirma en la autocorrelación del envelope de
onsets: el pico más fuerte está en **70 BPM = 140/2** (el pulso de compás),
con 140/145 justo detrás. El 112 aparece como pico espurio de la rejilla.

Por eso tampoco se reprodujo con audio sintético: los loops de prueba caían
en tempos representables.

### Subir la resolución NO es la solución

Con hop 256 ese track sale **140,01** — perfecto. Pero validado sobre 94
tracks reales (34 de usuario + 60 previews):

| | hop 512 | hop 256 |
|---|---:|---:|
| pasan el filtro de confianza (usuario) | 15 % | 15 % |
| pasan el filtro (publicados) | 45 % | **42 %** |
| coste por track (usuario) | 0,58 s | 1,70 s |

Y **rompe casos que estaban bien**: tracks que a 512 pasaban el filtro con
121 y 122 pasan a 120 y 123. Cambia unos errores por otros, cuesta el triple
y no mejora la confianza. **No se toca.** (Si alguien lo vuelve a proponer:
el problema es que ningún hop es bueno para todos los tempos — a 256, 128 BPM
empeora a 0,37 frames de distancia.)

### Lo importante: no afectó al diagnóstico

Su track pasado por el motor con 112 y con 140:

| | 112 (lo que se usó) | 140 (el real) |
|---|---|---|
| diagnóstico | enmascaramiento_bajo | enmascaramiento_bajo |
| estado | avanzado | avanzado |
| contraste | medio | medio |
| cambios significativos | 5 | 5 |
| desarrollo | sí | sí |
| bloques | 23 | 29 |

**El usuario recibió exactamente el diagnóstico correcto.** Y no es casualidad
de un track: forzando errores de ±25 % en 9 tracks distintos, 8 dan el mismo
diagnóstico y estado; en el noveno solo se mueve el contraste (medio → alto).

Esa tolerancia es hoy una propiedad medida, no una garantía — y como el BPM ya
no se enseña, si un día se perdiera nadie lo vería. Por eso la fija
`backend/tests/test_estructura_tolera_bpm_malo.py`.

## 4. Qué se retiró (v0.5.99)

Todo lo que **afirmaba** un BPM al usuario:

- el chip "BPM" de la cabecera del informe;
- la fila "BPM" de la pestaña Detalle;
- el paso "X BPM detectados" de la pantalla de análisis;
- `referencia_temporal` ("A 128 BPM, 8 compases duran ~15s…") y su gemela en
  el dato contextual — números derivados de un dato malo, que además esconden
  su procedencia: el usuario ve segundos, no ve de dónde salen;
- la cifra en segundos del consejo de automatización antes del drop (el
  consejo se mantiene, en compases, que no depende del tempo).

## 5. Qué se conservó, y por qué

- **El cálculo del BPM.** Se sigue haciendo y publicando en `datos_audio.bpm`.
- **El reparto en bloques de ~8 compases** para el análisis de estructura lo
  usa. Ahí un error de 1-3 % desplaza los límites un 1 % — irrelevante para
  medir contraste entre secciones. Un fallo grueso (25 %) sí lo desplazaría,
  pero el análisis mira energía relativa entre bloques consecutivos y aguanta.
- **`tempo_refinado`** (booleano) viaja al frontend: marca los casos en que el
  número SÍ es de fiar. Se usa para dos cosas:
  - pre-rellenar el BPM en el formulario de la comunidad solo cuando se puede
    (si no, el campo va vacío y lo escribe el usuario);
  - mandar el BPM a Relesit solo cuando se puede (antes se enviaba siempre, y
    Relesit hacía matching de sellos con un dato que ni nosotros enseñábamos).

## 6. Si algún día se quiere recuperar

Dos caminos, por orden de coste:

1. **Preguntárselo al usuario.** El endpoint ya acepta `bpm_manual` y el
   formulario podría pedirlo como campo opcional. Sería exacto por definición
   y además mejoraría el reparto en bloques. Es la opción barata.
2. **Un detector mejor.** El límite no es el refinado —que ya es exacto cuando
   el tempo es estable— sino el enganche al pulso correcto en material real.
   Eso pide otro algoritmo, y medirlo exige tracks etiquetados con su BPM real
   (que no tenemos).

Lo que **no** vale: volver a enseñar el número tal cual. Ya se midió, y la
respuesta fue 15 %.
