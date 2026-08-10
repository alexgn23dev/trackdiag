# Prueba de rediseño del diagnóstico

**Ábrelo con doble clic:** `docs/rediseno/prototipo.html`

No necesita servidor, ni internet, ni instalar nada. Pinta al instante.

> Esta carpeta **no se sirve en producción**: el catch-all de `main.py` solo
> publica lo que hay en `frontend/`. Es material de trabajo.

---

## Qué se está probando

El diagnóstico de hoy es una columna de 672 píxeles (`max-w-2xl`) con unas
veinticinco secciones apiladas. En una pantalla de 1920 usa el 35 % del ancho,
y todo el texto está a la vez.

Esta prueba cambia tres cosas:

1. **Ancho.** El contenedor pasa a 1280 px y el contenido se reparte en
   rejillas de dos y tres columnas.
2. **Pestañas.** Cinco: Resumen · Plan de acción · Mezcla · Máster · Detalle.
   Las que tienen algo que mirar llevan un punto de color.
3. **Texto desplegable.** Cada tarjeta enseña un avance de una o dos frases y
   guarda el resto tras «Saber más». **No se quita ni una palabra**: deja de
   estar toda de golpe.
4. **Sin emojis.** Cada tarjeta se identifica con un rótulo en versalitas y,
   cuando hay algo que mirar, con un punto de color. Es lo que separa un panel
   de herramienta de una app de consumo.
5. **Lo que rodea al diagnóstico va en el Resumen**, no escondido: la
   derivación al Máster, los tutoriales del canal filtrados por diagnóstico y
   la pregunta de calibración. Compartir y descargar, en la barra de acciones.
   Los textos salen de `contenido.json`, extraído del `index.html` real para
   no inventar copy que luego no existe.

Los datos son **reales**, salidos del motor (v0.5.77). Hay tres análisis para
comparar: un boceto temprano, un máster caliente y un track cuidado.

Se puede enlazar una vista concreta:

```
prototipo.html?tab=master&caso=caliente
```

## Lo que NO se puede juzgar aquí

* **El móvil.** Los puntos de ruptura de CSS dependen del tamaño de la
  ventana. Para verlo, estrecha la ventana del navegador; no hay ningún botón
  que lo simule (había uno y se quitó porque mentía: estrechaba el contenedor
  sin mover los puntos de ruptura).
* **La tipografía.** Se usa la pila del sistema en vez de Arimo y Space
  Grotesk, para que el archivo no dependa de Google Fonts y abra sin red.
* **El comportamiento de la barra de acciones.** «Compartir», «Descargar» y
  «Analizar otra versión» no hacen nada: en la prueba no hay informe ni
  sesión. Llevan un `title` que lo dice, para que nadie los persiga.

  Lo que **sí** funciona: el botón del Máster navega a la URL real con sus
  parámetros UTM, los tutoriales abren su vídeo y el feedback responde (aunque
  no envía a ningún sitio).

---

## Archivos

| Archivo | Qué es |
|---|---|
| `prototipo.html` | **Lo que hay que abrir.** Generado, autocontenido, 230 KB |
| `prototipo.src.html` | La fuente con JSX. Es lo que se edita |
| `casos.json` | Los tres análisis reales |
| `contenido.json` | Tutoriales y variantes del CTA, extraídos del `index.html` real |
| `incrustar-logo.cjs` | Mete el logo de Producción Online como data URI |
| `construir.cjs` | Genera `prototipo.html` a partir de lo anterior |
| `verificar.cjs` | Renderiza cada pestaña con cada análisis en Node |
| `tailwind.config.cjs`, `tw.in.css`, `tw.out.css` | Solo las clases que se usan |
| `react.js`, `react-dom.js` | UMD de producción, para no depender del CDN |

## Volver a generarlo

```bash
# Solo si se han añadido clases de Tailwind nuevas
npx tailwindcss@3 -c docs/rediseno/tailwind.config.cjs \
    -i docs/rediseno/tw.in.css -o docs/rediseno/tw.out.css --minify

SCRATCH=<dir-con-node_modules> node docs/rediseno/construir.cjs
SCRATCH=<dir-con-node_modules> node docs/rediseno/verificar.cjs
```

`verificar.cjs` no sustituye a mirar la página, pero atrapa lo que de verdad
la rompe con datos reales: un `undefined.toFixed()`, un `.map` sobre un campo
que ese análisis no trae, un `.split` sobre `null`. Eso deja la página en
blanco y no se ve hasta abrirla.

---

## Fallos encontrados y corregidos mientras se construía

Se anotan porque son los mismos que habría que evitar al llevarlo a
`index.html`:

* **El título del diagnóstico salía dos veces**, en la cabecera y en la
  primera tarjeta, una debajo de la otra.
* **Las prioridades son párrafos de 400 caracteres.** Cortarlas por la primera
  frase no bastaba: algunas son una sola frase encadenada con puntos y coma.
* **`253164` y `3.9683 ms`** se pintaban en crudo.
* **La tarjeta de saturación se contradecía**: el indicador decía «moderada» en
  amarillo y el cuerpo, debajo, «el limitador no ha aplastado la dinámica».
* **La escala de picos llegaba a +3 dBTP** y un máster recortado se va a +4,9,
  así que la marca se quedaba clavada en el borde.

## Pendiente de decidir antes de llevarlo a producción

* **El móvil.** Con cinco pestañas y rejillas de tres columnas, hay que
  mirarlo en un teléfono de verdad antes de dar nada por bueno.
* **El informe descargable** sigue siendo un volcado lineal en texto plano.
  ¿Se reordena para que siga el orden de las pestañas?
* **Qué pasa con un análisis sin diagnóstico secundario o sin tutoriales**
  para su categoría: la rejilla de tres se queda con dos tarjetas y un hueco.
* **Dónde va el aviso de género fuera de alcance** (vallenato, pop, rock…),
  que hoy sale arriba del todo y aquí no está contemplado.

### Los 13 tutoriales rotos: arreglados (2026-08-10)

Estaban rotos porque **el canal los resubió con otro ID**, no porque los
borrara. Se han buscado por título uno a uno y sustituido en
`frontend/index.html`. Las doce categorías vuelven a tener tutoriales.

Antes de que se arreglaran, **33 de los 147 clicks (22 %)** acabaron en un
"vídeo no disponible".

Para que no vuelva a pasar en silencio:

```bash
python backend/scripts/verificar_tutoriales.py
```

No está en el CI a propósito: depende de YouTube y de la red, y un test que
falla por causas ajenas al commit acaba ignorándose.

### El logo de Producción Online

Ya está puesto: `frontend/logo-po.svg` (la versión _VR_B, que viene en blanco
y por eso no hay que recolorearla) va incrustado como data URI en
`contenido.json`, así que el prototipo sigue abriéndose sin red.

Si algún día cambia el archivo:

```bash
node docs/rediseno/incrustar-logo.cjs frontend/logo-po.svg
node docs/rediseno/construir.cjs
```

El script detecta si el SVG ya viene en claro y, si no, lo recolorea a blanco
— las tarjetas son oscuras y el monograma en su versión normal es negro.

### Ya resuelto

* La primera prioridad decía `n_bloques bajo`, un nombre de variable interno
  colándose en el texto del usuario. Arreglado en `engine/templates.py`, con
  `tests/test_lenguaje.py` barriendo todo el texto de cara al usuario para que
  no vuelva a pasar.
