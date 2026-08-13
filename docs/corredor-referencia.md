# El corredor de referencia del balance espectral

Nota técnica sobre `V2_CORREDOR` (en `frontend/index.html`): de dónde salen sus
números, qué se puede afirmar con ellos y qué no.

Se escribe porque el corpus **vive fuera de este repo** y sin esta nota no hay
forma de saber qué son esos percentiles. Auditado en agosto de 2026.

---

## 1. Qué es

La franja que se dibuja detrás de la curva del usuario en la tarjeta de Balance
espectral: **dónde cae el espectro de una colección de música electrónica ya
publicada**. Sin ella el usuario ve su curva y no tiene con qué compararla.

Son percentiles por banda de tercio de octava, **5 / 25 / 50 / 75 / 95**. Los
del 5 y el 95 delimitan la franja y son los únicos que intervienen en la
comparación; los del 25 y 75 no se juzgan, solo dan forma al sombreado.

Se pinta como una nube: catorce capas anidadas entre percentiles cada vez más
juntos —(5, 95), (8.2, 91.8)… hasta rozar la mediana— todas con la misma
opacidad baja. Se suman hacia el centro y se quedan solas en los bordes, así
que **la densidad que se ve es la densidad de la muestra**, no un degradado
decorativo: donde el corpus se dispersa (el sub) la nube sale difusa porque de
verdad lo es. Entre los cinco percentiles medidos se interpola lineal, pero eso
solo reparte sombreado — el borde exterior sigue siendo exactamente el 5-95, y
un test lo vigila.

Anchos medianos: **11.1 dB** el 5–95, **4.3 dB** el 25–75.

## 2. De dónde sale el audio

De **`label-match`**, otro proyecto del mismo directorio padre:

```
Herramientas IA producción musical/label-match/data/audio_samples/{sello}/{track_id}.mp3
```

Los descargó `label-match/scripts/download_label_samples.py`, que se autentica
contra la API de Beatport (`BEATPORT_USER` / `BEATPORT_PASS`), pide
`/catalog/labels/{id}/tracks/?order_by=-publish_date` y baja el `sample_url` del
CDN público.

**No son másters ni temas de usuarios de Mentotrack.** Mentotrack no almacena
audio: lo escribe en un `tempfile` y lo borra. Tampoco son los tracks de la
carpeta `Mentotrack/alimentar la tool` de Alex — comprobado, cero archivos en
común.

### Qué son exactamente

| | |
|---|---|
| formato | **MP3, 96 kbps, 44.1 kHz, estéreo** — los 328, sin excepción |
| duración | **120.000 s exactos** en 313 de 328; el resto entre 34.8 y 119.3 |
| codificador | `Lavc61.19` / `Lavf61.7.100` (FFmpeg) |
| etiquetas ID3 | solo 50 de 328 llevan artista/título; 54 llevan fecha |

Es decir: **previews de 120 s transcodificados a bitrate bajo**. Homogéneos en
formato, pero no material de máster.

## 3. De 328 archivos a 322 observaciones

```
328  archivos .mp3 en audio_samples/
 −1  ilegible para libsndfile (whoyostro/28342850.mp3)
327  medibles
 −5  duplicados de audio: mismo tema con distinto track_id, todos en
     roche-musique (un caso aparece 3 veces)
322  observaciones independientes
```

La deduplicación se hace por **huella del audio decodificado**, no por nombre:
los duplicados tienen ID distinto y por nombre no se detectan. Quitarlos cambió
el corredor **0.29 dB como máximo**.

`backend/scripts/calibrar_corredor.py` regenera el bloque completo y aplica la
deduplicación, así que una recalibración futura reproduce 322 sola.

## 4. Composición y sesgo

**Por sello — sin sesgo.** 26 sellos, mediana de 12 temas cada uno (mín 12, máx
20). Los 3 sellos mayores aportan el **15.9 %** y los 5 mayores el **23.2 %**.
Ningún sello domina la estadística.

**Por género — sesgo grande.** El género procede del sello
(`label-match/data/label_genre_truth.json`), no está verificado tema a tema:

| género | temas | % | nº de sellos |
|---|---:|---:|---|
| Progressive House | 132 | 40.2 % | 11 |
| **sin etiqueta** | 64 | 19.5 % | 4 |
| Tech House | 36 | 11.0 % | 3 |
| Minimal / Deep Tech | 36 | 11.0 % | 3 |
| Melodic House & Techno | 24 | 7.3 % | 2 |
| Afro House | 12 | 3.7 % | **1** |
| Techno (Raw / Deep / Hypnotic) | 12 | 3.7 % | **1** |
| Deep House | 12 | 3.7 % | **1** |

No hay **techno duro, trance, psytrance, drum & bass ni hard dance**, que sí son
géneros que Mentotrack ofrece en el formulario. Y los tres géneros con un solo
sello no miden el género: miden ese sello.

**El 83 % de los temas no tiene fecha**, así que no se puede caracterizar la
distribución temporal del corpus. El script descargaba por `-publish_date`, pero
eso es una inferencia sobre el script, no un dato.

## 5. Por qué no hay corredores por género

Dos motivos, y el segundo pesa más que el primero.

**Falta muestra.** De los 20 géneros que ofrece la app, solo Progressive House
(132) y a duras penas Tech House (36) tendrían suficiente.

**Y el género apenas cambia el balance.** Medido sobre los 263 temas con género
conocido, descomponiendo la varianza banda a banda entre 50 Hz y 12.5 kHz:

| explica | fracción de la variación |
|---|---|
| el **género** | **13 %** |
| el **sello** | **24 %** |

El sello pesa casi el doble. Y dentro de un mismo género, el sello sigue
explicando el 12–19 %: dos sellos de progressive se diferencian tanto entre sí
como progressive de tech house.

Lo que lo cierra: cada corredor por género mediría **7.6–8.8 dB de ancho**, y la
distancia entre las medianas de dos géneros es de **0.7–2.4 dB**. Se solaparían
casi por completo. Dibujar corredores distintos daría una precisión aparente que
la medida no respalda.

**Límite de esa conclusión:** los cuatro géneros medibles son todos de la familia
house / progressive / tech, los que más se parecen entre sí. Sobre techno duro,
trance o DnB **no hay dato y no se puede afirmar nada**. Si algún día se amplía
el corpus, el valor está ahí y no en más progressive.

## 5 bis. Por qué hay una sola lectura del espectro (y no dos)

Hubo una vista **"Oído"** conmutable, que pasaba cada banda por la ponderación A
(la forma normalizada de la curva de 40 fon). Se retiró en agosto de 2026.
Se documenta porque la idea vuelve sola.

**No decía nada nuevo.** La ponderación A es un desplazamiento fijo por banda:
corre la curva del usuario y la del corpus por igual. Medido sobre los 322
previews y 19 temas de usuario, la desviación respecto al corredor correlaciona
**0.9994** entre las dos vistas, con **0.03 dB** de diferencia media. Era la
misma medida dibujada en otro eje.

**Y podía contradecir a la insignia.** Aquella vista se anclaba al pico del tema
en vez de al cuerpo, y con ese anclaje sí es una estadística distinta: **27 de
322 previews (8 %)** habrían visto `REFERENCIA / DENTRO` en la cabecera con la
curva saliéndose del corredor en pantalla. La insignia la calcula `V2TabMezcla`
una sola vez y no se entera de qué pestaña miras.

**Y la ponderación A no es la curva de esta música.** 40 fon es escucha a
volumen bajo. Esto se oye a 85-100 dB SPL, donde las isofónicas son mucho más
planas, así que compensaba de más. Como ilustración valía; con un corredor
encima habría pasado a juzgar con una autoridad que no tiene.

**Si vuelve**, la condición es anclarla al cuerpo del tema, no al pico — con eso
su corredor es el actual desplazado en bloque y no puede contradecir nada. El
precio es la escala: con ponderación A el espectro dibujado ocupa **79 dB** (93
contando curvas de usuario) contra los 42 de ahora, así que o se recorta el
grave o el detalle en medios se queda en un temblor.

El motor sigue publicando `db_pond` y `espectro_display_pond`. Ya no los lee
nadie: son el dato crudo por si la vista vuelve.

## 6. El mismo pipeline para la referencia y para el usuario

Es una condición, no una coincidencia. Cada referencia pasa por lo mismo que el
track del usuario:

| paso | dónde |
|---|---|
| carga estéreo a 22 050 Hz, mono por media de canales | ambos |
| RMS con `hop_length=512` | ambos |
| **ventana de 10 s de más energía** | `engine.extractor.ventana_drop()` |
| espectro en tercios de octava a la frecuencia nativa | `_espectro_tercios_octava()` |
| inclinación de dibujo `V2_TILT = 1.5` dB/oct | frontend, ambos |
| anclaje al cuerpo del tema (200 Hz – 2 kHz) | frontend, ambos |

`ventana_drop()` vive en el motor **precisamente para que haya una sola
implementación**. Cuando eran dos copias, el camino de usuario redondeaba el
inicio a 0.1 s y el de referencia no: 50 ms de desfase movían las bandas hasta
**1.5 dB**, el 13 % del ancho del corredor. Unificarlo cambió el corredor
0.40 dB como máximo.

## 7. Qué se dibuja y qué se juzga

Son dos rangos distintos, a propósito.

| | rango | constante |
|---|---|---|
| se **dibuja** | 20 Hz – 16 kHz | `V2_TOPE_DIBUJO` |
| se **compara** | 50 Hz – 12.5 kHz | `V2_VEREDICTO_DESDE` + tope de `V2_CORREDOR` |

**Por qué no se juzga por debajo de 50 Hz.** Ahí el corredor mide 21–28 dB de
ancho, contra 11–16 dB por encima: cabe casi cualquier cosa, así que un aviso no
informa. Además filtrar el subgrave es una decisión de producción correcta y muy
común. El corredor **sí se sigue dibujando** ahí, desvanecido. Efecto acotado:
cambia el veredicto de 2 de 322 previews y 2 de 33 tracks de usuario, siempre de
FUERA a DENTRO.

**Por qué no se juzga por encima de 12.5 kHz.** No es que los archivos se corten
ahí — cada uno corta donde le deja su encoder, entre 16 y 20 kHz (mediana 18.3,
p10 16.0, y 27 de 327 por debajo de 16 kHz). El problema es esa
**heterogeneidad**: más arriba el corredor mediría la variedad de compresores y
no la de la música. Se ensancha a 20.7 dB en 16 kHz y a 64 dB en 20 kHz.

La garantía es estructural: `ref` se construye desde `V2_CORREDOR`, que termina
en 12.5 kHz, y una banda sin entrada devuelve 0 desviación. Hay un test que
vigila las dos mitades.

## 8. La regla de comparación

No es "no salirse nunca": con 25 bandas juzgadas y un corredor del 5 al 95,
salirse en alguna es aritmética — solo el **30 %** de los propios previews se
queda dentro en todas. Una banda suelta fuera es la textura del tema; lo que
describe una zona es una **racha**.

Se marcan **rachas de 4 bandas seguidas del mismo signo**. Con ese umbral, y
sobre el rango que de verdad se juzga (50 Hz – 12.5 kHz, 25 bandas):

| | dentro de la referencia |
|---|---|
| los 322 previews de catálogo | **88 %** |
| 33 tracks de usuario | **79 %** |

**Nueve puntos de separación.** Esto no distingue a un aficionado de un
profesional y no debe presentarse como si lo hiciera.

(El calibrador imprime por stderr un 87 % porque lo calcula sobre las 29 bandas
del corredor entero, incluidas las de menos de 50 Hz que la regla ignora. Es la
misma medida sobre distinto rango; la que manda es la de 25 bandas.)

## 9. Por qué la UI dice DENTRO / FUERA y no EQUILIBRADO / REVISAR

Por esos 9 puntos.

"EQUILIBRADO" afirma que el balance está bien. "Sobra en los graves" receta
bajarlos. Lo único que se ha medido es **dónde cae el track respecto a una
colección concreta**, y con esa capacidad de separación ninguna de las dos
afirmaciones está respaldada.

El copy resultante:

```
REFERENCIA · DENTRO   "Tu balance cae dentro del rango de referencia."
REFERENCIA · FUERA    "Tus graves están por encima del 95 % de la referencia."
                      "Tu presencia está por debajo del 5 % de la referencia."
anotación             "Tus graves, 4 dB sobre la referencia"
pie                   "Referencia: 322 previews de catálogo de 26 sellos,
                       sobre todo progressive y house."
```

Todo enunciado dice **respecto a qué**. La zona que se nombra se decide por
mayoría de bandas de la racha, no por la banda de mayor desviación: una racha de
50 a 200 Hz cuyo pico cayera en 200 se llamaba "medios bajos" siendo casi toda
graves.

## 10. Regla que no se negocia

**La interfaz no puede sugerir un problema que el análisis no haya detectado.**

De ahí salen decisiones que si no parecen arbitrarias: el corredor es morado
apagado y no rojo; la curva es blanca y solo se tiñe donde hay una racha
marcada; no hay relleno hasta el fondo (una montaña alta no es un defecto, toda
la música tiene el grave alto); y el corredor se desvanece por debajo de 50 Hz,
que es donde deja de opinar.

Cuidado con leer ese desvanecido como si marcara siempre el límite: por la
derecha el corredor lleva **una pluma corta —poco más de una banda— que es solo
acabado**, para que no termine en un tajo vertical. Ahí sigue juzgando hasta
12.5 kHz. El límite de verdad lo fija `V2_CORREDOR`, no la máscara del dibujo.

## 11. Cómo regenerarlo

```bash
python backend/scripts/calibrar_corredor.py \
  --corpus "../label-match/data/audio_samples"
```

Imprime el bloque `V2_CORREDOR` listo para pegar en `frontend/index.html`, y por
stderr el reparto que produce la regla — que es lo que hay que vigilar: si el
porcentaje de previews "dentro" se aleja mucho del 87 % que imprime, algo ha cambiado en el
corpus o en el pipeline.

El número de observaciones aparece en tres sitios del frontend (cabecera de
`V2_CORREDOR`, comentario de `v2CompararCorredor` y el pie que ve el usuario) y
en `backend/tests/test_corredor_espectro.py`. **Están escritos a mano**: si el
corpus cambia, hay que actualizarlos o mentirán en silencio.
