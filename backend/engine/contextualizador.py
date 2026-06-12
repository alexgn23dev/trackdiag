"""
Contextualizador de feedback.
Toma el diagnóstico base + contexto del usuario + señales de audio
y genera texto adaptado a experiencia, género, objetivo y fase.

Principio: el diagnóstico no cambia, pero la forma de comunicarlo sí.
"""

from .reglas import es_genero_estatico

# =============================================================================
# DURACIONES DE REFERENCIA POR GÉNERO (en segundos)
# =============================================================================

DURACIONES_GENERO = {
    "tech_house":        {"min": 300, "max": 420, "label": "5–7 minutos"},
    "house":             {"min": 300, "max": 420, "label": "5–7 minutos"},
    "techno":            {"min": 330, "max": 480, "label": "5:30–8 minutos"},
    "techno_acido":      {"min": 330, "max": 480, "label": "5:30–8 minutos"},
    "hard_techno":       {"min": 300, "max": 420, "label": "5–7 minutos"},
    "minimal":           {"min": 330, "max": 480, "label": "5:30–8 minutos"},
    "dub_techno":        {"min": 360, "max": 540, "label": "6–9 minutos"},
    "progressive_house": {"min": 360, "max": 540, "label": "6–9 minutos"},
    "trance":            {"min": 360, "max": 540, "label": "6–9 minutos"},
    "psytrance":         {"min": 420, "max": 540, "label": "7–9 minutos"},
    "melodic_techno":    {"min": 360, "max": 540, "label": "6–9 minutos"},
    "deep_house":        {"min": 300, "max": 420, "label": "5–7 minutos"},
    "afro_house":        {"min": 360, "max": 480, "label": "6–8 minutos"},
    "indie_dance":       {"min": 240, "max": 360, "label": "4–6 minutos"},
    "breaks":            {"min": 300, "max": 420, "label": "5–7 minutos"},
    "hard_dance":        {"min": 240, "max": 360, "label": "4–6 minutos"},
    "dnb":               {"min": 210, "max": 330, "label": "3:30–5:30 minutos"},
    "organic_house":     {"min": 360, "max": 540, "label": "6–9 minutos"},
}

# =============================================================================
# ESTRUCTURA ESPERADA POR GÉNERO
# =============================================================================

ESTRUCTURA_GENERO = {
    "tech_house": {
        "patron": "groove repetitivo con variaciones sutiles",
        "breaks": "cortos (8–16 compases), no rompen demasiado la energía",
        "builds": "tensión gradual con filtros y percusión",
        "nota": "En tech house el groove ES el track. La estructura se construye quitando y poniendo elementos sobre un patrón rítmico sólido.",
    },
    "house": {
        "patron": "secciones claras con builds y drops progresivos",
        "breaks": "moderados (16–32 compases), dan respiro",
        "builds": "crescendo con percusión, pads y efectos",
        "nota": "El house clásico tiene una narrativa clara: intro → build → drop → breakdown → build → drop → outro. No reinventes la rueda.",
    },
    "techno": {
        "patron": "evolución constante con capas que entran y salen",
        "breaks": "pueden ser largos si mantienen tensión (percusión, texturas)",
        "builds": "hipnóticos, basados en repetición + adición gradual",
        "nota": "En techno la evolución es más importante que los golpes de efecto. Las transiciones pueden ser lentas y funcionar perfectamente.",
    },
    "techno_acido": {
        "patron": "línea de 303 como eje, con variaciones de filtro",
        "breaks": "generalmente cortos, la 303 puede mantener la energía sola",
        "builds": "filtro del ácido abriendo gradualmente + capas percusivas",
        "nota": "El ácido tiene su propia narrativa: el filtro de la 303 sube y baja la tensión. Aprovecha eso como herramienta estructural.",
    },
    "minimal": {
        "patron": "micro-variaciones sobre un patrón muy reducido",
        "breaks": "sutiles, a veces solo quitar un elemento basta",
        "builds": "casi imperceptibles, acumulativos",
        "nota": "En minimal, menos es más literalmente. Si tienes más de 8-10 canales, probablemente sobran cosas.",
    },
    "dub_techno": {
        "patron": "loops hipnóticos con acordes con reverb y delay como protagonistas",
        "breaks": "casi imperceptibles, suelen ser cambios de textura más que de energía",
        "builds": "muy graduales, vive en el flotar sostenido más que en el clímax",
        "nota": "El dub techno se construye sobre el espacio. Reverbs largos, delays con feedback, sub profundo. Las variaciones son tímbricas (filtros, automatizaciones de FX), no estructurales. Si lo evalúas con la vara del techno de pista, todo te parecerá 'falta de desarrollo' cuando en realidad es lenguaje.",
    },
    "progressive_house": {
        "patron": "evolución larga y gradual, secciones amplias",
        "breaks": "largos (32–64 compases) con melodías y atmósferas",
        "builds": "épicos, crescendo largo con capas y armonía",
        "nota": "El progressive se toma su tiempo. Los builds de 32+ compases son normales y esperados. No tengas prisa por llegar al drop.",
    },
    "trance": {
        "patron": "intro larga → breakdown emocional → build épico → clímax",
        "breaks": "largos y melódicos (32–64 compases), son el corazón del track",
        "builds": "crescendo emocional, capas de sintes, risers, FX",
        "nota": "En trance, el breakdown largo NO es un problema — es donde vive la emoción. El build hacia el drop es donde se gana o se pierde al oyente.",
    },
    "melodic_techno": {
        "patron": "techno con capas melódicas y atmósferas",
        "breaks": "moderados a largos, con melodía y textura",
        "builds": "combinan percusión techno con crescendo melódico",
        "nota": "El melodic techno vive entre el techno y el progressive. La melodía da emoción pero el groove da energía. Equilibra ambos.",
    },
    "deep_house": {
        "patron": "groove relajado con progresiones de acordes",
        "breaks": "suaves, a veces solo quitar el kick basta",
        "builds": "orgánicos, sin prisa",
        "nota": "El deep house es sobre sensación, no sobre impacto. Si tu break suena demasiado dramático, probablemente no encaja en el género.",
    },
    "hard_techno": {
        "patron": "kicks distorsionados y tempo rápido (140-160 BPM)",
        "breaks": "cortos y tensos, mantienen la presión",
        "builds": "agresivos, basados en distorsión y filtros",
        "nota": "En hard techno el kick es el track. La distorsión y el tempo elevado son parte del lenguaje — pero ojo con el rango dinámico: que esté limitado no significa que tenga que sonar plano.",
    },
    "psytrance": {
        "patron": "bassline rodante 16ths + capas psicodélicas",
        "breaks": "largos y melódicos, con FX y atmósferas",
        "builds": "graduales, con risers y modulaciones de filtro",
        "nota": "En psytrance el bajo es el motor. El groove kick+bass funciona como un solo elemento y debe ser tight. Cuida especialmente el rango 60-120Hz.",
    },
    "afro_house": {
        "patron": "percusión orgánica latina/africana + 4/4 house",
        "breaks": "moderados, sostenidos por la percusión",
        "builds": "acumulación de capas percusivas y vocales",
        "nota": "El afro house vive de la percusión orgánica. Los hi-hats programados y las congas dan vida al groove — no los tapes con elementos digitales fuertes.",
    },
    "indie_dance": {
        "patron": "estructura tipo canción con bajo prominente",
        "breaks": "cortos, dan paso a versos o estribillos",
        "builds": "cantados o instrumentales con melodía clara",
        "nota": "El indie dance se mueve entre canción y club. La estructura puede tener verso-estribillo, pero el groove de pista tiene que sostenerse.",
    },
    "breaks": {
        "patron": "breakbeat (no 4/4) + bajo prominente",
        "breaks": "definidos, con cambios rítmicos claros",
        "builds": "típicamente con tensión rítmica antes del drop",
        "nota": "En breaks el ritmo no es lineal — el groove vive en el shuffle. Asegúrate de que el kick y el snare tengan suficiente espacio para que el patrón se entienda.",
    },
    "hard_dance": {
        "patron": "kick distorsionado protagonista + melodías eufóricas o raw",
        "breaks": "melódicos y emocionales, preparan el siguiente drop",
        "builds": "agresivos, con risers y screeches hacia el kick del drop",
        "nota": "En hard dance / hardstyle el kick ES el track: cuerpo distorsionado y tono afinado a la tonalidad. La energía es alta por diseño; cuida que el kick tenga pegada y no se coma toda la mezcla, y que el rango dinámico no quede totalmente plano.",
    },
    "dnb": {
        "patron": "breakbeat rápido (~174 BPM) + sub/reese protagonista",
        "breaks": "el breakdown baja energía antes del 'drop' (cambio de bajo)",
        "builds": "tensión con risers y corte de graves antes de soltar el bajo",
        "nota": "En drum & bass el groove vive en el breakbeat y el bajo es el motor. El momento clave es el drop donde entra el reese/sub — debe pegar fuerte y limpio. Cuida la relación kick+snare+sub y que el sub no emborrone.",
    },
    "organic_house": {
        "patron": "groove orgánico y atmosférico con melodía y textura",
        "breaks": "largos y envolventes, viven de la atmósfera más que del impacto",
        "builds": "graduales y sin prisa, acumulando capas melódicas y percusión orgánica",
        "nota": "El organic / melodic house es sobre viaje y atmósfera, no sobre golpes de efecto. Deja respirar la mezcla: instrumentos orgánicos, reverbs amplios y un bajo redondo que no tape la melodía. Si suena demasiado dramático o saturado, probablemente no encaja en el género.",
    },
}

# =============================================================================
# REFERENCIAS DE LUFS POR GÉNERO (target + rango aceptable)
# =============================================================================

LUFS_GENERO = {
    "techno":             {"target": -8,  "rango": "-7 a -9"},
    "techno_acido":       {"target": -8,  "rango": "-7 a -9"},
    "hard_techno":        {"target": -7,  "rango": "-6 a -8"},
    "trance":             {"target": -9,  "rango": "-8 a -10"},
    "deep_house":         {"target": -10, "rango": "-9 a -11"},
    "house":              {"target": -9,  "rango": "-8 a -10"},
    "tech_house":         {"target": -8,  "rango": "-7 a -9"},
    "minimal":            {"target": -9,  "rango": "-8 a -10"},
    "dub_techno":         {"target": -11, "rango": "-10 a -13"},
    "progressive_house":  {"target": -10, "rango": "-9 a -11"},
    "melodic_techno":     {"target": -9,  "rango": "-8 a -10"},
    "afro_house":         {"target": -9,  "rango": "-8 a -10"},
    "indie_dance":        {"target": -9,  "rango": "-8 a -10"},
    "breaks":             {"target": -8,  "rango": "-7 a -9"},
    "psytrance":          {"target": -8,  "rango": "-7 a -9"},
    "hard_dance":         {"target": -6,  "rango": "-5 a -7"},
    "dnb":                {"target": -8,  "rango": "-7 a -9"},
    "organic_house":      {"target": -10, "rango": "-9 a -11"},
}


# =============================================================================
# TIPS SEGÚN OBJETIVO
# =============================================================================

TIPS_OBJETIVO = {
    "pinchar": {
        "mantra": "Si no se puede mezclar, no se puede pinchar.",
        "enfoque_ok": "Tu track tiene intro y outro adecuadas para mezclar. Ahora asegúrate de que la energía sea predecible para el DJ y que no haya sorpresas raras en los primeros/últimos 30 segundos.",
        "enfoque_falta_intro": "Para que funcione en sesión necesitas una intro limpia de al menos 32 compases para que el DJ pueda mezclar la entrada. Ahora mismo tu track arranca demasiado rápido.",
        "enfoque_falta_outro": "Tu track necesita un outro limpio de al menos 32 compases para que el DJ pueda salir con una transición suave. Ahora mismo el final es demasiado abrupto.",
        "enfoque_falta_ambos": "Para que funcione en sesión necesitas: intro y outro limpias de al menos 32 compases. Ahora mismo el track no tiene la estructura necesaria para que un DJ pueda mezclarlo cómodamente.",
        "prioridad_extra_ok": "Prueba a mezclar tu track con otro del mismo género para confirmar que las transiciones funcionan.",
        "prioridad_extra_fix": "Prueba a mezclar tu track con otro del mismo género. ¿La intro permite una transición limpia? ¿El outro da tiempo suficiente para salir?",
    },
    "aprender": {
        "mantra": "Cada problema es una clase práctica.",
        "enfoque": "Este track es tu campo de entrenamiento. No importa si el resultado final no es publicable — lo que importa es que entiendas POR QUÉ el diagnóstico detecta esto y aprendas a escucharlo tú.",
        "prioridad_extra": "Antes de aplicar los cambios, escucha el track e intenta identificar tú el problema que se describe. Entrenar el oído es más valioso que arreglar un track.",
    },
    "sellos": {
        "mantra": "Envía siempre tu mejor versión — masterizada y a volumen competitivo.",
        "enfoque": "Si tu objetivo es enviar a sellos, el track necesita estar a nivel profesional en estructura, mezcla y energía. Envía siempre la versión masterizada — es tu carta de presentación. Si te firman y quieren masterizarlo ellos, les mandas la versión sin mastering después. Por eso es clave que tu mezcla suene bien por sí sola, sin depender de la cadena de mastering para sonar bien.",
        "prioridad_extra": "Compara tu intro con la de 3 tracks de referencia del sello al que quieres enviar. ¿Engancha igual de rápido?",
        "prioridad_extra_mezcla": "Bypasea tu cadena de mastering y escucha solo la mezcla. ¿Suena equilibrada y con energía? Si sin mastering suena débil o desequilibrada, trabaja primero la mezcla antes de volver a masterizar.",
    },
    "todo": {
        "mantra": "Primero que funcione, después que brille.",
        "enfoque": "Quieres que tu track sirva para todo: tocarlo, publicarlo y enviarlo a sellos. Eso significa que tiene que cumplir el estándar más exigente de los tres. Enfócate primero en que la estructura y la mezcla sean sólidas — un track bien construido funciona en cualquier contexto.",
        "prioridad_extra": "Define qué versión necesitas primero: un extended mix para DJ o un edit para plataformas. Trabaja una y adapta la otra después.",
    },
}

# =============================================================================
# ADAPTACIONES POR EXPERIENCIA
# =============================================================================

TONO_EXPERIENCIA = {
    "menos_6m": {
        "estilo": "cercano",
        "prefijo_motivacion": "Que esto no te desanime — es completamente normal en esta fase.",
        "nota_proceso": "Producir música tiene una curva de aprendizaje larga. Cada track que terminas (aunque suene mal) te enseña más que diez tutoriales.",
        "nivel_tecnico": "basico",
    },
    "6m_2a": {
        "estilo": "equilibrado",
        "prefijo_motivacion": "Buen trabajo llegando hasta aquí.",
        "nota_proceso": "Ya llevas un recorrido. Ahora es cuando empiezas a desarrollar criterio propio — y eso a veces significa ver problemas donde antes no los veías.",
        "nivel_tecnico": "intermedio",
    },
    "2a_5a": {
        "estilo": "directo",
        "prefijo_motivacion": "Esto tiene solución directa.",
        "nota_proceso": "Con tu experiencia, probablemente ya intuías algo de esto. Confía en ese instinto y usa el diagnóstico para confirmar y priorizar.",
        "nivel_tecnico": "avanzado",
    },
    "mas_5a": {
        "estilo": "conciso",
        "prefijo_motivacion": "Al grano:",
        "nota_proceso": "Sabes de qué va esto. El diagnóstico es un segundo par de oídos objetivo, no un profesor.",
        "nivel_tecnico": "avanzado",
    },
}


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def contextualizar_feedback(diagnostico_id: str, contexto: dict, senales: dict) -> dict:
    """
    Genera feedback contextualizado basado en el diagnóstico, contexto del usuario
    y señales de audio. Retorna campos adicionales para enriquecer el resultado.
    """
    genero = contexto.get("genero", "")
    experiencia = contexto.get("experiencia", "")
    objetivo = contexto.get("objetivo", "")
    fase = contexto.get("fase", "")
    dificultad = contexto.get("dificultad_habitual", "")

    resultado = {
        "nota_contextual": "",
        "tips_genero": [],
        "tip_objetivo": "",
        "referencia_temporal": "",
        "prioridades_extra": [],
        "nota_motivacional": "",
        "referencia_lufs_genero": "",
    }

    # --- Nota motivacional según experiencia ---
    tono = TONO_EXPERIENCIA.get(experiencia, TONO_EXPERIENCIA["6m_2a"])
    if diagnostico_id == "sin_diagnostico":
        resultado["nota_motivacional"] = "Buenas noticias:"
    else:
        resultado["nota_motivacional"] = tono["prefijo_motivacion"]

    # --- Tips de género ---
    info_genero = ESTRUCTURA_GENERO.get(genero)
    if info_genero:
        resultado["tips_genero"] = _generar_tips_genero(diagnostico_id, info_genero, genero, senales)

    # --- Tip según objetivo ---
    # ¿Track en fase temprana? Si lo es, no empujamos lenguaje de "máster/sello"
    # aunque el objetivo sea enviar a sellos: primero hay que cerrar el track.
    # Feedback 2026-06 (n43/n47/n100): tracks tempranos recibían el enfoque de
    # "envía masterizado a A&Rs", descontextualizado.
    _madurez = senales.get("madurez_estimada", "")
    _track_temprano = (
        diagnostico_id in ("track_verde", "problema_arreglo", "poco_contraste")
        or _madurez == "verde"
    )
    info_objetivo = TIPS_OBJETIVO.get(objetivo)
    if info_objetivo:
        if objetivo == "pinchar":
            # Contextualizar según si el track ya tiene intro/outro adecuadas
            dist = senales.get("distribucion", {})
            falta_intro = dist.get("inicio_abrupto", False)
            falta_outro = dist.get("sin_outro", False)

            if falta_intro and falta_outro:
                resultado["tip_objetivo"] = info_objetivo["enfoque_falta_ambos"]
                resultado["prioridades_extra"].append(info_objetivo["prioridad_extra_fix"])
            elif falta_intro:
                resultado["tip_objetivo"] = info_objetivo["enfoque_falta_intro"]
                resultado["prioridades_extra"].append(info_objetivo["prioridad_extra_fix"])
            elif falta_outro:
                resultado["tip_objetivo"] = info_objetivo["enfoque_falta_outro"]
                resultado["prioridades_extra"].append(info_objetivo["prioridad_extra_fix"])
            else:
                resultado["tip_objetivo"] = info_objetivo["enfoque_ok"]
                resultado["prioridades_extra"].append(info_objetivo["prioridad_extra_ok"])
        elif objetivo == "sellos" and _track_temprano:
            resultado["tip_objetivo"] = (
                "Tu objetivo es enviar a sellos, pero este track todavía está en una fase "
                "temprana. Antes de pensar en máster o en A&Rs, céntrate en cerrar la "
                "estructura y la mezcla — un sello descarta en los primeros segundos un track "
                "sin terminar. Cuando esté cerrado, volvemos al enfoque de sello."
            )
        else:
            resultado["tip_objetivo"] = info_objetivo["enfoque"]
            resultado["prioridades_extra"].append(info_objetivo["prioridad_extra"])

        # Para sellos: prioridad de mezcla solo cuando el track NO es temprano
        # (si lo es, el foco es cerrar el track, no comparar máster con el sello).
        if (objetivo == "sellos" and not _track_temprano
                and info_objetivo.get("prioridad_extra_mezcla")):
            dx_mezcla = [
                "exceso_lowend", "carencia_espectral", "exceso_densidad",
                "harshness_mezcla",
            ]
            if diagnostico_id in dx_mezcla:
                resultado["prioridades_extra"].append(info_objetivo["prioridad_extra_mezcla"])

    # --- Referencia temporal (BPM → compases en segundos) ---
    bpm = senales.get("bpm", 0)
    if bpm > 0:
        seg_8_compases = round((60.0 / bpm) * 4 * 8, 1)
        seg_16_compases = round(seg_8_compases * 2, 1)
        resultado["referencia_temporal"] = (
            f"A {bpm:.0f} BPM, 8 compases duran ~{seg_8_compases:.0f}s "
            f"y 16 compases ~{seg_16_compases:.0f}s."
        )

    # --- Referencia LUFS por género (comparar medición vs target del género) ---
    lufs_ref = LUFS_GENERO.get(genero)
    lufs_medido = senales.get("loudness", {}).get("lufs_integrado", -99)
    if lufs_ref and lufs_medido > -50:
        target = lufs_ref["target"]
        rango = lufs_ref["rango"]
        diff = lufs_medido - target
        label_g = _label_genero(genero)
        if abs(diff) <= 1.5:
            resultado["referencia_lufs_genero"] = (
                f"Tu LUFS integrado ({lufs_medido:.1f}) está en el rango habitual de "
                f"{label_g} ({rango} LUFS)."
            )
        elif diff > 0:
            resultado["referencia_lufs_genero"] = (
                f"Tu LUFS integrado ({lufs_medido:.1f}) está {abs(diff):.1f}dB por encima "
                f"del target típico de {label_g} ({target} LUFS, rango {rango})."
            )
        else:
            resultado["referencia_lufs_genero"] = (
                f"Tu LUFS integrado ({lufs_medido:.1f}) está {abs(diff):.1f}dB por debajo "
                f"del target típico de {label_g} ({target} LUFS, rango {rango})."
            )

    # --- Nota contextual (la pieza central personalizada) ---
    resultado["nota_contextual"] = _generar_nota_contextual(
        diagnostico_id, contexto, senales, tono, info_genero, info_objetivo
    )

    # --- Disclaimer para diagnósticos espectrales/tonales ---
    diagnosticos_con_disclaimer = [
        "exceso_lowend", "carencia_espectral", "exceso_densidad",
        "conflicto_armonico", "pobreza_armonica",
    ]
    if diagnostico_id in diagnosticos_con_disclaimer:
        resultado["disclaimer"] = (
            "Este diagnóstico se basa en lo que es habitual en el género que has seleccionado "
            "y en estándares de producción profesional. Si tu intención creativa es precisamente "
            "romper con esos estándares (un balance atípico, una textura inusual, una disonancia "
            "deliberada), confía en tu criterio. La clave es que sea una decisión consciente. "
            "Esta herramienta está para señalarte cosas que quizá no estabas teniendo en cuenta, "
            "no para limitar tu creatividad."
        )

    # --- Aviso de género fuera de scope (música no-electrónica de club) ---
    # En el feedback hemos visto usuarios con tracks de vallenato, indie pop,
    # rock, reggaeton, etc. El motor está calibrado para electrónica de club;
    # los diagnósticos no aplican igual fuera de eso. Detectamos sub-géneros
    # comunes en el campo libre de "Otro" para avisar al inicio del informe.
    if genero == "otro":
        custom = (contexto.get("genero_custom") or "").lower()
        # Whitelist: si el custom contiene una palabra electrónica conocida,
        # NO disparar el aviso aunque también contenga ruido. Evita falsos
        # positivos como "rock electrónico" o "indie dance pop".
        _whitelist_electronic = (
            "tech", "techno", "house", "trance", "minimal", "ambient", "drum",
            "dnb", "d&b", "garage", "dubstep", "electro", "edm", "dance",
            "downtempo", "breakbeat", "breaks", "psy", "hardstyle", "hardcore",
            "dub techno", "deep", "future", "club", "rave",
        )
        es_electronic_friendly = any(k in custom for k in _whitelist_electronic)

        _palabras_no_electronicas = (
            "vallenato", "salsa", "bachata", "merengue", "cumbia", "mariachi",
            "ranchera", "banda", "mambo", "rumba", "tango", "samba", "bossa",
            "reggaeton", "reggaetón", "dembow", "perreo",
            "pop ", " pop", "indie pop", "k-pop", "kpop",
            "rock", "metal", "punk", "grunge", "hardcore punk",
            "rap", "hip hop", "hip-hop", "trap latino", "drill",
            "jazz", "blues", "soul", "gospel", "r&b", "rnb",
            "country", "folk", "bluegrass",
            "reggae", "ska",
            "classical", "clásica", "clasica", "sinfónic", "sinfonic",
            "opera", "ópera", "flamenco", "fandango",
            "vals", "paso doble", "polka", "celta", "afrobeat", "afrobeats",
        )
        match_no_electronic = next(
            (p.strip() for p in _palabras_no_electronicas if p in custom),
            None,
        )
        if match_no_electronic and not es_electronic_friendly:
            resultado["aviso_genero"] = (
                f"Mentotrack está calibrado específicamente para música electrónica de club "
                f"(house, techno, trance y derivados). Has marcado '{contexto.get('genero_custom', '').strip()}' "
                f"como género — el motor todavía aplica sus reglas, pero algunos diagnósticos pueden no encajar "
                f"con las convenciones de tu estilo. Trátalo como una segunda opinión técnica, no como verdad absoluta."
            )

    return resultado


# =============================================================================
# GENERADORES ESPECÍFICOS
# =============================================================================

def _generar_tips_genero(diagnostico_id: str, info_genero: dict, genero: str, senales: dict) -> list:
    """Genera tips específicos del género relevantes para el diagnóstico."""
    tips = []
    duracion_ref = DURACIONES_GENERO.get(genero)

    if diagnostico_id in ("problema_arreglo", "track_verde", "poco_contraste"):
        tips.append(info_genero["nota"])

        if duracion_ref:
            dur_seg = senales.get("duracion_seg", 0)
            if dur_seg > 0 and dur_seg < duracion_ref["min"]:
                tips.append(
                    f"Tu track dura {senales.get('duracion_fmt', '?')}. "
                    f"Para {_label_genero(genero)}, lo habitual es {duracion_ref['label']}. "
                    f"No hace falta que llegues ahí ahora, pero tenlo como referencia."
                )

        if diagnostico_id == "poco_contraste":
            tips.append(
                f"Estructura típica: {info_genero['patron']}. "
                f"Los breaks en este género suelen ser {info_genero['breaks'].lower()}."
            )

        if diagnostico_id == "problema_arreglo":
            dist = senales.get("distribucion", {})
            if dist.get("break_desproporcionado"):
                tips.append(
                    f"En {_label_genero(genero)}, los breaks son {info_genero['breaks'].lower()}. "
                    f"Si tu sección de baja energía es muy larga, considera acortarla o añadir "
                    f"elementos que mantengan el interés (percusión, texturas, variaciones rítmicas)."
                )
            if dist.get("drop_corto"):
                tips.append(
                    f"Los builds en {_label_genero(genero)} son {info_genero['builds'].lower()}. "
                    f"Tu sección de alta energía parece corta — dale más espacio para desarrollarse."
                )

    elif diagnostico_id == "exceso_lowend":
        # Géneros con kicks prominentes vs sutiles
        generos_kick_fuerte = ["techno", "techno_acido", "tech_house", "minimal"]
        if genero in generos_kick_fuerte:
            tips.append(
                f"En {_label_genero(genero)} el kick es protagonista, así que algo de dominancia "
                f"grave es normal. Pero si enmascara al bajo o al resto de elementos, hay que limpiar."
            )
        else:
            tips.append(
                f"En {_label_genero(genero)} el low-end suele ser más contenido. "
                f"Revisa que el kick y el bajo no estén compitiendo y que haya espacio para "
                f"las melodías y atmósferas."
            )

    elif diagnostico_id == "exceso_densidad":
        generos_densos = ["techno", "trance"]
        if genero in generos_densos:
            tips.append(
                f"{_label_genero(genero)} puede sonar denso, pero incluso en este género "
                f"necesitas momentos de respiro. La densidad debe variar entre secciones."
            )
        else:
            tips.append(
                f"En {_label_genero(genero)}, el espacio es parte del sonido. "
                f"Menos elementos bien colocados suenan mejor que muchos compitiendo."
            )

    elif diagnostico_id == "falta_impacto":
        tips.append(
            f"En {_label_genero(genero)}, el impacto del drop es clave. "
            f"Escucha una referencia con un medidor de volumen y fíjate en cómo "
            f"la energía baja justo antes del drop y sube al entrar."
        )
        bpm = senales.get("bpm", 0)
        if bpm > 0:
            compas_seg = 4 * 60 / bpm
            tips.append(
                f"A {bpm} BPM, prueba a hacer la automatización de bajada de volumen "
                f"durante los últimos 4 compases antes del drop ({compas_seg * 4:.0f}s). "
                f"Una bajada sutil de 1-3dB es suficiente para crear la sensación de impacto."
            )

    elif diagnostico_id == "carencia_espectral":
        carencia_medios = senales.get("carencia_medios", False)
        carencia_agudos = senales.get("carencia_agudos", False)
        generos_percusivos_ce = ["techno", "techno_acido", "minimal", "tech_house", "hard_techno"]
        generos_melodicos_ce = ["trance", "progressive_house", "melodic_techno",
                                "deep_house", "house", "afro_house", "indie_dance"]

        # Sugerencias por pista cuando faltan MEDIOS (200 Hz – 2 kHz)
        if carencia_medios:
            if genero in generos_percusivos_ce:
                tips.append(
                    "Para llenar medios (200 Hz – 2 kHz) en este género suele faltar percusión "
                    "con cuerpo: claps con peso, snares con tono, congas, toms o shakers de "
                    "frecuencia media. Un stab corto o una textura de pad recortada también ayudan."
                )
            elif genero in generos_melodicos_ce:
                tips.append(
                    "Para llenar medios (200 Hz – 2 kHz) suele faltar la zona donde viven leads, "
                    "voces, stabs y la parte alta del bajo. Revisa si tu lead principal tiene "
                    "cuerpo en esa banda o si está demasiado en agudos; añade un pad de mid-range "
                    "o una capa de plucks para rellenar."
                )
            else:
                tips.append(
                    "Faltan medios (200 Hz – 2 kHz): la zona donde 'vive el cuerpo' del track. "
                    "Revisa percusiones de tono medio (claps, snares, congas), la parte alta del "
                    "bajo, y elementos sostenidos como pads o stabs."
                )

        # Sugerencias por pista cuando faltan AGUDOS (>5 kHz)
        if carencia_agudos:
            if genero in generos_percusivos_ce:
                tips.append(
                    "Para llenar agudos (>5 kHz) en este género lo más rápido es trabajar el bus "
                    "de percusión metálica: hi-hats cerrados, charles abiertos, rides, shakers. "
                    "Un crash bien colocado al cambio de sección también suma aire."
                )
            elif genero in generos_melodicos_ce:
                tips.append(
                    "Para llenar agudos (>5 kHz) suele faltar aire en los elementos sostenidos: "
                    "high-shelf suave (+1-2dB a 8-10kHz) sobre pads, leads y voces. También crashes, "
                    "risers y reverbs con cola en agudos durante los builds y aperturas."
                )
            else:
                tips.append(
                    "Faltan agudos (>5 kHz): es lo que aporta brillo y 'aire'. Mira hi-hats, "
                    "shakers, rides, crashes, y las colas de reverb de los pads o leads."
                )

        # Cierre de comparación con referencias — siempre
        tips.append(
            f"Como contraste, escucha 2-3 referencias de {_label_genero(genero)} y haz A/B: "
            f"¿qué pistas tiene la referencia en esas zonas que tú no tienes?"
        )

    elif diagnostico_id == "conflicto_armonico":
        generos_tonales = ["trance", "progressive_house", "melodic_techno", "deep_house"]
        generos_percusivos = ["techno", "techno_acido", "minimal"]
        if genero in generos_tonales:
            tips.append(
                f"En {_label_genero(genero)} la armonía es fundamental. Si hay elementos "
                f"en tonalidades distintas, se nota mucho. Asegúrate de que todo esté en "
                f"la misma escala."
            )
        elif genero in generos_percusivos:
            tips.append(
                f"Aunque {_label_genero(genero)} es más percusivo, los pocos elementos "
                f"tonales que uses (bajo, stabs, FX tonales) deben ser coherentes entre sí."
            )
        else:
            tips.append(
                f"En {_label_genero(genero)}, verifica que todos los loops y samples "
                f"melódicos estén en la misma tonalidad antes de seguir trabajando el track."
            )
        # Añadir info de key detectada
        armonia = senales.get("armonia", {})
        if armonia.get("key") and armonia.get("key_confidence", 0) > 0.5:
            tips.append(
                f"Tonalidad detectada: {armonia['key']} {armonia.get('modo', '')} "
                f"(confianza: {armonia['key_confidence']:.0%}). Úsalo como referencia "
                f"para verificar que tus elementos encajan."
            )

    elif diagnostico_id == "pobreza_armonica":
        generos_melodicos = ["trance", "progressive_house", "melodic_techno", "deep_house", "house"]
        generos_percusivos = ["techno", "techno_acido", "minimal"]
        if genero in generos_melodicos:
            tips.append(
                f"En {_label_genero(genero)}, el contenido melódico es parte esencial "
                f"de la identidad del track. Sin un elemento tonal claro (lead, pad, vocal, "
                f"progresión de acordes), el track pierde su gancho emocional."
            )
        elif genero in generos_percusivos:
            tips.append(
                f"En {_label_genero(genero)} no siempre hace falta melodía, pero incluso "
                f"un bajo con movimiento de notas o un stab puntual pueden dar mucha vida al track."
            )

    elif diagnostico_id == "harshness_mezcla":
        harshness = senales.get("harshness", {})
        zona = harshness.get("zona_problema", "")
        generos_percusivos_h = ["techno", "techno_acido", "minimal", "tech_house", "hard_techno"]
        generos_melodicos_h = ["trance", "progressive_house",
                               "melodic_techno", "deep_house"]

        if zona == "presencia":
            if genero in generos_percusivos_h:
                tips.append(
                    f"En {_label_genero(genero)}, la energía entre 2-6kHz suele venir de "
                    f"hi-hats, claps y leads percusivos. Soluciona el harshness identificando "
                    f"qué elemento es el más adelante: solea cada track de tu bus de percusión "
                    f"y baja el que más empuje en esa banda. Un EQ dinámico es preferible a "
                    f"un corte estático."
                )
            elif genero in generos_melodicos_h:
                tips.append(
                    f"En {_label_genero(genero)}, los 2-6kHz son la zona donde brillan leads "
                    f"y vocales. Si chirría, probablemente el lead principal está saturando esa "
                    f"banda. Prueba un de-esser sobre el lead o un EQ dinámico con threshold "
                    f"suave a 3-4kHz."
                )
            else:
                tips.append(
                    "La zona de 2-6kHz controla la sensación de 'estar adelante' en la mezcla. "
                    "Si chirría, hay demasiados elementos peleando por esa banda."
                )
        elif zona == "brillos":
            if genero in generos_melodicos_h:
                tips.append(
                    f"En {_label_genero(genero)} los crashes, risers y reverbs de synths viven "
                    f"en 6-10kHz. Revisa los tails: aplica un low-pass shelf suave en las colas "
                    f"de los reverbs y baja el envío de high-shelf de los crashes."
                )
            elif genero in generos_percusivos_h:
                tips.append(
                    f"En {_label_genero(genero)} la zona de 6-10kHz viene casi siempre de "
                    f"hi-hats abiertos, shakers y crashes. Si te suena duro, baja el bus de "
                    f"percusión aguda 1-2dB o pon un shelf -2dB a 8kHz en el master."
                )
            else:
                tips.append(
                    "Los 6-10kHz dan brillo y aire, pero exceso ahí fatiga el oído. "
                    "Revisa hi-hats, crashes, reverbs y exciters."
                )
        elif zona == "ambas":
            tips.append(
                "El rango entero de agudos está empujando. Antes de tocar EQs individuales, "
                "bypasea el limiter de master y vuelve a escuchar: si la harshness baja, el "
                "problema es de mastering. Si persiste, hay un problema general de mezcla "
                "en agudos que tienes que resolver pista a pista."
            )

        # Pista extra según carácter del pico (transitorio/sostenido/mixto)
        caracter_h = harshness.get("caracter", "")
        peak_khz_h = harshness.get("peak_freq_hz", 0) / 1000.0
        if caracter_h == "transitorio" and peak_khz_h > 0:
            tips.append(
                f"El pico en {peak_khz_h:.1f} kHz aparece en ráfagas cortas: empieza soleando "
                f"hi-hats, claps, snares y otros elementos percusivos. Aplica un EQ dinámico "
                f"sobre ese bus con threshold suave en esa frecuencia para que solo actúe en "
                f"los picos."
            )
        elif caracter_h == "sostenido" and peak_khz_h > 0:
            tips.append(
                f"El pico en {peak_khz_h:.1f} kHz es sostenido: revisa primero los elementos "
                f"que permanecen tocando largo (leads, pads, voces, reverbs largos). Un "
                f"high-shelf de -2dB sobre el lead o una cola más corta en el reverb suele "
                f"resolverlo."
            )
        elif caracter_h == "mixto" and peak_khz_h > 0:
            tips.append(
                f"El pico en {peak_khz_h:.1f} kHz combina golpes y sostenidos: revisa tanto "
                f"el bus de percusión metálica como los leads/pads dominantes en esa banda. "
                f"Atacar solo uno no va a resolverlo."
            )

        # Aviso fijo de cierre — independiente de género y zona
        tips.append(
            "Pista universal: cuando hay chirrido, lo primero que casi siempre vale la pena "
            "bajar son los hi-hats abiertos, rides, shakers y crashes. Bypasea ese bus en "
            "el momento más harsh del track y compara — si el chirrido cae notablemente, "
            "ya tienes el culpable."
        )

    return tips


def _generar_nota_contextual(
    diagnostico_id: str,
    contexto: dict,
    senales: dict,
    tono: dict,
    info_genero: dict | None,
    info_objetivo: dict | None,
) -> str:
    """Genera la nota contextual personalizada — el párrafo central del feedback."""
    experiencia = contexto.get("experiencia", "")
    objetivo = contexto.get("objetivo", "")
    fase = contexto.get("fase", "")
    dificultad = contexto.get("dificultad_habitual", "")
    genero = contexto.get("genero", "")

    partes = []

    # --- Conexión experiencia + diagnóstico ---
    if diagnostico_id == "problema_arreglo":
        if experiencia == "menos_6m":
            partes.append(
                "Estructurar un track es de lo más difícil cuando empiezas. "
                "No es que estés haciendo algo mal — es que esta habilidad se desarrolla "
                "con la práctica. Cada track que estructures te saldrá más natural."
            )
        elif experiencia in ("6m_2a",):
            partes.append(
                "Ya tienes herramientas para crear ideas que suenan bien, "
                "pero convertir un loop en un track completo es el siguiente nivel. "
                "Es exactamente donde se atasca la mayoría en tu etapa."
            )
        elif experiencia in ("2a_5a", "mas_5a"):
            partes.append(
                "El problema de estructura a veces aparece incluso con experiencia — "
                "sobre todo cuando una idea te gusta mucho y te cuesta decidir cómo desarrollarla. "
                "La clave es tomar decisiones rápido y comprometerte con ellas."
            )

    elif diagnostico_id == "poco_contraste":
        if experiencia == "menos_6m":
            partes.append(
                "El contraste es lo que hace que un track cuente una historia en vez de ser "
                "un loop largo. No hace falta que sea dramático — basta con quitar algunos "
                "elementos en unas secciones y añadirlos en otras."
            )
        else:
            partes.append(
                "El contraste es lo que distingue un track que engancha de uno que se vuelve "
                "monótono. Tu track tiene elementos, pero les falta variación entre secciones."
            )

    elif diagnostico_id == "mezcla_prematura":
        partes.append(
            "Es tentador ponerse a mezclar cuando las cosas empiezan a sonar bien, "
            "pero mezclar un arreglo incompleto es como pintar las paredes de una casa "
            "sin terminar los cimientos."
        )

    elif diagnostico_id == "exceso_lowend":
        if experiencia == "menos_6m":
            partes.append(
                "Los graves son la zona más complicada de controlar, especialmente "
                "si produces con auriculares o monitores pequeños. "
                "Lo importante es que kick y bajo se escuchen por separado con claridad."
            )
        else:
            partes.append(
                "El exceso de graves suele ser un problema de acumulación: kick, bajo, "
                "pads con contenido sub, efectos con cola grave... Cada uno parece poco, "
                "pero juntos saturan la zona."
            )

    elif diagnostico_id == "falta_impacto":
        if experiencia == "menos_6m":
            partes.append(
                "¿Sabes esa sensación cuando un drop entra y se siente potente? "
                "El secreto no está en subir el volumen del drop, sino en bajar la energía "
                "justo antes. Es contraintuitivo, pero es uno de los trucos más usados "
                "en producción profesional."
            )
        else:
            partes.append(
                "El impacto de un drop se crea con contraste de volumen: si la subida llega "
                "al mismo nivel que el drop, no hay sorpresa. Una automatización sutil de volumen "
                "hacia abajo en los últimos compases antes del drop crea esa sensación de 'explosión' "
                "cuando entra. 1-3dB de bajada es suficiente."
            )

    elif diagnostico_id == "exceso_densidad":
        partes.append(
            "Hay una paradoja en producción: cuantos más elementos pones, peor suena. "
            "No es falta de sonidos, es falta de espacio. El silencio relativo es un "
            "instrumento más."
        )

    elif diagnostico_id == "track_verde":
        if experiencia == "menos_6m":
            partes.append(
                "Tu idea está ahí, y eso es lo que importa ahora. "
                "No te preocupes por cómo suena — preocúpate por qué pasa en el track. "
                "¿Qué quieres que sienta quien lo escuche?"
            )
        else:
            partes.append(
                "Tienes una idea que funciona como punto de partida. "
                "El reto ahora es extenderla sin perder lo que la hace interesante."
            )

    elif diagnostico_id == "carencia_espectral":
        partes.append(
            "Un track con poca presencia en medios o agudos suena apagado y sin vida, "
            "incluso si la idea es buena. No es cuestión de subir volúmenes — es de "
            "añadir elementos que llenen esas zonas del espectro."
        )

    elif diagnostico_id == "conflicto_armonico":
        armonia = senales.get("armonia", {})
        key_info = ""
        if armonia.get("key") and armonia.get("key_confidence", 0) > 0.4:
            key_info = f" La tonalidad principal detectada es {armonia['key']} {armonia.get('modo', '')}."
        if experiencia == "menos_6m":
            partes.append(
                "Los conflictos armónicos son difíciles de detectar al principio — "
                "tu oído los registra como 'algo suena raro' sin saber exactamente qué. "
                "Lo más probable es que tengas samples o loops en tonalidades distintas." + key_info
            )
        else:
            partes.append(
                "Cuando hay elementos en tonalidades distintas, el track suena turbio "
                "o tenso de una forma que no es intencional. Es sutil pero hace que todo "
                "suene menos profesional." + key_info
            )

    elif diagnostico_id == "pobreza_armonica":
        if experiencia == "menos_6m":
            partes.append(
                "No necesitas ser un experto en teoría musical para dar contenido armónico a tu track. "
                "Un bajo con 3-4 notas distintas o un pad con un acorde simple ya cambian completamente "
                "la sensación del track."
            )
        elif experiencia in ("6m_2a",):
            partes.append(
                "Tu track funciona rítmicamente pero le falta un ancla melódica — algo que "
                "el oyente pueda recordar o tararear, aunque sea un simple motivo de 4 notas."
            )
        else:
            partes.append(
                "A veces un track técnicamente correcto no conecta porque no tiene un elemento "
                "tonal que le dé identidad. Un hook melódico o una progresión sencilla pueden "
                "ser la diferencia."
            )

    elif diagnostico_id == "sin_diagnostico":
        partes.append(
            "El análisis no detecta bloqueos evidentes. Eso puede significar que "
            "el track está en buen camino, o que el problema está en un aspecto "
            "creativo o de detalle fino."
        )

    # --- Conexión dificultad habitual + diagnóstico ---
    if dificultad == diagnostico_id.replace("problema_arreglo", "estructura"):
        pass  # El diagnóstico ya coincide con su dificultad habitual
    elif dificultad == "terminar" and diagnostico_id in ("problema_arreglo", "track_verde", "poco_contraste"):
        partes.append(
            "Dices que terminar tracks es lo que más te cuesta. "
            "Este diagnóstico está directamente relacionado: resolver la estructura "
            "es el primer paso para poder cerrar un track."
        )
    elif dificultad == "mezcla" and diagnostico_id in ("problema_arreglo", "poco_contraste", "track_verde"):
        partes.append(
            "Mencionas que la mezcla es tu mayor dificultad habitual, pero en este track "
            "el primer cuello de botella es otro. La buena noticia: una vez resuelvas "
            "la estructura, la mezcla será más fácil porque cada elemento tendrá su sitio."
        )
    elif dificultad == "sonidos" and diagnostico_id == "carencia_espectral":
        partes.append(
            "Tu dificultad habitual es encontrar buenos sonidos, y eso conecta con "
            "lo que se detecta aquí: falta contenido en ciertas zonas del espectro. "
            "Prueba a buscar sonidos que complementen lo que ya tienes en vez de "
            "buscar sonidos que suenen bien solos."
        )
    elif dificultad == "todo":
        if experiencia == "menos_6m":
            partes.append(
                "Dices que todo te cuesta — y es normal cuando llevas poco tiempo. "
                "En vez de intentar mejorar todo a la vez, enfócate solo en lo que dice "
                "este diagnóstico. Un problema a la vez."
            )
        else:
            partes.append(
                "Mencionas que todo te cuesta. Este diagnóstico te da un foco concreto "
                "para esta sesión — no intentes resolver todo, solo esto."
            )

    # --- Conexión objetivo ---
    if objetivo == "pinchar" and diagnostico_id in ("problema_arreglo", "track_verde"):
        dist = senales.get("distribucion", {})
        falta_intro = dist.get("inicio_abrupto", False)
        falta_outro = dist.get("sin_outro", False)
        if falta_intro or falta_outro:
            partes.append(
                "Si tu objetivo es pincharlo, necesitas como mínimo una intro y outro "
                "limpias de al menos 16 compases (idealmente 32) para que el DJ pueda mezclar."
            )
        else:
            partes.append(
                "Tu track tiene intro y outro, lo cual es esencial para pincharlo. "
                "Asegúrate de que las transiciones sean limpias y predecibles para el DJ."
            )
    elif objetivo == "sellos" and diagnostico_id not in ("sin_diagnostico",):
        _temprano_s = (
            diagnostico_id in ("track_verde", "problema_arreglo", "poco_contraste")
            or senales.get("madurez_estimada") == "verde"
        )
        if _temprano_s:
            partes.append(
                "Sé que el objetivo es enviarlo a sellos, pero este track aún no está en ese "
                "punto. Cierra primero lo que marca el diagnóstico — el enfoque de sello "
                "(máster competitivo, comparar con releases del sello) llega cuando el track "
                "esté terminado, no antes."
            )
        else:
            partes.append(
                "Para enviar a sellos, este problema debería estar completamente resuelto. "
                "Un A&R lo detectaría en los primeros 30 segundos de escucha. "
                "Recuerda: envía siempre tu mejor versión masterizada, pero asegúrate de que "
                "la mezcla suene bien por sí sola sin la cadena de mastering — si te firman, "
                "probablemente te pidan la versión sin masterizar."
            )

    # --- Dato contextual temporal ---
    bpm = senales.get("bpm", 0)
    if bpm > 0 and diagnostico_id in ("problema_arreglo", "poco_contraste", "track_verde"):
        seg_16 = round((60.0 / bpm) * 4 * 16)
        seg_32 = round((60.0 / bpm) * 4 * 32)
        partes.append(
            f"Referencia práctica: a {bpm:.0f} BPM, 16 compases duran ~{seg_16}s "
            f"y 32 compases ~{seg_32}s. Úsalo para planificar la duración de tus secciones."
        )

    return " ".join(partes) if partes else ""


def _reconstruir_secciones(bloques_rms: list) -> list:
    """Reconstruye las secciones alto/bajo desde bloques_rms (misma lógica que
    _analizar_distribucion del extractor). Devuelve [(tipo, longitud, inicio), …]."""
    if not bloques_rms or len(bloques_rms) < 4:
        return []
    media = sum(bloques_rms) / len(bloques_rms)
    clasif = ["alto" if b > media else "bajo" for b in bloques_rms]
    secciones = []
    t, l, s = clasif[0], 1, 0
    for i in range(1, len(clasif)):
        if clasif[i] == t:
            l += 1
        else:
            secciones.append((t, l, s))
            t, l, s = clasif[i], 1, i
    secciones.append((t, l, s))
    return secciones


def generar_sugerencias_estructura(diagnostico_id: str, contexto: dict, senales: dict) -> list:
    """Sugerencias de estructura CONCRETAS y LOCALIZADAS (con timecode) a partir
    del mapa de energía que ya calcula el motor + la plantilla del género. No es
    análisis nuevo: cruza la distribución real de secciones contra cómo debería
    ser el género y emite 2-5 acciones puntuales. Feedback 2026-06 (5 votos)."""
    bloques = senales.get("bloques_rms") or []
    n_bloques = senales.get("n_bloques", len(bloques)) or len(bloques)
    dur = senales.get("duracion_seg", 0)
    genero = contexto.get("genero", "")
    dist = senales.get("distribucion", {}) or {}

    if not bloques or n_bloques < 4 or dur <= 0:
        return []

    # Cinturón de seguridad: en géneros estáticos (minimal, dub techno, ambient,
    # hypnotic…) la estructura de club no aplica — no sugerimos drops/builds. En
    # la práctica el diagnóstico estructural ya está gatekept a 0 para estos
    # géneros, pero lo blindamos aquí también.
    try:
        if es_genero_estatico(contexto, senales):
            return []
    except Exception:
        pass

    spb = dur / n_bloques  # segundos por bloque

    def t(b):
        s = int(max(0, b) * spb)
        return f"{s // 60}:{s % 60:02d}"

    info = ESTRUCTURA_GENERO.get(genero)
    dur_ref = DURACIONES_GENERO.get(genero)
    label_g = _label_genero(genero)
    secciones = _reconstruir_secciones(bloques)
    bi, bf = dist.get("break_bloque_inicio", -1), dist.get("break_bloque_fin", -1)
    # ¿La sección baja más larga tiene energía alta ANTES? Si no, es la intro,
    # no un break real — no la tratamos como "break desproporcionado".
    hay_alto_antes = bi > 0 and any(s[0] == "alto" and s[2] < bi for s in secciones)

    especificas = []   # localizadas y puntuales — prioridad alta
    generales = []     # contextuales — prioridad baja

    # Break (con o sin payoff). break_sin_payoff ya exige una sección alta antes.
    if dist.get("break_sin_payoff") and bi >= 0:
        especificas.append(
            f"Break sin payoff: el break entre {t(bi)} y {t(bf)} no genera subida al volver. "
            f"Justo antes de {t(bf)} mete un build (riser + filtro abriendo ~8 compases) y "
            "diferencia el drop posterior con una capa nueva (percusión, sub o vocal) para que "
            "se sienta liberación."
        )
    elif dist.get("break_desproporcionado") and hay_alto_antes:
        breaks_desc = info["breaks"].lower() if info else "moderados"
        especificas.append(
            f"Break largo: la sección de baja energía entre {t(bi)} y {t(bf)} es desproporcionada. "
            f"En {label_g} los breaks suelen ser {breaks_desc} — acórtala o mete variación dentro "
            "(percusión, textura, un giro) para que no se desinfle."
        )

    if dist.get("inicio_abrupto"):
        especificas.append(
            "Intro: el track arranca con energía alta desde 0:00. Añade ~16-32 compases de intro "
            "(kick + percusión + 1 elemento) para que un DJ pueda mezclar la entrada."
        )
    if dist.get("sin_outro"):
        especificas.append(
            f"Outro: el track termina con energía alta (sobre {t(n_bloques - 1)}) sin bajar. Añade "
            "~16-32 compases de salida quitando elementos para una transición limpia."
        )
    if dist.get("drop_corto"):
        especificas.append(
            f"Drop corto: tu sección de más energía dura poco. En {label_g} los drops principales "
            "suelen ser de 32-64 compases — dale más recorrido antes de cambiar de sección."
        )

    if not senales.get("tiene_desarrollo") and senales.get("contraste_energetico") == "bajo":
        generales.append(
            "Desarrollo: apenas hay cambios de energía entre secciones. Diseña al menos un break "
            "claro (quita el kick + filtra) y un build de subida — el contraste es lo que hace que "
            "el track 'respire'."
        )
    if dur_ref and dur < dur_ref["min"]:
        generales.append(
            f"Duración: tu track dura {senales.get('duracion_fmt', '?')}; en {label_g} lo habitual es "
            f"{dur_ref['label']}. Si es para pista, extiende intro/outro y añade una segunda variación "
            "del drop."
        )

    # Máximo 3: priorizamos las localizadas; rellenamos con generales si hay hueco.
    resultado = especificas[:3]
    for g in generales:
        if len(resultado) >= 3:
            break
        resultado.append(g)
    return resultado


def _label_genero(genero: str) -> str:
    """Convierte el ID del género a su label legible."""
    labels = {
        "tech_house": "Tech House",
        "house": "House",
        "techno": "Techno",
        "techno_acido": "Techno Ácido",
        "hard_techno": "Hard Techno",
        "minimal": "Minimal",
        "dub_techno": "Dub Techno",
        "progressive_house": "Progressive House",
        "trance": "Trance",
        "psytrance": "Psytrance",
        "melodic_techno": "Melodic Techno",
        "deep_house": "Deep House",
        "afro_house": "Afro House",
        "indie_dance": "Indie Dance",
        "breaks": "Breaks",
        "otro": "tu género",
    }
    return labels.get(genero, "tu género")
