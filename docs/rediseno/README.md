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
   Las que tienen algo que mirar llevan un punto amarillo.
3. **Texto desplegable.** Cada tarjeta enseña un avance de una o dos frases y
   guarda el resto tras «Saber más». **No se quita ni una palabra**: deja de
   estar toda de golpe.

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
* **Lo que rodea al diagnóstico.** Feedback, tutoriales, CTA al Máster,
  compartir en comunidad: no están. Esto es solo la vista de resultados.

---

## Archivos

| Archivo | Qué es |
|---|---|
| `prototipo.html` | **Lo que hay que abrir.** Generado, autocontenido, 222 KB |
| `prototipo.src.html` | La fuente con JSX. Es lo que se edita |
| `casos.json` | Los tres análisis reales |
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

* Dónde encajan feedback, tutoriales y el CTA al Máster: ¿fuera de las
  pestañas, siempre visibles, o en una sexta?
* Si el informe descargable en texto plano sigue igual (ahora es un volcado
  lineal y no tiene pestañas).
* La primera prioridad del motor menciona `n_bloques`, que es un nombre de
  variable interno. Se cuela en el texto que ve el usuario; no es cosa del
  rediseño, pero se ve mucho más ahora que está arriba del todo.
