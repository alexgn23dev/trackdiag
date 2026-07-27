# Estudio histórico de Mentotrack — material verificado para newsletter

**Fecha del estudio:** 2026-07-24 · **Fuente:** Postgres de producción (Railway), tabla `analisis` completa
**Scripts reejecutables:** `backend/scripts/estudio_historico/` (cada cifra referencia su sección §N de `02_estudio.py`)
**Regla del documento:** ninguna cifra está estimada; todas salen de una query sobre el N limpio y llevan su n al lado.

---

## 0. Higiene de datos (§0)

| Concepto | n |
|---|---|
| Análisis totales en la base de datos | **2.507** |
| Excluidos: cuentas internas de Alex (alexgn23@gmail.com, alex@producciononline.com, producciononline.blog@gmail.com) | 18 |
| Excluidos: análisis fallidos (informe vacío y señales nulas, todos de motor antiguo) | 23 |
| Excluidos: duplicados — mismo email + misma huella de audio (BPM, LUFS, energía grave, duración, tonalidad) reanalizado en ≤30 min | 94 |
| **N limpio (todo el estudio usa este número)** | **2.372** |

Notas de higiene:
- El histórico cubre del 2026-04-30 al 2026-07-24. Julio está incompleto (hasta el día 24).
- `mentotrack.heave239@passmail.net` parece interno por el nombre pero es el patrón de alias automático de Proton Pass (`sitio.palabraNNN@passmail.net`): se trata como usuario real y **no** se excluye.
- Además de los 94 duplicados rápidos, hay 208 re-subidas del mismo archivo en ventanas más largas. No se excluyen: reanalizar el mismo bounce días después es uso legítimo (comprobar progreso), pero conviene saber que existen.
- La métrica interna `rango_dinamico` (mediana 2,2 dB) no es el "DR" estándar de la industria; para dinámica se usa aquí el rango de loudness LRA (`rango_loudness`).
- El true peak solo está disponible en 1.570 de los 2.372 análisis (66%): se añadió al informe a mitad del histórico. Todos los porcentajes de true peak usan ese subconjunto.

---

## 1. Tabla resumen

| Métrica | Valor | n | Clasificación |
|---|---|---|---|
| Análisis subidos declarando "creo que está casi listo" | 65,1% | 2.372 | SÓLIDO |
| Brecha de autopercepción (definición D1, motor actual) | **75,5%** | 1.543 | SÓLIDO |
| Brecha ajustada a base comparable con el estudio de 613 | 62,7% | 1.543 | SÓLIDO |
| Réplica del hallazgo previo (~64%) sobre los primeros 613 análisis limpios | 61,8% | 401 | SÓLIDO (replica) |
| Brecha ponderando 1 usuario = 1 voto | 72,1% | 556 usuarios | SÓLIDO |
| Brecha inversa (declaran fase temprana y el audio sale limpio y maduro) | 9,4% | 384 | INDICATIVO |
| Diagnóstico más frecuente: carencia espectral (falta cuerpo/aire) | 22,4% | 2.372 | SÓLIDO |
| Análisis que salen sin ningún bloqueo | 21,9% | 2.372 | SÓLIDO |
| LUFS integrado mediano | −10,5 LUFS | 2.372 | SÓLIDO |
| True peak ≥ 0 dBTP (clipping) | 39,4% | 1.570 | SÓLIDO |
| True peak ≥ −1 dBTP (no pasa el estándar de streaming) | 74,5% | 1.570 | SÓLIDO |
| Clipping en tracks "para sello" que su autor da por casi listos | 41,3% | 368 | SÓLIDO |
| Clipping: menos de 6 meses de experiencia vs más de 5 años | 27,1% vs 51,2% (z=7,3) | 424 / 455 | SÓLIDO |
| Usuarios con un solo análisis | 50,6% | 789 usuarios | SÓLIDO |
| Reanálisis en menos de 1 hora (del total de reanálisis) | 47,3% | 1.583 pares | SÓLIDO |
| Concentración: top 17 usuarios (2,2%) sobre el total de análisis | 26,4% | 2.372 | SÓLIDO |
| v1→v2 del mismo proyecto: el bloqueo principal cambia | 45,9% | 148 | INDICATIVO |
| v1→v2 del mismo proyecto: sale totalmente limpio | 7,4% | 148 | INDICATIVO |
| Par de problemas más ligado: arreglo repetitivo + falta de impacto | lift 6,4 | 56 | INDICATIVO |
| Par de problemas más frecuente: carencia espectral + exceso de graves | lift 2,5 | 329 | SÓLIDO |
| Acuerdo del usuario con el diagnóstico "mezcla prematura" | 45,0% de "Sí" | 20 | ESPECULATIVO |

Definiciones de clasificación: **SÓLIDO** = n alto y diferencia clara, publicable. **INDICATIVO** = n medio o efecto pequeño, usable con cautela y matiz. **ESPECULATIVO** = n bajo, no publicable.

---

## 2. Los hallazgos principales (lenguaje llano)

### H1. Tres de cada cuatro tracks que su autor da por "casi listos" tienen todavía un problema principal (§5) — SÓLIDO

De los 2.372 análisis limpios, 1.543 (el 65%) llegan con el productor declarando que el track "está casi listo". En 1.165 de esos 1.543 (75,5%), el análisis encuentra un bloqueo principal: algo concreto que arreglar antes de darlo por terminado. La cifra apenas se mueve si se cuenta por personas en vez de por tracks (72,1%) y es estable mes a mes. **Definición operativa:** campo declarado `fase` = "Creo que está casi listo", contra `diagnostico_principal` ≠ `sin_diagnostico` del motor.

### H2. El hallazgo del 64% se sostiene — y la subida al 75% es del motor, no de los usuarios (§5) — SÓLIDO

Recalculado sobre los primeros 613 análisis limpios (la ventana del estudio previo), la brecha da 61,8%: el ~64% anterior **se replica**. Con el histórico completo sube a 75,5%, pero la subida viene sobre todo de que el motor detecta hoy más tipos de problema (en particular `enmascaramiento_bajo`, añadido en junio). Quitando esa hipótesis para comparar en igualdad de condiciones, la brecha da 62,7%. Conclusión honesta: la brecha real ronda el **62–75% según lo fino que mida el motor** — nunca contar que "los usuarios han empeorado del 64% al 75%".

### H3. Decir "está casi listo" no aporta casi información (§5) — SÓLIDO

Quien declara "casi listo" recibe un bloqueo el 75,5% de las veces; quien declara estar aún ajustando la mezcla, el 78,2%; quien dice tener el arreglo a medias, el 84,4%. Y la madurez que el audio demuestra es casi idéntica entre "casi listo" (69,5% avanzado) y "ajustando mezcla" (71,0%). Es decir: la sensación de "ya casi está" apenas distingue un track del que aún se está trabajando — solo la fase "idea/loop" se autodeclara con realismo.

### H4. El true peak es la epidemia silenciosa: 3 de cada 4 tracks no pasan el estándar de streaming (§3) — SÓLIDO

De los 1.570 análisis con dato de true peak, el 39,4% clipea directamente (≥ 0 dBTP) y otro 35,2% queda entre −1 y 0 dBTP: en total, el 74,5% supera el techo de −1 dBTP que piden las plataformas. Incluso entre los tracks que van "para sello" y que su autor da por casi listos, el 41,3% clipea (n=368). Es el fallo técnico más masivo y el más fácil de arreglar (bajar el ceiling del limiter).

### H5. Los veteranos clipean el doble que los novatos (§7a) — SÓLIDO

Contra toda intuición, el clipping crece con la experiencia declarada: 27,1% en menores de 6 meses (n=424), 34,8% en 6m–2 años, 45,4% en 2–5 años y 51,2% en más de 5 años (n=455). La diferencia es enorme (z=7,3). La lectura probable no es "los veteranos mezclan peor": es que empujan el máster más fuerte (más loudness: −9,9 vs −11,4 LUFS de mediana) y sacrifican el true peak, mientras los novatos suben mezclas sin masterizar con headroom. Pero el estándar lo incumplen igual.

### H6. Da igual cuál creas que es tu punto débil: el análisis encuentra otra cosa (§7b) — SÓLIDO

Quien declara que su dificultad habitual es "que la mezcla suene bien" recibe un diagnóstico de mezcla el 61,9% de las veces… y quien declara que su dificultad es "estructurar las ideas" también recibe mezcla el 59,5% (y estructura solo el 39,0%). La distribución de lo que encuentra el motor es casi la misma en los cinco grupos de dificultad declarada. La autopercepción no falla solo en "cuánto de terminado está": falla también en **qué tipo de problema** se tiene.

### H7. El uso "one-shot mayoritario" YA NO SE REPLICA: hoy es mitad y mitad (§6) — SÓLIDO ⚠️ contradice el estudio previo

Con el histórico completo, el 50,6% de los 789 usuarios tiene un solo análisis y el 49,4% repite — llamar a eso "mayoritariamente one-shot" ya no es defendible. Además, el que repite lo hace rápido: el 47,3% de los reanálisis llega en menos de 1 hora (mediana 1,4 h) — se usa como herramienta de iteración en sesión, no como chequeo puntual. Ojo con la concentración: 17 usuarios (el 2,2%) generan el 26,4% de todos los análisis.

### H8. Iterar funciona… a medias (§6) — INDICATIVO

En los 175 proyectos con v1 y v2 analizadas, cuando la v1 tenía un bloqueo, en el 45,9% de los casos ese bloqueo ya no es el principal en la v2 (mediana de 2,5 h entre versiones). Pero solo el 7,4% consigue que la v2 salga totalmente limpia, y el loudness no se mueve (ΔLUFS mediana 0,0). El clipping sí mejora algo entre versiones: del 49% al 39% (60→48 de 123 pares con dato). Se arregla el problema señalado y aparece (o aflora) el siguiente.

---

## 3. Cifras publicables (formulación exacta recomendada)

Cada formulación está redactada para no exagerar lo que el dato soporta:

1. **"2 de cada 3 tracks se suben al análisis con su autor convencido de que están casi listos."** (65,1%, n=2.372)
2. **"3 de cada 4 tracks que sus autores dan por casi terminados tienen todavía un problema principal detectable."** (75,5%, n=1.543). Versión conservadora si se quiere serie comparable en el tiempo: **"más de 6 de cada 10"** (62,7% ajustada).
3. **"El 39% de los tracks analizados clipea (true peak ≥ 0 dBTP), y 3 de cada 4 superan el techo de −1 dBTP recomendado para streaming."** (n=1.570)
4. **"Incluso entre los tracks que van camino de un sello y que su autor da por casi listos, 4 de cada 10 clipean."** (41,3%, n=368)
5. **"Los productores con más de 5 años de experiencia clipean casi el doble que los que llevan menos de 6 meses: 51% frente a 27%."** (n=455 y 424) — añadir el matiz de H5: no es que mezclen peor, es que empujan el máster más fuerte.
6. **"Da igual cuál creas que es tu punto débil: la distribución de problemas que encuentra el análisis es prácticamente la misma declares lo que declares."** (§7b, n=1.853 con bloqueo)
7. **"El track mediano llega a −10,5 LUFS; solo un 2,5% llega 'aplastado' por encima de −6."** (n=2.372)
8. **"La mitad de quienes prueban el análisis repiten, y casi la mitad de las repeticiones llegan en menos de una hora: se usa para iterar en la misma sesión de estudio."** (50,6% de 789; 47,3% de 1.583)
9. **"El combo más repetido: graves que dominan de más y a la vez falta de cuerpo en medios y aire en agudos — la clásica mezcla desequilibrada hacia abajo."** (par carencia_espectral + exceso_lowend, n=329, 2,5× lo esperado por azar)

## 4. No publicar (demasiado flojo o directamente engañoso)

- **"La brecha subió del 64% al 75%"** — la subida es del motor (hipótesis nuevas), no de los usuarios. Publicarlo como evolución sería falso (H2).
- **Evolución temporal de los diagnósticos** (§4) — los cambios mes a mes (p. ej. `break_sin_payoff` 13,5%→0,5%, `enmascaramiento_bajo` 3,7%→18%) reflejan cambios de versión del motor, no cambios en los productores. No usar como tendencia.
- **"A los usuarios les convence menos el diagnóstico de mezcla prematura"** (45% de "Sí", n=20) — ESPECULATIVO; solo 169 análisis (7,1%) tienen respuesta de `fue_util`, con sesgo de autoselección.
- **Techno como "el género con mayor brecha"** (83,1%, n=362) y su inversa (Techno es el que menos clipea, 24,2%) — INDICATIVO; interesante para investigar, pero confundido con perfil de usuario y no controlado. Como mucho, gancho interno para un análisis futuro.
- **"Los tracks cortos tienen problemas de estructura"** (<3 min → 72,3% estructural, n=267) — parcialmente circular: el motor usa la duración como señal estructural. No presentarlo como descubrimiento.
- **La brecha inversa del 9,4%** ("humildes con track terminado", n=384/36 casos) — INDICATIVO, n bajo en la celda que importa.
- **Cualquier cifra de `rango_dinamico`** — es una métrica interna no comparable con el "DR" que la gente conoce; usar LRA si hace falta hablar de dinámica.
- **Mejora v1→v2 como "el 46% arregla su problema"** — el n es medio (148) y "el bloqueo cambia" no siempre significa "resuelto" (puede aflorar otro). Formularlo como en H8 o no usarlo.

## 5. Reproducibilidad

- `backend/scripts/estudio_historico/01_extraer.py` — vuelca `analisis` y `usuarios` de Postgres (Railway) a un SQLite local gitignored (contiene emails; no debe salir de la máquina).
- `backend/scripts/estudio_historico/02_estudio.py` — recalcula e imprime TODAS las cifras de este documento por secciones §0–§7 (las referencias §N de arriba).
- Ejecutado el 2026-07-24 sobre 2.507 filas brutas / 2.372 limpias. Para actualizar el estudio: reejecutar ambos scripts; las definiciones operativas (internos, duplicados, D1, dominios mezcla/estructura) viven en el código.
- Privacidad: este documento solo contiene agregados; ningún dato individual identificable.
