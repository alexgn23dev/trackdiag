# Cómo se le pide el feedback al usuario, y por qué dejó de llegar

Agosto 2026. Alex notó que apenas recibía feedback desde el rediseño. Lo era, y
había dos causas encadenadas — solo una la trajo el rediseño.

## 1. La caída, medida

Respuestas guardadas (`analisis.fue_util` no vacío) sobre análisis de esa semana:

| semana | análisis | respuestas | % |
|---|---:|---:|---:|
| 11-may | 548 | 77 | **14,1 %** |
| 25-may | 450 | 33 | 7,3 % |
| 8-jun | 164 | 2 | 1,2 % |
| 27-jul | 320 | 11 | 3,4 % |
| 17-ago | 142 | 1 | **0,7 %** |

Dos escalones, los dos reales:

- **junio:** 10,4 % → 3,7 % (p = 0,000006)
- **13-ago, la v2 por defecto:** 2,95 % → **0,31 %** (p = 0,007). Una sola
  respuesta guardada en 319 análisis.

## 2. Causa A — el widget desapareció de la v2

Los extras del Resumen llevaban `feedback: null`, con este comentario:

> El widget en tarjeta se quitó: Alex lo prefiere como en la vista clásica, en
> la barra flotante de abajo.

El comentario tenía un error de hecho: **la vista clásica tenía las dos cosas**,
la barra flotante *y* el widget en el cuerpo del informe. Al quedarse solo la
barra, la única vía para responder pasó a ser un elemento que aparece a los 20
segundos y se puede cerrar con una ✕.

Arreglado devolviendo el widget al Resumen (`v2-feedback`, media columna junto a
los tutoriales) y conservando la barra.

## 3. Causa B — el primer clic no guardaba nada

Esta **no la trajo el rediseño**: llevaba ahí desde el principio, y explica por
qué la tasa nunca pasó del 14 % ni en su mejor semana.

Pulsar *Sí / Parcial / No* solo hacía `setFeedbackStep(1)`. El `fue_util` se
escribía **únicamente** al enviar el formulario de detalle del paso siguiente —
y justo al lado de ese botón había un **«Saltar»** que avanzaba sin guardar.
Todo el que contestaba y cerraba la pestaña contaba como que no había
contestado.

Ahora el veredicto se guarda en el primer clic, con `keepalive: true` para que
el POST sobreviva al cierre de la pestaña. El detalle sigue siendo opcional y
completa la misma fila: el `UPDATE` del backend usa **`COALESCE`**, así que el
segundo envío no pisa lo que ya había.

```sql
SET fue_util   = COALESCE($1, fue_util),
    comentario = COALESCE($2, comentario)
```

Todos los análisis de los últimos 30 días tienen email (1.039 de 1.039), así que
`find_latest_analisis_by_email` siempre encuentra la fila. No hace falta tocar
el backend.

## 4. Causa C — la interfaz destacaba el «No»

`bg-green-900/40` y `bg-yellow-900/30` sobre el fondo del informe se leían como
texto suelto, mientras `bg-gray-800` del «No» sí parecía un botón. Los tres
llevan ahora fondo y borde explícitos del mismo peso. La barra flotante aparece
a los 8 s en vez de a los 20.

Ojo al tocar esto: `bg-yellow-900/30` **sigue siendo legítimo** fuera de aquí —
lo usan las insignias de estado, que no son botones y hacen familia con
`bg-red-900/30` y `bg-blue-900/30`. El guard solo mira la zona de feedback.

## 5. Lo que NO está demostrado

**El escalón de junio no tiene causa confirmada.** Coincide con la tanda de CTAs
del 28-29 de mayo (consultoría, embudo), que llenó de tarjetas la zona baja del
informe donde vivía el widget. Es plausible y encaja en el tiempo, pero es
correlación: no está medido como el de agosto.

## 6. Por qué hay un guard automático

`backend/tests/test_feedback_se_pide_y_se_guarda.py`.

Es un fallo que no se nota: no rompe nada, no sale en ningún log, y la única
señal es una métrica que hay que ir a mirar a propósito. Tardó unos dos meses en
detectarse, y por el camino se perdió el feedback que calibra el motor. El test
está verificado contra los dos sabotajes reales (volver a poner `feedback: null`
y devolver un botón a `setFeedbackStep(1)` sin guardar): falla en ambos.
