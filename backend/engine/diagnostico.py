"""
Generador de diagnóstico.
Combina señales + contexto + reglas → informe estructurado.
v0.3: feedback contextualizado por experiencia, género, objetivo y fase.
"""

from .reglas import evaluar_diagnosticos, aplicar_jerarquia
from .templates import TEMPLATES
from .contextualizador import contextualizar_feedback


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

    estado_map = {
        "verde": ("verde", "Fase temprana — aún necesita desarrollo"),
        "avanzado": ("avanzado", "Listo para revisión más fina"),
        "en_desarrollo": ("en_desarrollo", "Buena base, necesita iteración"),
    }
    estado, estado_texto = estado_map.get(madurez_final, estado_map["en_desarrollo"])

    # Explicación
    razones = [r for r in detalles.get(principal_id, []) if not r.startswith("(−)")]
    explicacion = "\n".join(f"• {r}" for r in razones[:3]) or "No hay señales específicas que reportar."

    # Feedback contextualizado (v0.3)
    feedback_ctx = contextualizar_feedback(principal_id, contexto, senales)

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
        "no_tocar_aun": template["no_tocar"],
        "siguiente_sesion": template["siguiente_sesion"],
        "estado_track": estado,
        "estado_texto": estado_texto,
        "datos_audio": {
            "bpm": senales["bpm"],
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
                "nivel": senales["loudness"]["nivel"],
                "referencia": senales["loudness"]["referencia"],
                "consejo_master": senales["loudness"].get("consejo_master", ""),
                "referencia_genero": feedback_ctx.get("referencia_lufs_genero", ""),
                "saturacion_dinamica": senales["loudness"].get("saturacion_dinamica", ""),
                "aviso_saturacion": senales["loudness"].get("aviso_saturacion", ""),
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
        },
        # Señales crudas para calibración del motor (el frontend las guarda en el Sheet)
        "senales": {
            "db_grave": senales.get("db_grave"),
            "db_media": senales.get("db_media"),
            "db_aguda": senales.get("db_aguda"),
            "diff_grave_media": senales.get("diff_grave_media"),
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
    }

    if secundario_id:
        tmpl_sec = TEMPLATES.get(secundario_id, {})
        resultado["diagnostico_secundario"] = {
            "id": secundario_id,
            "titulo": tmpl_sec.get("titulo", ""),
            "score": scores.get(secundario_id, 0),
        }

    return resultado
