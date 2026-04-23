"""
Templates de texto para cada diagnóstico.
Escritos a mano para controlar tono, claridad y utilidad.
"""

TEMPLATES = {
    "problema_arreglo": {
        "titulo": "Tu cuello de botella principal parece estar en la estructura del arreglo.",
        "prioridades": [
            "Define al menos 3-4 secciones diferenciables (intro, desarrollo, break, drop/clímax, outro).",
            "Crea contrastes claros de energía entre secciones — sube y baja la intensidad.",
            "No añadas más elementos todavía. Trabaja la estructura con lo que ya tienes.",
        ],
        "no_tocar": [
            "No te centres en la mezcla todavía — primero necesitas un arreglo claro.",
            "No busques más presets o samples. Usa los que tienes para cerrar la estructura.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, crea un mapa de bloques con duración y función para cada sección. "
            "Después, mueve y duplica tus elementos actuales para rellenar esa estructura. No añadas nada nuevo."
        ),
    },
    "poco_contraste": {
        "titulo": "El track necesita más desarrollo — suena como un loop continuo sin evolución.",
        "prioridades": [
            "Crea al menos una sección de alta energía y una de baja energía claramente diferenciadas.",
            "Añade un break o parón que rompa la monotonía y genere expectativa antes del drop.",
            "Usa filtros, automatizaciones o silencios para crear transiciones entre las secciones.",
        ],
        "no_tocar": [
            "No sigas sumando capas por todo el track — el problema no es falta de elementos, es falta de estructura.",
            "No mezcles en detalle hasta que tengas una estructura con intro, desarrollo, clímax y cierre.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, escucha un track de referencia de tu género y fíjate en su estructura: "
            "dónde quita elementos, dónde los suma, dónde hay un parón. Intenta replicar ese esquema "
            "con tus propios sonidos."
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
        "titulo": "Estás intentando pulir la mezcla antes de tiempo.",
        "prioridades": [
            "Para de mezclar y vuelve al arreglo — tu track tiene problemas más básicos que resolver primero.",
            "Cierra la estructura completa antes de tocar EQ, compresión o niveles.",
            "Asegúrate de que el track funciona en estructura y energía antes de preocuparte por cómo suena técnicamente.",
        ],
        "no_tocar": [
            "No toques EQ ni compresión individual todavía.",
            "No compares tu mezcla con tracks de referencia en esta fase — es prematuro.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, desactiva todos los plugins de mezcla que hayas puesto y escucha el track "
            "solo con los faders. ¿La estructura funciona? ¿Las secciones tienen contraste? Si no, trabaja eso primero."
        ),
    },
    "exceso_lowend": {
        "titulo": "Hay un exceso notable de energía en la zona grave.",
        "prioridades": [
            "Revisa la relación entre kick y bajo — probablemente están compitiendo en la misma zona frecuencial.",
            "Aplica un high-pass filter a todo lo que no necesite graves (pads, leads, efectos, voces).",
            "Verifica que el sidechain entre kick y bass está funcionando correctamente.",
        ],
        "no_tocar": [
            "No intentes resolver esto solo con EQ en el master — el problema suele estar en los elementos individuales.",
            "No subas los medios y agudos para compensar — primero limpia los graves.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, solea kick y bajo juntos. ¿Se escuchan los dos con claridad? Si no, "
            "ajusta el sidechain, la EQ del bajo o el diseño del kick hasta que convivan sin enmascararse."
        ),
    },
    "exceso_densidad": {
        "titulo": "El track suena demasiado denso — hay muchos elementos compitiendo.",
        "prioridades": [
            "Identifica los 3-4 elementos más importantes del track y baja o mutea el resto.",
            "Revisa si hay elementos que cumplen la misma función (dos pads, dos melodías similares) y elimina uno.",
            "Deja espacio: no todos los elementos necesitan sonar durante todo el track.",
        ],
        "no_tocar": [
            "No intentes resolver la densidad solo con EQ — a veces el problema es que sobran elementos, no frecuencias.",
            "No añadas más capas pensando que falta algo. Probablemente sobra algo.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, haz un ejercicio de resta: mutea todos los canales y ve activándolos uno a uno. "
            "Cada vez que actives uno, pregúntate: ¿esto aporta algo que los demás no aportan? Si no, déjalo muteado."
        ),
    },
    "track_verde": {
        "titulo": "Este track está en una fase muy temprana — es una idea sin desarrollar.",
        "prioridades": [
            "No te preocupes por cómo suena todavía. Preocúpate por qué quieres que pase en el track.",
            "Extiende la idea a al menos 2-3 minutos con secciones diferenciables.",
            "Define qué tipo de track quieres hacer: ¿para pinchar? ¿para escuchar? ¿qué energía debería tener?",
        ],
        "no_tocar": [
            "No mezcles ni ecualices nada todavía — es demasiado pronto.",
            "No busques feedback externo en esta fase — primero cierra tú la idea.",
            "No te compares con tracks terminados — esto es un boceto y es normal que suene así.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, escribe en un papel (sí, papel) las secciones que debería tener tu track "
            "y cuánto debería durar cada una. Después, extiende tu proyecto para cubrir esa duración aunque sea "
            "con elementos básicos."
        ),
    },
    "carencia_espectral": {
        "titulo": "El track tiene poco contenido en la zona media y/o aguda del espectro.",
        "prioridades": [
            "Añade elementos que ocupen la zona de medios: percusiones con cuerpo, voces, stabs o texturas.",
            "Revisa si tus sonidos principales tienen suficiente presencia en medios — un EQ puede ayudar a abrir esa zona.",
            "Los agudos dan definición y aire: hi-hats, shakers, rides o texturas brillantes pueden llenar esa zona.",
        ],
        "no_tocar": [
            "No subas el volumen general para compensar — el problema no es de nivel, es de contenido frecuencial.",
            "No quites graves para que los medios 'se oigan más' — añade lo que falta en lugar de quitar lo que funciona.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, compara tu track con una referencia del mismo género. Escucha específicamente "
            "la zona media: ¿qué tiene la referencia que le da cuerpo y tú no tienes? Percusiones, texturas, "
            "capas rítmicas... Añade 2-3 elementos en esa zona."
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
        "titulo": "El track tiene poco contenido melódico o armónico.",
        "prioridades": [
            "Valora si el track necesita un elemento melódico que le dé identidad: una línea de bajo con notas, un lead, un stab con acordes, o una vocal.",
            "Si ya tienes algún elemento tonal, intenta desarrollarlo más: variaciones, transposiciones entre secciones, o una progresión de acordes simple.",
            "Una progresión de 2-4 acordes en loop puede ser suficiente para dar dirección armónica al track.",
        ],
        "no_tocar": [
            "No fuerces melodías complejas si tu track funciona como una pieza rítmica — en algunos géneros, menos armonía es intencional.",
            "No copies progresiones de otros tracks directamente — escucha qué emoción quieres transmitir y busca acordes que la representen.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, experimenta con un sintetizador simple (un pad o un pluck) "
            "y prueba 3-4 notas diferentes sobre tu loop principal. Si alguna combinación "
            "te hace sentir algo, desarróllala. No busques complejidad — busca emoción."
        ),
    },
    "harshness_mezcla": {
        "titulo": "La mezcla tiene zonas duras o chirriantes en medios-altos.",
        "prioridades": [
            "Identifica qué elementos suenan más agresivos o chirriantes: hi-hats, leads, voces procesadas o percusiones metálicas.",
            "Aplica un EQ sustractivo en la zona de 2-6kHz a los elementos que más molestan — cortes de 2-4dB pueden hacer mucho.",
            "Revisa si hay saturación o distorsión no intencionada en algún canal — a veces un plugin está empujando demasiado.",
        ],
        "no_tocar": [
            "No bajes todos los agudos del master — el problema suele estar en 1-2 elementos concretos, no en todo el track.",
            "No compenses subiendo los graves — primero doma lo que chirría.",
        ],
        "siguiente_sesion": (
            "En tu próxima sesión, escucha el track a volumen moderado-bajo. Los elementos que más te molestan o "
            "se escuchan por encima de todo son los que necesitan un EQ sustractivo. Prueba con un corte estrecho "
            "(Q alto) entre 2-6kHz y barre hasta encontrar la zona que molesta, luego recorta 2-4dB."
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
