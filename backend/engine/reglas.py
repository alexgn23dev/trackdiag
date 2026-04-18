"""
Motor de reglas diagnósticas.
Evalúa hipótesis, aplica jerarquía pedagógica y genera el diagnóstico final.
"""

UMBRAL_MINIMO_CONFIANZA = 3


def evaluar_diagnosticos(senales: dict, contexto: dict) -> tuple[dict, dict]:
    scores = {}
    detalles = {}

    bloqueo = contexto.get("bloqueo_percibido", "").lower()
    fase = contexto.get("fase", "")
    dificultad = contexto.get("dificultad_habitual", "")
    dist = senales["distribucion"]

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
        score += 3; razones.append(f"Hay una sección de baja energía desproporcionadamente larga ({dist['max_seccion_baja']} bloques de {senales['n_bloques']})")
    if dist["drop_corto"]:
        score += 2; razones.append(f"La sección de alta energía más larga es muy corta ({dist['max_seccion_alta']} bloques)")
    if dist["inicio_abrupto"]:
        score += 1; razones.append("El track empieza directamente con energía alta, sin introducción")
    if dist["sin_outro"]:
        score += 1; razones.append("El track termina con energía alta, sin outro")
    if senales["contraste_energetico"] == "alto" and senales["tiene_desarrollo"] and not dist["estructura_problematica"]:
        score -= 3; razones.append("(−) El track muestra buen contraste, desarrollo y distribución")
    scores["problema_arreglo"] = score
    detalles["problema_arreglo"] = razones

    # --- 2: Poco contraste entre secciones ---
    score, razones = 0, []
    if senales["contraste_energetico"] == "bajo" and senales["duracion_seg"] > 150:
        score += 3; razones.append("Contraste bajo en un track de duración razonable")
    elif senales["contraste_energetico"] == "bajo":
        score += 1; razones.append("Contraste energético bajo")
    if not senales["tiene_desarrollo"] and senales["duracion_seg"] > 180:
        score += 2; razones.append("Track largo sin cambios significativos de energía")
    if senales["rango_dinamico"] < 2.0:
        score += 1; razones.append(f"Rango dinámico reducido ({senales['rango_dinamico']})")
    if any(p in bloqueo for p in ["repetitivo", "repite", "loop", "monótono", "monotono", "aburrido", "igual"]):
        score += 2; razones.append("El usuario percibe repetitividad")
    if dist["break_desproporcionado"] and senales["duracion_seg"] > 150:
        score += 2; razones.append("Hay un break tan largo que el track pierde narrativa")
    if senales["duracion_seg"] < 120:
        score -= 2; razones.append("(−) Track muy corto — contraste bajo es esperado en ideas")
    scores["poco_contraste"] = score
    detalles["poco_contraste"] = razones

    # --- 3: Mezcla prematura ---
    score, razones = 0, []
    palabras_mezcla = ["mezcla", "mix", "eq", "ecualiz", "compres", "volumen", "paneo", "pan",
                       "master", "loudness", "nivel", "db", "sidechain"]
    usuario_enfocado_mezcla = any(p in bloqueo for p in palabras_mezcla)
    fase_mezcla = fase in ["ajustando_mezcla", "casi_listo"]
    track_no_maduro = senales["madurez_estimada"] in ["verde", "en_desarrollo"]
    problemas_estructura = (not senales["tiene_desarrollo"]
                           or senales["contraste_energetico"] == "bajo"
                           or dist["estructura_problematica"])
    if fase_mezcla and problemas_estructura:
        score += 4; razones.append("El usuario dice estar mezclando pero el track tiene problemas estructurales")
    if usuario_enfocado_mezcla and track_no_maduro:
        score += 3; razones.append("El usuario habla de mezcla pero el track aún no está maduro")
    if fase_mezcla and senales["madurez_estimada"] == "verde":
        score += 2; razones.append("Fase de mezcla declarada en un track claramente verde")
    if usuario_enfocado_mezcla and problemas_estructura:
        score += 1; razones.append("Foco en mezcla cuando hay señales de problema estructural")
    if senales["madurez_estimada"] == "avanzado" and senales["tiene_desarrollo"]:
        score -= 4; razones.append("(−) El track parece avanzado — la mezcla sí es relevante ahora")
    scores["mezcla_prematura"] = score
    detalles["mezcla_prematura"] = razones

    # --- 4: Exceso de low-end ---
    # Ponderado por género: géneros oscuros/percusivos toleran más graves
    score, razones = 0, []
    genero = contexto.get("genero", "")
    generos_graves_ok = ["techno", "techno_acido", "minimal", "tech_house"]
    generos_graves_menos = ["trance", "progressive_trance", "progressive_house", "melodic_techno"]
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
    # Ajuste por género: en géneros con kick protagonista, ser más permisivo
    if genero in generos_graves_ok and senales["balance_grave"] != "excesivo":
        score -= 1; razones.append(f"(−) En {genero}, cierta dominancia grave es natural")
    # En géneros melódicos, el exceso de graves es más problemático
    if genero in generos_graves_menos and senales["balance_grave"] in ["elevado", "excesivo"]:
        score += 1; razones.append(f"(−) En {genero}, el exceso de graves enmascara melodías y atmósferas")
    if not senales["tiene_desarrollo"] and senales["contraste_energetico"] == "bajo":
        score -= 1; razones.append("(−) Hay problemas estructurales más prioritarios")
    if dist["estructura_problematica"]:
        score -= 1; razones.append("(−) La estructura del track tiene problemas más prioritarios")
    scores["exceso_lowend"] = score
    detalles["exceso_lowend"] = razones

    # --- 5: Exceso de capas / densidad ---
    score, razones = 0, []
    if senales["densidad_global"] == "saturada":
        score += 3; razones.append(f"Densidad espectral saturada ({senales['densidad_espectral']:.4f})")
    elif senales["densidad_global"] == "alta":
        score += 2; razones.append(f"Densidad espectral alta ({senales['densidad_espectral']:.4f})")
    if senales["rango_dinamico"] < 1.8:
        score += 2; razones.append(f"Muy poco rango dinámico ({senales['rango_dinamico']}) — todo suena al mismo nivel")
    elif senales["rango_dinamico"] < 2.5:
        score += 1; razones.append(f"Rango dinámico reducido ({senales['rango_dinamico']})")
    if any(p in bloqueo for p in ["lleno", "denso", "saturado", "confuso", "empastad", "cargado", "capas"]):
        score += 2; razones.append("El usuario percibe exceso de densidad")
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

    # --- 7: Carencia espectral ---
    # Ponderado por género: no todo género necesita el mismo brillo o cuerpo en medios
    score, razones = 0, []
    generos_brillantes = ["trance", "progressive_trance", "progressive_house", "melodic_techno", "house"]
    generos_oscuros = ["techno", "techno_acido", "minimal"]
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
    scores["conflicto_armonico"] = score
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
        generos_melodicos = ["trance", "progressive_trance", "progressive_house", "melodic_techno", "deep_house"]
        generos_percusivos = ["techno", "techno_acido", "minimal"]
        if genero in generos_melodicos and armonia.get("contenido_tonal", 0) < 0.35:
            score += 2; razones.append(
                f"En {genero}, el contenido melódico es parte esencial del género — "
                f"un track predominantemente percusivo pierde identidad"
            )
        elif genero in generos_percusivos:
            score -= 2; razones.append(f"(−) En {genero}, un perfil percusivo puede ser intencional")
    scores["pobreza_armonica"] = score
    detalles["pobreza_armonica"] = razones

    return scores, detalles


def aplicar_jerarquia(scores: dict, senales: dict, contexto: dict) -> tuple:
    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ranking = [(k, v) for k, v in ranking if v > 0]

    if not ranking or ranking[0][1] < UMBRAL_MINIMO_CONFIANZA:
        return "sin_diagnostico", None, False, ""

    principal_id = ranking[0][0]
    secundario_id = ranking[1][0] if len(ranking) > 1 and ranking[1][1] >= UMBRAL_MINIMO_CONFIANZA else None

    # Regla 1: estructura antes que mezcla/espectro/armonía
    problemas_estructura = scores.get("problema_arreglo", 0) > 3 or scores.get("poco_contraste", 0) > 3
    if principal_id in ["exceso_lowend", "exceso_densidad", "conflicto_armonico", "pobreza_armonica"] and problemas_estructura:
        if scores.get("problema_arreglo", 0) >= scores.get("poco_contraste", 0):
            principal_id = "problema_arreglo"
        else:
            principal_id = "poco_contraste"
        secundario_id = ranking[0][0]

    # Regla 2: error de foco
    error_de_foco = False
    error_foco_msg = ""
    fase = contexto.get("fase", "")
    bloqueo = contexto.get("bloqueo_percibido", "").lower()
    palabras_mezcla = ["mezcla", "mix", "eq", "ecualiz", "compres", "volumen", "master"]

    if (fase in ["ajustando_mezcla", "casi_listo"] or any(p in bloqueo for p in palabras_mezcla)):
        if principal_id in ["problema_arreglo", "poco_contraste", "track_verde"]:
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
