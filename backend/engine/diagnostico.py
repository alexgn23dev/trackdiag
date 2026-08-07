"""
Generador de diagnóstico.
Combina señales + contexto + reglas → informe estructurado.
v0.3: feedback contextualizado por experiencia, género, objetivo y fase.
"""

from .reglas import evaluar_diagnosticos, aplicar_jerarquia, UMBRAL_MINIMO_CONFIANZA
from .templates import TEMPLATES
from .contextualizador import contextualizar_feedback, generar_sugerencias_estructura
from .versiones import algoritmos as _versiones_algoritmos

# Umbrales por dx para contar "puntos pendientes" en el estado.
# Coincide con aplicar_jerarquia en reglas.py: armónicos exigen más evidencia.
_UMBRALES_PUNTOS = {
    "conflicto_armonico": 3,
    "pobreza_armonica": 3,
}


def _contar_puntos_pendientes(scores: dict) -> int:
    """Cuenta hipótesis con score >= umbral, excluyendo sin_diagnostico."""
    return sum(
        1 for dx, score in scores.items()
        if dx != "sin_diagnostico"
        and score >= _UMBRALES_PUNTOS.get(dx, UMBRAL_MINIMO_CONFIANZA)
    )


def generar_diagnostico(senales: dict, contexto: dict) -> dict:
    scores, detalles = evaluar_diagnosticos(senales, contexto)
    principal_id, secundario_id, error_foco, error_foco_msg = aplicar_jerarquia(scores, senales, contexto)

    template = TEMPLATES.get(principal_id, TEMPLATES["sin_diagnostico"])

    # Estado del track con peso del contexto
    fase = contexto.get("fase", "")
    madurez_audio = senales["madurez_estimada"]

    if fase == "idea" and madurez_audio == "avanzado":
        madurez_final = "en_desarrollo"
    elif fase == "idea" and madurez_audio != "avanzado":
        madurez_final = "verde"
    elif madurez_audio == "verde":
        madurez_final = "verde"
    else:
        madurez_final = madurez_audio

    # Conteo de puntos pendientes — hipótesis con score >= umbral.
    # Permite que el texto del estado se mueva con el progreso del usuario.
    puntos_pendientes = _contar_puntos_pendientes(scores)

    if madurez_final == "verde":
        estado = "verde"
        estado_texto = "Fase temprana — aún necesita desarrollo"
    elif madurez_final == "avanzado":
        estado = "avanzado"
        estado_texto = "Mezcla lista — foco en máster y nivel"
    else:
        estado = "en_desarrollo"
        if puntos_pendientes == 0:
            estado_texto = "Mezcla casi lista — ajusta los detalles"
        elif puntos_pendientes == 1:
            estado_texto = "Mezcla casi lista — 1 punto pendiente antes del máster"
        else:
            estado_texto = f"Mezcla casi lista — {puntos_pendientes} puntos pendientes antes del máster"

    # Explicación
    razones = [r for r in detalles.get(principal_id, []) if not r.startswith("(−)")]
    # Priorizar razones con localización temporal (timecode "aprox. entre X:XX y
    # Y:YY") — son las más accionables. Feedback 2026-06 (n8/n34/n140): usuarios
    # pedían referencias de sección concretas. sort estable conserva el orden del resto.
    razones.sort(key=lambda r: 0 if "aprox. entre" in r else 1)
    explicacion = "\n".join(f"• {r}" for r in razones[:3]) or "No hay señales específicas que reportar."

    # Feedback contextualizado (v0.3)
    feedback_ctx = contextualizar_feedback(principal_id, contexto, senales)

    # Sugerencias de estructura concretas y localizadas — solo cuando el cuello
    # de botella es estructural (o hay error de foco hacia estructura).
    _dx_estructurales = {
        "problema_arreglo", "poco_contraste", "break_sin_payoff",
        "arreglo_repetitivo", "track_verde", "falta_impacto",
    }
    sugerencias_estructura = (
        generar_sugerencias_estructura(principal_id, contexto, senales)
        if (principal_id in _dx_estructurales or error_foco)
        else []
    )

    # Prioridades: base + extras contextuales
    prioridades = list(template["prioridades"])
    for extra in feedback_ctx.get("prioridades_extra", []):
        if extra:
            prioridades.append(extra)

    resultado = {
        "diagnostico_principal": {
            "id": principal_id,
            "titulo": template["titulo"],
            "explicacion": explicacion,
            "score": scores.get(principal_id, 0),
        },
        "diagnostico_secundario": None,
        "prioridades": prioridades,
        "sugerencias_estructura": sugerencias_estructura,
        "no_tocar_aun": template["no_tocar"],
        "siguiente_sesion": template["siguiente_sesion"],
        "estado_track": estado,
        "estado_texto": estado_texto,
        "datos_audio": {
            # None si no hay pulso detectable. La interfaz debe mostrar
            # "no detectado", nunca un valor por defecto.
            "bpm": senales.get("bpm"),
            "tempo_detectado": senales.get("tempo_detectado", True),
            "tempo_fuente": senales.get("tempo_fuente", ""),
            "duracion": senales["duracion_fmt"],
            "contraste": senales["contraste_energetico"],
            "balance_grave": senales["balance_grave"],
            "densidad": senales["densidad_global"],
            "desarrollo_temporal": senales["tiene_desarrollo"],
            "n_bloques": senales["n_bloques"],
            "distribucion": {
                "break_largo": senales["distribucion"]["break_desproporcionado"],
                "drop_corto": senales["distribucion"]["drop_corto"],
                "sin_intro": senales["distribucion"]["inicio_abrupto"],
                "sin_outro": senales["distribucion"]["sin_outro"],
                "estructura_problematica": senales["distribucion"]["estructura_problematica"],
            },
            "armonia": {
                "key": senales["armonia"]["key"],
                "modo": senales["armonia"]["modo"],
                "key_confidence": senales["armonia"]["key_confidence"],
                "contenido_tonal": senales["armonia"]["contenido_tonal"],
                "consistencia_armonica": senales["armonia"]["consistencia_armonica"],
                "notas_dominantes": senales["armonia"]["notas_dominantes"],
                "complejidad_armonica": senales["armonia"]["complejidad_armonica"],
                "ratio_tonal_percusivo": senales["armonia"]["ratio_tonal_percusivo"],
            },
            "loudness": {
                "lufs_integrado": senales["loudness"]["lufs_integrado"],
                "lufs_short_term_max": senales["loudness"]["lufs_short_term_max"],
                "rango_loudness": senales["loudness"]["rango_loudness"],
                # Picos sin redondear: el redondeo lo hace la interfaz.
                "true_peak_dbtp": senales["loudness"].get("true_peak_dbtp", -99.0),
                "sample_peak_dbfs": senales["loudness"].get("sample_peak_dbfs", -99.0),
                # Estado del método de medición (no del archivo)
                "sample_peak_source": senales["loudness"].get("sample_peak_source", ""),
                "true_peak_method": senales["loudness"].get("true_peak_method", ""),
                "true_peak_oversampling": senales["loudness"].get("true_peak_oversampling", 0),
                "true_peak_internal_validation_passed": senales["loudness"].get("true_peak_internal_validation_passed", False),
                "true_peak_external_validation_passed": senales["loudness"].get("true_peak_external_validation_passed", False),
                "true_peak_validated": senales["loudness"].get("true_peak_validated", False),
                "peak_measurement_sample_rate": senales["loudness"].get("peak_measurement_sample_rate", 0),
                "peak_measurement_channels": senales["loudness"].get("peak_measurement_channels", 0),
                "nivel": senales["loudness"]["nivel"],
                "referencia": senales["loudness"]["referencia"],
                "consejo_master": senales["loudness"].get("consejo_master", ""),
                "referencia_genero": feedback_ctx.get("referencia_lufs_genero", ""),
                "saturacion_dinamica": senales["loudness"].get("saturacion_dinamica", ""),
                "aviso_saturacion": senales["loudness"].get("aviso_saturacion", ""),
                # Campos antiguos: se conservan para parsers e histórico.
                # La interfaz NO los usa desde la fase 2A.
                "nivel_true_peak": senales["loudness"].get("nivel_true_peak", ""),
                "aviso_true_peak": senales["loudness"].get("aviso_true_peak", ""),
                # Taxonomía de picos (fase 2A) — lo que se muestra al usuario
                "categoria_picos": senales["loudness"].get("categoria_picos", ""),
                "peak_taxonomy_version": senales["loudness"].get("peak_taxonomy_version"),
                # Valor cuantizado con el que se decide la taxonomía y que se
                # muestra. La medición cruda sigue en `true_peak_dbtp`.
                "true_peak_classification_value": senales["loudness"].get("true_peak_classification_value"),
                "sample_peak_classification_value": senales["loudness"].get("sample_peak_classification_value"),
                "severidad_picos": senales["loudness"].get("severidad_picos", ""),
                "titulo_picos": senales["loudness"].get("titulo_picos", ""),
                "aviso_picos": senales["loudness"].get("aviso_picos", ""),
                "nota_lossy_picos": senales["loudness"].get("nota_lossy_picos", ""),
            },
            "mono_compat": {
                "es_stereo": senales["mono_compat"]["es_stereo"],
                "correlacion_lr": senales["mono_compat"]["correlacion_lr"],
                "perdida_mono_db": senales["mono_compat"]["perdida_mono_db"],
                "nivel_compatibilidad": senales["mono_compat"]["nivel_compatibilidad"],
                "fase_invertida": senales["mono_compat"]["fase_invertida"],
                "bandas": senales["mono_compat"]["bandas"],
                "resumen": senales["mono_compat"]["resumen"],
            },
            "harshness": {
                "tiene_harshness": senales["harshness"]["tiene_harshness"],
                "nivel": senales["harshness"]["nivel"],
                "pico_p95": senales["harshness"]["pico_p95"],
                "pct_frames_harsh": senales["harshness"]["pct_frames_harsh"],
                "zona_problema": senales["harshness"]["zona_problema"],
                "peak_freq_hz": senales["harshness"].get("peak_freq_hz", 0),
                "caracter": senales["harshness"].get("caracter", ""),
            },
            # Metadatos del archivo — solo registro en fase 1, nada los usa.
            "formato": senales.get("formato", {}),
        },
        # Con qué se midió esto. Permite saber después qué análisis son
        # comparables entre sí sin deducirlo por la fecha.
        "versiones": _versiones_algoritmos(),
        # Señales crudas para calibración del motor (el frontend las guarda en el Sheet)
        "senales": {
            "db_grave": senales.get("db_grave"),
            "db_media": senales.get("db_media"),
            "db_aguda": senales.get("db_aguda"),
            "diff_grave_media": senales.get("diff_grave_media"),
            "diff_sub_low": senales.get("diff_sub_low"),
            "densidad_espectral": senales.get("densidad_espectral"),
            "varianza_energia": senales.get("varianza_energia"),
            "rango_dinamico": senales.get("rango_dinamico"),
            "cambios_significativos": senales.get("cambios_significativos"),
            "madurez_estimada": senales.get("madurez_estimada"),
            "carencia_medios": senales.get("carencia_medios"),
            "carencia_agudos": senales.get("carencia_agudos"),
        },
        "error_de_foco": error_foco,
        "error_de_foco_mensaje": error_foco_msg if error_foco else "",
        "scores": {k: v for k, v in sorted(scores.items(), key=lambda x: x[1], reverse=True)},
        # Feedback contextualizado (v0.3)
        "nota_contextual": feedback_ctx.get("nota_contextual", ""),
        "tips_genero": feedback_ctx.get("tips_genero", []),
        "tip_objetivo": feedback_ctx.get("tip_objetivo", ""),
        "referencia_temporal": feedback_ctx.get("referencia_temporal", ""),
        "nota_motivacional": feedback_ctx.get("nota_motivacional", ""),
        "disclaimer": feedback_ctx.get("disclaimer", ""),
        "aviso_genero": feedback_ctx.get("aviso_genero", ""),
        # Alcance del análisis — siempre presente. Gestiona la expectativa más
        # repetida en el feedback: usuarios que esperan juicio de notas/acordes/
        # melodía (afinación, disonancia), que el análisis de señal no puede dar.
        "alcance_analisis": (
            "Este análisis evalúa mezcla, balance espectral, estructura, dinámica y loudness. "
            "No juzga si las notas, los acordes o la melodía están bien afinados o son acertados "
            "— eso queda a tu oído y tu intención artística."
        ),
    }

    if secundario_id:
        tmpl_sec = TEMPLATES.get(secundario_id, {})
        resultado["diagnostico_secundario"] = {
            "id": secundario_id,
            "titulo": tmpl_sec.get("titulo", ""),
            "score": scores.get(secundario_id, 0),
        }

    return resultado
