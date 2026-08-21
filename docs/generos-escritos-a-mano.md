# Qué escribe la gente cuando elige «Otro» en el género

Medido el 21-ago-2026 sobre la tabla `analisis` de producción. **3.506 análisis**,
de los cuales **451 (12,9 %) traen género escrito a mano**, de **241 personas
distintas**, en **211 valores distintos** una vez normalizados.

Todo lo de aquí sale de `genero_custom`. El script que lo genera está en el
scratchpad de la sesión; la consulta es directa y se rehace en un minuto.

## 1. Por qué importa: «Otro» no es neutro para el motor

El género **no es decorativo**. Entra en las reglas (`generos_kick_protagonista`,
`generos_graves_ok`, `GENEROS_ESTATICOS`) y en decenas de textos del
contextualizador, siempre con la forma `genero in [...]` sobre el **valor del
selector**. Cuando alguien elige «Otro», su track cae fuera de todas esas listas
y recibe el trato genérico, por muy bien que haya descrito su estilo.

Hay dos desajustes concretos entre lo que el motor sabe y lo que el formulario
ofrece:

| | |
|---|---|
| Valores que el motor reconoce pero **no se pueden elegir** | `ambient`, `downtempo`, `drone` |
| Opción del formulario que el motor **nunca mira** | `breaks` |

`ambient`/`downtempo`/`drone` están en `GENEROS_ESTATICOS` (reglas.py): el motor
ya sabe que ahí la estructura repetitiva y el contraste bajo son lenguaje del
estilo, no un fallo. Simplemente no hay forma de decírselo desde el formulario.
Y quien elige **Breaks** cree estar informando al motor, pero no informa de nada.

## 2. El reparto: qué se repite

De las 451 escrituras, **297 (66 %) siguen dentro de alcance** hoy y **154
(34 %) las rechazaría el filtro de `engine/generos.py`** con un 422. Ese 34 % es
casi todo pop, rock, trap, reggaetón, rap y hip hop.

Lo más escrito, ya normalizado:

| n | valor |
|---:|---|
| 32 | bounce |
| 19 | trap |
| 14 | drum and bass |
| 13 | reggaeton |
| 13 | hardgroove |
| 12 | pop |
| 12 | balkan beat |
| 9 | nu disco · dubstep · rap |
| 8 | organic house · d&b ragga jungle |
| 7 | hip hop · drum and bass ragga jungle |

**153 de los 211 valores se escribieron una sola vez.** La cola es larguísima y
no se puede cubrir con opciones: «psychdelic forest ih tech», «breaks hard
trance percusión asiática techno», «upbeat anime ost», «chunflinflan».

## 3. El corte que manda: el 12 de junio

El 12-jun-2026 se añadieron **Drum & Bass / Jungle**, **Hard Dance / Bounce /
Hardstyle** y **Organic / Melodic House**. Solo lo escrito **después** de esa
fecha dice algo sobre el formulario de hoy.

| grupo | antes | después | personas después | ¿está ya en el formulario? |
|---|---:|---:|---:|---|
| Ambient / Downtempo / IDM / lo-fi | 1 (1 pers.) | **17** | **13** | **no** |
| Hardgroove / Schranz / raw-hypnotic | 7 (7 pers.) | **28** | **8** | **no** |
| Bounce / Makina / Newstyle | 27 (7 pers.) | 18 | 4 | sí, dentro de «Hard Dance / Bounce / Hardstyle» |
| Nu disco / Funky / Jackin house | 10 | 6 | 6 | no |
| Dubstep / Bass house | 13 | 7 | 3 | no |
| UK Garage / 2-step | 3 | 3 | 3 | no |
| Drum & Bass / Jungle | 31 (7 pers.) | **1** | 1 | sí, desde el 12-jun |
| Hardstyle / Hardcore / Gabber | 5 (4 pers.) | **1** | 1 | sí, desde el 12-jun |

**Las opciones de junio funcionaron.** Drum & Bass pasó de 31 escrituras (7
personas) a 1. Hardstyle, de 5 a 1. Cuando la opción existe, la gente la usa.

**Bounce es la excepción aparente, y no lo es:** de las 18 posteriores, **14 son
de una sola persona** que sigue escribiéndolo aunque la opción exista. Las otras
4 se reparten entre 3 personas. No es demanda amplia, es un usuario tozudo.

**Los dos huecos reales son Ambient y Hardgroove**, y se comportan distinto:

- **Ambient** pasó de 1 persona a **13**, con reparto plano (casi todos escriben
  una vez). Es el grupo **más amplio** y es **nuevo**: no existía antes de junio.
- **Hardgroove** creció de 7 a 28 escrituras, pero **22 de esas 28 son de 2
  personas**. Amplitud media (8 personas), volumen concentrado.

## 4. Qué NO es un hueco

**Electro no existe como demanda.** El grupo parecía tener 30 escrituras, pero
al mirarlo de cerca casi todo es gente escribiendo «música electrónica» en
general o pegando «electrónico» a otro género: «pop electrónico», «blues
electrónico», «electro reggaeton», «nu electro hyper pop rock alternativo».
Añadir una opción «Electro» no recogería a nadie.

De paso: la lista blanca de `generos.py` casa **por subcadena**, así que
«electro» dentro de «pop electrónico» hace que esos tracks entren. Es el sesgo
a aceptar que el diseño busca a propósito —el error caro es rechazar a alguien
que sí hace electrónica— y **no propongo tocarlo**. Pero explica por qué siguen
entrando tracks de pop.

**Nu disco (6 personas), Dubstep (3) y UK Garage (3)** están por debajo de lo
que justifica una opción. Alargar el selector tiene coste: cuantas más opciones,
menos se lee cada una.

## 5. Qué dicen los diagnósticos

Reparto del diagnóstico ganador (`senales->'scores'`, 3.483 análisis):

| diagnóstico | hardgroove/raw (38) | otro, dentro (259) | otro, **fuera** (154) | techno (765) | resto (2.267) |
|---|---:|---:|---:|---:|---:|
| enmascaramiento_bajo | **36,8 %** | 18,5 % | 16,2 % | 27,2 % | 19,1 % |
| exceso_lowend | 13,2 % | 12,0 % | 11,7 % | 7,5 % | 14,3 % |
| track_verde | 0 % | 9,3 % | **29,9 %** | 1,8 % | 4,5 % |

Dos lecturas:

- **En música no-electrónica el motor no encuentra nada que decir el 30 % de las
  veces**, frente al 9 % de la electrónica escrita a mano (p < 0,00001). Es la
  confirmación más limpia que hay de que el filtro de alcance de agosto acertó.
- **Los tracks de hardgroove se llevan diagnósticos de graves el 50 % de las
  veces, frente al 35 % del techno** (p = 0,053 — al filo, no concluyente con
  n=38). Encaja con que no reciben el descuento de `generos_kick_protagonista`,
  que sí recibirían si estuvieran etiquetados como techno.

**Lo que NO se sostiene:** la satisfacción de «Otro» es 55 % (16 de 29) frente
al 67 % del selector (111 de 165), pero con esas muestras **la diferencia no es
significativa** (p = 0,21; el intervalo de «Otro» va de 37 % a 73 %). No se
puede afirmar que estos usuarios estén peor servidos — solo que reciben menos
contexto, que es un argumento de mecanismo, no de medición.

## 6. Recomendación

Añadir **dos** opciones, ambas **reutilizando valores que el motor ya entiende**,
así que no hay calibración nueva ni riesgo de cambiar diagnósticos existentes:

1. **«Ambient / Downtempo»** → valor `ambient`. 13 personas, el grupo más amplio
   y en crecimiento. El motor **ya** tiene la sintonía (`GENEROS_ESTATICOS`) y
   hoy es inalcanzable desde el formulario. Es la ganancia más barata que hay.
2. **Renombrar «Hard Techno» → «Hard Techno / Hardgroove / Schranz»** (mismo
   valor `hard_techno`). 8 personas, y les da el descuento de kick protagonista
   que la tabla de arriba sugiere que les falta. Cero cambios de código en el
   motor.

Sobre el miedo razonable de que Ambient contradiga el «solo electrónica de
club»: **no amplía nada**. `fuera_de_alcance` ya acepta ambient, downtempo,
idm, lo-fi y trip hop hoy — esos 17 análisis ya entraron y ya se diagnosticaron.
La opción solo pone nombre a lo que ya pasa, y encima con mejor sintonía.

**No añadir** Electro, Nu disco, Dubstep, UK Garage ni bounce como opción
propia.

**Aparte, a decidir:** `breaks` es una opción que el motor ignora por completo.
O se le da tratamiento (es percusivo, tempo distinto) o al menos conviene saber
que esos usuarios creen estar informando y no informan.
