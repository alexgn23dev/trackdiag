"""
Contextualizador de feedback.
Toma el diagnóstico base + contexto del usuario + señales de audio
y genera texto adaptado a experiencia, género, objetivo y fase.

Principio: el diagnóstico no cambia, pero la forma de comunicarlo sí.
"""

# =============================================================================
# DURACIONES DE REFERENCIA POR GÉNERO (en segundos)
# =============================================================================

DURACIONES_GENERO = {
    "tech_house":        {"min": 300, "max": 420, "label": "5–7 minutos"},
    "house":             {"min": 300, "max": 420, "label": "5–7 minutos"},
    "techno":            {"min": 330, "max": 480, "label": "5:30–8 minutos"},
    "techno_acido":      {"min": 330, "max": 480, "label": "5:30–8 minutos"},
    "minimal":           {"min": 330, "max": 480, "label": "5:30–8 minutos"},
    "progressive_house": {"min": 360, "max": 540, "label": "6–9 minutos"},
    "trance":            {"min": 360, "max": 540, "label": "6–9 minutos"},
    "progressive_trance":{"min": 420, "max": 600, "label": "7–10 minutos"},
    "melodic_techno":    {"min": 360, "max": 540, "label": "6–9 minutos"},
    "deep_house":        {"min": 300, "max": 420, "label": "5–7 minutos"},
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
    "progressive_trance": {
        "patron": "builds muy largos, evolución hipnótica",
        "breaks": "extensos, con capas melódicas y atmósferas",
        "builds": "graduales, casi meditativos, muy largos",
        "nota": "El progressive trance es un viaje. Los builds de 64+ compases son normales. La clave es que cada compás añada algo sutil.",
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
}

# =============================================================================
# TIPS SEGÚN OBJETIVO
# =============================================================================

TIPS_OBJETIVO = {
    "terminar": {
        "mantra": "Menos decisiones, más ejecución.",
        "enfoque": "Tu objetivo es cerrar este track, no perfeccionarlo. Cada decisión que tomes ahora debería acercarte al bounce final, no abrir nuevas ramas creativas.",
        "prioridad_extra": "Pon una fecha límite realista y comprométete a hacer el bounce final ese día, aunque no sea perfecto.",
    },
    "aprender": {
        "mantra": "Cada problema es una clase práctica.",
        "enfoque": "Este track es tu campo de entrenamiento. No importa si el resultado final no es publicable — lo que importa es que entiendas POR QUÉ el diagnóstico detecta esto y aprendas a escucharlo tú.",
        "prioridad_extra": "Antes de aplicar los cambios, escucha el track e intenta identificar tú el problema que se describe. Entrenar el oído es más valioso que arreglar un track.",
    },
    "sellos": {
        "mantra": "Los sellos buscan tracks terminados, no ideas con potencial.",
        "enfoque": "Si tu objetivo es enviar a sellos, el track necesita estar a nivel profesional en estructura, mezcla y energía. Los A&R escuchan los primeros 30 segundos — si no engancha ahí, no llegan al drop.",
        "prioridad_extra": "Compara tu intro con la de 3 tracks de referencia del sello al que quieres enviar. ¿Engancha igual de rápido?",
    },
    "pinchar": {
        "mantra": "Si no se puede mezclar, no se puede pinchar.",
        "enfoque_ok": "Tu track tiene intro y outro adecuadas para mezclar. Ahora asegúrate de que la energía sea predecible para el DJ y que no haya sorpresas raras en los primeros/últimos 30 segundos.",
        "enfoque_falta_intro": "Para que funcione en sesión necesitas una intro limpia de al menos 32 compases para que el DJ pueda mezclar la entrada. Ahora mismo tu track arranca demasiado rápido.",
        "enfoque_falta_outro": "Tu track necesita un outro limpio de al menos 32 compases para que el DJ pueda salir con una transición suave. Ahora mismo el final es demasiado abrupto.",
        "enfoque_falta_ambos": "Para que funcione en sesión necesitas: intro y outro limpias de al menos 32 compases. Ahora mismo el track no tiene la estructura necesaria para que un DJ pueda mezclarlo cómodamente.",
        "prioridad_extra_ok": "Prueba a mezclar tu track con otro del mismo género para confirmar que las transiciones funcionan.",
        "prioridad_extra_fix": "Prueba a mezclar tu track con otro del mismo género. ¿La intro permite una transición limpia? ¿El outro da tiempo suficiente para salir?",
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
        else:
            resultado["tip_objetivo"] = info_objetivo["enfoque"]
            resultado["prioridades_extra"].append(info_objetivo["prioridad_extra"])

    # --- Referencia temporal (BPM → compases en segundos) ---
    bpm = senales.get("bpm", 0)
    if bpm > 0:
        seg_8_compases = round((60.0 / bpm) * 4 * 8, 1)
        seg_16_compases = round(seg_8_compases * 2, 1)
        resultado["referencia_temporal"] = (
            f"A {bpm:.0f} BPM, 8 compases duran ~{seg_8_compases:.0f}s "
            f"y 16 compases ~{seg_16_compases:.0f}s."
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
        generos_densos = ["techno", "trance", "progressive_trance"]
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

    elif diagnostico_id == "carencia_espectral":
        tips.append(
            f"Escucha 2-3 referencias de {_label_genero(genero)} y compara qué elementos "
            f"llenan la zona media y alta. Fíjate en percusiones, hi-hats, texturas y capas "
            f"de apoyo que dan cuerpo y brillo."
        )

    elif diagnostico_id == "conflicto_armonico":
        generos_tonales = ["trance", "progressive_trance", "progressive_house", "melodic_techno", "deep_house"]
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
        generos_melodicos = ["trance", "progressive_trance", "progressive_house", "melodic_techno", "deep_house", "house"]
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
        partes.append(
            "Para enviar a sellos, este problema debería estar completamente resuelto. "
            "Un A&R lo detectaría en los primeros 30 segundos de escucha."
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


def _label_genero(genero: str) -> str:
    """Convierte el ID del género a su label legible."""
    labels = {
        "tech_house": "Tech House",
        "house": "House",
        "techno": "Techno",
        "techno_acido": "Techno Ácido",
        "minimal": "Minimal",
        "progressive_house": "Progressive House",
        "trance": "Trance",
        "progressive_trance": "Progressive Trance",
        "melodic_techno": "Melodic Techno",
        "deep_house": "Deep House",
        "otro": "tu género",
    }
    return labels.get(genero, "tu género")
