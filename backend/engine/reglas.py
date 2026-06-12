"""
Motor de reglas diagnósticas.
Evalúa hipótesis, aplica jerarquía pedagógica y genera el diagnóstico final.
"""

# Recalibrado con 38 sesiones: 3 era demasiado alto, muchos falsos "sin_diagnostico"
UMBRAL_MINIMO_CONFIANZA = 2


# =============================================================================
# Familias de género reutilizadas por varias reglas
# =============================================================================
# Géneros "estáticos" — la repetición prolongada, el bajo contraste energético
# y la falta de desarrollo son lenguaje del estilo, no fallos de mezcla/arreglo.
GENEROS_ESTATICOS = ["minimal", "ambient", "drone", "downtempo", "dub_techno"]

# Palabras-clave para detectar género estático cuando el usuario escribe en
# texto libre (campo `genero_custom` cuando genero == "otro"). Ampliada tras
# el feedback de usuarios que trabajan sub-géneros nicho (deetron, hypnotic
# deep, micro house, raw techno, etc.) y recibían dx descontextualizados.
PALABRAS_CUSTOM_ESTATICO = [
    "ambient", "drone", "downtempo", "dub techno", "dub_techno",
    "atmosfer", "ambiente",
    # Sub-géneros minimalistas / repetitivos detectados en feedback (2026-05):
    "minimal", "micro", "deetron", "hypnotic", "raw", "tool",
]


def es_genero_estatico(contexto: dict, senales: dict) -> bool:
    """True si el género (catálogo o texto libre) o la heurística atmosférica
    indican que estructura repetitiva / contraste bajo es lenguaje del estilo.
    Centraliza el check para que todas las reglas lo usen igual."""
    genero = contexto.get("genero", "")
    custom = (contexto.get("genero_custom") or "").lower()
    armonia = senales.get("armonia", {}) or {}
    parece_atmosferico = (
        genero == "otro"
        and armonia.get("ratio_tonal_percusivo", 1.0) > 2.5
        and armonia.get("contenido_tonal", 0.5) > 0.55
    )
    return (
        genero in GENEROS_ESTATICOS
        or any(k in custom for k in PALABRAS_CUSTOM_ESTATICO)
        or parece_atmosferico
    )


def evaluar_diagnosticos(senales: dict, contexto: dict) -> tuple[dict, dict]:
    scores = {}
    detalles = {}

    bloqueo = contexto.get("bloqueo_percibido", "").lower()
    fase = contexto.get("fase", "")
    dificultad = contexto.get("dificultad_habitual", "")
    dist = senales["distribucion"]

    # Localización temporal del break más largo, para dar razones con timecode
    # ("el break entre 2:10 y 3:00"). Feedback 2026-06 (n8/n34/n140): el usuario
    # pedía referencias de sección concretas, no lenguaje general.
    def _fmt_t(seg: float) -> str:
        seg = int(seg)
        return f"{seg // 60}:{seg % 60:02d}"
    _nb = senales.get("n_bloques", 0) or 0
    _spb = (senales.get("duracion_seg", 0) / _nb) if _nb else 0
    _b_ini = dist.get("break_bloque_inicio", -1)
    _b_fin = dist.get("break_bloque_fin", -1)
    _tc_break = ""
    if _b_ini >= 0 and _b_fin > _b_ini and _spb > 0:
        _tc_break = f" (aprox. entre {_fmt_t(_b_ini * _spb)} y {_fmt_t(_b_fin * _spb)})"

    # --- 1: Problema de arreglo / estructura ---
    score, razones = 0, []
    if not senales["tiene_desarrollo"]:
        score += 3; razones.append("No se detectan cambios significativos de energía entre secciones")
    if senales["contraste_energetico"] == "bajo":
        score += 2; razones.append("El contraste energético entre bloques es bajo")
    if fase in ["idea", "arreglo_en_progreso"]:
        score += 2; razones.append(f"El usuario indica estar en fase: {fase}")
    if senales["duracion_seg"] < 120:
        score += 2; razones.append(f"Duración muy corta ({senales['duracion_fmt']})")
    elif senales["duracion_seg"] < 180:
        score += 1; razones.append(f"Duración corta ({senales['duracion_fmt']})")
    if dificultad in ["estructura", "terminar", "todo"]:
        score += 1; razones.append(f"Dificultad habitual del usuario: {dificultad}")
    if senales["n_bloques"] <= 2:
        score += 2; razones.append(f"Solo se detectan {senales['n_bloques']} bloques de energía")
    if dist["break_desproporcionado"]:
        score += 3; razones.append(f"Hay una sección de baja energía desproporcionadamente larga ({dist['max_seccion_baja']} bloques de {senales['n_bloques']}){_tc_break}")
    if dist["drop_corto"]:
        score += 2; razones.append(f"La sección de alta energía más larga es muy corta ({dist['max_seccion_alta']} bloques)")
    if dist["inicio_abrupto"]:
        score += 1; razones.append("El track empieza directamente con energía alta, sin introducción gradual")
    if dist["sin_outro"]:
        score += 1; razones.append("El track termina con energía alta, sin outro gradual")
    # Track con buen contraste y desarrollo: descontar puntos de estructura
    if senales["contraste_energetico"] in ["medio", "alto"] and senales["tiene_desarrollo"] and not dist["estructura_problematica"]:
        score -= 3; razones.append("(−) El track muestra buen contraste, desarrollo y distribución")
    # Gatekeeper por género estático (minimal, ambient, dub techno, etc.):
    # contraste bajo y poco desarrollo son lenguaje del género, no problema.
    # Se aplica el mismo criterio que en mezcla_prematura — calculado al inicio
    # de esa rama. Para no duplicar, lo recalculamos local aquí.
    if es_genero_estatico(contexto, senales) and not dist["estructura_problematica"]:
        # Capping a 0 — conservamos el diagnóstico solo si la distribución de
        # secciones está realmente rota (señal específica, no global).
        if score > 0:
            score = 0
        razones.append("(−) En géneros estáticos (minimal, ambient, dub techno…), poco contraste y bajo desarrollo son intencionales")
    scores["problema_arreglo"] = score
    detalles["problema_arreglo"] = razones

    # --- 2: Falta de desarrollo / estructura pobre ---
    # SOLO se activa en casos MUY obvios: loops continuos sin parones, sin desarrollo real.
    # NO opinamos sobre "contraste entre secciones" porque es subjetivo y difícil de acertar.
    # Si hay al menos un parón/break y desarrollo, no damos este diagnóstico.
    score, razones = 0, []
    if not senales["tiene_desarrollo"] and senales["contraste_energetico"] == "bajo" and senales["duracion_seg"] > 150:
        # Caso claro: track largo, sin desarrollo, sin contraste = loop continuo
        score += 4; razones.append("El track suena como un loop continuo sin desarrollo ni variaciones de energía")
    elif not senales["tiene_desarrollo"] and senales["duracion_seg"] > 180:
        score += 2; razones.append("Track largo sin cambios significativos de energía — falta desarrollo")
    if senales["cambios_significativos"] == 0 and senales["duracion_seg"] > 120:
        score += 2; razones.append("No se detectan transiciones ni parones en todo el track")
    if any(p in bloqueo for p in ["repetitivo", "repite", "loop", "monótono", "monotono", "aburrido", "igual"]):
        score += 2; razones.append("El usuario percibe repetitividad")
    if dist["break_desproporcionado"] and senales["duracion_seg"] > 150:
        score += 2; razones.append("Hay un break tan largo que el track pierde narrativa")
    if senales["duracion_seg"] < 120:
        score -= 2; razones.append("(−) Track muy corto — es normal que no haya mucho desarrollo aún")
    # Si hay desarrollo y contraste, descartar este diagnóstico
    if senales["tiene_desarrollo"] and senales["contraste_energetico"] in ["medio", "alto"]:
        score -= 3; razones.append("(−) El track tiene desarrollo y variación de energía")
    # Gatekeeper género estático: en ambient/minimal/dub techno, "loop continuo
    # sin desarrollo" es lenguaje del género. Si el usuario no se queja de
    # repetitividad, no diagnosticar.
    _usuario_se_queja_repe = any(p in bloqueo for p in
                                  ["repetitivo", "repite", "loop", "monóton", "monoton", "aburrido", "igual"])
    if es_genero_estatico(contexto, senales) and not _usuario_se_queja_repe:
        if score > 0:
            score = 0
        razones.append("(−) En géneros estáticos (minimal, ambient, dub techno…), un loop continuo es lenguaje del género")
    scores["poco_contraste"] = score
    detalles["poco_contraste"] = razones

    # --- 2b: Falta de impacto (rango dinámico bajo) ---
    # SOLO diagnosticar en casos MUY obvios donde el track es realmente plano.
    # Un rango dinámico de ~2.0 es perfectamente normal en producción electrónica
    # bien comprimida. Solo alertamos cuando es extremadamente bajo (<1.5).
    # Recalibrado: track de productor profesional con rango 1.99 generaba falso positivo.
    score, razones = 0, []
    if senales["tiene_desarrollo"] and senales["duracion_seg"] > 120:
        if senales["rango_dinamico"] < 1.4:
            score += 3; razones.append(f"Rango dinámico extremadamente bajo ({senales['rango_dinamico']:.1f}) — el track suena completamente plano, sin diferencia entre partes")
        elif senales["rango_dinamico"] < 1.6:
            score += 1; razones.append(f"Rango dinámico bastante bajo ({senales['rango_dinamico']:.1f}) — poca diferencia de volumen entre secciones")
        # Cruce: loudness alto + rango dinámico MUY bajo = over-compression clara
        loudness = senales.get("loudness", {})
        if senales["rango_dinamico"] < 1.6 and loudness.get("nivel") in ["alto", "muy_alto"]:
            score += 1; razones.append("Loudness alto combinado con rango dinámico muy bajo — posible over-compression")
    # Track corto o sin desarrollo: no aplica
    if senales["duracion_seg"] < 120:
        score -= 2; razones.append("(−) Track corto — el impacto del drop no es relevante aún")
    if not senales["tiene_desarrollo"]:
        score -= 2; razones.append("(−) Sin estructura clara — el problema es de desarrollo, no de impacto")
    scores["falta_impacto"] = score
    detalles["falta_impacto"] = razones

    # --- 3: Mezcla prematura ---
    score, razones = 0, []
    palabras_mezcla = ["mezcla", "mix", "eq", "ecualiz", "compres", "volumen", "paneo", "pan",
                       "master", "loudness", "nivel", "db", "sidechain"]
    usuario_enfocado_mezcla = any(p in bloqueo for p in palabras_mezcla)
    fase_mezcla = fase in ["ajustando_mezcla", "casi_listo"]
    track_no_maduro = senales["madurez_estimada"] in ["verde", "en_desarrollo"]
    sin_desarrollo = not senales["tiene_desarrollo"]
    contraste_bajo = senales["contraste_energetico"] == "bajo"
    estructura_rota = bool(dist["estructura_problematica"])
    problemas_estructura = sin_desarrollo or contraste_bajo or estructura_rota

    # Gatekeeper por género (añadido 2026-05 tras feedback de Alex):
    # En géneros donde poco desarrollo y bajo contraste son lenguaje del género
    # (minimal, ambient, dub techno, drone, downtempo, etc.), las señales de
    # problemas_estructura son falsos positivos sistemáticos.
    genero_actual = contexto.get("genero", "")
    es_estatico = es_genero_estatico(contexto, senales)

    def _motivo_estructura():
        """Devuelve el texto preciso según qué señal disparó."""
        if estructura_rota:
            return "problemas estructurales en el reparto de secciones"
        if sin_desarrollo and contraste_bajo:
            return "poco desarrollo entre secciones y contraste energético bajo"
        if sin_desarrollo:
            return "poco desarrollo entre secciones"
        if contraste_bajo:
            return "poco contraste energético entre secciones"
        return "señales de arreglo todavía abierto"

    # Cuántas señales fuertes de inmadurez del arreglo hay simultáneamente.
    # Con UNA sola señal débil + fase casi_listo, no debemos diagnosticar
    # "mezcla prematura" — es el patrón de falso positivo más quejado en
    # el feedback (usuario considera el track ya cerrado, motor disiente).
    n_problemas = sum([sin_desarrollo, contraste_bajo, estructura_rota])
    madurez = senales["madurez_estimada"]

    if fase_mezcla and problemas_estructura:
        # Peso modulado por madurez del audio: si el motor también lo ve
        # claramente inmaduro (verde) la señal es fuerte (+4). Si el motor
        # lo ve "en_desarrollo" y solo hay una señal, es ambiguo (+1).
        if madurez == "verde":
            score += 4
        elif n_problemas >= 2:
            score += 3
        else:
            score += 1
        razones.append(f"El usuario dice estar mezclando pero el track presenta {_motivo_estructura()}")
    if usuario_enfocado_mezcla and track_no_maduro:
        score += 3; razones.append("El usuario habla de mezcla pero el track aún no está maduro")
    if fase_mezcla and madurez == "verde":
        score += 2; razones.append("Fase de mezcla declarada en un track claramente verde")
    if usuario_enfocado_mezcla and problemas_estructura:
        score += 1
        razones.append(f"Foco en mezcla cuando hay {_motivo_estructura()}")
    if madurez == "avanzado" and senales["tiene_desarrollo"]:
        score -= 4; razones.append("(−) El track parece avanzado — la mezcla sí es relevante ahora")
    # Cruce: loudness alto + estructura inmadura = el usuario ha masterizado antes de arreglar
    loudness = senales.get("loudness", {})
    loudness_alto = loudness.get("nivel") in ["alto", "muy_alto"]
    if loudness_alto and track_no_maduro:
        score += 2; razones.append("Loudness alto en un track inmaduro — parece que se ha masterizado antes de cerrar el arreglo")
    # Gatekeeper final 1: en géneros estáticos / atmosféricos, neutralizar los
    # positivos derivados de problemas_estructura. Si el usuario aún declara
    # estar mezclando un track verde (madurez), eso se mantiene como señal real.
    if es_estatico and problemas_estructura and madurez != "verde":
        if score > 0:
            score = 0
        etiqueta_gen = (genero_actual if genero_actual in GENEROS_ESTATICOS
                        else "track atmosférico/minimalista")
        razones.append(f"(−) En {etiqueta_gen}, poco desarrollo y bajo contraste suelen ser intencionales — no se diagnostica como mezcla prematura")
    # Gatekeeper final 2: fase casi_listo + el track tiene desarrollo + solo
    # una señal débil de estructura + loudness no excesivo = el usuario está
    # razonablemente cerca de cerrar. Diagnosticar "mezcla prematura" aquí
    # es lo que generó las quejas tipo "el arreglo ya está cerrado".
    if (fase == "casi_listo"
            and madurez == "en_desarrollo"
            and senales["tiene_desarrollo"]
            and n_problemas <= 1
            and not loudness_alto):
        if score > 0:
            score = 0
        razones.append("(−) El track tiene desarrollo y solo una señal floja — en fase casi_listo no se diagnostica como mezcla prematura sin más evidencia")
    scores["mezcla_prematura"] = score
    detalles["mezcla_prematura"] = razones

    # --- 4: Exceso de low-end ---
    # Ponderado por género: géneros oscuros/percusivos toleran más graves
    score, razones = 0, []
    genero = contexto.get("genero", "")
    generos_graves_ok = ["techno", "techno_acido", "minimal", "tech_house",
                         "hard_techno", "psytrance"]
    generos_graves_menos = ["trance", "progressive_house",
                            "melodic_techno", "indie_dance", "organic_house"]
    usuario_menciona_graves = any(p in bloqueo for p in
                                  ["grave", "bajo", "bass", "kick", "bombo", "turbio", "mud", "sub"])
    if senales["balance_grave"] == "excesivo":
        score += 3; razones.append(f"Los graves dominan {senales['diff_grave_media']:.0f}dB por encima de los medios")
    elif senales["balance_grave"] == "elevado":
        score += 1; razones.append(f"Los graves dominan {senales['diff_grave_media']:.0f}dB por encima de los medios")
    if senales["carencia_medios"]:
        score += 1; razones.append(f"Poca presencia en medios (nivel medio: {senales['db_media']:.0f}dB)")
    if senales["carencia_agudos"]:
        score += 1; razones.append(f"Poca presencia en agudos (nivel medio: {senales['db_aguda']:.0f}dB)")
    if usuario_menciona_graves:
        score += 2; razones.append("El usuario percibe problemas en graves")
    # Ajuste por género: en géneros con kick protagonista, ser muy permisivo.
    # tech_house y techno especialmente — el kick prominente es parte del lenguaje.
    # "elevado" → -2 (suficiente para neutralizar el +1 de balance y los +1/+1 de
    # carencias, evitando que se acumule a falso positivo).
    # "excesivo" → -1 (suaviza pero no anula — si pasa de 28dB hay algo real).
    # Géneros donde el kick/bajo es protagonista. deep_house y afro_house añadidos
    # tras feedback de Alex (2026-05): en estos géneros el bajo prominente forma
    # parte del lenguaje y no debe penalizarse como "exceso".
    generos_kick_protagonista = ["techno", "techno_acido", "tech_house", "hard_techno",
                                  "minimal", "deep_house", "afro_house", "dub_techno",
                                  "hard_dance", "dnb"]
    if genero in generos_kick_protagonista:
        if senales["balance_grave"] == "elevado":
            score -= 2; razones.append(f"(−) En {genero} el kick es protagonista — cierta dominancia grave es esperable")
        elif senales["balance_grave"] == "excesivo":
            score -= 1; razones.append(f"(−) En {genero} el kick es protagonista, pero los graves superan ya el rango habitual")
    elif genero in generos_graves_ok:
        # Resto de géneros del grupo (psytrance, etc): descuento moderado
        if senales["balance_grave"] != "excesivo":
            score -= 1; razones.append(f"(−) En {genero}, cierta dominancia grave es natural")
    # En géneros melódicos, el exceso de graves es más problemático
    if genero in generos_graves_menos and senales["balance_grave"] in ["elevado", "excesivo"]:
        score += 1; razones.append(f"(−) En {genero}, el exceso de graves enmascara melodías y atmósferas")
    if not senales["tiene_desarrollo"] and senales["contraste_energetico"] == "bajo":
        score -= 1; razones.append("(−) Hay problemas estructurales más prioritarios")
    if dist["estructura_problematica"]:
        score -= 1; razones.append("(−) La estructura del track tiene problemas más prioritarios")
    # Cruce: graves excesivos + mono compat problemática en graves = problema real de fase/acumulación
    mono = senales.get("mono_compat", {})
    if senales["balance_grave"] in ["elevado", "excesivo"] and mono.get("bandas", {}).get("graves", {}).get("estado") in ["revisar", "problema"]:
        score += 2; razones.append("Los graves están altos Y tienen problemas de compatibilidad mono — posible acumulación de fase entre kick y bajo")
    # Cruce: graves excesivos + densidad alta = todo se pelea en la zona baja
    if senales["balance_grave"] in ["elevado", "excesivo"] and senales["densidad_global"] in ["alta", "saturada"]:
        score += 1; razones.append("Graves altos combinado con densidad alta — demasiados elementos compitiendo en la zona baja")
    # Cruce: graves excesivos + loudness muy alto = el limiter está inflando los graves
    loudness = senales.get("loudness", {})
    if senales["balance_grave"] == "excesivo" and loudness.get("nivel") in ["alto", "muy_alto"]:
        score += 1; razones.append("Graves excesivos con loudness alto — el mastering puede estar inflando artificialmente la zona baja")
    scores["exceso_lowend"] = score
    detalles["exceso_lowend"] = razones

    # --- 5: Exceso de capas / densidad ---
    # SOLO se activa si la densidad medida es alta o saturada.
    # Si la densidad es baja o media, este diagnóstico no aplica (evitar incoherencia).
    score, razones = 0, []
    # Géneros donde la densidad alta es lenguaje del género (kick + percusión
    # densa + capas saturadas son parte de la firma). Añadido 2026-05 tras
    # feedback de Alex: penalizar densidad sin co-síntoma generaba falsos
    # positivos sistemáticos en tech_house/techno/hard_techno.
    generos_densos_naturales = ["tech_house", "techno", "techno_acido",
                                 "hard_techno", "minimal", "psytrance",
                                 "hard_dance", "dnb"]
    if senales["densidad_global"] in ["alta", "saturada"]:
        if senales["densidad_global"] == "saturada":
            score += 3; razones.append(f"Densidad espectral saturada ({senales['densidad_espectral']:.4f})")
        else:
            score += 2; razones.append(f"Densidad espectral alta ({senales['densidad_espectral']:.4f})")
        if senales["rango_dinamico"] < 1.8:
            score += 2; razones.append(f"Muy poco rango dinámico ({senales['rango_dinamico']}) — todo suena al mismo nivel")
        elif senales["rango_dinamico"] < 2.5:
            score += 1; razones.append(f"Rango dinámico reducido ({senales['rango_dinamico']})")
        if any(p in bloqueo for p in ["lleno", "denso", "saturado", "confuso", "empastad", "cargado", "capas"]):
            score += 2; razones.append("El usuario percibe exceso de densidad")
        # Cruce: densidad alta + contraste bajo = muro de sonido (problema real)
        if senales["contraste_energetico"] == "bajo":
            score += 2; razones.append("Densidad alta sin variación — suena como un muro de sonido constante")
        # Cruce: densidad alta + contraste alto = solo son los drops, probablemente ok
        if senales["contraste_energetico"] == "alto":
            score -= 1; razones.append("(−) Hay contraste — la densidad puede ser solo de las secciones de alta energía")
        # Cruce: densidad + loudness alto = posible over-compression aplastando la mezcla
        loudness = senales.get("loudness", {})
        if loudness.get("nivel") in ["alto", "muy_alto"]:
            score += 1; razones.append("Densidad alta combinada con loudness alto — posible over-compression aplastando la mezcla")
        # Descuento por género: si la densidad alta convive con contraste medio/alto
        # en un género denso por naturaleza, no es problema — es lenguaje. Exige
        # un co-síntoma real (contraste bajo, rango dinámico muy reducido o queja
        # del usuario) para mantener el diagnóstico vivo.
        if (genero in generos_densos_naturales
                and senales["densidad_global"] == "alta"
                and senales["contraste_energetico"] in ["medio", "alto"]
                and senales["rango_dinamico"] >= 2.5
                and not any(p in bloqueo for p in ["lleno", "denso", "saturado", "confuso", "empastad", "cargado", "capas"])):
            score -= 3
            razones.append(f"(−) En {genero}, densidad alta con buen contraste y rango dinámico es parte del lenguaje del género, no un problema")
    else:
        # Densidad baja/media: solo considerar si el usuario lo percibe explícitamente
        if any(p in bloqueo for p in ["lleno", "denso", "saturado", "confuso", "empastad", "cargado", "capas"]):
            score += 1; razones.append("El usuario percibe exceso de densidad (aunque las mediciones no lo confirman)")
    scores["exceso_densidad"] = score
    detalles["exceso_densidad"] = razones

    # --- 6: Track verde / idea sin cerrar ---
    score, razones = 0, []
    if senales["madurez_estimada"] == "verde":
        score += 3; razones.append("El track parece estar en fase muy temprana")
    if senales["duracion_seg"] < 90:
        score += 3; razones.append(f"Duración muy corta ({senales['duracion_fmt']})")
    elif senales["duracion_seg"] < 150:
        score += 1; razones.append(f"Duración corta ({senales['duracion_fmt']})")
    if fase == "idea":
        score += 2; razones.append("El usuario confirma estar en fase de idea")
    if senales["n_bloques"] <= 2:
        score += 2; razones.append("Muy pocos bloques de energía detectados")
    if not senales["tiene_desarrollo"]:
        score += 1; razones.append("Sin desarrollo temporal")
    if senales["duracion_seg"] > 240 and senales["tiene_desarrollo"]:
        score -= 4; razones.append("(−) Track largo con desarrollo — no es una idea sin cerrar")
    scores["track_verde"] = score
    detalles["track_verde"] = razones

    # --- 6b: Break sin payoff ---
    # Detecta cuando el break más largo del track no recupera energía después,
    # es decir, la sección que viene tras el break no es más intensa que la
    # que la precedía. Para el oyente: "el break no paga". Añadido tras
    # feedback de Alex (insight 4, 2026-05).
    score, razones = 0, []
    if dist.get("break_sin_payoff"):
        ratio = dist.get("ratio_payoff", 1.0)
        score += 3
        razones.append(
            f"El break más largo{_tc_break} no recupera energía al volver: tras el break la energía es "
            f"{ratio:.2f}× la de antes — el drop posterior se siente como continuación, no como liberación"
        )
        # Cruce: si encima el break es desproporcionado, doble problema
        if dist.get("break_desproporcionado"):
            score += 1
            razones.append("El break es desproporcionadamente largo además de no pagar — la anticipación se desinfla")
        # Cruce: si el usuario menciona el problema
        if any(p in bloqueo for p in ["break", "parón", "paron", "subida", "drop", "anticipa", "intensidad", "engancha", "engancha"]):
            score += 1
            razones.append("El usuario percibe falta de intensidad/anticipación")
    # Si el track es muy corto o la fase es muy temprana, este diagnóstico no aplica
    if senales["duracion_seg"] < 120:
        score -= 3
    if senales["madurez_estimada"] == "verde":
        score -= 2
    scores["break_sin_payoff"] = score
    detalles["break_sin_payoff"] = razones

    # --- 6c: Arreglo repetitivo (track largo con pocas variaciones) ---
    # Distinto de poco_contraste (que mira solo contraste energético) y de
    # problema_arreglo (que mira la distribución de secciones). Apunta al
    # caso "track de 6 minutos con la misma idea durante 4 sin variación".
    score, razones = 0, []
    duracion = senales["duracion_seg"]
    cambios = senales.get("cambios_significativos", 0)
    if duracion > 300:  # >5 min
        if cambios <= 2:
            score += 4
            razones.append(
                f"Track de {senales['duracion_fmt']} con solo {cambios} transición(es) de energía significativa(s) — "
                "la duración no se justifica con la información musical"
            )
        elif cambios <= 4:
            score += 2
            razones.append(
                f"Track de {senales['duracion_fmt']} con solo {cambios} transiciones — "
                "podría aprovechar más variación para no sentirse repetitivo"
            )
    elif duracion > 240:  # 4-5 min
        if cambios <= 2:
            score += 2
            razones.append(
                f"Track de {senales['duracion_fmt']} con solo {cambios} transición(es) — empieza a sentirse repetitivo"
            )
    # Boost si el usuario menciona repetición
    palabras_repe = ["repetitivo", "repite", "monóton", "monoton", "aburrido", "largo",
                      "no engancha", "demasiado largo", "se hace pesado"]
    if any(p in bloqueo for p in palabras_repe):
        score += 2
        razones.append("El usuario percibe el track como repetitivo o demasiado largo")
    # Descuento: si el género es ambient/minimal/dub_techno, la repetición es lenguaje
    if es_genero_estatico(contexto, senales):
        if score > 0:
            score = 0
        razones.append("(−) En géneros estáticos (minimal, ambient, dub techno…), la repetición prolongada es parte del lenguaje")
    # Si hay desarrollo y muchas transiciones, descartar
    if cambios >= 6:
        score -= 3
        razones.append(f"(−) {cambios} transiciones detectadas — el track varía suficiente")
    scores["arreglo_repetitivo"] = score
    detalles["arreglo_repetitivo"] = razones

    # --- 7: Carencia espectral ---
    # Ponderado por género: no todo género necesita el mismo brillo o cuerpo en medios
    score, razones = 0, []
    generos_brillantes = ["trance", "progressive_house",
                          "melodic_techno", "house", "psytrance", "indie_dance"]
    generos_oscuros = ["techno", "techno_acido", "minimal", "hard_techno"]
    if senales["carencia_medios"]:
        score += 3; razones.append(f"Los medios están a {senales['db_media']:.0f}dB — falta cuerpo y presencia en esa zona")
    if senales["carencia_agudos"]:
        score += 2; razones.append(f"Los agudos están a {senales['db_aguda']:.0f}dB — falta brillo y definición")
    if senales["balance_grave"] in ["elevado", "excesivo"]:
        score += 1; razones.append("El exceso de graves acentúa la carencia en el resto del espectro")
    # Ajuste por género: géneros oscuros/percusivos naturalmente tienen menos agudos
    if genero in generos_oscuros:
        if senales["carencia_agudos"] and not senales["carencia_medios"]:
            score -= 2; razones.append(f"(−) En {genero}, un perfil más oscuro es habitual — la carencia de agudos puede ser intencional")
        elif senales["carencia_agudos"]:
            score -= 1; razones.append(f"(−) En {genero}, menos brillo en agudos es aceptable")
    # Géneros brillantes: la carencia pesa más
    if genero in generos_brillantes and senales["carencia_agudos"]:
        score += 1; razones.append(f"En {genero}, la falta de brillo es especialmente notable")
    # Cruce: carencia espectral + densidad baja = track vacío, falta añadir elementos
    if (senales["carencia_medios"] or senales["carencia_agudos"]) and senales["densidad_global"] == "baja":
        score += 1; razones.append("Carencia espectral combinada con densidad baja — el track necesita más elementos que llenen el espectro")
    # Cruce: carencia espectral + loudness bajo = ni volumen ni contenido, fase muy temprana
    loudness = senales.get("loudness", {})
    if (senales["carencia_medios"] or senales["carencia_agudos"]) and loudness.get("nivel") in ["bajo", "muy_bajo"]:
        score -= 1; razones.append("(−) Loudness muy bajo — la carencia puede ser simplemente que el track está sin mezclar/masterizar")
    # Cruce: si hay harshness en medios-altos, la "carencia de agudos" es falsa — hay contenido pero mal balanceado
    harshness = senales.get("harshness", {})
    if harshness.get("tiene_harshness") and senales["carencia_agudos"]:
        score -= 2; razones.append("(−) Hay harshness en medios-altos — no es carencia sino exceso mal distribuido")
    # Gatekeeper de espectro disperso (añadido 2026-05-26 tras reanálisis de
    # 583 tracks): en minimal, afro_house, deep_house, dub_techno — y en
    # géneros nicho que el usuario escribe en "Otro" tipo deetron, micro
    # house, hypnotic deep, raw techno — el espectro con menos cuerpo en
    # medios es lenguaje del estilo. Solo mantenemos el dx si hay refuerzo
    # claro (carencias en ambas bandas + exceso de graves arrastrándolas).
    generos_esparsos = ["minimal", "afro_house", "deep_house", "dub_techno"]
    custom_lower = (contexto.get("genero_custom") or "").lower()
    es_esparso = (
        genero in generos_esparsos
        or any(k in custom_lower for k in PALABRAS_CUSTOM_ESTATICO)
        # Heurística "Otro" + perfil atmosférico: ya cubierta por
        # es_genero_estatico(), reutilizamos.
        or (genero == "otro" and es_genero_estatico(contexto, senales))
    )
    if es_esparso:
        refuerzo_real = (
            senales["carencia_medios"]
            and senales["carencia_agudos"]
            and senales["balance_grave"] in ["elevado", "excesivo"]
        )
        if not refuerzo_real and score > 0:
            score = 0
            etiqueta = genero if genero in generos_esparsos else "este sub-género"
            razones.append(
                f"(−) En {etiqueta}, un espectro con menos cuerpo en medios suele ser parte "
                f"del lenguaje del estilo y no se diagnostica como carencia"
            )
    scores["carencia_espectral"] = score
    detalles["carencia_espectral"] = razones

    # --- 8: Conflicto armónico / problemas tonales ---
    # Conservador: solo diagnosticar cuando hay evidencia fuerte
    score, razones = 0, []
    armonia = senales.get("armonia", {})
    if armonia:
        if armonia.get("posible_conflicto_tonal"):
            score += 3; razones.append(
                "Se detectan indicios claros de conflicto tonal — la armonía cambia de forma inconsistente entre secciones"
            )
        if armonia.get("complejidad_armonica") == "caotica" and armonia.get("key_confidence", 1) < 0.4:
            score += 2; razones.append(
                f"Hay {armonia.get('n_notas_activas', 0)} notas activas sin una tonalidad clara — "
                f"posible choque entre elementos"
            )
        if armonia.get("consistencia_armonica", 1) < 0.4:
            score += 2; razones.append(
                f"La consistencia armónica entre secciones es muy baja ({armonia['consistencia_armonica']:.2f}) — "
                f"posibles elementos en tonalidades distintas"
            )
        elif armonia.get("consistencia_armonica", 1) < 0.55:
            score += 1; razones.append(
                f"Variación armónica notable entre secciones ({armonia['consistencia_armonica']:.2f})"
            )
        # Contexto del usuario
        palabras_armonia = ["nota", "tono", "armon", "acorde", "desafin", "disonant", "melod",
                           "escala", "key", "tonalidad", "chord", "choque"]
        if any(p in bloqueo for p in palabras_armonia):
            score += 2; razones.append("El usuario percibe problemas armónicos o melódicos")
        # Contenido tonal bajo = track muy percusivo, el diagnóstico armónico es menos relevante
        if armonia.get("contenido_tonal", 0) < 0.3:
            score -= 2; razones.append("(−) El track es principalmente percusivo — la armonía es secundaria")
        # Si hay problemas estructurales graves, la armonía es secundaria
        if not senales["tiene_desarrollo"] and senales["contraste_energetico"] == "bajo":
            score -= 1; razones.append("(−) Hay problemas estructurales más prioritarios")
        # Cruce: conflicto armónico + densidad alta = los choques se amplifican
        if armonia.get("posible_conflicto_tonal") and senales["densidad_global"] in ["alta", "saturada"]:
            score += 1; razones.append("Posible conflicto armónico agravado por la densidad alta — muchos elementos compitiendo enturbian más la armonía")
        # Cruce: conflicto armónico + graves excesivos = el low-end enmascara y confunde el análisis tonal
        if armonia.get("consistencia_armonica", 1) < 0.5 and senales["balance_grave"] == "excesivo":
            score -= 1; razones.append("(−) El exceso de graves puede estar enmascarando la información tonal — resolver graves primero")
    # DESACTIVADO (decisión 2026-06): igual que pobreza_armonica, el motor NO emite
    # diagnóstico de "conflicto armónico". Si hay elementos en tonalidades que chocan
    # depende del oído y la intención; el análisis de chroma no lo percibe de forma
    # fiable. Se conserva el cálculo por si se reactivara, pero el score publicado es
    # 0 para que nunca se muestre. Coherente con el disclaimer 'alcance_analisis'.
    scores["conflicto_armonico"] = 0
    detalles["conflicto_armonico"] = razones

    # --- 9: Pobreza armónica / melódica ---
    score, razones = 0, []
    if armonia:
        if armonia.get("contenido_tonal", 0) < 0.25 and senales.get("duracion_seg", 0) > 150:
            score += 2; razones.append(
                f"Muy poco contenido tonal ({armonia['contenido_tonal']:.1%}) para un track de "
                f"{senales['duracion_fmt']} — suena predominantemente percusivo"
            )
        if armonia.get("n_notas_activas", 0) <= 2 and armonia.get("contenido_tonal", 0) > 0.3:
            score += 2; razones.append(
                f"Solo {armonia['n_notas_activas']} notas con presencia significativa — "
                f"hay contenido tonal pero es muy limitado melódicamente"
            )
        if armonia.get("complejidad_armonica") == "simple" and armonia.get("contenido_tonal", 0) > 0.35:
            score += 1; razones.append(
                "La armonía es muy simple — pocas notas activas sobre contenido melódico"
            )
        if armonia.get("key_confidence", 0) < 0.4 and armonia.get("contenido_tonal", 0) > 0.3:
            score += 1; razones.append(
                f"No se identifica una tonalidad clara (confianza: {armonia['key_confidence']:.0%}) — "
                f"los elementos melódicos no están bien definidos tonalmente"
            )
        # Géneros melódicos: la falta de armonía pesa más
        genero = contexto.get("genero", "")
        generos_melodicos = ["trance", "progressive_house", "melodic_techno", "deep_house"]
        generos_percusivos = ["techno", "techno_acido", "minimal", "tech_house"]
        if genero in generos_melodicos and armonia.get("contenido_tonal", 0) < 0.35:
            score += 2; razones.append(
                f"En {genero}, el contenido melódico es parte esencial del género — "
                f"un track predominantemente percusivo pierde identidad"
            )
        elif genero in generos_percusivos:
            score -= 2; razones.append(f"(−) En {genero}, un perfil percusivo puede ser intencional")
    # DESACTIVADO (decisión 2026-06): el motor NO emite diagnóstico de "pobreza
    # armónica". Que una melodía/armonía sea "pobre" depende de factores artísticos
    # y de contexto que el análisis de señal (chroma) no percibe de forma fiable —
    # no es cuestión de género ni de contenido_tonal. Se conserva el cálculo por si
    # se reactivara, pero el score publicado es 0 para que nunca se muestre como
    # diagnóstico. Coherente con el disclaimer 'alcance_analisis'.
    scores["pobreza_armonica"] = 0
    detalles["pobreza_armonica"] = razones

    # --- 10: Harshness / mezcla agresiva en medios-altos ---
    score, razones = 0, []
    harshness = senales.get("harshness", {})
    if harshness:
        if harshness.get("nivel") == "severo":
            score += 4; razones.append(
                f"Medios-altos dominan en {harshness.get('pct_frames_harsh', 0):.0f}% del track con picos de "
                f"{harshness.get('pico_p95', 0):.1f}dB — suena chirriante y agresivo"
            )
        elif harshness.get("nivel") == "notable":
            score += 3; razones.append(
                f"Medios-altos dominan en {harshness.get('pct_frames_harsh', 0):.0f}% del track — "
                f"puede sonar duro o fatigante"
            )
        elif harshness.get("nivel") == "leve":
            score += 1; razones.append(
                f"Ligero exceso puntual en medios-altos (picos de {harshness.get('pico_p95', 0):.1f}dB)"
            )
        # Localización — razones específicas cruzando zona + género
        zona = harshness.get("zona_problema", "")
        peak_hz = harshness.get("peak_freq_hz", 0)
        caracter = harshness.get("caracter", "")
        generos_percusivos = ["techno", "techno_acido", "minimal", "tech_house", "hard_techno"]
        generos_melodicos = ["trance", "progressive_house",
                            "melodic_techno", "deep_house"]

        if zona == "presencia":
            if genero in generos_percusivos:
                razones.append(
                    "Problema en zona de presencia (2-6kHz): probablemente hi-hats metálicos, "
                    "claps con demasiado top o synth leads agresivos. Revisa qué elemento "
                    "percusivo o sintetizado está acumulando energía en esa banda."
                )
            elif genero in generos_melodicos:
                razones.append(
                    "Problema en zona de presencia (2-6kHz): suele venir de leads, voces o "
                    "stabs sintéticos demasiado adelante en la mezcla. Prueba un EQ dinámico "
                    "o de-esser en esa banda sobre los elementos protagonistas."
                )
            else:
                razones.append(
                    "Problema en zona de presencia (2-6kHz) — sintes, voces o percusiones "
                    "pueden estar demasiado adelante"
                )
        elif zona == "brillos":
            if genero in generos_melodicos:
                razones.append(
                    "Problema en zona de brillos (6-10kHz): crashes, risers o reverbs de "
                    "synths con demasiada cola en agudos. Revisa los tails de tus efectos "
                    "y los high shelves de los reverbs."
                )
            elif genero in generos_percusivos:
                razones.append(
                    "Problema en zona de brillos (6-10kHz): hi-hats, shakers o crashes "
                    "demasiado altos. Baja el nivel del bus de percusión aguda o aplica "
                    "un low-pass shelf sutil."
                )
            else:
                razones.append(
                    "Problema en zona de brillos (6-10kHz) — hi-hats, crashes o efectos "
                    "pueden estar demasiado altos"
                )
        elif zona == "ambas":
            razones.append(
                "Todo el rango de agudos está elevado — posible falta de EQ correctivo "
                "general o compresión en el bus master que está empujando los agudos. "
                "Bypasea el limiter de master y comprueba si persiste el problema."
            )

        # Pico exacto + carácter (pistas adicionales sobre el tipo de elemento)
        if peak_hz > 0:
            peak_khz = peak_hz / 1000.0
            if caracter == "transitorio":
                razones.append(
                    f"El pico se concentra en torno a {peak_khz:.1f} kHz y aparece en ráfagas "
                    f"cortas — perfil compatible con percusión (hi-hats, claps, transientes de snare) "
                    f"o golpes secos de elementos sintéticos."
                )
            elif caracter == "sostenido":
                razones.append(
                    f"El pico se concentra en torno a {peak_khz:.1f} kHz de forma sostenida — "
                    f"perfil compatible con leads, voces, pads o reverbs largos en esa banda."
                )
            elif caracter == "mixto":
                razones.append(
                    f"El pico se concentra en torno a {peak_khz:.1f} kHz combinando ráfagas "
                    f"cortas y contenido sostenido — probable mezcla de percusión y elementos "
                    f"tonales empujando la misma banda."
                )

        # Aviso fijo: en casi todos los casos los hi-hats/percusión metálica
        # son corresponsables. Vale la pena recordarlo siempre.
        razones.append(
            "Independientemente del género: una causa muy frecuente de harshness son los "
            "hi-hats abiertos, rides, shakers o crashes con demasiado top. Solea tu bus de "
            "percusión metálica y comprueba si el chirrido baja con un low-pass shelf suave "
            "(-2dB a 8kHz) o bajando 1-2dB ese bus."
        )
        # Cruce: harshness + densidad alta = todo compite y se amplifica
        if harshness.get("tiene_harshness") and senales["densidad_global"] in ["alta", "saturada"]:
            score += 1; razones.append("Harshness agravada por la densidad alta — demasiados elementos compitiendo en la misma zona")
        # Cruce: harshness + loudness alto = el limiter acentúa los picos
        loudness = senales.get("loudness", {})
        if harshness.get("tiene_harshness") and loudness.get("nivel") in ["alto", "muy_alto"]:
            score += 1; razones.append("El loudness alto puede estar acentuando la dureza — el limiter empuja los picos de medios-altos")
        # Contexto usuario
        if any(p in bloqueo for p in ["chirri", "duro", "agresivo", "harsh", "brillante", "molest", "agudo"]):
            score += 2; razones.append("El usuario percibe dureza o exceso en agudos/medios-altos")
        # Descuento por género (añadido 2026-05 tras feedback de Alex):
        # en géneros donde hi-hats agresivos, distorsión y rumble son lenguaje
        # propio (tech house, techno, hard techno, minimal, psytrance), bajar
        # el peso del diagnóstico salvo que sea severo (real). El usuario aún
        # puede ver la métrica si la mira, pero no se levanta como bloqueo.
        generos_agresivos_aceptados = ["tech_house", "techno", "techno_acido",
                                        "hard_techno", "minimal", "psytrance", "dub_techno"]
        if genero in generos_agresivos_aceptados and harshness.get("tiene_harshness"):
            if harshness.get("nivel") == "leve":
                score -= 2
                razones.append(f"(−) En {genero}, hi-hats agresivos o distorsión moderada son parte del género")
            elif harshness.get("nivel") == "notable":
                score -= 1
                razones.append(f"(−) En {genero} se tolera algo de dureza en medios-altos por el lenguaje del género")
    scores["harshness_mezcla"] = score
    detalles["harshness_mezcla"] = razones

    # --- 11: Enmascaramiento bajo↔kick / bajo↔graves-medios ---
    # Detecta cuando el bajo (60-200 Hz) está alto y crea un "agujero" en
    # graves-medios (200-800 Hz), o cuando el sub (0-60 Hz) domina sobre los
    # graves audibles. Síntoma típico: el kick pierde transient, los medios
    # bajos quedan amagados, el bajo "se come" el espacio.
    # Distinto de exceso_lowend, que mira el balance grave→medio global.
    score, razones = 0, []
    bandas = senales.get("espectro_bandas", {}) or {}
    db_graves_b = bandas.get("graves", -80)
    db_low_mid_b = bandas.get("low_mid", -80)
    diff_sub_low = senales.get("diff_sub_low", 0)
    diff_graves_lowmid = db_graves_b - db_low_mid_b

    # Solo aplica si NO es ya un caso claro de exceso_lowend (que tiene su
    # propio diagnóstico). El masking es más sutil: graves dominantes pero el
    # balance global no llega a "excesivo".
    if senales["balance_grave"] != "excesivo":
        if diff_graves_lowmid > 12:
            score += 2
            razones.append(
                f"Los graves audibles (60-200 Hz) están {diff_graves_lowmid:.1f} dB por encima de los graves-medios (200-800 Hz) — "
                "señal típica de un bajo prominente comiéndose el espacio del kick y los medios bajos"
            )
        elif diff_graves_lowmid > 8:
            score += 1
            razones.append(
                f"Diferencia notable entre graves (60-200 Hz) y graves-medios (200-800 Hz): {diff_graves_lowmid:.1f} dB"
            )
        if diff_sub_low > 4:
            score += 1
            razones.append(
                f"El sub (0-60 Hz) está {diff_sub_low:.1f} dB por encima de los graves audibles — posible rumble o sub descontrolado"
            )

    # Boost si el usuario describe el problema con palabras del campo léxico
    palabras_masking = ["kick", "bombo", "bajo", "bass", "enmasc", "barro", "mud",
                         "turbio", "se come", "pierde el kick", "kick perdido", "low end"]
    if any(p in bloqueo for p in palabras_masking):
        score += 2
        razones.append("El usuario percibe problemas con el kick o el bajo")

    # Cruce: enmascaramiento + densidad baja = no es densidad, es masking
    if senales["densidad_global"] == "baja" and diff_graves_lowmid > 10:
        score += 1
        razones.append("Densidad baja con graves dominantes — el bajo ocupa espacio que debería ser de otros elementos")

    # Cruce: harshness severo simultáneo puede ser por barro de graves-medios
    # (caso típico: el motor lee chirrido porque los low-mids están aplastados).
    # Empuja al enmascaramiento como hipótesis alternativa.
    if (harshness.get("nivel") == "severo"
            and diff_graves_lowmid > 8
            and senales["balance_grave"] != "excesivo"):
        score += 1
        razones.append(
            "Harshness severo simultáneo — el barro de graves-medios puede estar amplificando la lectura de aspereza"
        )

    # Si exceso_lowend ya es claro, este diagnóstico no aporta — penalizar para
    # evitar doble diagnóstico del mismo problema.
    if senales["balance_grave"] == "excesivo":
        score -= 2
        razones.append("(−) Hay exceso_lowend más claro — se diagnostica eso en su lugar")

    scores["enmascaramiento_bajo"] = score
    detalles["enmascaramiento_bajo"] = razones

    return scores, detalles


def aplicar_jerarquia(scores: dict, senales: dict, contexto: dict) -> tuple:
    # Umbrales por diagnóstico: los armónicos/tonales necesitan más evidencia
    # porque el análisis tonal es más incierto que el espectral/estructural
    UMBRALES_POR_DX = {
        "conflicto_armonico": 3,
        "pobreza_armonica": 3,
    }

    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ranking = [(k, v) for k, v in ranking
               if v > 0 and v >= UMBRALES_POR_DX.get(k, UMBRAL_MINIMO_CONFIANZA)]

    if not ranking:
        return "sin_diagnostico", None, False, ""

    principal_id = ranking[0][0]
    secundario_id = ranking[1][0] if len(ranking) > 1 else None

    # Regla 1: estructura antes que mezcla/espectro/armonía
    problemas_estructura = (
        scores.get("problema_arreglo", 0) > 3
        or scores.get("poco_contraste", 0) > 3
        or scores.get("break_sin_payoff", 0) > 3
        or scores.get("arreglo_repetitivo", 0) > 3
    )
    if principal_id in ["exceso_lowend", "exceso_densidad", "conflicto_armonico", "pobreza_armonica", "harshness_mezcla", "enmascaramiento_bajo"] and problemas_estructura:
        # Promueve al estructural con mayor score (incluyendo los nuevos).
        candidatos_estructura = [
            ("problema_arreglo", scores.get("problema_arreglo", 0)),
            ("poco_contraste", scores.get("poco_contraste", 0)),
            ("break_sin_payoff", scores.get("break_sin_payoff", 0)),
            ("arreglo_repetitivo", scores.get("arreglo_repetitivo", 0)),
        ]
        principal_id_anterior = principal_id
        principal_id = max(candidatos_estructura, key=lambda x: x[1])[0]
        secundario_id = principal_id_anterior

    # Regla 2: error de foco
    error_de_foco = False
    error_foco_msg = ""
    fase = contexto.get("fase", "")
    bloqueo = contexto.get("bloqueo_percibido", "").lower()
    palabras_mezcla = ["mezcla", "mix", "eq", "ecualiz", "compres", "volumen", "master"]

    if (fase in ["ajustando_mezcla", "casi_listo"] or any(p in bloqueo for p in palabras_mezcla)):
        if principal_id in ["problema_arreglo", "poco_contraste", "track_verde",
                            "break_sin_payoff", "arreglo_repetitivo"]:
            error_de_foco = True
            error_foco_msg = ("Mencionas estar enfocado en la mezcla, pero el diagnóstico principal "
                            "apunta a un problema más fundamental de estructura o desarrollo. "
                            "Antes de mezclar, conviene resolver eso primero.")

    if fase in ["ajustando_mezcla", "casi_listo"] and principal_id == "track_verde":
        error_de_foco = True
        error_foco_msg = ("Indicas estar en fase avanzada, pero el track parece estar aún "
                         "en una fase muy temprana de desarrollo. Conviene cerrar la idea "
                         "y la estructura antes de preocuparte por mezcla o pulido.")

    return principal_id, secundario_id, error_de_foco, error_foco_msg
