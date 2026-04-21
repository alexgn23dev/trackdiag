"""
Extractor de señales de audio.
Recibe un path de audio y retorna un diccionario con señales crudas y derivadas.
"""

import librosa
import numpy as np
import pyloudnorm as pyln
import soundfile as sf


def extraer_senales(audio_path: str, bpm_manual: int | None = None) -> dict:
    y, sr = librosa.load(audio_path, sr=22050, mono=True)

    # Cargar versión estéreo para análisis de mono compatibility
    y_stereo, sr_stereo = librosa.load(audio_path, sr=22050, mono=False)
    es_stereo = y_stereo.ndim == 2 and y_stereo.shape[0] == 2
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
    # Normal: hasta 18dB es típico en producción electrónica con kick prominente
    # Elevado: 18-24dB indica acumulación grave que vale la pena revisar
    # Excesivo: >24dB es claramente problemático
    if diff_grave_media > 24:
        balance_grave = "excesivo"
    elif diff_grave_media > 18:
        balance_grave = "elevado"
    else:
        balance_grave = "normal"

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
    loudness = _analizar_loudness(audio_path)

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
        "nivel": "",           # "leve", "notable", "severo"
        "pico_p95": 0.0,      # percentil 95 del ratio presencia/medios por frame
        "pct_frames_harsh": 0.0,  # % de frames donde presencia > medios
        "zona_problema": "",   # "presencia" (2-6kHz) o "brillos" (6-8kHz) o "ambas"
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

    # Sistema de puntos para decidir harshness (calibrado con 38 sesiones reales):
    # Track 23 (chirriante): p95=9.2, pct=33% → debe detectar severo
    # Track 19 (bien):       p95=5.0, pct=25% → NO debe detectar
    # Track 10 (bien):       p95=2.3, pct=14% → NO debe detectar
    # Track 25 (chirriante): p95=2.2, pct=10% → no detectable por espectro (es tímbrico)
    puntos = 0
    if p95 > 7:
        puntos += 2
    elif p95 > 5:
        puntos += 1

    if pct_mayor > 30:
        puntos += 2
    elif pct_mayor > 20:
        puntos += 1

    if puntos >= 3:
        resultado["tiene_harshness"] = True
        resultado["nivel"] = "severo"
    elif puntos >= 2:
        resultado["tiene_harshness"] = True
        resultado["nivel"] = "notable"
    elif puntos >= 1 and p95 > 4 and pct_mayor > 15:
        # Solo leve si ambas señales coinciden
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

    return resultado


def _analizar_loudness(audio_path: str) -> dict:
    """
    Mide loudness según ITU-R BS.1770 (LUFS).
    Carga a sample rate original para máxima precisión.
    Retorna: LUFS integrado, short-term max, rango, y nivel relativo.
    """
    resultado = {
        "lufs_integrado": -99.0,
        "lufs_short_term_max": -99.0,
        "rango_loudness": 0.0,
        "nivel": "",        # "bajo", "moderado", "alto", "muy_alto"
        "referencia": "",   # texto con contexto
    }

    try:
        # Cargar a sample rate original para precisión LUFS
        data, rate = sf.read(audio_path)

        # Si es mono, duplicar a estéreo (pyloudnorm espera al menos 1D)
        if data.ndim == 1:
            data = np.column_stack([data, data])

        meter = pyln.Meter(rate)

        # LUFS integrado (todo el track)
        lufs_i = meter.integrated_loudness(data)
        resultado["lufs_integrado"] = round(float(lufs_i), 1)

        # Short-term loudness (ventanas de 3 segundos) para encontrar el pico
        block_size = int(rate * 3)  # 3 segundos
        hop = int(rate * 1)         # salto de 1 segundo
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
            resultado["rango_loudness"] = round(
                float(max(lufs_blocks) - min(lufs_blocks)), 1
            )

        # Clasificación de nivel
        lufs = resultado["lufs_integrado"]
        if lufs > -6:
            resultado["nivel"] = "muy_alto"
            resultado["referencia"] = (
                "Nivel muy alto. El track probablemente está sobre-comprimido o clippeando. "
                "Las plataformas de streaming lo van a bajar de volumen igualmente."
            )
        elif lufs > -9:
            resultado["nivel"] = "alto"
            resultado["referencia"] = (
                "Nivel alto, típico de masters agresivos. "
                "Spotify normaliza a -14 LUFS, así que parte de este volumen se perderá en streaming."
            )
        elif lufs > -14:
            resultado["nivel"] = "moderado"
            resultado["referencia"] = (
                "Buen nivel para un pre-master o master. "
                "Cerca del estándar de streaming (-14 LUFS en Spotify, -16 en Apple Music)."
            )
        elif lufs > -20:
            resultado["nivel"] = "bajo"
            resultado["referencia"] = (
                "Nivel bajo — normal si el track no está masterizado. "
                "Un mastering profesional subirá esto a -8 a -14 LUFS según el género."
            )
        else:
            resultado["nivel"] = "muy_bajo"
            resultado["referencia"] = (
                "Nivel muy bajo. Puede ser que el track esté en fase muy temprana "
                "o que los niveles de mezcla estén demasiado bajos."
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
    }

    if len(bloques_rms) < 4:
        return distribucion

    media_rms = np.mean(bloques_rms)
    clasificacion = ["alto" if b > media_rms else "bajo" for b in bloques_rms]

    secciones = []
    current_type = clasificacion[0]
    current_len = 1
    for i in range(1, len(clasificacion)):
        if clasificacion[i] == current_type:
            current_len += 1
        else:
            secciones.append((current_type, current_len))
            current_type = clasificacion[i]
            current_len = 1
    secciones.append((current_type, current_len))

    secciones_bajas = [s[1] for s in secciones if s[0] == "bajo"]
    secciones_altas = [s[1] for s in secciones if s[0] == "alto"]
    n_bloques_bajos = sum(secciones_bajas) if secciones_bajas else 0
    n_bloques_altos = sum(secciones_altas) if secciones_altas else 0
    max_baja = max(secciones_bajas) if secciones_bajas else 0
    max_alta = max(secciones_altas) if secciones_altas else 0
    total_bloques = len(bloques_rms)

    distribucion["max_seccion_baja"] = max_baja
    distribucion["max_seccion_alta"] = max_alta
    distribucion["ratio_bajo_alto"] = round(n_bloques_bajos / (n_bloques_altos + 1e-10), 2)

    if len(secciones) >= 2 and secciones[0][0] == "alto" and secciones[0][1] >= 2:
        distribucion["inicio_abrupto"] = True
    if len(secciones) >= 2 and secciones[-1][0] == "alto" and secciones[-1][1] >= 2:
        distribucion["sin_outro"] = True
    if max_baja > total_bloques * 0.35:
        distribucion["break_desproporcionado"] = True
    if max_alta > 0 and max_alta < total_bloques * 0.20 and max_baja > max_alta * 1.5:
        distribucion["drop_corto"] = True

    distribucion["estructura_problematica"] = (
        distribucion["break_desproporcionado"]
        or distribucion["drop_corto"]
        or (distribucion["inicio_abrupto"] and distribucion["sin_outro"])
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

    for banda_nombre, (freq_min, freq_max) in bandas_config.items():
        # Filtrar por banda usando STFT
        stft_left = librosa.stft(left, n_fft=n_fft)
        stft_right = librosa.stft(right, n_fft=n_fft)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

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

    # Chromagrama sobre la parte armónica (más limpio que sobre el mix completo)
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
