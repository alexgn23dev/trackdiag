"""
Templates de texto para cada diagnóstico.
Escritos a mano para controlar tono, claridad y utilidad.
"""

TEMPLATES = {
    "problema_arreglo": {
        "titulo": "La estructura del arreglo es el cuello de botella — falta forma reconocible.",
        "prioridades": [
            # Ojo al reescribir esto: la versión anterior decía "n_bloques bajo",
            # que es el nombre de una variable interna colándose en el texto que
            # lee el productor. Aquí no puede aparecer nada que no se entienda
            # sin conocer el código.
            "Mira qué señal ha disparado el diagnóstico: la tienes justo encima, en «por qué lo decimos». Cada una pide una cosa distinta. Si es poco contraste entre secciones, mete drops y breaks claros. Si es que no hay desarrollo, añade transiciones: filtros que abren, capas que van entrando. Si el break es desproporcionado, recórtalo o súbele intensidad. Y si el track tiene pocas secciones, el problema es que aún no hay estructura que arreglar: hay que crearla.",
            "Estructura base de track de club (4-6 minutos): intro de 32 bars con kick + percusión + 1 elemento (DJ-friendly); build-up de 16 bars donde entran elementos progresivamente; drop principal de 32-64 bars con todo activo; break de 16-32 bars con la mitad de elementos quitados y un giro melódico/atmosférico; segundo drop de 32-64 bars (variado, no idéntico al primero); outro de 16-32 bars perdiendo elementos para mix. Si tu track no encaja vagamente con esto, tienes ahí los huecos.",
            "Antes de seguir, haz el ejercicio del mapa de bloques en papel: divide el tiempo del track en bloques de 32 compases y, para cada bloque, escribe (a) qué energía tiene (1-5), (b) qué elementos están sonando, (c) qué cambia respecto al bloque anterior. Si dos bloques contiguos tienen exactamente lo mismo, ahí está el problema — o añades variación o recortas el bloque repetido.",
        ],
        "no_tocar": [
            "No mezcles ni masterices hasta que la estructura esté cerrada — vas a tomar decisiones de EQ/compresión que se invalidan en cuanto muevas las secciones.",
            "No busques sonidos nuevos como excusa. La estructura se trabaja con lo que ya tienes — copy/paste de patrones, mutes, automatizaciones de volumen. Solo después decides si hace falta material nuevo.",
            "No copies la duración de tu track favorito sin más. Los tracks de DJ extendidos miden 5-7 min con varias variaciones, no 8 min del mismo loop. La duración debe estar justificada por la información musical, no por el género.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: ignora todo lo que no sea estructura durante 60-90 minutos. Cierra plugins, "
            "haz el mapa de bloques en papel, define qué pasa en cada bloque y mueve/duplica/recorta tu material "
            "actual para encajar en ese mapa. Objetivo realista: tu track debe poder escucharse plano (sin mezcla) "
            "y reconocerse la forma a primera escucha. Cuando lo consigas, vuelves a mezcla."
        ),
    },
    "poco_contraste": {
        "titulo": "El track suena como un loop continuo — falta una curva de energía clara.",
        "prioridades": [
            "Crea contraste de energía de manera quirúrgica: en el track entero, debe haber al menos una sección donde el oyente sienta 'bajada' (energy 2-3 sobre 5) y al menos una donde sienta 'subida' (energy 4-5). Las técnicas más rápidas para conseguirlo: (a) mute del kick durante 8-16 compases en una sección — el simple hecho de quitar el pulso ya baja la energía percibida; (b) low-pass filter sweep que abre desde 200 Hz hasta full en 8-16 bars antes del drop; (c) sección donde solo suenan kick + bajo + 1 elemento atmosférico, vs sección con todo activo.",
            "Mete al menos un break perceptible: punto del track donde la energía cae claramente (kick fuera o filtrado, percusiones secundarias muteadas, queda pad o atmosfera + 1 elemento tonal) durante 8-16 compases. La regla: si tras el break, al volver a entrar el drop, no se siente subida, el break está fallando. Comparado al drop, debería sentirse al menos 30% más bajo en energía.",
            "Usa automatizaciones de filtro, volumen y send a reverb para construir transiciones graduales entre secciones (4-8 bars de transición). Sin transiciones, los cortes son secos y el oyente no anticipa lo que viene — esto se percibe como 'el track no respira'.",
        ],
        "no_tocar": [
            "No sigas sumando capas pensando que el track suena plano por falta de elementos. Probablemente tienes los elementos suficientes — lo que falta es distribuirlos en el tiempo con curva de energía.",
            "No mezcles en detalle todavía. Si la estructura no tiene contraste, vas a tomar decisiones de EQ y compresión que se invalidan cuando cambies la curva de energía.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: escucha un track de referencia del mismo estilo con auriculares y un papel. Apunta "
            "minuto a minuto qué hace la energía (sube, baja, mantiene). Verás que tiene 4-6 cambios claros. "
            "Vuelve a tu track e intenta replicar esa curva, usando mutes y filter sweeps antes de añadir nada nuevo. "
            "Si tras 90 minutos tu track tiene al menos 3 cambios claros de energía, sesión cumplida."
        ),
    },
    "falta_impacto": {
        "titulo": "La subida y el drop suenan a un volumen similar — se pierde impacto.",
        "prioridades": [
            "Crea una automatización de volumen en el bus master (o en los elementos principales) que baje ligeramente el nivel durante la subida, y vuelva al volumen original justo al entrar el drop. Aunque suene contraintuitivo, este truco es muy usado en producción profesional para aumentar la sensación de impacto.",
            "Revisa los elementos de la subida: si tienes risers, snare rolls o efectos que suben de volumen progresivamente, asegúrate de que no igualan o superan el nivel del drop.",
            "Prueba a quitar algún elemento justo antes del drop (un compás de silencio, un corte de kick, un filtro) — el contraste momentáneo hará que la entrada del drop se sienta mucho más potente.",
        ],
        "no_tocar": [
            "No subas el volumen del drop para compensar — el truco está en bajar lo que viene antes, no en subir lo que viene después.",
            "No apliques más compresión o limiting al master para intentar igualar niveles — eso aplasta más la dinámica.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, escucha tu track de referencia favorito con un medidor de volumen. "
            "Fíjate en cómo el volumen baja justo antes del drop y sube al entrar. "
            "Intenta replicar esa curva de energía con automatizaciones en tu track."
        ),
    },
    "mezcla_prematura": {
        "titulo": "Aún quedan detalles del arreglo antes de cerrar la mezcla.",
        "prioridades": [
            "Antes de seguir afinando EQ y compresión, dedica una sesión a cerrar la estructura: revisa que cada sección tiene un propósito claro (intro, break, drop, outro) y que el contraste energético se nota a primera escucha.",
            "Bajada técnica: bypass de todos los plugins del master y de los buses. Escucha el track plano. Si la energía y el desarrollo siguen funcionando así, la estructura está cerrada y puedes volver a la mezcla. Si no, el problema no era de mezcla.",
            "Compara con un track de referencia del mismo estilo: ¿tu desarrollo entre secciones es comparable? ¿Tus drops llegan al mismo nivel de energía? Si no, ahí está lo que mover.",
        ],
        "no_tocar": [
            "Evita afinar EQ por elementos individuales mientras la estructura no esté cerrada — vas a cambiar las decisiones de mezcla cuando muevas las secciones.",
            "No subas el loudness final ni pongas limitador de master todavía — distorsiona la percepción del contraste entre secciones.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: abre el proyecto, desactiva el master y los plugins de mezcla individuales, y "
            "haz una pasada centrada solo en arreglo y energía. Marca los puntos donde el track 'no respira' "
            "o donde dos secciones suenan demasiado parecidas, y resuélvelos antes de volver a la mezcla."
        ),
    },
    "exceso_lowend": {
        "titulo": "Los graves dominan demasiado el espectro — el track va a sonar turbio o aburrido.",
        "prioridades": [
            "Limpia los elementos que no necesitan graves con un high-pass filter en su canal individual: pads en 150-200 Hz, leads en 200-300 Hz, voces en 100-120 Hz, FX y reverbs en 200-300 Hz, percusiones agudas (hats, shakers) en 300-500 Hz. Solo el kick, el bajo, los toms graves y las percusiones tonales con cuerpo deben llegar bajos. Es el cambio que más rápido te baja la suciedad en graves.",
            "Revisa la relación kick ↔ bajo: una de las dos causas más típicas. Solea kick + bajo. Si pelean, aplica sidechain compression (4-6 ms attack, 100-150 ms release, ratio 4:1, threshold para 4-6 dB de reducción) o EQ dinámico en el bajo que se reduzca solo cuando entra el kick. Frecuencias típicas de pelea: el kick vive en 50-80 Hz, el bajo en 80-200 Hz — si tu bajo está empujando por debajo de 80 Hz, súbele un high-pass moderado (around 50 Hz).",
            "Verifica el control del sub (0-60 Hz): tracks con rumble suelen tener un sub que no se controla. Pon un analizador low-end (SPAN con resolution alta, o un goniómetro) y mira qué hay debajo de 40 Hz. Si tu kick o tu bajo tienen contenido por debajo de 30-40 Hz que no aporta nada (no se oye en altavoces normales pero come headroom y excita el limiter), córtalo con un high-pass de 24 dB/oct a 30 Hz.",
        ],
        "no_tocar": [
            "No metas un EQ ancho en el master a -3 dB en 100 Hz pensando que arreglas el problema. Vas a debilitar el kick que sí debe sonar fuerte. El low-end se trabaja por canal individual, no por el master.",
            "No subas medios y agudos para 'igualar' — el balance no se arregla añadiendo más sobre lo que ya hay demasiado. Resta lo que sobra primero.",
            "No confíes solo en monitores con poco grave (KRK 5\", auriculares de gama media). Cruza siempre la decisión con un analizador o con auriculares de referencia (HD600/650, DT 1990) — los altavoces pequeños mienten en sub.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: ronda de high-pass en serie. Empieza por mute solo del kick y el bajo y "
            "escucha el resto del track. Cualquier cosa que tenga peso en graves cuando no debería (un pad "
            "rumboso, un FX que sopla por debajo, una voz con bocazo) recibe high-pass en su canal. Luego activa "
            "kick + bajo y soléalos: que se entiendan los dos. Si no se entienden, sidechain. Cierra la sesión "
            "habiendo eliminado contenido grave de los 3-5 canales que más cargaban innecesariamente."
        ),
    },
    "exceso_densidad": {
        "titulo": "Demasiados elementos sonando a la vez — el track se siente saturado.",
        "prioridades": [
            "Haz el ejercicio del mute progresivo: mutea TODOS los canales, luego activa uno a uno empezando por kick, bajo, percusión principal. Cuando lleves 4-5 elementos activos, pregúntate antes de añadir el siguiente: ¿lo que estoy oyendo ya cuenta la historia? Si la respuesta es sí, lo siguiente que actives tiene que aportar algo nuevo (frecuencia, ritmo, color) o se queda fuera. Los tracks que sienten densos suelen tener 12-15 elementos cuando con 7-8 bien escogidos sobraría.",
            "Caza duplicados de función: ¿tienes dos pads cubriendo el mismo rango (200-800 Hz)? Mutea uno y escucha. ¿Dos elementos rítmicos secundarios en la misma posición temporal (un clap y un snare que caen en el 2 y 4)? Elimina uno. ¿Capas de hi-hats que ocupan exactamente la misma banda? Junta a una y dale más peso. La regla: cada elemento debe tener una banda frecuencial dominante distinta o una función rítmica distinta.",
            "Crea respiración temporal: ningún elemento (salvo el kick si es 4x4) tiene que sonar durante todo el track. Define en qué bloques entra y sale cada cosa — pad solo en el break, lead en el drop principal pero no en el secundario, shaker solo en los compases pares. Esto reduce densidad sin perder elementos, solo distribuyéndolos en el tiempo.",
        ],
        "no_tocar": [
            "No intentes resolver densidad solo con EQ. EQ ayuda a separar elementos que conviven, pero si tienes 14 capas, la solución es quitar 4, no ecualizar más fino.",
            "No te pongas a ecualizar el master para 'limpiar'. Si el master suena turbio es porque hay demasiada información llegando — soluciona arriba, en los canales.",
            "No añadas más capas pensando que falta algo. Si el diagnóstico dice exceso de densidad, casi seguro sobra. La sensación de 'le falta algo' suele ser sensación de 'no se entiende lo que ya hay'.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: graba un bounce de cómo suena ahora. Después, mutea de golpe la mitad de los canales "
            "secundarios (no kick/bajo/elemento principal). Escucha. Si el track sigue funcionando, la mitad sobraba. "
            "Si pierde algo importante, activa solo lo que de verdad echas en falta. Compara con el bounce inicial. "
            "Objetivo: cerrar la sesión con al menos 3-4 canales muteados permanentemente o reemplazados por algo que sí aporte."
        ),
    },
    "track_verde": {
        "titulo": "Es un boceto temprano — todavía no hay un track, hay una idea que crece.",
        "prioridades": [
            "Trabaja la idea, no la mezcla. En esta fase, las preguntas correctas son: ¿qué emoción quieres transmitir? ¿quién bailaría/escucharía esto? ¿en qué momento de un set encajaría? Si no tienes respuesta clara a ninguna, dedica 20 minutos a escribir 3 referencias concretas (artista + track + por qué te gusta) que vayan en la línea de lo que quieres hacer. Sin eso, vas a hacer mil decisiones sin criterio.",
            "Extiende la duración a 4-5 minutos con secciones básicas, aunque sea con copy/paste y muy poca variación. Plantilla mínima viable: 32 bars de intro (solo kick + 1 elemento), 32 bars de desarrollo (suma elementos), 16 bars de break (quita kick + ambient), 32 bars de drop (todo activo), 16 bars de outro. Eso solo, con tu material actual duplicado y arrastrado, ya te pone en posición de empezar a tomar decisiones reales.",
            "Limita el alcance de la sesión: en esta fase, terminar la estructura completa (aunque suene mal) vale infinitamente más que perfeccionar 16 compases. La razón es psicológica: con la estructura completa ves dónde fallan las cosas; sin ella te quedas dando vueltas al mismo loop.",
        ],
        "no_tocar": [
            "No mezcles ni ecualices nada todavía. Salvo high-pass evidente o sidechain básico, todo plugin que metas ahora se va a tener que rehacer cuando cambien las decisiones del arreglo.",
            "No te compares con tracks terminados de tus referencias. Es un boceto vs un release pulido — la comparación no es informativa, solo te frustra.",
            "No busques presets ni samples nuevos como excusa para no decidir. La paralización por exceso de opciones es el error #1 en esta fase. Cierra el navegador y trabaja con lo que ya tienes en sesión.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: 60 minutos máximo. Objetivo único — terminar la estructura completa de principio a fin "
            "con el material actual + las plantillas mínimas (intro, desarrollo, break, drop, outro). Aunque suene "
            "repetitivo o aburrido. Cuando tengas eso, escúchalo entero sin parar y apunta los 3 puntos que más "
            "te molesten. Esos serán los target de la SIGUIENTE sesión, no de esta."
        ),
    },
    "carencia_espectral": {
        "titulo": "Al track le falta cuerpo en medios y/o aire en agudos.",
        "prioridades": [
            "Primero diagnostica si es problema de CONTENIDO o de NIVEL: solea por separado los pads, leads, percusiones secundarias (claps, shakers) y hi-hats. Si alguno suena claro pero en la mezcla desaparece, es nivel — sube ese canal 2-3 dB. Si al solearlo ya suena pobre o vacío, es contenido — necesitas añadir algo en esa banda, no subir lo que tienes.",
            "Para los medios (200 Hz–2 kHz): suelen vivir aquí pads, stabs, vocal chops, percusiones tonales (claves, congas). Si tu track no tiene nada de esto, añade una capa: un pad ancho con cuerpo en 300-600 Hz, un stab corto con ataque en 800 Hz–1.2 kHz, o una percusión tonal. Como guía, abre un track de referencia de tu estilo y mira el analizador en esa zona — debería haber actividad constante, no un valle.",
            "Para los agudos (4 kHz en adelante): faltan probablemente hi-hats, shakers, rides, foley o aire general. Si ya los tienes pero no se notan, prueba un shelf de +2-3 dB desde 8 kHz con Q ancho en el canal del hi-hat o usa un exciter (Soothe en modo expansivo, Fresh Air, o el de tu DAW). Si no tienes nada brillante, añade un shaker o un loop de ambiente — incluso a -25 dB aporta aire.",
        ],
        "no_tocar": [
            "No subas el master para compensar — el problema no es volumen, es contenido. El limiter va a aplastar los pocos medios que tengas en lugar de añadirlos.",
            "No cortes graves para 'destapar' los medios. Eso solo desbalancea el track más. Añade en lo que falta, no restes de lo que ya funciona.",
            "No abras un EQ ancho en el master a +5 dB en 2 kHz buscando brillo — vas a subir también ruido, harshness y reverbs no intencionadas. Trabaja siempre en el canal del elemento, no en el master.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: abre tu track con un analizador (SPAN, iZotope Insight, Voxengo SPAN) "
            "junto a un track de referencia del mismo estilo. Compara la curva entre 500 Hz y 8 kHz — "
            "ese es el rango donde se pierde el cuerpo. Identifica los 1-2 huecos más obvios y, "
            "para cada uno, decide si añades un elemento nuevo o subes uno existente. Cierra la sesión "
            "habiendo cubierto al menos un hueco."
        ),
    },
    "conflicto_armonico": {
        "titulo": "Se detectan posibles conflictos armónicos entre elementos del track.",
        "prioridades": [
            "Identifica qué elementos melódicos o armónicos suenan simultáneamente y comprueba que estén en la misma tonalidad.",
            "Si usas samples o loops melódicos, verifica que estén en la misma escala o en escalas compatibles.",
            "Solea los elementos de uno en uno: kick + bajo, bajo + lead, lead + pad. Si alguna combinación suena disonante, ahí está el conflicto.",
        ],
        "no_tocar": [
            "No intentes arreglarlo afinando todo con un auto-tune — el problema suele ser de selección de sonidos, no de afinación.",
            "No añadas más capas melódicas hasta resolver los choques entre las que ya tienes.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, abre un analizador de notas (muchos DAW lo traen) y verifica "
            "la nota fundamental de cada elemento melódico. Si alguno no encaja en la escala del track, "
            "transpónlo o reemplázalo. A veces basta con subir o bajar un semitono."
        ),
    },
    "pobreza_armonica": {
        "titulo": "El track tiene poco contenido melódico o armónico (apenas notas, sin progresión).",
        "prioridades": [
            "Primero decide si tu track lo necesita: en techno crudo, dub techno, minimal, hypnotic o tracks puramente rítmicos, la pobreza armónica es intencional y este diagnóstico no aplica — ignóralo. Si tu estilo sí pide armonía (house, melodic techno, progressive, trance, indie dance, deep house), sigue al punto 2.",
            "Añade al menos una capa con dirección armónica. Tres opciones por orden de complejidad: (a) progresión de 2-4 acordes en un pad ancho (basta con i–VI–III–VII en menor para sonar profesional); (b) un stab corto que toque solo 2-3 notas en cada bar para dar movimiento; (c) un bajo con notas (no solo el root del kick) que recorra la progresión. Para empezar simple, prueba un pad con un envolvente lento (attack 200-500 ms) sobre tu loop.",
            "Si ya tienes algo tonal pero suena estático, dale movimiento entre secciones: cambia la nota raíz cada 16 ó 32 compases, mete una transposición de +5 (cuarta justa) en el break, o varía el ritmo de los acordes (que el pad cambie cada compás en el drop y cada 2 compases en el verso). En 8 bars de cambio armónico se nota mucho.",
        ],
        "no_tocar": [
            "No fuerces melodía si tu estilo es rítmico-percusivo — minimal, dub, raw techno funcionan perfectamente sin progresión armónica explícita. Marca el género correcto en el cuestionario y el diagnóstico debería desaparecer.",
            "No copies directamente la progresión de tu track favorito. Apunta qué emoción te transmite y busca acordes que tú asocies a esa emoción (menor para tensión, mayor para resolución, séptimas para color jazz/house, suspended para flotante).",
            "No te enredes con teoría musical antes de probar: en electrónica, una progresión de 4 acordes en menor con notas básicas funciona para el 90% de los tracks. Si quieres ir más allá luego, perfecto, pero no es lo primero.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: abre un sintetizador simple (pad o pluck), pon el track en loop sobre 8 compases "
            "y prueba progresiones de 4 acordes en menor (Am–F–C–G es un clásico que funciona en cualquier estilo). "
            "Toca cada acorde durante 2 compases. Si algo te emociona, queda. Si nada te convence, prueba una "
            "progresión más oscura (Am–Em–F–Dm). Cierra la sesión con una progresión que te guste, aunque sea de pads "
            "muy bajitos en volumen — la decisión armónica afecta a todo lo demás."
        ),
    },
    "harshness_mezcla": {
        "titulo": "Hay zonas duras o chirriantes en medios-altos (2–6 kHz).",
        "prioridades": [
            "Caza al culpable: pon el track a volumen moderado-bajo y solea uno por uno los candidatos típicos — hi-hats, claps, snares con sample chirriante, leads brillantes, voces procesadas con saturación, percusiones metálicas o cymbals. Apunta los 1-2 que más cansan al oído. Trabaja sobre esos canales, no sobre el master.",
            "Sobre el elemento problemático, abre un EQ paramétrico con un corte estrecho (Q 4-8) y +4 dB. Barre lentamente entre 2 kHz y 6 kHz hasta encontrar el punto exacto donde más chirría. Una vez localizado, INVIERTE el corte a -3 dB con el mismo Q (puedes bajar el Q a 2-3 si quieres suavizar). Si el elemento sigue molestando, repite el barrido entre 6 y 10 kHz — ahí están las resonancias más finas (ssss de las voces, brillos exagerados de las cymbals).",
            "Si el harshness viene de saturación o distorsión no intencionada: revisa si tienes plugins empujando — un compresor con make-up muy alto, un saturador en serie, una tape emulation con drive subido. Baja el input/drive de esos plugins antes de meter más EQ sustractivo. Soothe2 o Smart:EQ Live también funcionan muy bien para resonancias dinámicas si tienes presupuesto, pero un EQ paramétrico bien usado resuelve el 80% de los casos.",
        ],
        "no_tocar": [
            "No bajes todos los agudos del master con un shelf negativo — vas a apagar también lo que sí tiene que brillar (hats, percusiones, aire). El harshness suele venir de 1-2 elementos puntuales, no de toda la zona alta.",
            "No compenses subiendo los graves o medios para 'tapar' el chirrido — solo desbalanceas el track. Resuelve el harshness primero, luego ajusta balance si hace falta.",
            "No uses un de-esser genérico en el master pensando que es atajo. Está pensado para una banda muy concreta (5-9 kHz típicamente) y se va a comer también la presencia útil de otros elementos.",
        ],
        "siguiente_sesion": (
            "Próxima sesión: escucha el track a volumen bajo durante un minuto entero — el oído detecta harshness "
            "mucho mejor a niveles moderados que a volumen de monitor. Cualquier elemento que destaque por encima "
            "del resto o que te haga querer bajar el volumen es candidato. Aplica el barrido + corte sobre ese "
            "elemento (no sobre el master) y vuelve a escuchar a volumen bajo. Si sigue molestando, repite con el "
            "siguiente candidato. Objetivo: cierra la sesión habiendo tratado los 2 elementos más agresivos."
        ),
    },
    "break_sin_payoff": {
        "titulo": "El break largo no genera el contraste que pide — al volver al drop no se siente subida.",
        "prioridades": [
            "Sube ligeramente la energía del drop POSTERIOR al break: añade una capa más (percusión secundaria, una vocal chop, un sub que entre solo ahí, automatización de filtro abriendo) que diferencie ese drop del que iba antes del break.",
            "Si quieres que la subida funcione, baja también lo de ANTES del break: filtros que se cierran, percusiones que desaparecen, un compás de silencio. Cuanto más bajo el suelo, más alto se siente el techo cuando vuelve a entrar.",
            "Acorta el break si no aporta variación: si su única función es 'descansar' y luego volvemos a lo mismo, mejor que dure 8 compases que 32. El break necesita o variación interna o un payoff claro al final.",
        ],
        "no_tocar": [
            "No metas más capas DURANTE el break para 'rellenarlo' — un break es por definición un momento de menos. Aporta variación o acórtalo, pero no lo satures.",
            "No subas el volumen del master en el drop posterior — el limiter se come la dinámica que estás intentando ganar.",
        ],
        "siguiente_sesion": (
            "Coge un track de referencia de tu género que tenga un break que te ponga la piel de gallina al volver al drop. "
            "Apunta qué cambia entre el drop pre-break y el post-break: ¿qué entra nuevo? ¿qué se queda fuera? "
            "Aplica la misma diferencia a tu track."
        ),
    },
    "arreglo_repetitivo": {
        "titulo": "El track es largo pero con pocas variaciones — la estructura no acompaña a la duración.",
        "prioridades": [
            "Identifica el bloque más repetitivo de tu track (probablemente el groove principal) y diseña una variación cada 32 ó 64 compases: un fill, un drop de un elemento, un cambio de patrón en la percusión, un giro armónico breve.",
            "Si el track dura más de 5 minutos, debería tener al menos 4-5 transiciones perceptibles. Crea contrastes: filtros que abren y cierran, capas que entran y salen, mutes intencionales en el kick o en el bajo.",
            "Plantéate si la duración actual está justificada por la información musical. Si no, recorta — un track de 4 minutos bien contado vale más que uno de 7 minutos repetitivo.",
        ],
        "no_tocar": [
            "No metas elementos nuevos solo para llenar tiempo. La variación tiene que tener intención narrativa, no ser ruido.",
            "No alargues el track pensando que un set de DJ pide duración: hoy lo habitual son 5-6 minutos extendidos con varias variaciones, no 8 minutos del mismo loop.",
        ],
        "siguiente_sesion": (
            "Haz un mapa de bloques de 32 compases de tu track. En cada bloque, anota qué elementos están sonando "
            "y qué cambió respecto al bloque anterior. Si dos o más bloques contiguos tienen exactamente lo mismo, "
            "ahí tienes los huecos donde añadir variación o de donde recortar."
        ),
    },
    "enmascaramiento_bajo": {
        "titulo": "El bajo está enmascarando al kick o a los graves medios.",
        "prioridades": [
            "Identifica qué frecuencias ocupa tu bajo: probablemente está empujando entre 80 y 200 Hz por encima de lo que debería. Aplica un corte sustractivo en esa zona del bajo (1-3 dB) y vuelve a comparar contra el kick.",
            "Revisa la relación kick ↔ bajo: si están en zonas similares, usa sidechain compression (4-6 ms attack, 80-120 ms release) para que el bajo se aparte cuando entra el kick.",
            "Si tras esto los medios siguen apagados, sube ligeramente el bus de percusión o de medios (no del master) para recuperar presencia sin tocar el bajo.",
        ],
        "no_tocar": [
            "No subas el kick para compensar — el problema es de espacio, no de volumen. Subir el kick solo empeora la pelea con el bajo.",
            "No apliques un EQ ancho a la banda 80-200 Hz del master — afectarás también al kick. Trabaja siempre sobre el canal del bajo individualmente.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, solea kick + bajo y escucha el patrón rítmico. Si el kick se 'apaga' cuando entra el bajo, "
            "tienes enmascaramiento. Prueba un EQ dinámico en el bajo que se reduzca solo en la banda del kick "
            "(60-100 Hz) o un sidechain rápido. Vuelve a comprobar con el resto de la mezcla activada."
        ),
    },
    "sin_diagnostico": {
        "titulo": "No se detectan bloqueos evidentes en este track.",
        "prioridades": [
            "El track parece estar en buen estado a nivel de estructura y balance general.",
            "Si sientes que algo no funciona, el problema puede estar en aspectos creativos o de detalle que un análisis automático no detecta.",
            "Considera pedir feedback humano a alguien de confianza para afinar los últimos detalles.",
        ],
        "no_tocar": [],
        "siguiente_sesion": (
            "Si el track te convence a nivel de arreglo y energía, es buen momento para hacer una escucha "
            "en distintos sistemas (auriculares, altavoces, coche) y anotar qué te molesta. "
            "Esas notas son tu siguiente lista de ajustes."
        ),
    },
}
