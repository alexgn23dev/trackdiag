"""
Comparador contra track de referencia.

Compara las señales del track del usuario contra las de una referencia
profesional y devuelve "las diferencias que importan", en lenguaje de escucha.

Método clave (validado empíricamente, ver experimento 2026-06): el balance
espectral se compara sobre la FORMA CENTRADA por media de bandas — cada banda
menos la media de las 6 bandas del propio track. Eso lo hace invariante a la
ganancia Y a la cresta/transitorios (el término `ref=np.max` del extractor es
uniforme entre bandas y se cancela al centrar). Es BALANCE RELATIVO, no SPL
absoluto: "tu sub pesa +4 dB respecto a tu media, frente a la referencia".

Solo se comparan dimensiones medibles y robustas. La armonía/tonalidad queda
fuera a propósito (chroma poco fiable; diagnóstico armónico desactivado).
"""

# Bandas espectrales en orden, con su etiqueta legible.
_BANDAS = [
    ("sub",       "el sub (20-60 Hz)"),
    ("graves",    "los graves (60-200 Hz)"),
    ("low_mid",   "los graves-medios (200-800 Hz)"),
    ("mid",       "los medios (800 Hz-4 kHz)"),
    ("presencia", "la presencia (4-8 kHz)"),
    ("air",       "el aire / brillo (>8 kHz)"),
]

# Umbral de relevancia por banda (dB de forma relativa). PUNTO DE PARTIDA — el
# delta centrado sale ~la mitad del movimiento de EQ en señal, así que estos
# umbrales están pensados para detectar ~2-3 dB de diferencia audible. PENDIENTE
# DE CALIBRAR con pares de tracks reales (con audio sintético no se afinan bien).
_UMBRAL_BANDA = {
    "sub": 1.0, "graves": 1.0, "low_mid": 1.2,
    "mid": 1.2, "presencia": 1.5, "air": 1.5,
}


def _severidad(peso: float) -> str:
    """Descriptor cualitativo a partir del peso (delta / umbral). Es lo que se
    muestra como titular — el número en dB es balance relativo, no un movimiento
    de EQ, y puede dispararse en mezclas extremas; el descriptor es robusto."""
    if peso >= 3.5:
        return "mucho"
    if peso >= 2.0:
        return "bastante"
    return "algo"

# Texto de escucha por banda y dirección: (más alto que la ref, más bajo que la ref).
_HINT_BANDA = {
    "sub": (
        "Tu sub pesa más que en la referencia — el kick/sub puede emborronar en un club. Revisa el nivel del sub o si el limiter te lo está inflando.",
        "Te falta peso de sub respecto a la referencia — el track puede sonar pequeño en sistemas grandes. Sube el sub del kick/bajo o revisa un high-pass demasiado agresivo.",
    ),
    "graves": (
        "Tus graves (60-200 Hz) pesan más que en la referencia — la zona del cuerpo del kick y el bajo puede estar tapando. Revisa el solapamiento kick↔bajo.",
        "Tienes menos graves que la referencia — el track puede sonar flaco. Da más cuerpo al kick/bajo en 60-200 Hz.",
    ),
    "low_mid": (
        "Tus graves-medios (200-800 Hz) pesan más que en la referencia — es la zona del 'barro', suele acumularse. Limpia con EQ sustractivo en pads, voces y reverbs.",
        "Tienes menos cuerpo en graves-medios que la referencia — puede sonar hueco. Revisa si has cortado de más en 200-500 Hz.",
    ),
    "mid": (
        "Tus medios (800 Hz-4 kHz) pesan más que en la referencia — leads y voces quedan más adelante. Bien si lo buscas; cuidado si fatiga.",
        "Tus medios están por detrás de la referencia — leads y voces pueden quedar tapados. Súbelos o hazles hueco con EQ en el resto.",
    ),
    "presencia": (
        "Tu presencia (4-8 kHz) pesa más que en la referencia — más filo y definición; vigila que no chirríe.",
        "Te falta presencia (4-8 kHz) respecto a la referencia — el track puede sonar mate o sin definición. Realza leads y percusión en esa zona.",
    ),
    "air": (
        "Tienes más aire (>8 kHz) que la referencia — más brillo; vigila sibilancias y hi-hats duros.",
        "Te falta aire / brillo (>8 kHz) respecto a la referencia — suena más cerrado. Realza hats, colas de reverb o un shelf alto suave.",
    ),
}


def _forma_centrada(espectro_bandas: dict) -> dict:
    """Forma espectral relativa: cada banda menos la media de las 6 bandas.
    Invariante a ganancia y a cresta (ver docstring del módulo)."""
    vals = [float(espectro_bandas.get(b, -80.0)) for b, _ in _BANDAS]
    media = sum(vals) / len(vals)
    return {b: float(espectro_bandas.get(b, -80.0)) - media for b, _ in _BANDAS}


def _fmt_db(x: float) -> str:
    return f"{x:+.1f} dB"


def comparar_senales(senales_user: dict, senales_ref: dict, contexto: dict | None = None) -> dict:
    """Compara dos dicts de señales. Devuelve diferencias priorizadas (lenguaje
    de escucha), coincidencias, contexto de loudness y avisos de fiabilidad."""
    contexto = contexto or {}
    candidatos = []   # cada uno: {clave, label, magnitud, peso, texto}
    coincidencias = []

    # --- 1. Balance espectral (forma centrada) ---
    forma_u = _forma_centrada(senales_user.get("espectro_bandas", {}))
    forma_r = _forma_centrada(senales_ref.get("espectro_bandas", {}))
    for banda, label in _BANDAS:
        delta = forma_u[banda] - forma_r[banda]
        umbral = _UMBRAL_BANDA[banda]
        if abs(delta) >= umbral:
            hint = _HINT_BANDA[banda][0 if delta > 0 else 1]
            candidatos.append({
                "clave": f"banda_{banda}", "label": label,
                "magnitud": _fmt_db(delta), "peso": abs(delta) / umbral, "texto": hint,
            })
        else:
            coincidencias.append(label)

    # --- 2. Rango dinámico (cresta RMS, ratio invariante a nivel) ---
    rd_u = float(senales_user.get("rango_dinamico", 0) or 0)
    rd_r = float(senales_ref.get("rango_dinamico", 0) or 0)
    if rd_u and rd_r:
        d = rd_u - rd_r
        if abs(d) >= 0.2:
            if d < 0:
                texto = ("Tu mezcla respira menos que la referencia — está más comprimida. "
                         "Mira tu compresor de bus o el limiter del máster; puede que estés "
                         "perdiendo pegada del kick y dinámica entre secciones.")
            else:
                texto = ("Tu mezcla tiene más rango dinámico que la referencia — puede sonar "
                         "menos contundente en un club. Si buscas más pegada, comprime algo "
                         "más el bus o el máster (sin pasarte).")
            candidatos.append({
                "clave": "rango_dinamico", "label": "el rango dinámico",
                "magnitud": ("más comprimida" if d < 0 else "más dinámica"),
                "peso": abs(d) / 0.2, "texto": texto,
            })
        else:
            coincidencias.append("el rango dinámico")

    # --- 3. Rango de loudness (LRA, variación entre secciones) ---
    lra_u = float((senales_user.get("loudness", {}) or {}).get("rango_loudness", 0) or 0)
    lra_r = float((senales_ref.get("loudness", {}) or {}).get("rango_loudness", 0) or 0)
    if lra_u and lra_r:
        d = lra_u - lra_r
        if abs(d) >= 1.5:
            if d < 0:
                texto = ("Tu loudness varía menos entre secciones que la referencia (LRA más "
                         "bajo) — el track es más constante/plano. La referencia respira más "
                         "entre intro, break y drop.")
            else:
                texto = ("Tu loudness varía más entre secciones que la referencia — el track "
                         "tiene más contraste de volumen. Bien para dinámica; vigila que el "
                         "drop no se quede corto de nivel para pista.")
            candidatos.append({
                "clave": "lra", "label": "la variación de loudness (LRA)",
                "magnitud": f"{d:+.1f} LU", "peso": abs(d) / 1.5, "texto": texto,
            })
        else:
            coincidencias.append("la variación de loudness")

    # --- 4. Anchura estéreo (correlación L/R) ---
    mc_u = senales_user.get("mono_compat", {}) or {}
    mc_r = senales_ref.get("mono_compat", {}) or {}
    if mc_u.get("es_stereo") and mc_r.get("es_stereo"):
        cu = float(mc_u.get("correlacion_lr", 1.0))
        cr = float(mc_r.get("correlacion_lr", 1.0))
        d = cu - cr  # correlación más alta = más estrecho/mono
        if abs(d) >= 0.1:
            if d > 0:
                texto = ("Tu mezcla es más estrecha (más mono) que la referencia. Si buscas "
                         "amplitud, ensancha medios y agudos (pads, reverbs, hats) — nunca los "
                         "graves, que deben ir centrados.")
            else:
                texto = ("Tu mezcla es más ancha que la referencia. Bien para sensación de "
                         "espacio, pero comprueba la compatibilidad mono: que no se cancele "
                         "nada importante al sumar a mono, sobre todo en graves.")
            candidatos.append({
                "clave": "estereo", "label": "la anchura estéreo",
                "magnitud": ("más estrecha" if d > 0 else "más ancha"),
                "peso": abs(d) / 0.1, "texto": texto,
            })
        else:
            coincidencias.append("la anchura estéreo")

    # --- 5. Densidad espectral (flatness 0-1) ---
    du = float(senales_user.get("densidad_espectral", 0) or 0)
    dr = float(senales_ref.get("densidad_espectral", 0) or 0)
    if du and dr:
        d = du - dr
        if abs(d) >= 0.02:
            if d > 0:
                texto = ("Tu mezcla está más cargada/densa que la referencia — hay más cosas "
                         "ocupando el espectro a la vez. La referencia deja más espacio. Quita "
                         "capas que no aporten o hazles hueco con EQ.")
            else:
                texto = ("Tu mezcla está menos densa que la referencia — deja más espacio. No "
                         "es malo en sí; solo revísalo si el track te suena vacío frente a la ref.")
            candidatos.append({
                "clave": "densidad", "label": "la densidad",
                "magnitud": ("más densa" if d > 0 else "más despejada"),
                "peso": abs(d) / 0.02, "texto": texto,
            })
        else:
            coincidencias.append("la densidad")

    # --- Priorización: las 3 que más importan (mayor peso relativo) ---
    for c in candidatos:
        c["severidad"] = _severidad(c["peso"])
    candidatos.sort(key=lambda c: c["peso"], reverse=True)
    top = candidatos[:3]
    n_extra = max(0, len(candidatos) - 3)

    # --- Contexto de loudness (NUNCA es una "diferencia"; se cruza con la fase) ---
    lu = (senales_user.get("loudness", {}) or {})
    lr = (senales_ref.get("loudness", {}) or {})
    lufs_u = lu.get("lufs_integrado", -99)
    lufs_r = lr.get("lufs_integrado", -99)
    fase = contexto.get("fase", "")
    user_no_masterizado = fase in ("idea", "arreglo_en_progreso", "ajustando_mezcla")
    nota_loudness = ""
    if lufs_u > -50 and lufs_r > -50:
        if user_no_masterizado and (lufs_r - lufs_u) > 3:
            nota_loudness = (
                "Tu track aún no está masterizado y la referencia es un release final: que "
                "esté más bajo de volumen es esperado, no es un defecto de mezcla. Compara el "
                "balance, no el volumen."
            )
        elif abs(lufs_u - lufs_r) > 2:
            nota_loudness = (
                "Diferencia de loudness notable. Si tu track ya está masterizado, acércate al "
                "nivel de la referencia con el limiter; si no, ignóralo por ahora."
            )
    loudness_contexto = {
        "lufs_user": lufs_u, "lufs_ref": lufs_r,
        "true_peak_user": lu.get("true_peak_dbtp", -99.0),
        "true_peak_ref": lr.get("true_peak_dbtp", -99.0),
        "nota": nota_loudness,
    }

    # --- Avisos de fiabilidad: ¿la comparación es válida? ---
    avisos = []
    parcial = False
    bpm_u = float(senales_user.get("bpm", 0) or 0)
    bpm_r = float(senales_ref.get("bpm", 0) or 0)
    if bpm_u and bpm_r:
        ratio = bpm_u / bpm_r
        cerca_2x = 0.45 <= ratio <= 0.55 or 1.8 <= ratio <= 2.2
        if abs(bpm_u - bpm_r) > 8 and not cerca_2x:
            parcial = True
            avisos.append(
                f"Tu track ({bpm_u:.0f} BPM) y la referencia ({bpm_r:.0f} BPM) van a tempos "
                "distintos. El balance y el loudness siguen siendo comparables; la estructura no."
            )
    dur_u = float(senales_user.get("duracion_seg", 0) or 0)
    dur_r = float(senales_ref.get("duracion_seg", 0) or 0)
    if dur_u and dur_r:
        rdur = dur_u / dur_r
        if rdur < 0.5 or rdur > 2.0:
            parcial = True
            avisos.append(
                "Tu track y la referencia tienen duraciones muy distintas — puede que la "
                "referencia sea un edit o un loop. Fíate sobre todo del balance espectral."
            )

    return {
        "diferencias": top,
        "n_diferencias_extra": n_extra,
        "coincidencias": coincidencias,
        "loudness_contexto": loudness_contexto,
        "avisos": avisos,
        "comparacion_parcial": parcial,
    }
