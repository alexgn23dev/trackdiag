# Mentotrack — Vías de monetización

> Borrador de trabajo para decidir cómo monetizar. Anclado en datos reales de la
> base a 2026-06-13. Pensado para que Alex reaccione, no como plan cerrado.

---

## TL;DR (mi recomendación en 4 líneas)

1. **El motor de ingresos NO es la auditoría 1:1** (los datos lo confirman: no convierte). Es **una suscripción barata de alto volumen + perks de comunidad.**
2. **Mentotrack Pro** (≈5 €/mes, con precio adaptado a LATAM): desbloquea las funciones "power" del análisis **y** las ventajas de comunidad (más slots, destacar tu track, badge verificado, feedback prioritario).
3. **La comunidad es el gancho de conversión**, no un extra. El 96% de la encuesta quiere compartir/recibir feedback → es ahí donde está la disposición a pagar.
4. **Primer paso técnico imprescindible:** integrar pagos (Stripe). Sin eso no hay nada que cobrar.

---

## 1. Punto de partida: los datos (no opiniones)

| Métrica | Valor | Qué nos dice |
|---|---|---|
| Usuarios | **661** (todos con email) | Base pequeña pero real y contactable |
| Análisis totales | **1.650** (2,6 / usuario) | Uso repetido, no de usar y tirar |
| Vuelven a analizar | **~52%** (342 de 661 con 2+ análisis) | Hay retención |
| Power users (4+ análisis) | **96 (14,5%)** | El núcleo que pagaría |
| Activos últimos 30 días | **517 (78%)** | Base muy viva / en crecimiento reciente |
| Geografía | ES (líder) + AR, CO, CL, EC, MX, UY… | Español: España + LATAM |
| **Auditoría 1:1 (embudo)** | 137 vieron CTA → **1** envió form → 2 solicitudes (rechazadas) | **El high-ticket NO convierte** |

### La conclusión incómoda pero útil
El producto **de pago que ya existe (la auditoría 1:1) no genera ingresos**. 0,7% de conversión del CTA y cero ventas cerradas. No es un fallo de ejecución puntual: es que **esta audiencia —productores emergentes, mayoría LATAM— no compra mentoría cara en frío.** Compran, si acaso, **algo barato y recurrente que les dé valor continuo.**

Esto **no** significa matar la auditoría. Significa **dejar de tratarla como el motor** y construir el motor en otro sitio.

---

## 2. Lo que los datos dicen sobre CÓMO cobrar

1. **Volumen × precio bajo, no pocos × precio alto.** Con 661 usuarios y poder adquisitivo LATAM, 5 €/mes a un 8% (≈53 personas) = ~265 €/mes recurrentes y creciendo. Eso es más realista y más estable que vender auditorías de 250 €.
2. **El precio tiene que respetar a LATAM.** Un Spotify Premium cuesta ~3-5 € en Argentina/Colombia por algo. Opciones: precio absoluto bajo global, o precio regional. **No** clavar un precio europeo.
3. **No mates el gancho.** El análisis básico **debe seguir gratis** — es el funnel que trae a los 661. Se monetiza la **profundidad** (historial, comparación, proyectos) y la **comunidad** (visibilidad), no el primer análisis.
4. **La disposición a pagar está en la comunidad.** 96% dijo que compartiría y comentaría. Ahí es donde "pagar para que te escuchen / destacar / verificarte" tiene sentido emocional.

---

## 3. Principios que seguiría

- **Free generoso, Pro irresistible.** El gratis tiene que ser usable de verdad (si no, no hay funnel). El Pro tiene que doler no tenerlo cuando ya estás enganchado a la comunidad.
- **Cobrar por estatus y velocidad, no por funciones básicas.** "Destaca tu track", "feedback prioritario", "badge verificado" se pagan mejor que "desbloquea el análisis".
- **Aprovechar lo ya construido.** Reputación, reciprocidad, perfil, comparación con referencia: ya existen. El premium se engancha encima casi gratis.
- **Una sola decisión de compra.** Un Pro claro > cinco micro-compras confusas. Micropagos, más adelante.

---

## 4. Los modelos (con pros, contras, precio y esfuerzo)

### 🟢 A — Mentotrack Pro (suscripción) — *el motor*
Una suscripción única que agrupa lo "power" del análisis + perks de comunidad.

**Free:** 1 análisis básico siempre, compartir 1 track, comentar, ganar slots dando feedback (la reciprocidad que ya existe).
**Pro (~5 €/mes ó ~45 €/año):**
- Análisis: comparación con referencia ilimitada, historial completo, proyectos/versiones, export completo, procesado prioritario.
- Comunidad: 3+ tracks a la vez sin reciprocidad, **destacar tu track** arriba del muro, **badge Pro/verificado**, **feedback prioritario** (tu track se muestra antes a productores con experiencia).

- **Pros:** recurrente, escala con la base, reutiliza todo lo construido, no depende del tiempo de Alex.
- **Contras:** requiere Stripe; hay que elegir bien qué queda gratis para no romper el funnel.
- **Esfuerzo:** medio (Stripe + gating de features + página de pricing).
- **Encaje:** ★★★★★

### 🟢 B — Perks de comunidad (la palanca de conversión de A)
No es un modelo aparte, es **el contenido emocional del Pro**. Modelo "pay to be heard" (tipo SubmitHub):
- Destacar/“boost” tu track en el muro.
- Saltarte la reciprocidad (tener varios tracks sin tener que comentar).
- Verificado: tu distintivo resalta → tu feedback pesa y tu track recibe más atención.
- (Futuro) Feedback garantizado de un pro/verificado.

- **Pros:** alimenta el deseo real validado por la encuesta; diferencia de cualquier herramienta de análisis.
- **Contras:** necesita masa crítica en el muro para que "destacar" valga algo (problema del huevo y la gallina al abrir).
- **Esfuerzo:** bajo-medio (encima de A).
- **Encaje:** ★★★★★ (es lo que hace vender A)

### 🟡 C — Auditoría 1:1 productizada — *el high-end del ladder*
No tirarla; **reposicionarla** como el escalón premium, no como la puerta de entrada.
- Niveles: **audit escrito asíncrono** (más barato, escala mejor que una llamada) vs **llamada en vivo** (premium).
- Llega como **upsell** tras enganche en la comunidad ("¿quieres que Alex te lo mire a fondo?"), no como CTA en frío.

- **Pros:** ticket alto, alto margen, ya existe la operativa.
- **Contras:** no escala (tiempo de Alex); los datos dicen que en frío no convierte.
- **Esfuerzo:** bajo (reusa Calendly/operativa actual).
- **Encaje:** ★★★ (complemento, no motor)

### 🟡 D — Founding members / lifetime — *para arrancar*
Antes de la suscripción mensual, una oferta de lanzamiento para bootstrappear caja y validar:
- "Miembro fundador": acceso Pro de por vida o 1 año por un pago único (p.ej. 29-39 €).
- Crea un núcleo de embajadores y valida que la gente paga **antes** de montar la maquinaria de suscripción.

- **Pros:** caja inmediata, valida willingness-to-pay, bajo riesgo.
- **Contras:** ingreso único, no recurrente; hay que honrar el "lifetime".
- **Esfuerzo:** bajo (un pago Stripe + un flag en la cuenta).
- **Encaje:** ★★★★ como **paso 0** de validación.

### ⚪ E — B2B / sponsorship / marketplace — *futuro, con escala*
- Marcas de samples/plugins/sellos pagando por llegar a 660+ productores activos.
- Marketplace: conectar productores con sellos/curadores (pago por envío o revenue share), usando los datos objetivos del motor como **filtro de calidad** (ventaja única).

- **Pros:** techo de ingresos alto; el marketplace es la visión grande.
- **Contras:** necesita mucha más escala y tracción de comunidad; complejidad alta.
- **Esfuerzo:** alto.
- **Encaje:** ★★★ a 12+ meses.

---

## 5. Recomendación secuenciada

**Fase 0 — Validar que pagan (semanas):**
Abre la comunidad a la base + lanza **"Miembro fundador"** (D): pago único ~29-39 € por Pro de por vida/1 año. Mide cuántos pican. Caja inmediata + prueba de que el modelo aguanta, sin montar suscripción todavía.

**Fase 1 — El motor recurrente (1-2 meses):**
Monta **Mentotrack Pro** (A) con Stripe: suscripción mensual/anual, precio LATAM-friendly, gating de features power + **perks de comunidad** (B) como gancho emocional.

**Fase 2 — El high-end (en paralelo):**
Reposiciona la **auditoría 1:1** (C) como upsell dentro del funnel de comunidad, con un nivel asíncrono más barato.

**Fase 3 — Escala (6-12 meses):**
Cuando el muro tenga vida y la base crezca: **B2B/sponsorship** (E) y, si hay tracción, el marketplace con sellos.

---

## 6. Pricing concreto (propuesta de partida)

| Plan | Precio | Qué incluye |
|---|---|---|
| **Free** | 0 € | Análisis básico, 1 track en comunidad, comentar, reciprocidad |
| **Pro mensual** | **~5 €/mes** | Todo lo power + perks de comunidad |
| **Pro anual** | **~45 €/año** (-25%) | Igual, más barato y fija caja |
| **Fundador** (lanzamiento) | **~35 € único** | Pro 1 año / lifetime, edición limitada |
| **Auditoría escrita** | ~49 € | Audit asíncrono de Alex |
| **Auditoría en vivo** | ~99-149 € | Llamada 1:1 (bajado del 250 € que no convertía) |

- **LATAM:** o bien Stripe con precios regionales, o un único precio bajo (5 € es ya asumible en gran parte de LATAM para algo que usan a menudo). Empezaría con **precio único bajo** por simplicidad y subiría sofisticación luego.

---

## 7. Proyección rápida (conservadora, con tu base actual)

Suponiendo que **no crece** la base (661) y conversión a Pro:

| Conversión a Pro | Suscriptores | Ingreso/mes (5 €) |
|---|---|---|
| 3% | ~20 | ~100 € |
| 5% | ~33 | ~165 € |
| 8% | ~53 | ~265 € |
| 12% (optimista, power users) | ~80 | ~400 € |

No es "hacerse rico", pero: (a) es **recurrente**, (b) **crece con la base** (que está creciendo), (c) el coste marginal es casi cero. Y la auditoría escrita a 49 € añade picos. El verdadero upside está en que la base siga creciendo + el marketplace a futuro.

---

## 8. Requisitos técnicos (lo que hay que construir)

1. **Pagos (Stripe) — bloqueante.** No hay nada de cobro montado. Stripe Checkout + webhooks para activar/desactivar Pro. (Hay conector de Stripe disponible para acelerar.)
2. **Flag `pro` en la cuenta** (columna en `usuarios`, como ya hicimos con `perfil_completo` / la allowlist de comunidad). Gatear features por ese flag — el patrón ya lo tenemos montado.
3. **Página de pricing** (`/pro` o similar) + estados "eres Pro" en el panel.
4. **Gating de features:** decidir y aplicar qué es Pro (comparación ilimitada, historial, boost, badge…).
5. **Portal de gestión** (cancelar/renovar) — Stripe Customer Portal lo da casi hecho.

Nada de esto es enorme: la arquitectura de flags/allowlist que montamos para la comunidad es exactamente el mismo patrón.

---

## 9. Riesgos y cómo mitigarlos

- **Romper el funnel gratis.** Si gateas de más, matas la entrada. → Mantén el análisis básico gratis siempre; cobra profundidad y comunidad.
- **Muro vacío al abrir.** "Destacar tu track" no vale nada si no hay tracks. → Abre la comunidad y deja que se llene **antes** de vender boost; o siembra contenido.
- **Poder adquisitivo LATAM.** → Precio bajo / regional desde el día 1.
- **Solo-founder / tiempo.** → Priorizar lo que NO depende del tiempo de Alex (suscripción) sobre lo que sí (auditorías).
- **Cobrar mata la buena onda de comunidad.** → El pago es por **estatus/velocidad/herramientas**, no por participar. Comentar y compartir 1 track siempre gratis.

---

## 10. El primer paso concreto que propongo

**Validar antes de construir la maquinaria:** cuando abras la comunidad, lanzar la oferta **"Miembro fundador"** (un pago único Stripe + flag `pro`). Es poco código (reusa el patrón de allowlist), da caja, y te dice **con dinero real** si la gente paga — antes de invertir en la suscripción completa.

Si pican → montamos Mentotrack Pro en serio. Si no pican ni a 35 € de por vida → replanteamos antes de gastar esfuerzo.

---

*Siguiente: cuando lo leas, decidimos (a) si validamos con "Fundador" o vamos directos a suscripción, (b) qué queda gratis vs Pro exactamente, (c) precio final. Con eso, el primer entregable técnico sería la integración de Stripe + el flag `pro`.*
