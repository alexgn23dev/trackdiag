"""
Extractor de señales de audio.
Recibe un path de audio y retorna un diccionario con señales crudas y derivadas.
"""

import librosa
import numpy as np
import pyloudnorm as pyln
import soundfile as sf


def extraer_senales(audio_path: str, bpm_manual: int | None = None) -> dict:
    # Carga única: stereo a 22050 Hz (sin límite de duración para no perder estructura)
    y_stereo, sr = librosa.load(audio_path, sr=22050, mono=False)
    es_stereo = y_stereo.ndim == 2 and y_stereo.shape[0] == 2

    # Derivar mono del stereo (evita segunda carga)
    if es_stereo:
        y = np.mean(y_stereo, axis=0)
    else:
        y = y_stereo if y_stereo.ndim == 1 else y_stereo[0]

    # Duración calculada del array cargado (evita re-lectura del archivo)
    duracion_seg = librosa.get_duration(y=y, sr=sr)

    # Tempo — usa BPM manual si se proporciona, si no detecta automáticamente
    if bpm_manual and bpm_manual > 0:
        tempo = bpm_manual
    else:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=128)
        tempo = float(tempo[0]) if hasattr(tempo, '__len__') else float(tempo)
        # En electrónica los BPM son siempre enteros; redondear al más cercano
        tempo = round(tempo)

    # RMS por bloques de ~8 compases
    compases_por_bloque = 8
    beats_por_bloque = compases_por_bloque * 4
    duracion_bloque_seg = (60.0 / tempo) * beats_por_bloque
    hop_length = 512

    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    frames_por_segundo = sr / hop_length
    frames_por_bloque = max(1, int(duracion_bloque_seg * frames_por_segundo))

    n_bloques = max(1, len(rms) // frames_por_bloque)
    bloques_rms = []
    for i in range(n_bloques):
        inicio = i * frames_por_bloque
        fin = min((i + 1) * frames_por_bloque, len(rms))
        bloques_rms.append(float(np.mean(rms[inicio:fin])))

    # Varianza de energía entre bloques
    varianza_energia = (
        float(np.std(bloques_rms) / (np.mean(bloques_rms) + 1e-10))
        if len(bloques_rms) > 1 else 0.0
    )

    # Balance espectral — mel spectrogram en dB
    mel_S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, hop_length=hop_length)
    mel_db = librosa.power_to_db(mel_S, ref=np.max)
    mel_freqs = librosa.mel_frequencies(n_mels=128, fmin=0, fmax=sr / 2)

    mask_grave = mel_freqs < 200
    mask_media = (mel_freqs >= 200) & (mel_freqs < 4000)
    mask_aguda = mel_freqs >= 4000

    db_grave = float(np.mean(mel_db[mask_grave, :])) if mask_grave.any() else -80
    db_media = float(np.mean(mel_db[mask_media, :])) if mask_media.any() else -80
    db_aguda = float(np.mean(mel_db[mask_aguda, :])) if mask_aguda.any() else -80
    diff_grave_media = db_grave - db_media

    db_vals = np.array([db_grave, db_media, db_aguda])
    db_shifted = db_vals - np.min(db_vals)
    ratios = db_shifted / np.sum(db_shifted) if np.sum(db_shifted) > 0 else np.array([.33, .33, .33])

    # Balance espectral detallado — 6 bandas
    bandas_freq = {
        "sub":       (0, 60),
        "graves":    (60, 200),
        "low_mid":   (200, 800),
        "mid":       (800, 4000),
        "presencia": (4000, 8000),
        "air":       (8000, sr / 2),
    }
    espectro_bandas = {}
    for nombre_banda, (f_min, f_max) in bandas_freq.items():
        mask = (mel_freqs >= f_min) & (mel_freqs < f_max)
        if mask.any():
            db_val = float(np.mean(mel_db[mask, :]))
        else:
            db_val = -80.0
        espectro_bandas[nombre_banda] = round(db_val, 1)

    # Normalizar bandas a escala 0-100 para visualización
    bandas_db_list = list(espectro_bandas.values())
    db_min = min(bandas_db_list)
    db_max = max(bandas_db_list)
    db_rango = db_max - db_min if db_max != db_min else 1.0
    espectro_bandas_norm = {}
    for nombre_banda, db_val in espectro_bandas.items():
        espectro_bandas_norm[nombre_banda] = round(((db_val - db_min) / db_rango) * 100, 1)

    # Densidad espectral
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0]
    densidad_espectral = float(np.mean(flatness))

    # Rango dinámico
    rms_mean = float(np.mean(rms))
    rms_max = float(np.max(rms))
    rango_dinamico = rms_max / (rms_mean + 1e-10)

    # Desarrollo temporal
    if len(bloques_rms) >= 3:
        diffs = np.diff(bloques_rms)
        umbral_cambio = np.mean(bloques_rms) * 0.15
        cambios_significativos = int(np.sum(np.abs(diffs) > umbral_cambio))
    else:
        cambios_significativos = 0

    # === Indicadores derivados ===

    contraste_energetico = (
        "alto" if varianza_energia > 0.25
        else "medio" if varianza_energia > 0.10
        else "bajo"
    )

    # Umbrales calibrados para electrónica (kick 4x4 → graves naturalmente dominantes)
    # Recalibrado en dos pasos (mayo 2026) tras feedback de productores reales:
    # los umbrales 18/24 y 20/26 seguían marcando como exceso tracks correctos
    # de tech_house y techno con kick prominente. Subimos a 22/28 para dar más
    # margen global. Combinado con descuentos por género reforzados en reglas.py,
    # los géneros con kick fuerte (tech_house, techno, hard_techno, minimal,
    # deep_house, afro_house) tienen triple protección contra falsos positivos.
    if diff_grave_media > 28:
        balance_grave = "excesivo"
    elif diff_grave_media > 22:
        balance_grave = "elevado"
    else:
        balance_grave = "normal"

    # Sub-grave vs grave audible: si el contenido en sub (0-60 Hz) domina sobre
    # graves audibles (60-200 Hz), el track puede tener rumble/sub descontrolado
    # aunque el balance general lea "normal". Se expone como señal informativa;
    # un diagnóstico que lo use vive en reglas.py si en el futuro lo activamos.
    db_sub = espectro_bandas.get("sub", -80)
    db_low_audible = espectro_bandas.get("graves", -80)
    diff_sub_low = db_sub - db_low_audible

    # Umbrales recalibrados con 21 sesiones reales (media=0.032)
    densidad_global = (
        "saturada" if densidad_espectral > 0.12
        else "alta" if densidad_espectral > 0.06
        else "media" if densidad_espectral > 0.03
        else "baja"
    )

    tiene_desarrollo = cambios_significativos >= 2

    # === Análisis de mono compatibility ===
    if es_stereo:
        mono_compat = _analizar_mono_compatibility(y_stereo, sr)
    else:
        mono_compat = {
            "es_stereo": False,
            "correlacion_lr": 1.0,
            "perdida_mono_db": 0.0,
            "nivel_compatibilidad": "excelente",
            "fase_invertida": False,
            "bandas": {
                "graves": {"correlacion": 1.0, "perdida_db": 0.0, "estado": "ok"},
                "medios": {"correlacion": 1.0, "perdida_db": 0.0, "estado": "ok"},
                "agudos": {"correlacion": 1.0, "perdida_db": 0.0, "estado": "ok"},
            },
            "resumen": "El archivo es mono — no aplica análisis estéreo.",
        }

    # === Análisis armónico / tonal ===
    armonia = _analizar_armonia(y, sr, hop_length, bloques_rms, frames_por_bloque)

    # === Distribución de secciones ===
    distribucion = _analizar_distribucion(bloques_rms)

    # Carencia espectral — umbrales recalibrados con 38 sesiones reales
    # En electrónica el kick domina graves, así que medios y agudos siempre están
    # por debajo en promedio. Umbrales anteriores (-46/-56) eran demasiado agresivos,
    # pero -50/-60 perdía tracks con carencia real (16, 23). Punto medio:
    carencia_medios = db_media < -48
    carencia_agudos = db_aguda < -58

    # === Harshness (picos molestos en medios-altos) ===
    harshness = _analizar_harshness(mel_db, mel_freqs)

    # === Loudness (LUFS) ===
    # Pasamos audio ya cargado para evitar re-lectura desde disco
    loudness = _analizar_loudness(audio_path, y_preloaded=y, sr_preloaded=sr,
                                  y_stereo_preloaded=y_stereo if es_stereo else None)

    # === Saturación dinámica (over-compression / "chafado") ===
    # Cruza LUFS + LRA + rango_dinamico para detectar si el limiter ha aplastado
    # la dinámica. Los tres juntos dan una firma fiable de over-limiting:
    #   - LUFS alto solo: puede ser correcto (master de club).
    #   - LRA bajo solo: track simple sin variaciones, no es por sí solo señal de saturación.
    #   - rango_dinamico bajo solo: track de mezcla densa, idem.
    #   - LUFS alto + LRA bajo + rango_dinamico bajo: el track está apretado.
    _lufs = loudness.get("lufs_integrado", -99)
    _lra = loudness.get("rango_loudness", 0)
    if _lufs > -50:  # solo si la medición es válida (no silencio)
        sat_score = 0
        if _lufs > -7:
            sat_score += 2
        elif _lufs > -9:
            sat_score += 1
        if _lra < 3:
            sat_score += 2
        elif _lra < 4.5:
            sat_score += 1
        if rango_dinamico < 1.5:
            sat_score += 2
        elif rango_dinamico < 1.8:
            sat_score += 1

        if sat_score >= 5:
            loudness["saturacion_dinamica"] = "extrema"
            loudness["aviso_saturacion"] = (
                f"El track muestra firma clara de over-limiting: LUFS {_lufs:.1f}, LRA "
                f"{_lra:.1f} LU y rango dinámico {rango_dinamico:.2f}. A este nivel de "
                f"compresión es casi seguro que estás perdiendo cuerpo, transitorios del "
                f"kick y aire en agudos. Probablemente el track suene 'pequeño' en sistemas "
                f"grandes y fatigue al oído. Recomendado: baja 2-3dB el input gain del "
                f"limiter y vuelve a comparar con una referencia del género."
            )
        elif sat_score >= 3:
            loudness["saturacion_dinamica"] = "elevada"
            loudness["aviso_saturacion"] = (
                f"Hay señales de compresión agresiva: LUFS {_lufs:.1f}, LRA {_lra:.1f} LU, "
                f"rango dinámico {rango_dinamico:.2f}. El track puede sonar plano o aplanado "
                f"al compararlo con referencias. Si tu intención es tocar en club está dentro "
                f"de norma, pero verifica con monitores grandes que no estés perdiendo "
                f"cuerpo ni transitorios."
            )
        elif sat_score >= 2:
            loudness["saturacion_dinamica"] = "moderada"
        else:
            loudness["saturacion_dinamica"] = "ok"

    # Madurez estimada
    if duracion_seg < 120 or (not tiene_desarrollo and contraste_energetico == "bajo"):
        madurez_estimada = "verde"
    elif (tiene_desarrollo and contraste_energetico in ["medio", "alto"]
          and duracion_seg > 180 and not distribucion["estructura_problematica"]):
        madurez_estimada = "avanzado"
    else:
        madurez_estimada = "en_desarrollo"

    return {
        "duracion_seg": round(duracion_seg, 1),
        "duracion_fmt": f"{int(duracion_seg // 60)}:{int(duracion_seg % 60):02d}",
        "bpm": round(tempo, 1),
        "bloques_rms": [round(b, 4) for b in bloques_rms],
        "n_bloques": n_bloques,
        "varianza_energia": round(varianza_energia, 4),
        "ratio_grave": round(float(ratios[0]), 4),
        "ratio_media": round(float(ratios[1]), 4),
        "ratio_aguda": round(float(ratios[2]), 4),
        "db_grave": round(db_grave, 1),
        "db_media": round(db_media, 1),
        "db_aguda": round(db_aguda, 1),
        "diff_grave_media": round(diff_grave_media, 1),
        "diff_sub_low": round(diff_sub_low, 1),
        "densidad_espectral": round(densidad_espectral, 4),
        "rango_dinamico": round(rango_dinamico, 2),
        "cambios_significativos": cambios_significativos,
        "contraste_energetico": contraste_energetico,
        "balance_grave": balance_grave,
        "densidad_global": densidad_global,
        "tiene_desarrollo": tiene_desarrollo,
        "madurez_estimada": madurez_estimada,
        "carencia_medios": carencia_medios,
        "carencia_agudos": carencia_agudos,
        "distribucion": distribucion,
        "armonia": armonia,
        "mono_compat": mono_compat,
        "espectro_bandas": espectro_bandas,
        "espectro_bandas_norm": espectro_bandas_norm,
        "loudness": loudness,
        "harshness": harshness,
    }


def _analizar_harshness(mel_db: np.ndarray, mel_freqs: np.ndarray) -> dict:
    """
    Detecta harshness (chirrido/aspereza) en medios-altos (2-8kHz).
    Enfoque multi-señal: combina análisis temporal frame-a-frame.
    Compara presencia (2-8kHz) contra medios (200-2000Hz) por frame,
    luego mide picos (p95), porcentaje de dominio, y varianza temporal.
    Calibrado con 38 sesiones reales + feedback experto.
    """
    resultado = {
        "tiene_harshness": False,
        "nivel": "",              # "leve", "notable", "severo"
        "pico_p95": 0.0,          # percentil 95 del ratio presencia/medios por frame
        "pct_frames_harsh": 0.0,  # % de frames donde presencia > medios
        "zona_problema": "",      # "presencia" (2-6kHz) o "brillos" (6-8kHz) o "ambas"
        "peak_freq_hz": 0,        # frecuencia (Hz) con más energía en la banda 2-10kHz
        "caracter": "",           # "transitorio", "sostenido" o "mixto" — pista del tipo de elemento
    }

    # Bandas de análisis
    mask_pres = (mel_freqs >= 2000) & (mel_freqs < 8000)
    mask_mid = (mel_freqs >= 200) & (mel_freqs < 2000)
    mask_pres_baja = (mel_freqs >= 2000) & (mel_freqs < 6000)
    mask_pres_alta = (mel_freqs >= 6000) & (mel_freqs < 10000)

    if not mask_pres.any() or not mask_mid.any():
        return resultado

    # Energía por frame en cada banda
    pres_por_frame = np.mean(mel_db[mask_pres, :], axis=0)
    mid_por_frame = np.mean(mel_db[mask_mid, :], axis=0)

    # Ratio presencia - medios por frame (en dB)
    ratio = pres_por_frame - mid_por_frame

    p95 = float(np.percentile(ratio, 95))
    pct_mayor = float(np.mean(ratio > 0) * 100)

    resultado["pico_p95"] = round(p95, 1)
    resultado["pct_frames_harsh"] = round(pct_mayor, 1)

    # Sistema de puntos para decidir harshness.
    # Recalibrado mayo 2026 con 19 tracks etiquetados por Alex: el set anterior
    # producía falsos positivos sistemáticos en tech house, techno, hard techno
    # y dub techno cuando había hi-hats/distorsión propios del género (p95~5-7,
    # pct~25-30). Subimos los puntos de corte para exigir más evidencia.
    # Tracks que antes disparaban "leve" o "notable" con p95<6.5 o pct<22 ahora
    # caen por debajo del umbral. El descuento adicional por género se aplica
    # en reglas.py (harshness_mezcla).
    puntos = 0
    if p95 > 9:
        puntos += 2
    elif p95 > 6.5:
        puntos += 1

    if pct_mayor > 35:
        puntos += 2
    elif pct_mayor > 22:
        puntos += 1

    # Para clasificar, además de los puntos exigimos que p95 y pct cumplan
    # un mínimo individual — evita "leve" disparado solo por pct alto con
    # p95 minúsculo (típico de hats moderados pero no agresivos).
    if puntos >= 4:
        resultado["tiene_harshness"] = True
        resultado["nivel"] = "severo"
    elif puntos >= 3:
        resultado["tiene_harshness"] = True
        resultado["nivel"] = "notable"
    elif puntos >= 2 and p95 > 6 and pct_mayor > 22:
        resultado["tiene_harshness"] = True
        resultado["nivel"] = "leve"

    # Localizar zona problema
    if resultado["tiene_harshness"]:
        db_pres_baja = float(np.mean(mel_db[mask_pres_baja, :])) if mask_pres_baja.any() else -80
        db_pres_alta = float(np.mean(mel_db[mask_pres_alta, :])) if mask_pres_alta.any() else -80
        if db_pres_baja > db_pres_alta + 2:
            resultado["zona_problema"] = "presencia"
        elif db_pres_alta > db_pres_baja + 2:
            resultado["zona_problema"] = "brillos"
        else:
            resultado["zona_problema"] = "ambas"

        # Pico exacto: frecuencia con mayor energía media dentro de 2-10kHz.
        # Da una pista más fina que la zona (ej: 3.5 kHz → presencia baja, sibilantes / leads;
        # 7 kHz → brillos / aire). Usa mask_pres ∪ mask_pres_alta para cubrir 2-10kHz.
        mask_full = mask_pres | mask_pres_alta
        if mask_full.any():
            mean_db_per_freq = np.mean(mel_db[mask_full, :], axis=1)
            peak_idx_local = int(np.argmax(mean_db_per_freq))
            peak_freq = float(mel_freqs[mask_full][peak_idx_local])
            # Redondear a 100Hz para no dar falsa precisión (el mel-spectrogram tiene
            # resolución limitada en agudos)
            resultado["peak_freq_hz"] = int(round(peak_freq / 100.0) * 100)

        # Carácter: transitorio vs sostenido.
        # - Transitorio: pocos frames con harshness pero picos altos → percusión/golpes
        # - Sostenido: muchos frames con harshness pero picos moderados → synth/voz/pad
        # - Mixto: cualquier combinación intermedia
        # Calibrado para los rangos típicos donde ya hay harshness detectada (p95 > 5, pct > 15)
        if pct_mayor < 25 and p95 > 5:
            resultado["caracter"] = "transitorio"
        elif pct_mayor > 35 and p95 < 7:
            resultado["caracter"] = "sostenido"
        else:
            resultado["caracter"] = "mixto"

    return resultado


def _analizar_loudness(audio_path: str, y_preloaded=None, sr_preloaded=None,
                       y_stereo_preloaded=None) -> dict:
    """
    Mide loudness según ITU-R BS.1770 (LUFS).
    Usa audio precargado si está disponible para evitar re-lectura de disco.
    Retorna: LUFS integrado, short-term max, rango, y nivel relativo.
    """
    resultado = {
        "lufs_integrado": -99.0,
        "lufs_short_term_max": -99.0,
        "rango_loudness": 0.0,
        "true_peak_dbtp": -99.0,      # true peak con oversampling 4x (ITU-R BS.1770)
        "nivel": "",                  # "bajo", "moderado", "alto", "muy_alto"
        "referencia": "",             # texto con contexto
        "consejo_master": "",         # texto accionable según nivel
        "saturacion_dinamica": "",    # "ok"|"moderada"|"elevada"|"extrema"
        "aviso_saturacion": "",       # texto solo cuando saturación elevada/extrema
        "nivel_true_peak": "",        # "ok"|"streaming"|"clipping" según severidad
        "aviso_true_peak": "",        # texto accionable cuando excede umbrales
    }

    try:
        # Usar audio precargado si disponible, si no cargar desde disco
        if y_preloaded is not None and sr_preloaded is not None:
            rate = sr_preloaded
            if y_stereo_preloaded is not None:
                # Stereo: transponer de (2, N) a (N, 2) para pyloudnorm
                data = y_stereo_preloaded.T
            else:
                # Mono: duplicar a estéreo
                data = np.column_stack([y_preloaded, y_preloaded])
        else:
            data, rate = sf.read(audio_path)
            if data.ndim == 1:
                data = np.column_stack([data, data])

        meter = pyln.Meter(rate)

        # LUFS integrado (todo el track)
        lufs_i = meter.integrated_loudness(data)
        resultado["lufs_integrado"] = round(float(lufs_i), 1)

        # True Peak (dBTP) — ITU-R BS.1770 exige medirlo sobre el archivo a su
        # sample rate nativo con oversampling 4x. Reusar el audio ya
        # resampleado a 22050 introduce overshoot del filtro de antialiasing
        # y falsea el valor (lo eleva 2-3 dB típicos).
        # Por eso releemos el archivo aquí desde disco, fuera del flujo
        # general que sí puede trabajar a 22050.
        try:
            native, native_sr = sf.read(audio_path, always_2d=True, dtype="float32")
            # Sample peak primero (referencia exacta sobre samples del archivo)
            sample_peak_lin = float(np.max(np.abs(native)))
            sample_peak_db = 20.0 * float(np.log10(sample_peak_lin)) if sample_peak_lin > 1e-9 else -99.0

            # Oversampling 4x con filtro polifásico de alta calidad para captar
            # inter-sample peaks. Procesamos canal a canal en sr nativo.
            tp_per_channel = []
            for ch in range(native.shape[1]):
                up = librosa.resample(
                    native[:, ch],
                    orig_sr=native_sr, target_sr=native_sr * 4,
                    res_type="soxr_hq",
                )
                tp_per_channel.append(float(np.max(np.abs(up))))
            tp_lin = max(tp_per_channel) if tp_per_channel else 0.0
            tp_db = 20.0 * float(np.log10(tp_lin)) if tp_lin > 1e-9 else -99.0

            # Sanity: el true peak nunca puede ser MENOR que el sample peak.
            # Si por artefacto el oversampleado da menos, nos quedamos con el
            # sample peak (cota inferior segura).
            resultado["true_peak_dbtp"] = round(max(tp_db, sample_peak_db), 1)
        except Exception:
            # Fallback: sample peak sobre el audio ya cargado (sin oversampling)
            peak_lin = float(np.max(np.abs(data)))
            if peak_lin > 1e-9:
                resultado["true_peak_dbtp"] = round(20.0 * float(np.log10(peak_lin)), 1)

        # Aviso de true peak según severidad. Umbrales basados en estándares
        # de industria, no en datos de Mentotrack (no necesitan calibrado).
        # - > 0 dBTP: clipping digital real, peor caso. Distorsión audible en
        #   cualquier reproducción que use bit depth fijo.
        # - > -1 dBTP: por encima del ceiling recomendado para streaming. Los
        #   codecs lossy (AAC, MP3, Opus) generan inter-sample peaks adicionales
        #   al comprimir y pueden saturar el reproductor del oyente.
        # - <= -1 dBTP: zona segura para streaming.
        tp_val = resultado["true_peak_dbtp"]
        if tp_val > 0.0:
            resultado["nivel_true_peak"] = "clipping"
            resultado["aviso_true_peak"] = (
                f"True peak en {tp_val:+.1f} dBTP — el master clipea digitalmente. "
                "Habrá distorsión audible en cualquier sistema de reproducción. "
                "Baja el ceiling del limiter del master a -1 dBTP y reanaliza."
            )
        elif tp_val > -1.0:
            resultado["nivel_true_peak"] = "streaming"
            resultado["aviso_true_peak"] = (
                f"True peak en {tp_val:+.1f} dBTP — por encima del ceiling recomendado para streaming. "
                "Spotify, YouTube y Apple Music aplican normalización + recodificación lossy que "
                "puede generar inter-sample peaks adicionales y meter distorsión audible. "
                "Pon el ceiling del limiter de master a -1 dBTP como margen de seguridad."
            )
        elif tp_val > -99.0:
            resultado["nivel_true_peak"] = "ok"

        # Short-term loudness (ventanas de 3 segundos) para encontrar el pico
        block_size = int(rate * 3)  # 3 segundos
        hop = int(rate * 1)         # salto de 1 segundo para no perder picos
        lufs_blocks = []
        for i in range(0, len(data) - block_size, hop):
            block = data[i:i + block_size]
            try:
                l = meter.integrated_loudness(block)
                if l > -70:  # ignorar silencio
                    lufs_blocks.append(l)
            except Exception:
                continue

        if lufs_blocks:
            resultado["lufs_short_term_max"] = round(float(max(lufs_blocks)), 1)
            # LRA según EBU R-128 (versión robustecida tras feedback de Alex, 2026-05):
            # El cálculo anterior producía rangos irreales (30-60 LU) en tracks
            # con tramos muy silenciosos pasando la puerta absoluta (-70 LUFS) o
            # bloques con loudness inestable por la naturaleza de calcular
            # integrated_loudness sobre ventanas de 3s.
            # Procedimiento corregido:
            # 1) Gate absoluto endurecido: descartar bloques < -50 LUFS (antes -70).
            #    Bloques bajo -50 LUFS son prácticamente silencio musical y suelen
            #    venir de fades/transiciones donde integrated_loudness es inestable.
            # 2) Gate relativo según ungated mean de los bloques supervivientes
            #    (no según lufs_i, que puede estar sesgado por silencios).
            # 3) LRA = percentil 95 − percentil 10 de los bloques que quedan.
            # 4) Cap defensivo a 25 LU para protegernos de outliers persistentes:
            #    en música producida un LRA > 25 LU es prácticamente imposible y
            #    casi seguro un artefacto. Logueamos cuando aplica.
            lufs_arr = np.array(lufs_blocks)
            lufs_arr = lufs_arr[lufs_arr > -50]
            if len(lufs_arr) >= 2:
                ungated_mean = float(np.mean(lufs_arr))
                lufs_arr_g = lufs_arr[lufs_arr > (ungated_mean - 20)]
                if len(lufs_arr_g) >= 2:
                    p95 = float(np.percentile(lufs_arr_g, 95))
                    p10 = float(np.percentile(lufs_arr_g, 10))
                    lra_raw = p95 - p10
                else:
                    lra_raw = float(max(lufs_arr) - min(lufs_arr))
            elif len(lufs_arr) == 1:
                lra_raw = 0.0
            else:
                lra_raw = 0.0

            if lra_raw > 25:
                print(f"[LRA] valor anómalo capeado: {lra_raw:.1f} → 25.0 LU")
                lra_raw = 25.0
            resultado["rango_loudness"] = round(float(lra_raw), 1)

        # Clasificación de nivel
        lufs = resultado["lufs_integrado"]
        if lufs > -6:
            resultado["nivel"] = "muy_alto"
            resultado["referencia"] = (
                "Nivel muy alto, típico de masters preparados para club o pista. "
                "Spotify normaliza a -14 LUFS, así que parte de este volumen se pierde en streaming."
            )
            resultado["consejo_master"] = (
                "Si la intención es tocar en sesión, este nivel es coherente con lo que se "
                "escucha hoy en pista. Asegúrate de que no estás sacrificando dinámica: el "
                "kick debe seguir teniendo pegada propia, el track debe respirar entre "
                "secciones, y la mezcla no debería sonar plana ni fatigada al escucharla "
                "varios minutos seguidos."
            )
        elif lufs > -9:
            resultado["nivel"] = "alto"
            resultado["referencia"] = (
                "Nivel alto, en línea con masters de club/pista actuales. "
                "Spotify normaliza a -14 LUFS, así que parte del volumen se perderá en streaming."
            )
            resultado["consejo_master"] = (
                "Nivel coherente con masters de club y pista actuales."
            )
        elif lufs > -14:
            resultado["nivel"] = "moderado"
            resultado["referencia"] = (
                "Buen nivel para un pre-master o master. "
                "Cerca del estándar de streaming (-14 LUFS en Spotify, -16 en Apple Music)."
            )
            resultado["consejo_master"] = (
                "Nivel bien situado para streaming. Si vas a club o sello, ajusta hacia "
                "-8/-10 LUFS según el género."
            )
        elif lufs > -20:
            resultado["nivel"] = "bajo"
            resultado["referencia"] = (
                "Nivel bajo — normal si el track no está masterizado. "
                "Un mastering profesional subirá esto a -8 a -14 LUFS según el género."
            )
            resultado["consejo_master"] = (
                "Si el track está terminado, un mastering básico lo sube: limiter con ceiling "
                "a -1dB, input gain hasta -8/-10 LUFS. Si suena distorsionado al subir, hay "
                "problemas de mezcla que resolver primero."
            )
        else:
            resultado["nivel"] = "muy_bajo"
            resultado["referencia"] = (
                "Nivel muy bajo. Puede ser que el track esté en fase muy temprana "
                "o que los niveles de mezcla estén demasiado bajos."
            )
            resultado["consejo_master"] = (
                "Antes de pensar en mastering, sube los niveles de mezcla. Apunta a que el "
                "bus master marque picos en -6dB y RMS en torno a -18dB. Luego ya aplicas "
                "limiter para llegar al target del género."
            )

    except Exception:
        resultado["referencia"] = "No se pudo medir el loudness de este archivo."

    return resultado


def _analizar_distribucion(bloques_rms: list) -> dict:
    distribucion = {
        "inicio_abrupto": False,
        "sin_outro": False,
        "break_desproporcionado": False,
        "drop_corto": False,
        "ratio_bajo_alto": 0.0,
        "max_seccion_baja": 0,
        "max_seccion_alta": 0,
        "estructura_problematica": False,
        # Añadido 2026-05 (insight 4 de Alex): el break más largo no recupera
        # energía después, "no paga" la anticipación que generó.
        "break_sin_payoff": False,
        "ratio_payoff": 1.0,  # energía después / energía antes del break (alto = ok)
        # Posición (en bloques) de la sección de baja energía más larga — para
        # convertir a timecode en el diagnóstico y decir "el break entre X:XX y Y:YY".
        "break_bloque_inicio": -1,
        "break_bloque_fin": -1,
    }

    if len(bloques_rms) < 4:
        return distribucion

    media_rms = np.mean(bloques_rms)
    clasificacion = ["alto" if b > media_rms else "bajo" for b in bloques_rms]

    # Construir secciones con (tipo, longitud, indice_inicio)
    secciones = []
    current_type = clasificacion[0]
    current_len = 1
    current_start = 0
    for i in range(1, len(clasificacion)):
        if clasificacion[i] == current_type:
            current_len += 1
        else:
            secciones.append((current_type, current_len, current_start))
            current_type = clasificacion[i]
            current_len = 1
            current_start = i
    secciones.append((current_type, current_len, current_start))

    secciones_bajas = [(s[1], s[2]) for s in secciones if s[0] == "bajo"]
    secciones_altas = [(s[1], s[2]) for s in secciones if s[0] == "alto"]
    n_bloques_bajos = sum(s[0] for s in secciones_bajas) if secciones_bajas else 0
    n_bloques_altos = sum(s[0] for s in secciones_altas) if secciones_altas else 0
    max_baja = max((s[0] for s in secciones_bajas), default=0)
    max_alta = max((s[0] for s in secciones_altas), default=0)
    total_bloques = len(bloques_rms)

    distribucion["max_seccion_baja"] = max_baja
    distribucion["max_seccion_alta"] = max_alta
    distribucion["ratio_bajo_alto"] = round(n_bloques_bajos / (n_bloques_altos + 1e-10), 2)

    # Inicio abrupto: solo si arranca con ≥3 bloques altos seguidos (≥24 compases)
    # En electrónica, 2 bloques altos al inicio (~16 compases) es una intro
    # normal con kick/hats para mezcla DJ, no un "inicio abrupto".
    if len(secciones) >= 2 and secciones[0][0] == "alto" and secciones[0][1] >= 3:
        distribucion["inicio_abrupto"] = True
    # Sin outro: ≥3 bloques altos al final sin caída
    if len(secciones) >= 2 and secciones[-1][0] == "alto" and secciones[-1][1] >= 3:
        distribucion["sin_outro"] = True
    if max_baja > total_bloques * 0.35:
        distribucion["break_desproporcionado"] = True
    if max_alta > 0 and max_alta < total_bloques * 0.20 and max_baja > max_alta * 1.5:
        distribucion["drop_corto"] = True

    # Break sin payoff: busca el break (sección baja) más largo y compara la
    # energía media de la sección alta INMEDIATAMENTE POSTERIOR con la
    # sección alta INMEDIATAMENTE ANTERIOR. Si la posterior no supera a la
    # anterior, el break "no paga" — no genera el contraste anticipado.
    # Sólo aplica si el break es de cierto tamaño (≥2 bloques, ~16 compases).
    if secciones_bajas:
        # Encontrar la sección "bajo" más larga
        idx_max_break = max(
            range(len(secciones)),
            key=lambda i: secciones[i][1] if secciones[i][0] == "bajo" else -1
        )
        len_break, start_break = secciones[idx_max_break][1], secciones[idx_max_break][2]
        distribucion["break_bloque_inicio"] = start_break
        distribucion["break_bloque_fin"] = start_break + len_break
        if len_break >= 2:
            # Sección alta anterior
            antes = next(
                (s for s in reversed(secciones[:idx_max_break]) if s[0] == "alto"),
                None,
            )
            # Sección alta posterior
            despues = next(
                (s for s in secciones[idx_max_break + 1:] if s[0] == "alto"),
                None,
            )
            if antes and despues:
                e_antes = float(np.mean(bloques_rms[antes[2]:antes[2] + antes[1]]))
                e_despues = float(np.mean(bloques_rms[despues[2]:despues[2] + despues[1]]))
                ratio = e_despues / (e_antes + 1e-10)
                distribucion["ratio_payoff"] = round(ratio, 2)
                # No paga: el post-break NO supera al pre-break en al menos un 5%.
                # Margen pequeño porque la diferencia de "subir energía después
                # del break" en electrónica suele ser audible incluso con ratios
                # de 1.05-1.15.
                if ratio < 1.05:
                    distribucion["break_sin_payoff"] = True

    # Estructura problemática: distribución real (break largo o drop corto, o
    # break sin payoff que es señal de arreglo flojo aunque no esté desproporcionado).
    distribucion["estructura_problematica"] = (
        distribucion["break_desproporcionado"]
        or distribucion["drop_corto"]
        or distribucion["break_sin_payoff"]
    )

    return distribucion


def _analizar_mono_compatibility(y_stereo: np.ndarray, sr: int) -> dict:
    """
    Análisis de compatibilidad mono del track estéreo.
    Mide correlación L/R, pérdida de energía al sumar a mono,
    y análisis por bandas frecuenciales (graves deben ser mono,
    agudos pueden tener más spread).
    """
    resultado = {
        "es_stereo": True,
        "correlacion_lr": 0.0,        # -1 a 1 (1=idénticos, 0=sin relación, <0=fase invertida)
        "perdida_mono_db": 0.0,       # dB perdidos al sumar a mono (negativo=pérdida)
        "nivel_compatibilidad": "",    # "excelente", "buena", "problematica", "critica"
        "fase_invertida": False,       # true si hay cancelación de fase significativa
        "bandas": {
            "graves": {"correlacion": 0.0, "perdida_db": 0.0, "estado": ""},
            "medios": {"correlacion": 0.0, "perdida_db": 0.0, "estado": ""},
            "agudos": {"correlacion": 0.0, "perdida_db": 0.0, "estado": ""},
        },
        "resumen": "",
    }

    left = y_stereo[0]
    right = y_stereo[1]

    # --- Correlación global L/R ---
    # Pearson correlation: 1=idénticos, 0=sin relación, -1=fase invertida
    correlacion = float(np.corrcoef(left, right)[0, 1])
    resultado["correlacion_lr"] = round(correlacion, 3)

    # --- Pérdida de energía al sumar a mono ---
    mono_sum = (left + right) / 2.0
    energia_stereo = float(np.mean(left ** 2) + np.mean(right ** 2)) / 2.0
    energia_mono = float(np.mean(mono_sum ** 2))

    if energia_stereo > 0:
        ratio_energia = energia_mono / energia_stereo
        perdida_db = float(round(10 * np.log10(ratio_energia + 1e-10), 1))
    else:
        perdida_db = 0.0
    resultado["perdida_mono_db"] = perdida_db

    # Fase invertida: si la suma mono tiene MENOS energía que cada canal individual
    resultado["fase_invertida"] = bool(perdida_db < -3.0)

    # --- Análisis por bandas frecuenciales ---
    # Graves (<200Hz), Medios (200-4000Hz), Agudos (>4000Hz)
    n_fft = 2048
    bandas_config = {
        "graves": (0, 200),
        "medios": (200, 4000),
        "agudos": (4000, sr // 2),
    }

    # Computar STFT una sola vez fuera del bucle (antes se calculaba 6 veces)
    stft_left = librosa.stft(left, n_fft=n_fft)
    stft_right = librosa.stft(right, n_fft=n_fft)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    for banda_nombre, (freq_min, freq_max) in bandas_config.items():

        mask = (freqs >= freq_min) & (freqs < freq_max)
        if not mask.any():
            continue

        # Reconstruir señal filtrada por banda
        stft_left_banda = np.zeros_like(stft_left)
        stft_right_banda = np.zeros_like(stft_right)
        stft_left_banda[mask, :] = stft_left[mask, :]
        stft_right_banda[mask, :] = stft_right[mask, :]

        left_banda = librosa.istft(stft_left_banda)
        right_banda = librosa.istft(stft_right_banda)

        # Alinear longitudes
        min_len = min(len(left_banda), len(right_banda))
        left_banda = left_banda[:min_len]
        right_banda = right_banda[:min_len]

        # Correlación de la banda
        if np.std(left_banda) > 1e-10 and np.std(right_banda) > 1e-10:
            corr_banda = float(np.corrcoef(left_banda, right_banda)[0, 1])
        else:
            corr_banda = 1.0  # silencio = compatible

        # Pérdida mono de la banda
        mono_banda = (left_banda + right_banda) / 2.0
        e_stereo_banda = (float(np.mean(left_banda ** 2)) + float(np.mean(right_banda ** 2))) / 2.0
        e_mono_banda = float(np.mean(mono_banda ** 2))

        if e_stereo_banda > 1e-10:
            perdida_banda = float(round(10 * np.log10(e_mono_banda / e_stereo_banda + 1e-10), 1))
        else:
            perdida_banda = 0.0

        # Estado de la banda
        if banda_nombre == "graves":
            # Graves DEBEN ser mono-compatibles (corr > 0.85)
            if corr_banda > 0.85:
                estado = "ok"
            elif corr_banda > 0.6:
                estado = "revisar"
            else:
                estado = "problema"
        elif banda_nombre == "medios":
            # Medios: tolerancia moderada
            if corr_banda > 0.5:
                estado = "ok"
            elif corr_banda > 0.2:
                estado = "revisar"
            else:
                estado = "problema"
        else:  # agudos
            # Agudos: más tolerancia a stereo spread
            if corr_banda > 0.2:
                estado = "ok"
            elif corr_banda > -0.1:
                estado = "revisar"
            else:
                estado = "problema"

        resultado["bandas"][banda_nombre] = {
            "correlacion": round(corr_banda, 3),
            "perdida_db": perdida_banda,
            "estado": estado,
        }

    # --- Nivel de compatibilidad global ---
    graves_ok = resultado["bandas"]["graves"]["estado"] == "ok"
    tiene_problema_banda = any(
        b["estado"] == "problema" for b in resultado["bandas"].values()
    )

    if resultado["fase_invertida"]:
        resultado["nivel_compatibilidad"] = "critica"
        resultado["resumen"] = (
            "El track tiene problemas graves de fase. Al sumar a mono se pierde "
            "energía significativa. Esto afectará la reproducción en sistemas mono "
            "(clubs, smartphones, radio)."
        )
    elif correlacion >= 0.95 and graves_ok:
        # Caso típico de duda del usuario: "correlación 100%, ¿es bueno o malo?"
        # Técnicamente la compatibilidad mono es perfecta, pero significa que el
        # track suena casi en mono — sin movimiento estéreo. Para club/streaming
        # da igual, para escucha doméstica puede sentirse "plano".
        resultado["nivel_compatibilidad"] = "excelente"
        resultado["resumen"] = (
            f"Compatibilidad mono perfecta — los canales L y R son casi idénticos "
            f"(correlación {correlacion*100:.0f}%). Eso garantiza que suena bien en "
            f"cualquier sistema (club, smartphone, radio), pero también significa "
            f"que el track tiene poca anchura estéreo: si buscas sensación de "
            f"profundidad o movimiento lateral, abre el panning de hats, pads o "
            f"FX hacia los lados. No toques kick ni bajo — deben quedarse al centro."
        )
    elif correlacion > 0.85 and graves_ok:
        resultado["nivel_compatibilidad"] = "excelente"
        resultado["resumen"] = (
            "El track es completamente compatible con mono. "
            "Sonará bien en cualquier sistema de reproducción."
        )
    elif correlacion > 0.5 and graves_ok and not tiene_problema_banda:
        resultado["nivel_compatibilidad"] = "buena"
        resultado["resumen"] = (
            "Buena compatibilidad mono con espacialidad estéreo saludable. "
            "No debería haber problemas en la mayoría de sistemas."
        )
    elif not graves_ok or tiene_problema_banda:
        resultado["nivel_compatibilidad"] = "problematica"
        problemas = []
        if not graves_ok:
            problemas.append("los graves no están centrados")
        if resultado["bandas"]["medios"]["estado"] == "problema":
            problemas.append("los medios tienen cancelaciones de fase")
        if resultado["bandas"]["agudos"]["estado"] == "problema":
            problemas.append("los agudos tienen fase invertida")
        resultado["resumen"] = (
            f"Hay aspectos a revisar: {', '.join(problemas)}. "
            f"Esto puede causar pérdida de impacto en sistemas mono."
        )
    else:
        resultado["nivel_compatibilidad"] = "buena"
        resultado["resumen"] = "Compatibilidad mono aceptable."

    return resultado


# Nombres de notas para el chromagrama
_NOTAS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Perfiles Krumhansl-Kessler para detección de tonalidad
_PERFIL_MAYOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_PERFIL_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def _analizar_armonia(y: np.ndarray, sr: int, hop_length: int,
                      bloques_rms: list, frames_por_bloque: int) -> dict:
    """
    Análisis armónico/tonal del track.
    Retorna: tonalidad estimada, consistencia armónica entre secciones,
    contenido tonal vs percusivo, y indicadores de posibles conflictos.
    """
    resultado = {
        "key": "",
        "key_confidence": 0.0,
        "modo": "",  # "mayor" o "menor"
        "contenido_tonal": 0.0,  # 0-1, cuánto contenido armónico tiene
        "consistencia_armonica": 0.0,  # 0-1, si la armonía es estable entre secciones
        "notas_dominantes": [],  # top 3 pitch classes
        "n_notas_activas": 0,  # cuántas pitch classes tienen presencia significativa
        "complejidad_armonica": "",  # "simple", "moderada", "compleja", "caotica"
        "posible_conflicto_tonal": False,  # si hay indicios de choques armónicos
        "ratio_tonal_percusivo": 0.0,  # >1 = más tonal, <1 = más percusivo
        "variacion_tonal_por_bloque": [],  # key dominante por bloque temporal
    }

    # Separar componentes armónico y percusivo
    y_harmonic, y_percussive = librosa.effects.hpss(y)

    # Ratio tonal/percusivo
    energia_tonal = float(np.sum(y_harmonic ** 2))
    energia_percusiva = float(np.sum(y_percussive ** 2))
    resultado["ratio_tonal_percusivo"] = round(
        energia_tonal / (energia_percusiva + 1e-10), 2
    )

    # Contenido tonal (0-1): proporción de energía en la parte armónica
    energia_total = energia_tonal + energia_percusiva
    resultado["contenido_tonal"] = round(
        energia_tonal / (energia_total + 1e-10), 3
    )

    # Chromagrama sobre la parte armónica (CQT para máxima precisión tonal en graves)
    chroma = librosa.feature.chroma_cqt(
        y=y_harmonic, sr=sr, hop_length=hop_length, n_chroma=12
    )

    # --- Detección de tonalidad (Krumhansl-Kessler) ---
    chroma_medio = np.mean(chroma, axis=1)  # perfil medio de las 12 notas

    mejor_score = -1
    mejor_key = 0
    mejor_modo = "mayor"

    for shift in range(12):
        perfil_rotado_mayor = np.roll(_PERFIL_MAYOR, shift)
        perfil_rotado_menor = np.roll(_PERFIL_MENOR, shift)

        corr_mayor = float(np.corrcoef(chroma_medio, perfil_rotado_mayor)[0, 1])
        corr_menor = float(np.corrcoef(chroma_medio, perfil_rotado_menor)[0, 1])

        if corr_mayor > mejor_score:
            mejor_score = corr_mayor
            mejor_key = shift
            mejor_modo = "mayor"
        if corr_menor > mejor_score:
            mejor_score = corr_menor
            mejor_key = shift
            mejor_modo = "menor"

    resultado["key"] = _NOTAS[mejor_key]
    resultado["modo"] = mejor_modo
    resultado["key_confidence"] = round(max(0, mejor_score), 3)

    # --- Notas dominantes y complejidad ---
    # Normalizar chroma medio
    chroma_norm = chroma_medio / (np.max(chroma_medio) + 1e-10)

    # Notas con presencia significativa (>55% de la más fuerte)
    # Umbral alto para filtrar armónicos de kicks/percusión que inflan el conteo
    umbral_nota = 0.55
    notas_activas = int(np.sum(chroma_norm > umbral_nota))
    resultado["n_notas_activas"] = notas_activas

    # Top 3 notas dominantes
    top_indices = np.argsort(chroma_medio)[::-1][:3]
    resultado["notas_dominantes"] = [_NOTAS[i] for i in top_indices]

    # Complejidad armónica (umbrales conservadores para evitar falsos positivos)
    if notas_activas <= 4:
        resultado["complejidad_armonica"] = "simple"
    elif notas_activas <= 7:
        resultado["complejidad_armonica"] = "moderada"
    elif notas_activas <= 9:
        resultado["complejidad_armonica"] = "compleja"
    else:
        resultado["complejidad_armonica"] = "caotica"

    # --- Consistencia armónica entre bloques temporales ---
    n_bloques = max(1, len(bloques_rms))
    n_frames_chroma = chroma.shape[1]
    frames_por_bloque_chroma = max(1, n_frames_chroma // n_bloques)

    perfiles_por_bloque = []
    keys_por_bloque = []

    for i in range(n_bloques):
        inicio = i * frames_por_bloque_chroma
        fin = min((i + 1) * frames_por_bloque_chroma, n_frames_chroma)
        if fin <= inicio:
            continue

        chroma_bloque = np.mean(chroma[:, inicio:fin], axis=1)
        perfiles_por_bloque.append(chroma_bloque)

        # Key del bloque
        mejor_score_bloque = -1
        mejor_key_bloque = 0
        for shift in range(12):
            corr = float(np.corrcoef(chroma_bloque, np.roll(_PERFIL_MAYOR, shift))[0, 1])
            if corr > mejor_score_bloque:
                mejor_score_bloque = corr
                mejor_key_bloque = shift
            corr = float(np.corrcoef(chroma_bloque, np.roll(_PERFIL_MENOR, shift))[0, 1])
            if corr > mejor_score_bloque:
                mejor_score_bloque = corr
                mejor_key_bloque = shift

        keys_por_bloque.append(_NOTAS[mejor_key_bloque])

    resultado["variacion_tonal_por_bloque"] = keys_por_bloque

    # Consistencia: correlación media entre perfiles de bloques consecutivos
    if len(perfiles_por_bloque) >= 2:
        correlaciones = []
        for i in range(len(perfiles_por_bloque) - 1):
            corr = float(np.corrcoef(perfiles_por_bloque[i], perfiles_por_bloque[i + 1])[0, 1])
            correlaciones.append(corr)
        resultado["consistencia_armonica"] = round(float(np.mean(correlaciones)), 3)
    else:
        resultado["consistencia_armonica"] = 1.0

    # --- Detección de posible conflicto tonal ---
    # Conservador: solo marcar cuando hay evidencia fuerte de choque real
    # Requiere consistencia MUY baja + muchas notas + key confidence baja
    if (resultado["consistencia_armonica"] < 0.45
            and notas_activas >= 8
            and resultado["key_confidence"] < 0.5):
        resultado["posible_conflicto_tonal"] = True
    # Keys muy distintas entre bloques + consistencia baja
    if (len(set(keys_por_bloque)) >= 4
            and resultado["consistencia_armonica"] < 0.5):
        resultado["posible_conflicto_tonal"] = True

    return resultado
