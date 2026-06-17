# Auditoría pre-lanzamiento — Comunidad + Monetización

Generada el 2026-06-17 por revisión multi-agente (4 frentes + verificación adversarial). 41 hallazgos, 37 confirmados, 3 descartados.

## Veredicto

CASI-GO para la beta gratis con una salvedad seria que conviene cerrar antes de abrir del todo: el endpoint de audio no tiene gating (lo sirve a cualquiera, incluso anónimo, con solo conocer el post_id) y NO existe forma técnica de ejecutar el borrado de cuenta que prometen las páginas legales. Lo demás que la beta gratis necesita ya funciona (reciprocidad, cuota, moderación, transcode MP3). NO-GO rotundo para COBRAR: no hay una sola línea de Stripe, ni webhook, ni columnas de suscripción, ni endpoint admin para tocar el flag pro, ni política de qué pasa con los FLAC al cancelar. Cobrar hoy sería vender Pro sin poder activarlo ni protegerlo.

## Resumen

La comunidad gratis está esencialmente lista para abrir, con dos cosas que cerraría antes: el endpoint de audio (main.py:4642) no tiene NINGÚN gating —lo sirve a cualquiera, incluso anónimo, con solo el post_id, que además se publica junto al flag 'lossless'— y el borrado de cuenta que prometen las páginas legales no existe técnicamente (y las FK de comunidad no tienen CASCADE). Prioridad #1: añadir 'await _require_comunidad' al endpoint de audio (15 min) y, en el mismo fix, no servir FLAC a quien no sea Pro ni autor. Para COBRAR el panorama es NO-GO claro: no hay absolutamente nada de Stripe (ni SDK, ni webhook, ni columnas, ni activación de pro, ni founder lifetime, ni downgrade, ni términos de suscripción) y el flag pro no diferencia cuota ni reciprocidad pese a que el modelo lo vende. Todo eso hay que construirlo antes del primer euro, cuidando la regla de oro de no capar nada de lo que hoy es gratis.


## 🚧 Bloqueantes para ABRIR (free beta)

1. GATING DE AUDIO ROTO (lo más grave). GET /api/comunidad/audio/{post_id} en backend/main.py:4642 (comunidad_audio) NO llama a _require_comunidad ni a _comunidad_habilitada ni siquiera a _optional_auth_user. Verificado leyendo 4640-4709: solo comprueba que el post existe y stream el fichero con Content-Range (descargable entero). Es el ÚNICO endpoint de comunidad sin gating (comunidad_posts:4562, perfil_publico:4616, comentarios:4808 sí lo tienen). Consecuencia: cualquiera, incluso ANÓNIMO sin sesión, con un post_id válido descarga el audio. Y el post_id se sirve en claro en /api/comunidad/posts junto al flag 'lossless' (main.py:~4595), así que un usuario beta ve qué tracks son FLAC y sus UUID. Contradice el propio comentario del código (4098-4100). FIX mínimo: al inicio de comunidad_audio añadir 'email,err = await _require_comunidad(request); if err: return err'. ~15 min.

2. BORRADO DE CUENTA INEXISTENTE pero PROMETIDO. privacidad.html:78 promete eliminación en 30 días tras baja, supresión (104) y portabilidad (107). En backend NO existe endpoint de borrado de cuenta (solo DELETE /api/perfil/foto borra el avatar). Además comunidad_posts y comunidad_comentarios referencian usuarios(id) SIN ON DELETE CASCADE (verificado en migraciones c7d2e9f4a1b6:29 y d8e1a4c7f2b9:28): ni a mano se podría borrar el usuario sin romper integridad. Incumplimiento legal vivo (GDPR art.17/LQPD), ya existe hoy. Para abrir a más gente: al menos proceso manual documentado + función repo.delete_user_account con soft-delete en cascada (o migración que añada CASCADE).


## 💶 Bloqueantes para COBRAR (Stripe/founder)

1. NO HAY STRIPE, NADA. Verificado: la única mención a 'stripe' en backend/ es un comentario en la migración a2c6e9b4d7f3:21. No hay SDK en requirements, ni POST /api/stripe/webhook, ni checkout, ni columnas stripe_customer_id/subscription_id/status, ni lógica que ponga pro=true al pagar. is_pro (repositories.py:1895) es un simple SELECT del booleano. Si metes un payment link hoy, el usuario paga y NUNCA recibe Pro. Bloqueante absoluto: construir webhook + columnas + checkout + repo.set_pro antes de cobrar.

2. GATING DE FLAC SOLO EN SUBIDA, NO EN DESCARGA. El split Pro/Gratis está bien en la subida (comunidad_compartir, main.py:4467 FLAC si user_pro, 4486 MP3 si no), pero como el endpoint de audio (4642) no valida Pro ni autoría, un usuario GRATIS descarga el FLAC que un Pro pagó por subir. En cuanto cobres, regalas el diferenciador de pago. El fix del gating de audio debe incluir: si post['audio_mime']=='audio/flac' y el viewer no es Pro ni autor -> 403 o servir MP3. Es exactamente la 'regla de oro' (no regalar FLAC a gratis).

3. FLAG 'pro' NO DIFERENCIA CUOTA NI RECIPROCIDAD. main.py:4385 aplica máx 3 tracks a TODOS y 4390 exige reciprocidad a TODOS, sin mirar user_pro (cargado en 4379 pero no usado en los gates). docs/monetizacion.md vende a Pro 'más tracks / sin reciprocidad'. Hoy un Pro tiene las mismas trabas que un gratis. Fix: envolver el check de reciprocidad en 'if not user_pro' y subir el tope de activos para Pro. OJO regla de oro: no bajes lo del gratis (3 tracks, 1 sin reciprocidad), solo AÑADE techo Pro.

4. SIN ACTIVACIÓN/AUDITORÍA DE pro Y SIN MODELO FOUNDER. No existe set_pro/toggle_pro en repositories.py ni endpoint admin (verificado). Hoy se pone a mano con SQL en Railway: sin auditoría, propenso a typos, imposible de soportar en disputes. Y no hay columna que distinga 'founder lifetime' de 'renovable mensual', que el founder pricing (~3€ de por vida) necesita. Antes de cobrar: columna founder_lifetime + POST /api/admin/user/{email}/set-pro con tabla de auditoría.

5. SIN POLÍTICA NI MECÁNICA DE DOWNGRADE. Nada decide qué pasa con los FLAC al cancelar Pro: se quedan en el volumen, descargables. Decidir política (convertir a MP3 / congelar / mantener), implementarla en el webhook de cancelación y documentarla en terminos.html antes de cobrar.

6. TÉRMINOS DE SUSCRIPCIÓN INEXISTENTES. terminos.html y aviso-legal.html no mencionan precio, renovación automática, derecho de desistimiento (14 días obligatorio UE), cancelación, reembolsos, IVA ni founder pricing. Cobrar suscripción digital en UE/ES/LATAM sin esto es ilegal. Añadir sección 'Suscripción y pagos' antes de activar Stripe.

7. EDAD MÍNIMA NO VALIDADA. Las políticas dicen 14+ (terminos.html:44, privacidad.html:123) pero el registro no pide ni valida edad. Para onboarding de Stripe, al menos un checkbox 'confirmo tener 14+' en el registro. Barato pero requerido antes de cobrar.

8. RESEND EN PLAN FREE Y EMAIL ROTO. La encuesta de 661 usuarios ya satura la cuota diaria (100/día); las confirmaciones de pago no pueden caer en cola free. Además REPLY_TO de la encuesta (encuesta_email.py:12) y el fallback admin (main.py:2153 _ADMIN_EMAIL_CANONICO usado en 3491) apuntan a alex@producciononline.com, que Resend NO entrega. Verificar plan Resend, SPF/DKIM de mentotrack.com y unificar remitente/reply-to antes de cobrar.


## 🔜 Recomendado pronto

1. Endpoint de exportación GET /api/perfil/export (GDPR art.20, ya prometido en privacidad.html:107). Reutiliza el patrón de GET /api/perfil. 1-2h. Cierra la otra promesa legal junto al borrado.

2. Reporte de contenido POST /api/comunidad/posts/{id}/reportar + botón en la UI. Abrir a 'todos los logueados' sin botón de reportar deja a Alex sin forma de enterarse de abusos. Aviso-legal §5.5 ya habla de retirar contenido pero no de cómo se reporta.

3. Logging de rechazos en compartir: cuando _validar_audio_upload falla (main.py:4401-4403) no se loguea nada. Un print con email+razón+tamaño da visibilidad sin coste. También loguear fallos de transcode y el unlink fallido de avatares (4022-4023, hoy silencioso).

4. Endpoint de almacenamiento GET /api/admin/storage-status + tarea periódica con alerta al 85%. El chequeo de disco es reactivo por-upload (4420); sin visibilidad proactiva el volumen de 5GB se puede llenar sin avisar y romper la comunidad para todos.

5. Añadir p.activo a la query de reciprocidad (repositories.py:1875): hoy cuenta comentarios en posts de otros aunque estén desactivados. Impacto bajo, pero es 1 línea y limpia la lógica.


## 🗂️ Diferible

1. Cuota de almacenamiento POR usuario (Pro vs Gratis). Hoy solo se valida el disco global (4420). Con 3 tracks/usuario y 5GB no es urgente; decidir techo Pro antes de tener decenas de Pro subiendo FLAC. Decisión de producto.

2. Backups del volumen de Railway. Crítico para vender durabilidad de FLAC como Pro, pero mientras la beta sea gratis es solo riesgo reputacional. Activar Railway Backups + (futuro) replica a B2/S3 al monetizar.

3. Reconciliación disco<->DB y limpieza de huérfanos (avatares y audios). El flujo ya limpia el tmp si falla el INSERT; los huérfanos se acumulan lento. Script de mantenimiento manual basta por ahora.

4. Auditoría de borrados de comunidad (tabla de log para soft-deletes). Útil para soporte/disputes con pago, no para la beta.

5. Escapar HTML en el backend (_sanitize, main.py:539 no hace html.escape). El frontend oficial ya escapa con textContent en todos los puntos de inserción; el XSS solo aplicaría a un cliente no oficial. Defensa en profundidad, bajo riesgo.

6. Rate limit de comentarios por user_id global (hoy 20/h por IP, main.py:4837) y verificar X-Forwarded-For en Railway. Suficiente para beta privada; revisar al escalar a >100 usuarios.

7. Reputación inflable con multicuentas (cosmético, no se usa en ningún gate hoy). Endurecer solo si en el futuro la reputación abre features.

8. IVA en términos: subcaso del bloque de términos de suscripción; Stripe Tax lo gestiona pero el texto debe mencionarlo cuando se monte el cobro.


---

## Detalle de hallazgos confirmados


### [CRITICA · BLOQUEA-COBRO] Flag 'pro' en DB se activa solo a mano — sin webhook Stripe ni automatización de pagos

**Por qué:** El flag `pro` en usuarios (agregado en commit 40e9241 del 2026-06-14, migración a2c6e9b4d7f3) determina si los tracks se transcodifican a FLAC sin pérdida (Pro) o MP3 320 (gratis) en el muro de comunidad. Hoy se activa SOLO a mano en la DB; el comentario de migración dice explícitamente "De momento se activa a mano (DB); cuando haya pagos, lo pondrá el webhook de Stripe". Sin embargo: (1) No existe integración Stripe en `requirements.txt`; (2) No hay endpoint POST /api/stripe/webhook; (3) No existen eventos escuchados (customer.subscription.updated, customer.subscription.deleted); (4) No hay columnas `stripe_customer_id` ni `stripe_subscription_id` para vincular usuarios a Stripe; (5) No existe lógica que actualice el flag pro en respuesta a pagos. Resultado: es imposible automatizar cobros o cambios de Pro↔Gratis. Si hoy metes Stripe sin webhooks, los usuarios pagan pero nunca reciben FLAC, y el descuento al cancelar no se aplica.


**Fix:** 1) Instalar Stripe SDK: `pip install stripe` en backend/requirements.txt. 2) Crear migración Alembic para agregar columnas a `usuarios`: `stripe_customer_id VARCHAR(255)`, `stripe_subscription_id VARCHAR(255)`, `stripe_subscription_status VARCHAR(50)`. 3) Crear POST /api/stripe/webhook en backend/main.py que: (a) valide firma del evento con `stripe.Webhook.construct_event()`, (b) escuche `customer.subscription.updated` (cuando se paga, es_pro=TRUE; cuando falla/cancela, es_pro=FALSE) y `customer.subscription.deleted`, (c) UPDATE usuarios SET pro=$1, stripe_subscription_status=$2 WHERE stripe_customer_id=$3. 4) En POST /api/stripe/checkout (nuevo endpoint), generar una sesión Stripe Checkout que setee metadata['usuario_id'] para vincular la suscripción al usuario. 5) Actualizar términos.html/privacidad.html para mencionar pagos, Stripe, cómo funciona Pro. 6) Validar que downgrade Pro→Gratis: (a) actualiza correctamente la BD, (b) no sirve un FLAC ya compartido si el usuario pierde Pro después (opcional: es_lossless=False al buscar posts).


### [CRITICA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Audio endpoint de comunidad sin autenticacion — FLAC/Pro tier completamente bypasseado

**Por qué:** El endpoint GET /api/comunidad/audio/{post_id} (líneas 4640-4709 en backend/main.py) sirve audio sin validar si el usuario está logueado, sin validar acceso a comunidad, y sin validar si el usuario es Pro. Esto crea dos vulnerabilidades críticas: (1) FLAC sin pérdida subido por Pro users está expuesto a cualquiera sin pagar; (2) La monetización Pro tier (línea 4379: user_pro = await repo.is_pro()) controla la transcodificación en /api/comunidad/compartir (líneas 4466-4504: si user_pro=True + lossless → FLAC sin pérdida; si False → MP3 320), pero el audio endpoint NO verifica si el usuario solicitante debería tener acceso al FLAC. Solo valida que el post_id existe, después sirve el archivo tal cual. Un usuario gratis puede obtener el post_id (via GET /api/comunidad/posts), ver que audio_mime=audio/flac (línea 4594), y descargar el FLAC completo sin ser Pro. Peor: ni siquiera necesita sesión — el endpoint no requiere autenticación.


**Fix:** URGENTE (antes de cualquier pago): (1) Añadir validación en GET /api/comunidad/audio/{post_id}: requiere sesión (email = _require_auth_user); valida que el usuario está habilitado en comunidad (_require_comunidad); si audio_mime==audio/flac, valida que post.usuario_id == email OR viewer is_pro. (2) Alternativa menos restrictiva si queréis permitir escucha a gratis: cambiar línea 4594 (lista de posts): no exponer 'lossless' flag en JSON si el viewer no es Pro y el post es de otro usuario. El frontend entonces no pide la descarga/stream del FLAC. (3) En /api/comunidad/compartir (transcoding logic): validar que `is_pro` es consistente antes de escribir, para evitar que bugs dejen FLAC en el volumen sin justificación. (4) Logging: cada request a audio con FLAC y usuario sin Pro → log de security violation para audit.


### [CRITICA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Falta endpoint de borrado de cuenta (violación GDPR Art. 17 + CCPA/LQPD)

**Por qué:** El código legal en privacidad.html (línea 78) y terminos.html (línea 83) promete borrado de cuenta en 30 días tras solicitud ("Si solicitas la baja, se eliminan en un plazo máximo de 30 días"). Sin embargo, NO existe endpoint técnico para ejecutarlo — solo DELETE /api/perfil/foto existe (borra avatar, no cuenta). El usuario debe escribir a email manualmente. Esto viola GDPR Art. 17 (derecho al olvido) para usuarios EU, CCPA para usuarios California, y LQPD para España. La política declara conformidad con GDPR (privacidad.html línea 29) pero no implementa mecanismo para cumplir. Bloquea cobro porque Stripe, VISA y Mastercard exigen "documented data deletion procedures" y auditoría de cumplimiento. Con la comunidad activa, el riesgo aumenta (posts, comentarios, perfil público también asociados al usuario y sin soft-delete). Sin cumplimiento documentado, eres vulnerable a multas de hasta 20M€ en EU.


**Fix:** Antes de abrir a cobro (incluso founder pricing): 1. Implementar DELETE /api/perfil/account (endpoint autenticado, 30-day grace period antes de hard-delete o soft-delete con TTL). 2. Borrar en cascada: user → password_hash (crypto shred), email (sustituir por fake "deleted_1234567890@mentotrack.local"), username (liberar para reutilización si user solicita), foto (borrar archivo de /avatars/), perfil público, posts de comunidad (borrar audio de /comunidad/ y soft-delete post), comentarios (soft-delete), diagnósticos antiguos (opcional: guardar count anonimizado "1 user, 42 analyses"), suscripción Stripe (marcar como deleted en Stripe). 3. Documentar procedimiento en privacidad.html: "Self-service deletion: usuario puede solicitar borrado en /perfil/account → 30 días de grace (puede revertir). Pasados 30 días, eliminación permanente. O: derecho de supresión ejercible en soporte@producciononline.com → cumplimiento en 7 días laborales". 4. Agregar soft-delete a `usuarios` (deleted_at TIMESTAMP) + índice. 5. Auditoría: guardar en table `data_deletion_log` (usuario_id, email, timestamp, IP, status) para demostrarlo a reguladores. 6. Test: verificar que DELETE /api/perfil/account borra TODAS las filas (usuario, posts, comentarios, diagnósticos, foto). 7. Antes de Stripe: documentar esto en DPA/Privacy Impact Assessment y entregar a Stripe en onboarding.


### [CRITICA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Sin implementación de borrado de cuenta = incumplimiento GDPR y contradicción legal

**Por qué:** La privacidad.html promete borrado en 30 días (GDPR derecho al olvido), los términos permiten solicitar baja escribiendo a soporte, pero el backend NO tiene: (1) endpoint DELETE /api/auth/account ni equivalente, (2) lógica de borrado en cascada en comunidad_posts ni comunidad_comentarios (ambas tienen REFERENCES usuarios(id) SIN ON DELETE CASCADE), (3) limpieza de perfil público (usuarios_perfil). Si un usuario solicita baja, no hay forma de ejecutarla sin romper integridad referencial. Además: incumple GDPR Arts. 17 (right to erasure) y 5 (data minimization). Si pagas con Stripe/procesador de pagos, ellos exigen que cumplas con derechos de datos de usuarios — auditoría fallará.


**Fix:** 1. Crear migration Alembic que agregue ON DELETE CASCADE a comunidad_posts.usuario_id y comunidad_comentarios.usuario_id (permite borrar cascada). 2. Crear función repo.delete_user_account(pool, usuario_id) que: (a) soft-delete usuario (marcar account_deleted=True o similar), (b) soft-delete todos los posts (activo=FALSE), (c) soft-delete todos los comentarios, (d) borrar perfil_* fields, (e) anonimizar tracks en histórico si procede. 3. Crear endpoint POST /api/auth/delete-account con email confirmation o password check. 4. Documentar en LEGAL: cuando usuario borra cuenta, tracks y comentarios se retiran en 24h; profile se anonimiza. NO dice \"borramos todo\", dice \"anonimizamos\" (porque otros pueden haberlo comentado — para GDPR e integridad). 5. Implementar task Celery/background que ejecute borrado 30 días después de solicitud (cooling-off).


### [CRITICA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Acceso a audio sin verificar gating de comunidad (CRÍTICO)

**Por qué:** El endpoint GET /api/comunidad/audio/{post_id} (línea 4642-4709 en backend/main.py) NO valida gating de comunidad. No llama a _require_comunidad() ni _comunidad_habilitada(). Comparado con otros endpoints (comunidad_posts línea 4562, comunidad_perfil_publico línea 4616, comunidad_listar_comentarios línea 4808) que SÍ validan, este está expuesto. Un usuario sin acceso a la comunidad (beta privada) puede descargar audios si tiene el post_id (que se expone públicamente en /api/comunidad/posts cuando SÍ hay gating). Crítico para monetización: FLAC Pro se descarga sin verificar if el downloader tiene suscripción. Cuando la comunidad está abierta a \"*\" (todos logueados), se agrava aún más la fuga de contenido Pro."


**Fix:** Añadir validación de gating al inicio de comunidad_audio() antes de servir el archivo. Opción A (permisivo): usar _optional_auth_user() + _comunidad_habilitada() y devolver 403 si no pasa. Opción B (estricto, recomendado): usar _require_comunidad() como hacen otros endpoints que modifican datos. Código: agregar estas líneas después de la docstring (línea 4644): email = _optional_auth_user(request); if not await _comunidad_habilitada(email): return JSONResponse(status_code=403, content={\"error\": \"La comunidad está en pruebas privadas todavía.\", \"codigo\": \"comunidad_oculta\"}). Ubicación: /Users/alexgonzalez/Documents/Claude/Projects/Herramientas IA producción musical/trackdiag/backend/main.py, función comunidad_audio, línea 4642-4644.


### [CRITICA · BLOQUEA-COBRO] Sin backups de volumen (RAILWAY_VOLUME_MOUNT_PATH) para FLAC/avatares de comunidad

**Por qué:** El volumen persistente de Railway (/data) es el ÚNICO destino de TODOS los archivos de audio FLAC (Pro tier) y avatares. El código (backend/main.py líneas 4184-4198, 4467-4485) no implementa backup, snapshot, replicación ni export alguno. La monetización planificada (docs/monetizacion.md §6) vende Pro a ~5€/mes EXPLÍCITAMENTE con FLAC lossless como diferenciador. Railway Hobby plan (la que aparentemente usa) NO tiene backups automáticos; Pro plan ($5/mo) los ofrece pero requieren activación manual no documentada. Una vez que usuarios PAGUEN por Pro, perder sus archivos FLAC por fallo de hardware/datacenter en Railway es breach de SLA implícito y genera obligación de reembolso. En beta (gratis), el riesgo es reputacional; en cobro, es legal + operativo. Cita específica: repo.is_pro() (repositories.py:1895) filtra quién sube FLAC, luego _transcodificar_flac() (main.py:4277) lo guarda en destino = _audio_comunidad_dir() = /data/comunidad sin redundancia alguna.


**Fix:** URGENTE ANTES DE MONETIZAR: (1) Activar Railway Backups en el plan ($5/mo adicional es insignificante vs riesgo); (2) Testear restore end-to-end (no asumir que "funciona"); (3) Implementar export diario asincrónico: script que lista posts activos, exporta audio_file + hash + timestamp a JSON en Postgres (tabla nueva: backup_manifests); (4) Para máxima durabilidad (tier 2): replicar FLAC a S3/Backblaze B2 (~$0.10/GB/mes) vía cron semanal post-backup Railway; (5) Documentar SLA en legal (aviso-legal.html §5 comunidad): "Los archivos de comunidad se respaldan [daily/weekly], RTO ~24h, RPO ~[X] horas"; (6) Comunicar en roadmap Pro que durabilidad de FLAC es SLA garantizado. Implementación: función async en main.py que corra daily (similar a _task_monthly_reporte), lee DB, verifica existencia de archivo en volumen, loguea discrepancias a tabla backup_metadata para audits post-fallo.


### [CRITICA · BLOQUEA-COBRO] Sin auditoria de borrados en comunidad

**Por qué:** Soft delete without logging


**Fix:** Create audit log table


### [ALTA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Descarga sin gating: FLAC accesible sin validar Pro en /api/comunidad/audio

**Por qué:** El endpoint GET /api/comunidad/audio/{post_id} (líneas 4640-4709 en /backend/main.py) sirve archivos FLAC sin validar si el usuario que descarga es Pro. Aunque el gating de FLAC en la subida (comunidad_compartir, líneas 4466-4504) es correcto, la descarga NO tiene protección: (1) No requiere autenticación específica (solo estar logueado en comunidad, que es gratis); (2) No valida el estado Pro del usuario descargador; (3) Expone directamente el archivo con Content-Ranges RFC 7233 sin restricción. Cuando se integre Stripe, un usuario gratis podrá descargar el FLAC que un usuario Pro pagó para subir, rompiendo el modelo de monetización. Esto afecta directamente la regla de oro: 'no quitar lo ya gratis' — pero el FLAC debe estar gateado al acceso, no solo a la subida.


**Fix:** 1. Modificar /api/comunidad/audio/{post_id} para requerir autenticación y validar Pro: si el post es FLAC (audio_mime == 'audio/flac'), verificar que: (a) el usuario está autenticado (añadir _require_comunidad), (b) es Pro (await repo.is_pro), o (c) es el autor del post (comparar usuario_id con post['usuario_id']). Si no cumple, devolver 403 Forbidden. 2. Opcionalmente, convertir archivos FLAC a MP3 on-the-fly al descargar si el usuario es gratis (más costoso pero mejor UX). 3. Actualizar aviso-legal.html y terminos.html para aclarar explícitamente que: 'Los archivos compartidos en formato FLACS solo pueden ser descargados por usuarios Pro o por el autor del track' y 'Si pasas de Pro a gratis, tus tracks existentes se mantienen; sin embargo, solo Pro puede descargarlos en FLAC'.


### [ALTA · BLOQUEA-COBRO] Track quota hard-coded to 3 para todos — no diferenciación Pro vs Gratis

**Por qué:** El código en /backend/main.py líneas 4385-4388 aplica un límite duro de 3 tracks activos para TODOS los usuarios, sin consultar el flag `pro` que ya existe en la BD (migration a2c6e9b4d7f3). El modelo de monetización (docs/monetizacion.md línea 62) promete a Pro: "3+ tracks a la vez sin reciprocidad" vs Free con cuota menor. Con Stripe, un usuario Pro pagando ~5€/mes tendrá el MISMO límite que un gratis, rompiendo la propuesta de valor y matando la conversión. Además, tampoco se saltea la reciprocidad para Pro (líneas 4390-4398 aplican igual a todos).


**Fix:** 1) Refactorizar línea 4385: cambiar `if recip["activos"] >= 3:` por `max_tracks = 10 if user_pro else 3; if recip["activos"] >= max_tracks:`. 2) Actualizar mensaje de error para reflejar el plan del usuario. 3) Saltarse el check de reciprocidad para Pro (líneas 4390-4398): envolver en `if not user_pro:`. 4) Documentar en términos públicos que "Pro desbloquea hasta 10 tracks simultáneos vs 3 en el plan gratis" (o los números que decidas). 5) Testear: crear usuario Pro y verificar que puede tener 10 activos; crear usuario gratis y verificar que máx 3.


### [ALTA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Reciprocidad y cuota de tracks no diferenciada por Pro — viola el modelo de monetización

**Por qué:** El código en /backend/main.py líneas 4385-4398 implementa las reglas de reciprocidad y cuota (máx 3 tracks) de forma incondicional para TODOS los usuarios, sin considerar el flag `pro`. El documento de monetización (docs/monetizacion.md línea 62) especifica que Pro debería tener '3+ tracks a la vez sin reciprocidad'. Actualmente: (1) Pro obtiene el flag en línea 4379 pero NO se usa para gates de reciprocidad. (2) Línea 4390: 'if recip[\"comentados\"] < recip[\"activos\"]' rechaza a TODOS incluído Pro. (3) Línea 4385: 'if recip[\"activos\"] >= 3' rechaza a TODOS sin importar si son Pro. Cuando se lance Stripe y usuarios paguen por Pro, descubrirán que el beneficio principal (saltarse reciprocidad, tener más tracks) NO funciona. Bloquea lanzamiento porque si Alex prueba Pro manualmente verá inconsistencia con la documentación. Bloquea cobro porque el modelo de negocio pierde sentido si Pro no diferencia reglas.


**Fix:** Modificar /backend/main.py líneas 4385-4398. Cambio: (1) Línea 4385: reemplazar 'if recip[\"activos\"] >= 3:' con 'max_tracks = None if user_pro else 3; if recip[\"activos\"] >= max_tracks:' (o decidir límite para Pro). (2) Línea 4390: reemplazar 'if recip[\"comentados\"] < recip[\"activos\"]:' con 'if not user_pro and recip[\"comentados\"] < recip[\"activos\"]:'. Esto permite que Pro (1) tenga ilimitados o más de 3 tracks, (2) no sea forzado a comentar en otros. Validar con usuarios Pro en DB (es_pro=true) que ahora pueden compartir sin trabas de reciprocidad.


### [ALTA · BLOQUEA-COBRO] No founder lifetime Pro tracking mechanism

**Por qué:** Database has only pro BOOLEAN flag with no lifetime vs renewable distinction needed for founder pricing model


**Fix:** Add founder_lifetime_pro column via alembic migration and update is_pro logic to check this flag


### [ALTA · BLOQUEA-COBRO] Sin política de retención de audio Pro/Gratis en caso de downgrade o cancelación

**Por qué:** El código implementa gating Pro/Gratis (Pro→FLAC, Gratis→MP3) en línea 4467-4504 de main.py. Sin embargo, NO hay manejo para cuando un usuario cancela su suscripción Pro: los FLACs quedan almacenados en el volumen (comunidad/), descargables sin degradación, incumpliendo el modelo de monetización acordado (Tier Pro = FLAC sin pérdida exclusivamente). No hay webhook de Stripe (confirmado en alembic migration a2c6e9b4d7f3, línea 21: 'cuando haya pagos, lo pondrá el webhook'), no hay job de conversión FLAC→MP3, ni política legal declarada en privacidad.html, aviso-legal.html o terminos.html. Un usuario Pro puede subir 3 FLACs, cancelar Pro 15 días después (en período de prueba), y sus archivos sin pérdida permanecerían descargables indefinidamente, rompiendo el contrato implícito de la monetización y creando riesgo de disputa legal al cobrar a nuevos usuarios.


**Fix:** ANTES de integrar Stripe: (1) Decidir política de retención: A) Auto-conversión FLAC→MP3 en webhook de cancelación (job async, ~15 min de demora para no saturar), B) Borrado automático de FLACs al cancelar (requiere confirmación en email), o C) Congelación de descarga (FLAC se mantiene pero no se sirve, solo metadatos). (2) Implementar webhook POST /api/stripe/webhook que maneje customer.subscription.deleted, actualice pro=False y lance tarea de conversión/borrado según política. (3) Agregar campo `audio_format_uploaded_as` en comunidad_posts (FLAC, MP3, WAV, etc.) para auditoría. (4) Documentar en privacidad.html (§3 Plazo de conservación) y terminos.html (nueva §6 sobre tiers) la política elegida, ej: 'Si cancelas Pro, tus tracks en FLAC se convierten automáticamente a MP3 320kbps en las siguientes 24h — conservas autoría, el cambio solo afecta a calidad de audio'. (5) Crear endpoint DELETE /api/comunidad/posts/{id}/downgrade (soft-delete) reutilizable por webhook. Esfuerzo: 4-6 horas (incluido testing y docs legales). Criticidad: BLOQUEANTE para Stripe porque sin definición clara de qué sucede con los datos Pro al downgrade, incumples el acuerdo de Tier y expones a reclamaciones.


### [ALTA · BLOQUEA-COBRO] Audio FLAC sin gating — cualquiera con el post_id puede descargar sin ser Pro

**Por qué:** El endpoint GET /api/comunidad/audio/{post_id} (líneas 4640-4709) no requiere autenticación ni valida si el viewer es Pro. Sirve el archivo (MP3 o FLAC según lo guardó el uploader) a cualquiera que tenga el UUID del post. Los post_id son UUIDs públicos, visibles en /api/comunidad/posts (línea 4578). El backend guarda FLAC si user_pro=True (línea 4468-4485) y MP3 si es gratis (línea 4486-4500). Sin gating en el download, un usuario Gratis puede descargar el FLAC de un Pro simplemente conociendo (o enumerando desde el muro) el post_id. Esto viola directamente el modelo de monetización Pro=FLAC+pago porque regala FLAC a gratis sin que el Pro pueda evitarlo. En el lanzamiento beta cerrado (todos logueados = aliados) es asumible; en monetización, es fatal."


**Fix:** OPCIÓN 1 (recomendada): Gating por tier. En comunidad_audio (línea 4642), después de validar que el post existe, chequear si es_lossless (audio_mime=='audio/flac'): si es verdad y el viewer no es Pro, servir 403 'solo Pro descarga FLAC' o redirigir a versión MP3. Añadir: `email = _optional_auth_user(request); user_pro = False; if email: user_pro = await repo.is_pro(pool, email); if post.get('audio_mime')=='audio/flac' and not user_pro: return JSONResponse(status_code=403, content={'error':'FLAC solo para Pro'})`. OPCIÓN 2 (menos segura pero más UX): Servidor siempre MP3 a gratis en el player (content-type negotiation), FLAC solo si is_pro. OPCIÓN 3 (hybrid): Permitir streaming de FLAC a gratis (para escuchar), bloquear range-request para download: `if post['audio_mime']=='audio/flac' and not user_pro and 'range' in request.headers: return 403`. Recomendación: Opción 1 es más clara y defensible legalmente (Pro paga por acceso a FLAC, punto). Implementar antes de Stripe.


### [ALTA · BLOQUEA-COBRO] Email config broken

**Por qué:** X


**Fix:** soporte email advertised in docs but not monitored. Setup SUPPORT_EMAIL env var and monitoring before Stripe</anfix>
</parameter>
</invoke>


### [ALTA · BLOQUEA-COBRO] Sin validación de edad mínima en registro (menores de 14 años, GDPR/COPPA incumplimiento)

**Por qué:** Cualquiera puede registrarse sin indicar edad. Las políticas (privacidad.html:123, terminos.html:44) dicen 14+ con consentimiento parental <14. El código no valida nada (backend/main.py:1380-1429 solo chequea email/username/password). Sin validación real, Stripe rechazará la integración de pagos por incumplimiento GDPR (art. 8: menores de 16 en EU requieren consentimiento parental). Además, potencial COPPA risk si hay usuarios <13 en US. La base es 661 usuarios, mayormente ES+LATAM adultos, pero sin validación es responsabilidad del founder. Diferible solo si esperas a montar Stripe.


**Fix:** Opción 1 (rápida, cobro seguro): cambiar políticas a 14 años Y agregar checkbox de confirmación "Confirmo tener 14+ años" en registro (frontend/index.html:3950). Opción 2 (robusta, largo plazo): agregar columna birth_date a usuarios (nueva migración alembic), validar en auth_register si age<14 y si es EU/US requerir consentimiento parental explícito. Opción 3 (conservadora): subir edad mínima a 18 en políticas, sin cambio técnico. CRÍTICO: resolver ANTES de montar Stripe en /api/stripe/.


### [ALTA · BLOQUEA-COBRO] Sin endpoint de exportación GDPR (art. 20: portabilidad de datos)

**Por qué:** La política de privacidad (privacidad.html línea 107) promete explícitamente "Portabilidad: recibir tus datos en formato estructurado y reutilizable", conforme a GDPR art. 20. Sin embargo, no existe endpoint GET /api/perfil/export o similar en el backend (main.py). El único mecanismo es escribir a soporte@producciononline.com (línea 111 de privacidad.html y términos.html), pero no hay formulario, sistema de tickets, ni flujo de respuesta. Hoy (sin Stripe) es diferible porque hay pocos usuarios. Con Stripe activo (cobro), la exposición legal es critica: GDPR exige responder en plazo máximo 1 mes (art. 12). Incumplimiento = multa de 10-20M€ o 2-4% de facturación anual.


**Fix:** Crear GET /api/perfil/export que devuelva JSON estructurado con: (1) Datos de cuenta (email, username, fecha_registro, flag pro), (2) Lista de diagnósticos (id, fecha, análisis, contexto), (3) Perfil de comunidad (experiencia, estilos, bio, foto_url), (4) Posts de comunidad (id, título, descripción, fecha, estado), (5) Comentarios (id, post_id, texto, fecha), (6) URLs de avatar y archivos. Implementar en backend/main.py como endpoint autenticado (similar a GET /api/perfil existente). Tiempo estimado: 1-2 horas. Opcional: permitir formato CSV o ZIP descargable. Integrar en política de privacidad: "Puedes descargar tus datos estructurados en /api/perfil/export o enviar solicitud a soporte@producciononline.com".


### [ALTA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Audio de tracks sin protección: anónimos pueden descargar si tienen el post_id

**Por qué:** El endpoint GET /api/comunidad/audio/{post_id} (línea 4640-4709 en backend/main.py) NO valida si el usuario está habilitado en la comunidad. El comentario de código (línea 4098) describe los tracks como 'bocetos privados sin terminar' solo para miembros logueados, pero el endpoint de audio es accesible a CUALQUIERA que tenga un post_id válido — incluyendo anónimos. Los IDs se exponen en /api/comunidad/posts (gateado), pero: (1) en beta abierta, usuarios habilitados ven IDs y pueden compartirlos; (2) social engineering o crawlers pueden obtenerlos. Esto viola directamente el modelo Beta (acceso restringido) y compromete monetización futura (Pro = FLAC sin acceso anónimo).


**Fix:** Añadir validación de _comunidad_habilitada() al inicio de comunidad_audio(), como en comunidad_listar_comentarios (línea 4808). Cambiar: if not await _comunidad_habilitada(_optional_auth_user(request)): return JSONResponse(status_code=403, content={...}) inmediatamente después de @app.get y @limiter, antes de cualquier otra lógica. Considerar 404 vs 403 para no revelar existencia de tracks a no-habilitados (usar 404 genérico para consistencia).


### [ALTA · BLOQUEA-LANZAMIENTO, BLOQUEA-COBRO] Cuota sin limites

**Por qué:** Sin control</anzonzon>
</invoke>



**Fix:** Implementar


### [ALTA · BLOQUEA-COBRO] Sin dashboard de monitorización de almacenamiento (disk space) para admin

**Por qué:** El backend (línea 4414-4422 en main.py) chequea espacio en cada upload y rechaza si queda poco (<250MB). Esto PREVIENE que se rompa la comunidad (el error es 503 claro para el usuario). PERO no existe endpoint admin para que Alex vea: total/usado/libre del volumen, trend, usuarios top consumidores, o alertas automáticas. El chequeo es REACTIVO (por upload). Para un producto de pago (Stripe), el admin necesita visibilidad PROACTIVA de la capacidad. Hoy: si el volumen de Railway (~5GB) se llena sin que Alex lo sepa, la comunidad entera se rompe. Con pagos activos, eso es un incident crítico de servicio. Diferible para este lanzamiento (la mitigación local lo evita), bloqueante para cobro.


**Fix:** 1. Crear endpoint GET /api/admin/storage-status (requiere cookie admin) que retorna JSON: { volumen: { total_bytes, used_bytes, free_bytes, pct_full }, audios: { count, total_bytes, avg_size, by_user_top10 }, avatars: { count, total_bytes }, last_checked_timestamp }. 2. Tarea cron asyncio.create_task() similar a _task_monthly_reporte() (línea 98) que cada 4 horas recalcula y cachea en variable global o DB. 3. En el endpoint, alertar si pct_full > 85% (email a ADMIN_EMAIL vía Resend). 4. Si > 95%, adicionar chequeo en compartir (línea 4420) que rechace uploads con mensaje: 'El almacenamiento de la comunidad está muy próximo al límite. Contacta a soporte.' (no genérico '503'). 5. Opcional: tab 'Almacenamiento' en dashboard.html con gráfico de trend (usado hace 7d vs hoy).


### [ALTA · BLOQUEA-COBRO] Resend está en plan Free (100 emails/día); encuesta masiva de 600+ emails ya consumió la cuota; avisos sin throttle escalan indefinidamente

**Por qué:** REALIDAD DEL CÓDIGO: (1) Encuesta masiva ya fue enviada el 2026-06-12 a 661 usuarios (línea 3567, _ENVIO_ENCUESTA_UTC). El código muestra asyncio.sleep(0.6) entre emails (línea 3598), que throttlea a ~1.67 req/s = 600 emails en ~360 segundos. (2) No hay referencia en el código de plan de pago de Resend: RESEND_API_KEY se obtiene de env sin validar nivel de servicio. (3) Avisos de comentario (_notificar_comentario, línea 4136) no tienen throttle: cada nuevo comentario envía 1 email inmediatamente sin asyncio.sleep ni rate limit — con 600 usuarios compartiendo tracks, 5 comentarios/día es conservador = 5 emails/día ya. (4) Si eso escala a 2000 usuarios y 10 comentarios/día activos = 20 emails/día, aún bajo. Pero la encuesta de 600 en 1 hora ya saturó Free. (5) Reporte mensual (línea 3554) envía 1 email. (6) El modelo de monetización (docs/monetizacion.md, §5) prevé newsletter y reportes mensuales recurrentes: eso multiplitica a 661 usuarios x 12 meses = 7932 emails/año de solo reportes si se abre. CRÍTICO para COBRO: no hay infraestructura de colas de email (Redis, Celery, Bull). Envíos síncronos a Resend. Cuando se metan pagos (Stripe), un usuario Pro podrá recibir: confirmación de pago (Stripe webhook), reporte mensual, avisos de comentario, newsletter. Fácilmente 3-4 emails/mes por usuario. 600 usuarios x 4 = 2400 emails/mes = 80 emails/día. Plan Free muere. Sin migración de plan, los pagos fallarán silenciosamente (emails perdidos = experiencia rota).


**Fix:** INMEDIATO (antes de cobro): (1) Confirmar plan de Resend con invoice/dashboard. Si es Free, upgrade a plan de pago ($20-30/mes da 50k-100k emails/mes = 1700-3300/día, suficiente para 5 años de crecimiento proyectado). (2) Documentar en env: RESEND_PLAN (free|pro|enterprise) y alertar en logs si plan < emails_proyectados_mes. (3) Implementar cola de email: Redis/Celery simple o job queue en DB (tabla email_queue, worker que procesa cada 1 min). Prioridad: transaccionales (pagos, reset) > avisos > marketing (newsletter, reportes). (4) Envío masivo (encuesta): meter en queue, no sincrónico. Parámetro RESEND_BATCH_SIZE (default 100, enviable en 1 min). (5) Avisos de comentario: agregación diaria (digest, 1 email/usuario/día con 10 comentarios en vez de 10 emails). Reducción 10x. (6) Rate limit en BD con tabla: email_sent_quota (email, day, count), bloquea si count >= RESEND_DAILY_LIMIT. (7) Test: simular 2000 usuarios, 5 comentarios/día cada uno = 10k comentarios/día = 10k avisos potenciales. Verificar que queue + digest reducen a 2000 (1 por usuario). (8) Documentar en CLAUDE.md o settings.json: "Email service: Resend [PLAN]. Daily capacity: X emails. Saturation at Y users. Currently at Z% utilization."


### [MEDIA · BLOQUEA-COBRO] Audio sin cuota de almacenamiento por usuario (Pro vs. Gratis)

**Por qué:** El código actual en /Users/alexgonzalez/Documents/Claude/Projects/Herramientas IA producción musical/trackdiag/backend/main.py (línea 4420) validaespacio libre GLOBAL del volumen (shutil.disk_usage(destino).free) pero NO tiene mecanismo de cuota POR USUARIO. El modelo de monetización (docs/monetizacion.md) NO especifica diferencia de almacenamiento entre Free y Pro, pero cuando se implemente Stripe y se empiece a cobrar, faltarán decisiones críticas: (A) ¿Hay límite de almacenamiento diferente por tier? (B) ¿Pro=ilimitado o Pro=500MB? (C) ¿Gratis=150MB o 0?. Hoy con 150 MB máximo por ARCHIVO y reciprocidad limitando a 3 tracks ACTIVOS, un usuario Free podría en teoría almacenar hasta 450 MB y un Pro también (si sube 3 FLAC de 50MB cada uno). Sin cuota individual y con la estrategia del documento que menciona 'Pro=3+ tracks sin reciprocidad' sin techo de almacenamiento, el volumen de 5GB podría llenarse rápidamente si un puñado de usuarios Pro empiezan a subir decenas de FLAC. Crítico si esperas 100+ usuarios activos pagando.


**Fix:** DIFERIBLE pero REQUIERE DECISIÓN ANTES DE COBRAR: (1) Decidir modelo: ¿Gratis tiene límite total (ej: 150MB = máx 1 track de 150MB ó 3×50MB) y Pro ilimitado? ¿O ambos tienen límite pero diferente (Free=150MB, Pro=500MB)? (2) Implementar tabla user_storage_quota (usuario_id, limit_mb, used_mb) o una vista que SUME audio_bytes por usuario. (3) En endpoint POST /api/comunidad/compartir (línea 4420), añadir ANTES del check global un check local: SELECT SUM(audio_bytes) FROM comunidad_posts WHERE usuario_id=$1 AND activo; si (usado + nuevo_audio_bytes > cuota) → rechazar. (4) En GET /api/comunidad/habilitada o en un endpoint de perfil, devolver remaining_storage al frontend para que el usuario sepa cuánto le queda. (5) Linea 4420 cambiar a: if (usuario_bytes_usados + new_audio_bytes > user_quota) OR (libre < 250MB) → rechazar ambos checks. Encaja en el patrón de flags/allowlist que ya existe (el campo pro está en usuarios). Esfuerzo: bajo-medio (1 tabla + 3 queries + 1 validación).


### [MEDIA · BLOQUEA-COBRO] Sin endpoint admin para cambiar flag pro — depende de SQL directo en Railway

**Por qué:** Es REAL y aplicable. El código confirma: (1) La migración a2c6e9b4d7f3 añade columna `pro BOOLEAN DEFAULT FALSE` a usuarios (backend/alembic/versions/a2c6e9b4d7f3_usuario_pro_flag.py). (2) No existe ningún endpoint, CLI tool, ni función en repositories.py para modificar el flag pro (grep de 'UPDATE usuarios SET pro', 'def set_pro', 'def toggle_pro' devuelven vacío). (3) El endpoint comunidad/compartir (main.py:4335) usa `is_pro()` para decidir si transcodificar a FLAC (Pro) o MP3 (gratis). (4) Los admin endpoints (/api/admin/*) no incluyen gestión de usuarios/pro; solo embudo, consultoría, reanalisis, encuesta, etc. (5) Hoy pro=true se pone MANUALMENTE en BD Railway (como confirma la migración: 'De momento se activa a mano (DB); cuando haya pagos, lo pondrá el webhook de Stripe'). Es opera manual, sin auditoría, sin interfaz gráfica, propenso a errores de tipografía en email/uuid. Cuando lleguen 50+ usuarios Pro pagadores en Stripe y haya disputes ('usuario dice que pagó pero no ve FLAC'), no hay forma segura de troubleshoot ni auditar quién cambió qué."


**Fix:** BLOQUEANTE PARA COBRO: Crear POST /api/admin/user/{email}/set-pro y POST /api/admin/user/{email}/unset-pro (o PATCH con toggle: true/false) con auth segura (cookie admin o HMAC-signed header) que: (a) verifique que el usuario existe en BD; (b) actualice la columna pro; (c) registre auditoria (quién, cuándo, antes/después) en una tabla `pro_changes(usuario_id, changed_by, changed_at, was_pro, is_pro)`; (d) opcionalmente, envíe email de confirmación al usuario. Alternativa: mini dashboard admin que liste usuarios, muestre stripe_subscription_id (cuando lo añadas), y permita toggle pro con confirmación. Esencial cuando cobres en Stripe, porque el webhook automático no cubre todos los casos (reversiones de pago, pruebas, soporte manual)."


### [MEDIA · BLOQUEA-COBRO] Términos de suscripción incompletos (antes de Stripe/monetización)

**Por qué:** frontend/terminos.html y frontend/aviso-legal.html NO mencionan NADA sobre suscripción, renovación automática, derecho de desistimiento (obligatorio en EU), cancelación de suscripción, reembolsos, IVA/impuestos, o founder pricing. docs/monetizacion.md propone Mentotrack Pro (suscripción ~5€/mes, Fase 1) + validación inicial con \"Miembro Fundador\" (Fase 0, pago único Stripe). Stripe NO está integrado aún (backend/repositories.py::is_pro es solo flag manual en DB). La comunidad actual (v0.5.61) usa el flag pro solo para FLAC vs MP3, sin pagos reales. Cuando integren Stripe (próximas fases), serán requisitos legales obligatorios en EU y en la mayoría de jurisdicciones para cobrar suscripciones digitales: período de renovación, derecho de desistimiento, instrucciones de cancelación, y datos fiscales. Sin estos términos, cualquier pago será legalmente problemático (DGCR 2022 en EU, regulaciones de consumidor).


**Fix:** ANTES de integrar Stripe en Fase 0 o 1, actualizar frontend/terminos.html con una sección nueva \"6. Suscripción y pagos\" (o expandir la sección 8 \"Modificación de los Términos\") que incluya: (a) Descripción clara de planes (Free, Pro, Founder), precios finales, período de renovación (mensual/anual). (b) Derecho de desistimiento: 14 días para usuarios en EU (DGCR 2022 Art. 12.1). (c) Cancelación: cómo cancelar la suscripción (Stripe Customer Portal, email, etc.), cuándo toma efecto, y qué ocurre con datos/acceso. (d) Reembolsos: política según país/tipo de compra (ej: reembolso proporcionado si se cancela antes de renovación). (e) Tratamiento de IVA/impuestos: Stripe maneja automáticamente, pero mencionar que precio mostrado es final (IVA incluido según país). (f) Founder pricing: si hay descuento especial de por vida para cohorte beta, especificarlo (duración, no transferible, qué pasa si se cancela). (g) Renovación automática: aclarar que ocurre cada período, cómo se carga (método de pago), y notification previa. También actualizar frontend/privacidad.html para incluir datos de pago/Stripe como proveedor y encargado del tratamiento si aplica. Frontend/cookies.html no requiere cambios (Stripe no carga cookies, aunque es bueno mencionarlo si trata datos de cookies). Ejemplo de texto: 'Mentotrack Pro se renueva automáticamente cada mes/año. Tienes derecho a cancelar en cualquier momento desde tu cuenta (Configuración > Suscripción > Cancelar) o escribiendo a soporte@producciononline.com. Si resides en la UE, tienes 14 días para desistirte sin coste (cambio de opinión). Reembolsos proporcionales si cancelas después de 14 días pero antes de la próxima renovación.'"


### [MEDIA · BLOQUEA-COBRO] GDPR SAR endpoint missing

**Por qué:** No hay endpoint in-app para solicitudes de derechos GDPR


**Fix:** Add GDPR endpoints</anfix>



### [MEDIA] REPLY_TO de encuestas + fallback admin dirigido a email roto (alex@producciononline.com)

**Por qué:** Se encontraron TWO problemas relacionados con el email roto (alex@producciononline.com) que Resend no puede entregar: (1) backend/encuesta_email.py:12 hardcodea REPLY_TO = "alex@producciononline.com", por lo que si usuarios responden a la encuesta masiva vía email, sus respuestas van a un buzón que filtra Resend (información perdida para Alex, pero el usuario puede enviar sin error). (2) backend/main.py:3491 usa _ADMIN_EMAIL_CANONICO = "alex@producciononline.com" como fallback en el endpoint admin_enviar_reporte_email, por lo que si Alex llama a ese endpoint sin parámetro email, el reporte se intenta enviar a una dirección que filtra Resend (sin embargo, también existe línea 3553 donde el cron usa ADMIN_EMAIL env var con fallback correcto a alexgn23@gmail.com). No bloquea UX del usuario (encuesta se envía, reset funciona), pero causa pérdida de información interna para Alex. El cron ya está "arreglado" (usa gmail), pero el endpoint manual tiene inconsistencia.


**Fix:** 1. Cambiar backend/encuesta_email.py:12 de REPLY_TO = "alex@producciononline.com" a REPLY_TO = "hola@mentotrack.com" o alexgn23@gmail.com (hacer configurable vía env var ENCUESTA_REPLY_TO). 2. Cambiar backend/main.py:3491 de email_dest = data.get("email", _ADMIN_EMAIL_CANONICO) a email_dest = data.get("email") or os.environ.get("ADMIN_EMAIL", "alexgn23@gmail.com") para que sea consistente con el cron. 3. Testear que ambos flujos usen una dirección que SÍ recibe emails Resend (alexgn23@gmail.com o hola@mentotrack.com). 4. Documentar en README qué variables de env configuran los emails admin (ADMIN_NOTIFY_EMAIL, ADMIN_EMAIL, RESEND_FROM, ENCUESTA_REPLY_TO)."


### [MEDIA · BLOQUEA-COBRO] Founder pricing mencionado (documentación: ~3€-35€) pero no documentado en términos ni implementado en código

**Por qué:** El documento docs/monetizacion.md (líneas 91-99, 135, 182) propone lanzar "Miembro fundador" a ~35€ (único, "lifetime") y luego Pro a ~5€/mes. El código implementa: (a) flag `pro` en DB (migración a2c6e9b4d7f3, 14-06-2026), (b) lógica FLAC vs MP3 basada en `pro` en /api/comunidad/compartir (líneas 4379-4504 main.py), (c) badge PRO visual. PERO: (1) cero endpoints de pago/Stripe/webhook para activar `pro`; (2) cero funciones en repositories.py para actualizar `pro` vía API; (3) términos legales (terminos.html, aviso-legal.html) NO mencionan nada sobre tiers, founder, precio, Stripe, duración, ni qué es Pro exactamente; (4) sin página de pricing ni flow de compra en frontend. Actualmente, `pro` se activa solo manualmente en DB (UPDATE usuarios SET pro=true WHERE...). Si Alex cobra "founder pricing" sin términos actualizados y sin endpoint de compra real, es ilegal (falta de transparencia + violación de leyes de consumo en ES/LATAM).


**Fix:** Antes de lanzar pagos: (1) TÉRMINOS LEGALES: Añadir sección "5. Tiers y Pagos" en terminos.html y aviso-legal.html. Debe especificar: (a) Free: MP3 320, comentar, reputación, 1 track sin reciprocidad; (b) Pro (~5€/mes): FLAC lossless, perks de comunidad (destacar, badges, prioritario); (c) Founder (~35€, única compra, 1 año o lifetime si se especifica); (d) duración exacta de "lifetime" si aplica; (e) derecho a cancelación (14 días en EU). (2) BACKEND: Crear endpoint POST /api/pro/comprar-founder o /api/pagos/checkout que: (a) valida email y contexto; (b) redirige a Stripe payment link con sesión; (c) en webhook de Stripe (POST /api/pagos/webhook), valida firma y actualiza pro=true + metadata de fecha/tipo en usuarios. (3) FUNCIÓN UPDATE: Crear async def activate_pro(pool, email, tipo, fecha_expiracion) en repositories.py. (4) FRONTEND: Página /pro con pricing, comparativa, y botón "Comprar Founder" que postea a /api/pro/comprar-founder. (5) DOCUMENTACIÓN: Actualizar docs/monetizacion.md con "IMPLEMENTADO:" listando endpoint/webhook/términos. Nota: No bloquea LANZAMIENTO de comunidad (beta gratis, solo flag), pero SÍ bloquea COBRO.


### [MEDIA · BLOQUEA-COBRO] IVA/impuestos no mencionados en términos de servicio (será obligatorio con pagos Stripe)

**Por qué:** REAL pero DIFERIBLE. La comunidad está activa en beta sin dinero. El flag `pro` existe en BD (migración a2c6e9b4d7f3) y diferencia FLAC/MP3 en upload (main.py línea 4467), pero NO HAY Stripe implementado aún. Los términos (terminos.html v30-04-2026, aviso-legal.html v15-06-2026) no mencionan precios, suscripciones ni IVA. CUANDO integres Stripe (fase 1 del plan de monetización en docs/monetizacion.md), será OBLIGATORIO en EU (y aplica a tu base: ES, AR, CO, CL, etc.) mencionar que el precio puede cambiar según IVA local y emitir facturas. Stripe puede gestionar IVA automáticamente, pero los T&Cs deben reflejarlo. Hoy no es bloqueante porque no hay dinero; será bloqueante antes de cobrar.


**Fix:** 1. ANTES de integrar Stripe: actualizar `frontend/terminos.html` (nueva sección §sobre pagos o §8 modificado) con: \"Los precios mostrados corresponden a la tarifa base del servicio. En caso de suscripciones de pago, se calculará impuesto sobre ventas (IVA) según tu país de residencia en el momento de la compra, conforme a la legislación tributaria aplicable. Se emitirá factura.\" 2. Actualizar `frontend/aviso-legal.html` §6: añadir que el titular es responsable de cumplir normativa fiscal en jurisdicciones de los usuarios. 3. Configurar Stripe Tax o tabla manual de IVA por país en la integración. 4. En `docs/monetizacion.md` §8 (Requisitos técnicos), añadir: \"6. IVA / Stripe Tax: configurar tasas por país; términos deben mencionarlo.\"


### [MEDIA · BLOQUEA-COBRO] Sin política de moderación de contenido comunitario explícita

**Por qué:** La comunidad funciona hoy (v0.5.61 en beta) con moderación discrecional (Alex como único moderador, env COMUNIDAD_MODERADORES). El backend permite editar/borrar tracks y comentarios a moderadores (línea 4080-4090 main.py). Sin embargo: (1) Aviso legal §5.5 dice «se reserva el derecho de retirar» pero NO define qué viola términos (¿discurso de odio, spam, infringement?), cómo reportan usuarios, procedimiento, SLA o notificación. (2) No hay endpoint de reporte para usuarios ni UI para reportar contenido. (3) Términos de uso NO menciona la sección de comunidad (Términos §7 habla de suspensión de cuenta pero no de contenido). Cuando implementes Stripe + perks Pro (monetizacion.md línea 62: «feedback prioritario»), crearás expectativa de que la comunidad es moderada profesionalmente. Sin política explícita, los usuarios Pro tendrán fricción legal y de UX si intentan reportar o si se les retira contenido sin criterios claros. Diferible para beta, crítico antes de cobro.


**Fix:** 1. Documenta política de moderación en frontend/aviso-legal.html §5.5.1 (nuevo): (a) Qué viola (infringement, discurso de odio, spam, suplantación, contenido sexual/violento, estafas), (b) Cómo reporta usuario (nuevo endpoint POST /api/comunidad/posts/{id}/reportar con motivo + descripción, gateado a comunidad_habilitada, rate-limited), (c) Procedimiento: moderador revisa en 24-48h, retira y envía email al autor con motivo, autor puede apelar via soporte, (d) SLA: respuesta a reportes en 48h. 2. Añade UI en comunidad.html para botón "Reportar" en cada post (salvo el autor y moderadores). 3. Añade endpoint backend POST /api/comunidad/posts/{id}/reportar (main.py): crea registro en tabla comunidad_reportes (post_id, reporter_id, timestamp, motivo, descripcion), envía Slack/email a Alex. 4. Sincroniza Términos de uso: añade §5bis (comunidad) copiando §5 de aviso-legal.html. 5. En monetizacion.md línea 78, especifica que feedback prioritario NO implica moderación preferente (Pro recibe feedback antes, no que su contenido se proteja más). 6. (Antes de Stripe) crea dashboard admin sencillo (/api/admin/reportes) para que Alex vea reportes pendientes sin tocar DB.


### [MEDIA · BLOQUEA-COBRO] Archivos de audio potencialmente huérfanos sin reconciliación periódica disco-DB

**Por qué:** El patrón es real pero está parcialmente mitigado. El archivo se escribe al volumen ANTES del INSERT en DB (comunidad_compartir línea ~4450-4512), pero el try/except en línea 4549-4551 limpia el archivo si el INSERT falla. Sin embargo: (1) NO hay transacción explícita en crear_comunidad_post (línea 1620 usa pool.acquire() sin conn.transaction()), lo que en asyncpg autocommit es seguro para INSERTs simples pero frágil si hay crashes entre INSERT y return; (2) NO existe reconciliación periódica disco ↔ DB, así que si hay crash parcial o corrupción de datos, los huérfanos se acumulan silenciosamente; (3) Con Stripe activo, habrá muchas más transacciones, network timeouts y reintentos parciales que pueden dejar inconsistencias — el riesgo escala. Con 661 usuarios y mayormente MP3 320 (solo founder es Pro), el impacto HOY es bajo. Pero cuando hayas Pro generando FLAC de 150-200 MB, la deuda de limpieza se hace insostenible."


**Fix:** 1. Cambiar el orden en comunidad_compartir: (a) INSERT post EN DB PRIMERO con audio_file='' o nombre tmp; (b) luego mover/escribir el archivo al volumen con su nombre final; (c) UPDATE post SET audio_file = nombre_real. Así la DB es la fuente de verdad y los archivos siempre están referenciados. 2. Agregar conn.transaction() explícito en crear_comunidad_post para mayor robustez frente a retries y partial failures. 3. Crear un endpoint/script de mantenimiento (o task de Celery si llega el caso) que: (a) liste archivos en /data/comunidad/audio/ y /data/comunidad/avatars/; (b) compara con referencias en DB (comunidad_posts.audio_file, usuarios.perfil_foto); (c) reporta/limpia huérfanos. Ejecutarlo manualmente en deploy, o cada X horas si crece la base. 4. En desactivar_comunidad_post, loguear si falla el unlink del archivo (línea 4773) para detectar desincronizaciones. 5. Considerar un soft-delete + archivado: marcar archivos como "disposable" en DB, y GC los borra después de 30d, por si hay rollbacks pendientes."


### [MEDIA · BLOQUEA-COBRO] Email Resend: dominio noreply@mentotrack.com sin verificar + split de dominios (producciononline.com) → riesgo en notificaciones de pago

**Por qué:** El código usa "noreply@mentotrack.com" como remitente por defecto (línea 1002 main.py, línea 11 encuesta_email.py) para emails de reset, solicitudes, avisos de comentario y encuestas masivas (~661 usuarios). El dominio remitente mentotrack.com puede no estar verificado en Resend (SPF/DKIM/DMARC), lo que reduce deliverability. Adicionales: (a) reply-to apunta a alex@producciononline.com (línea 12 encuesta_email.py, línea 3421 main.py), creando split de dominios; (b) admin email default es alexgn23@gmail.com (línea 3553); (c) existe comentario explícito en línea 3603 reconociendo que "el buzón de producciononline filtra los Resend". Cuando Stripe se integre (webhook → confirmación de pago, facturación, cambios de plan), estos emails serán críticos. Si mentotrack.com no está verificado o los registros SPF/DKIM no están en Cloudflare DNS, confirmaciones de pago terminarán en spam o rechazadas, degradando UX Pro y causando disputes/chargebacks.


**Fix:** 1. Verificar en Resend dashboard (Domains → mentotrack.com) que SPF, DKIM, DMARC están "Verified". Si no, añadir records DNS sugeridos en Cloudflare. 2. Unificar reply-to: cambiar de "alex@producciononline.com" (encuesta_email.py línea 12) a "support@mentotrack.com" verificado. 3. Cambiar ADMIN_EMAIL default (línea 3553 main.py) de "alexgn23@gmail.com" a "admin@mentotrack.com". 4. Documentar env vars en Railway: RESEND_FROM="Mentotrack &lt;noreply@mentotrack.com&gt;", ADMIN_EMAIL="admin@mentotrack.com". 5. Test deliverability: triggear reporte y aviso de comentario, verificar inbox (no spam). 6. Si mantienes producciononline.com para contacto externo (UI), eso es válido, pero email de sistema debe salir de mentotrack.com verificado.


### [MEDIA · BLOQUEA-COBRO] Sin monitorización de abuso: uploads corruptos/malformados y lack of per-user rate limiting + logging

**Por qué:** Es REAL. Análisis del código muestra: (1) Rate limit es IP-based (`key_func=get_remote_address` línea 53), no por usuario autenticado — permite bypass si un usuario cambia IP o usa proxy, o bloquea múltiples usuarios legítimos detrás de NAT compartido. (2) Validaciones fallidas (línea 4401-4403: `_validar_audio_upload`) retornan error pero NUNCA registran nada — zero logging en [COMUNIDAD] si un archivo es rechazado por magic bytes/extensión/corrupción. (3) Cero tabla/endpoint de admin para auditoría de uploads: no existe `/api/admin/storage`, no hay stats de intentos fallidos por usuario, bytes/usuario, patrones de rechazo. (4) Para cobro: un Pro podría saturar la comunidad con uploads válidos usando ciclos upload/delete (10/hora = 240/día), y sin logs es imposible detectar o refutar abuse en una disputa/refund. La reciprocidad (máx 3 posts activos) limita visibilidad pero no consumo de recursos ni logging de intentos. El chequeo de espacio disco (línea 4420) evita crash total pero no previene exploración de storage sin coste.


**Fix:** Implementar ANTES de cualquier pago: (1) Rate limit PER-USER en compartir: agregar límite de 3 posts/día máximo per `user_id`, no solo por IP. Usar un token de sesión o user_id en vez de IP para slowapi, o agregar check manual: `SELECT COUNT(*) FROM comunidad_posts WHERE usuario_id = $1 AND timestamp > now() - '1 day'::interval` antes de insertar (línea ~4545). (2) Logging detallado de rechazos: cuando `errv` es no-None en línea 4402, hacer `print(f"[COMUNIDAD-RECHAZO] usuario={email}, razon={errv.get('content', {}).get('error')}, archivo={audio.filename}, tamaño={len(content)}")` (o similar) para auditoría. (3) Endpoint admin `/api/admin/storage/activity` (nuevo) que retorne: usuario, # posts últimos 7 días, bytes promedio/post, # intentos rechazados, últimas razones de rechazo. Protegido por `_es_moderador()`. (4) Alert si usuario sube >5 posts en <1 hora: guardar timestamps de compartir exitosos y validar en línea 4400. (5) Log fallido de transcoding (líneas 4505-4507): cambiar "print" a "print(f\"[COMUNIDAD-TRANSCODE-FAIL] usuario={email}, archivo={audio.filename}\")". Esto cierra la brecha entre gratis y Pro: con logs, puedes refutar claims y detectar patrones antes de cobrar.


### [MEDIA] Reciprocidad manipulable: query de comentados no filtra posts inactivos

**Por qué:** La query de reciprocidad_stats en repositories.py línea 1871-1877 cuenta comentarios en posts inactivos (soft-deletados). Al desactivar un post con activo=FALSE, sus comentarios siguen siendo contables para la reciprocidad porque la query no filtra por p.activo. Esto permite a un usuario desactivar su track tras recibir comentarios y seguir acumulando \"crédito de reciprocidad\" sin haber dado feedback en posts activos realmente, eludiendo el gate de \"da-para-recibir\". Aunque los comentarios no se muestran en UI, generan deuda técnica y permiten lógica de negocio manipulable. No bloquea lanzamiento (impacto bajo hoy, beta con usuarios cuidados) ni cobro (Stripe no se ve afectado), pero es vulnerabilidad de integridad de datos y debe arreglarse antes de abrir al público o monetizar."


**Fix:** 1. Añadir filtro p.activo = TRUE en la query de reciprocidad_stats (línea 1875): cambiar \"WHERE c.usuario_id = $1 AND c.activo AND p.usuario_id <> $1\" a \"WHERE c.usuario_id = $1 AND c.activo AND p.activo AND p.usuario_id <> $1\". 2. Opcionalmente, añadir ON DELETE CASCADE en la FK de comunidad_comentarios.post_id (d8e1a4c7f2b9_comunidad_comentarios.py línea 27) para purga automática al borrar posts, aunque soft-delete en lugar de DELETE lo hace innecesario hoy. 3. Script admin que liste comentarios en posts inactivos (orféans) y permita purgarlos o reactivar posts. 4. Documentar: soft-delete es transitorio (ej. 30 días), luego hard-delete automático con CASCADE de comentarios."


### [BAJA] Frontend confía en JSON de `util` sin re-validación de servidor (FALSO POSITIVO)

**Por qué:** El backend (repositories.py línea 1840-1859) valida correctamente que SOLO el dueño del track puede marcar útil un comentario. El endpoint POST /api/comunidad/comentarios/{id}/util verifica `row['owner'] != owner_id` y devuelve 403 si no autorizado. La BD está protegida. El frontend (comunidad.html línea 297, 306) sí confía ciegamente en el campo `util` del JSON sin re-validación, lo que en un escenario MitM permitiría inyectar falsa UI ('✓ le ayudó'). PERO: (1) Afecta solo la UI, no la BD; (2) La reputación real está en `autor_utiles` en la DB, no es modificada por el cliente; (3) HTTPS + `allow_credentials=False` + localStorage (no cookie) mitigan MitM; (4) No afecta badges PRO ni conteos de reputación reales. El hallazgo identifica un escenario teórico válido pero con impacto negligible. Diferible tras beta abierta si se quiere agregar echo-back server de verdad en UI."


**Fix:** Opcional/Defensa en profundidad: El frontend podría re-validar tras POST /util leyendo nuevamente GET /comentarios del servidor (ya lo hace en línea 316: `cargarComentarios(postId, el.closest('.com-seccion'))`), o agregar un field `validada_en_servidor` en respuesta del GET. Hoy no es necesario porque: BD está segura, HTTPS obligatorio, reputación no es falsificable desde cliente. Evaluar post-beta si riesgo de MitM es real."


### [BAJA] Backend confía en frontend para escapar XSS en posts/comentarios

**Por qué:** El backend no escapa HTML al retornar posts, comentarios, bio, titulo, mensaje. Líneas 539-543: _sanitize() solo strip+truncate, no html.escape(). Líneas 4361, 4726, 4844: entrada se sanitiza pero no se escapa antes del return JSON. Sin embargo, el frontend implementa esc() (línea 260) correctamente usando textContent en TODOS los puntos de inserción (líneas 308, 545, 552, 600, 606, 610, 302). Esto mitiga XSS en el cliente web oficial. Riesgo real si: (1) frontend se edita mal y quita esc(), (2) API se consume desde cliente no oficial (mobile/curl) sin escapar, (3) inyección en atributo HTML (title attribute en línea 294, pero contiene int(utiles) que es seguro). Email (_notificar_comentario, línea 4146) ya usa html.escape() correctamente. VIOLACIÓN DE PRINCIPIO: backend debe escapar output, no confiar en frontend."


**Fix:** Cambiar _sanitize() para incluir html.escape(): def _sanitize(text: str, max_len=500) -> str: import html; return html.escape(text.strip()[:max_len].replace('\\x00', '')). Esto se aplica sin romper nada porque frontend ya escapa (doble escape es seguro en textContent). O crear _sanitize_for_json() separada. Líneas clave: 539 (función), 4361 (titulo), 4726 (titulo), 4729 (mensaje), 4844 (texto comentario), 3971 (bio)."


### [BAJA] Rate limit bajo en comentarios permite spam (20/hour) — Riesgo INFLADO

**Por qué:** VERIFICADO en código: /backend/main.py línea 4837 límite 20/hour por IP (get_remote_address). NO hay rate limit por user_id global. PERO: 1) 20/hour = 1 comentario cada 3 minutos, es MODERADO no bajo; 2) Beta privada (1 usuario actualmente), escala no aplicable; 3) Requiere perfil completo (barrera); 4) Moderación manual existe; 5) Daño es UX no seguridad de servidor. RIESGO REAL en elusión de IP si slowapi está mal configurado para X-Forwarded-For en Railway, pero eso es problema de proxy config, no de rate limiter per se. Hallazgo INFLA severidad al compararla con DoS de servidor (no aplica).


**Fix:** PRIORITARIO (cuando escale a N usuarios): 1) Verificar slowapi está configurado para confiar en X-Forwarded-For en Railway (Limiter(key_func=..., trusted_proxies=...)). 2) Añadir rate limit por user_id GLOBAL: ej. @limiter.limit("200/day") + cache redis/memory. 3) OPCIONAL (baja prioridad): limitar comentarios por post/día (ej. máx 100/post) para evitar que uno sea "spam magnet". Hoy: DIFERIBLE hasta >100 usuarios beta. El 20/hour por IP es suficiente para beta privada.


### [BAJA] Avatar antiguo no se borra al actualizar perfil (potencial garbage collector debt)

**Por qué:** El flujo de actualizar avatar (POST /api/perfil/foto, líneas 4002-4024 en backend/main.py) escribe el nuevo archivo a disco (línea 4004), actualiza la DB para obtener el nombre del anterior (línea 4011, via repos línea 167-174), e intenta borrarlo (línea 4021). Esto está implementado correctamente CON el mecanismo unlink(missing_ok=True), pero el manejo de errores es SILENCIOSO: si falla el unlink() por permisos/espacio, se ignora sin log de warning (línea 4022-4023). Esto puede dejar avatares huérfanos a escala (~15-30 MB en 600 usuarios con ~5 cambios/año cada uno = 0.3-0.6% del volumen de 5GB). Es debt técnica, no bloqueante porque no causa crashes ni afecta UX directamente. No hay scripts de cleanup ni monitoreo de orfandad de archivos. El mismo patrón (pero PEOR controlado) existe en borrar posts (línea 4773 maneja el audio_file con unlink(missing_ok=True) pero sin chequeo previo en DB de que exista).


**Fix:** 1. Agregar logging en línea 4023 si el unlink() falla: 'if antigua: print(f"[PERFIL FOTO] no se pudo borrar avatar antiguo {antigua}: {e}")' 2. Crear un endpoint admin POST /api/admin/cleanup-orphans que liste archivos en /data/avatars e identifique huérfanos (no en usuarios.perfil_foto) y /data/comunidad (no en comunidad_posts.audio_file), y opcionalmente los borre con confirmación. 3. En README/docs de operación: agregar nota sobre ejecutar cleanup mensualmente. 4. OPCIONAL pero recomendado: cambiar a un patrón transaccional donde el borrado del archivo anterior ocurra DENTRO de la transacción DB (esto requiere que Postgres ejecute un trigger BEFORE UPDATE usuarios.perfil_foto que borre el archivo, o usar una cola de jobs para async cleanup postconfirmación DB). Actualmente Mentotrack no tiene job queue, así que la opción admin/cleanup es la más realista.


### [INFO] Reputación sin gating actual — cosmético social, no vulnerabilidad de acceso

**Por qué:** El código PERMITE técnicamente que un atacante marque sus propios comentarios (vía múltiples cuentas) como útiles, inflando `utiles_recibidos`. PERO: (1) la reputación hoy es solo cosmética (badge social en el perfil y muro, linea 4635 en main.py), (2) NO se usa en gating alguno — el gating real de compartir usa reciprocidad (COUNT DISTINCT posts comentados, línea 1872 en repositories.py), que está protegida, (3) el modelo de monetización (docs/monetizacion.md) NO propone usar reputación como criterio de acceso hoy. Resultado: atacante infla un badge social sin acceso a features restringidas. Es cosmético, no crítico. Relevante solo si futuro usa reputación en gating (feedback prioritario, etc.), cosa que no está implementada.


**Fix:** No es crítico hacer hoy, pero para defensar futuro gating: en `marcar_comentario_util` (línea 1840-1859), agregar validación: `AND c.usuario_id <> $1` (comentarista ≠ owner del post). Esto previene que un user marque útiles a comentarios del mismo propietario (caso edge: Alice comenta en su propio post y ella misma se marca útil, inflando su reputación directamente, aunque es menos probable en comunidades sociales). Alternativa: si se implementa "feedback prioritario por reputación", aplicar un deweight: contar máximo 1 útil por comentarista por track, o contar solo útiles de usuarios con N tracks propios (anti-bot). Bajo riesgo hoy = diferible a cuando se use reputación en gating.
