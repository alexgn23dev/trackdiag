"""
Extractor de señales de audio.
Recibe un path de audio y retorna un diccionario con señales crudas y derivadas.
"""

import os

import librosa
import numpy as np
import pyloudnorm as pyln
import soundfile as sf

from .versiones import PEAK_ALGORITHM_VERSION

# ===========================================================================
# Estado de validación del medidor de true peak
# ===========================================================================
# Cuatro estados separados, porque significan cosas distintas y mezclarlos
# permitiría dar por validado algo que solo se ha comprobado contra sí mismo.
#
# VERDAD — el que decide. Se le pide al medidor recuperar un pico CONSTRUIDO
#   de antemano: se fabrica una señal a 44100x64 limitada en banda, se anota
#   su máximo real, se decima a 44,1 kHz y se mide. No compara contra otra
#   implementación: comprueba si acierta un número que no conocía.
#   tests/test_reconstruccion.py::TestContraUnaVerdadConstruida.
# INTERNA — la batería automatizada: valor analítico, FIR de referencia del
#   anexo 2 de BS.1770-5, interpolación sinc por FFT, polifásico de scipy y
#   ffmpeg. Detecta regresiones; no puede certificar, porque todo vive dentro
#   del mismo ecosistema Python/ffmpeg.
# EXTERNA — contraste manual contra un medidor profesional de escritorio
#   (Youlean, iZotope Insight, el del DAW). Se registra en
#   tests/VALIDACION_MANUAL.md.
#
#   ATENCIÓN — desde el 2026-08-09 este estado es INFORMATIVO y ya NO decide.
#   Se montó creyendo que un medidor comercial era la referencia ajena
#   definitiva. Medido contra la verdad construida, no lo es: sobre los
#   fixtures 01 y 06, Youlean se desvía -0,16 dB y soxr +0,17 dB. Los dos
#   fallan, en direcciones opuestas. Certificar contra Youlean era corregir
#   un examen con las respuestas de otro alumno. Se conserva porque documenta
#   cuánto se separan las implementaciones reales entre sí, que es un dato
#   útil de cara al usuario — pero no es un aprobado.
#
# GLOBAL — se deriva, no se pone a mano: VERDAD **y** INTERNA.
#
# Y los cuatro están ATADOS A LA VERSIÓN DEL ALGORITMO. Una validación dice
# "este método, medido así, da estos números". Si el método cambia, la
# validación deja de aplicar: no se hereda. `_VALIDADO_PARA_ALGORITMO` es la
# versión contra la que se validó; si `PEAK_ALGORITHM_VERSION` deja de
# coincidir, todos los estados caen a False solos y hay que revalidar.
_VALIDADO_PARA_ALGORITMO = "peak-soxr_hq_8x-1"

# Estas constantes NO son de fiar por sí solas: son una declaración humana.
# Lo que las hace válidas es que test_reconstruccion.py y test_picos.py
# vuelven a ejecutar la comprobación y fallan si la declaración no coincide
# con lo medido. Poner True a mano sin que la medida acompañe rompe el CI.
_VALIDACION_VERDAD_DECLARADA = True     # 2026-08-08, RESULTADOS_VALIDACION.md §8b
_VALIDACION_INTERNA_DECLARADA = True    # 2026-08-07, RESULTADOS_VALIDACION.md §8
_VALIDACION_EXTERNA_DECLARADA = False   # informativa; tests/VALIDACION_MANUAL.md

# Tolerancia de la validación contra la verdad construida, en dB. El error
# medido con material realista (contenido hasta 20 kHz) es de 0,002 dB con la
# referencia y 0,002 dB con el medidor de producción; 0,01 deja margen para
# cambios de versión de numpy o soxr sin dar un falso aprobado.
TOL_VERDAD_CONSTRUIDA_DB = 0.01

# Factor de sobremuestreo para la medida de picos. Ver la nota en
# `_analizar_loudness` y tests/test_reconstruccion.py: 8 no es un número
# elegido a ojo, es donde el error de rejilla deja de ser medible.
OVERSAMPLING_PICOS = 8

_ALGORITMO_COINCIDE = PEAK_ALGORITHM_VERSION == _VALIDADO_PARA_ALGORITMO

TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED = _VALIDACION_VERDAD_DECLARADA and _ALGORITMO_COINCIDE
TRUE_PEAK_INTERNAL_VALIDATION_PASSED = _VALIDACION_INTERNA_DECLARADA and _ALGORITMO_COINCIDE
TRUE_PEAK_EXTERNAL_VALIDATION_PASSED = _VALIDACION_EXTERNA_DECLARADA and _ALGORITMO_COINCIDE
# Lo que decide es acertar la verdad construida. La batería interna sigue
# haciendo falta: es la que detecta que una actualización de librería mueva
# algo. La externa NO entra — ver la nota de arriba.
_TRUE_PEAK_VALIDATED = (TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED
                        and TRUE_PEAK_INTERNAL_VALIDATION_PASSED)

if not _ALGORITMO_COINCIDE:
    print(f"[PICOS] El algoritmo es {PEAK_ALGORITHM_VERSION} pero la validación "
          f"se hizo para {_VALIDADO_PARA_ALGORITMO}: los estados de validación "
          f"quedan en False hasta revalidar (tests/validar_true_peak.py y "
          f"tests/VALIDACION_MANUAL.md).")

# Versión de la TAXONOMÍA de picos, independiente de la del algoritmo: una
# cambia cómo se mide, la otra cómo se nombra lo medido.
#   1 — hasta v0.5.70: ok | streaming | clipping  (llamaba clipping a un over)
#   2 — desde v0.5.72: ok | margen_streaming | true_peak_over |
#                      overs_float_recuperables
PEAK_TAXONOMY_VERSION = 2

#
# PRIORIDAD DE FASE 2A, registrada aquí a propósito: un WAV 32-bit float con
# picos por encima de 0 dBFS se sigue clasificando como "clipping" y se le
# dice al usuario que "el master clipea digitalmente". Es falso — en coma
# flotante esos overs son recuperables bajando el gain. Desde v0.5.71 ya se
# registra `archivo_sample_format`, así que el dato para distinguirlo existe;
# lo que falta es usarlo.

# Bits de almacenamiento por subtype de libsndfile. OJO: en FLOAT/DOUBLE esto
# es el tamaño del contenedor de la muestra, NO un techo PCM — por eso
# `archivo_pcm_bit_depth` queda a None en esos casos.
_SUBTYPE_STORAGE_BITS = {
    "PCM_S8": 8, "PCM_U8": 8, "PCM_16": 16, "PCM_24": 24, "PCM_32": 32,
    "FLOAT": 32, "DOUBLE": 64,
    "ALAW": 8, "ULAW": 8, "VOX_ADPCM": 4, "IMA_ADPCM": 4, "MS_ADPCM": 4,
}
_SUBTYPES_FLOAT = {"FLOAT", "DOUBLE"}
_SUBTYPES_LOSSY = {
    "MPEG_LAYER_I", "MPEG_LAYER_II", "MPEG_LAYER_III",
    "VORBIS", "OPUS", "GSM610", "G721_32", "G723_24", "G723_40",
}
_EXTENSIONES_LOSSY = {".mp3", ".ogg", ".opus", ".m4a", ".aac"}

# ===========================================================================
# Señal analizable
# ===========================================================================
# Umbral por debajo del cual damos por hecho que NO hay señal, no que la haya
# floja. Un pico de -80 dBFS es una diezmilésima de fondo de escala: ni la
# grabación más silenciosa de un track real baja de ahí. Un bounce bajo de
# verdad (mezcla sin masterizar, -30/-40 dBFS de pico) queda muy por encima y
# se analiza con normalidad — es un caso legítimo que el motor ya cubre con
# el nivel "muy_bajo".
_UMBRAL_PICO_SIN_SENAL_DBFS = -80.0
# Segundo criterio, para señales con un chasquido aislado sobre silencio:
# si la energía media es despreciable, tampoco hay nada que analizar.
_UMBRAL_RMS_SIN_SENAL_DBFS = -90.0

# Ventana de bloque cuando no hay tempo detectable. 15 s son ~8 compases a
# 128 BPM, el mismo orden que el camino con tempo, para que los umbrales
# calibrados de contraste y estructura sigan siendo comparables.
_BLOQUE_SIN_TEMPO_SEG = 15.0


class AudioSinSenalAnalizable(Exception):
    """El archivo se decodifica pero no contiene señal que se pueda analizar.

    Silencio digital, un archivo de puros ceros o muestras no finitas. NO se
    lanza por tener nivel bajo: para eso está el nivel "muy_bajo" del
    diagnóstico normal.
    """

    codigo = "AUDIO_WITHOUT_ANALYZABLE_SIGNAL"

    def __init__(self, motivo: str, detalle: dict | None = None):
        super().__init__(motivo)
        self.motivo = motivo
        self.detalle = detalle or {}


def _comprobar_senal_analizable(y: np.ndarray) -> None:
    """Lanza AudioSinSenalAnalizable si el audio no da para analizar nada.

    Se ejecuta ANTES que cualquier medición: sin esto, pyloudnorm devuelve
    -inf en silencio, ese -inf viaja hasta la respuesta y Starlette revienta
    con `Out of range float values are not JSON compliant` (HTTP 500).
    """
    if y is None or y.size == 0:
        raise AudioSinSenalAnalizable("El archivo no contiene muestras de audio.",
                                      {"motivo_tecnico": "sin_muestras"})

    finitos = np.isfinite(y)
    if not finitos.all():
        n_malos = int(y.size - np.count_nonzero(finitos))
        # Si además de valores raros no queda nada útil, es inanalizable.
        if n_malos == y.size:
            raise AudioSinSenalAnalizable(
                "El archivo contiene valores de audio inválidos (NaN o infinito).",
                {"motivo_tecnico": "muestras_no_finitas", "n_muestras_malas": n_malos})
        y = y[finitos]

    pico = float(np.max(np.abs(y))) if y.size else 0.0
    pico_db = 20.0 * float(np.log10(pico)) if pico > 0 else -999.0
    rms = float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0
    rms_db = 20.0 * float(np.log10(rms)) if rms > 0 else -999.0

    if pico_db <= _UMBRAL_PICO_SIN_SENAL_DBFS or rms_db <= _UMBRAL_RMS_SIN_SENAL_DBFS:
        raise AudioSinSenalAnalizable(
            "El archivo está en silencio o no tiene señal suficiente para analizarlo.",
            {
                "motivo_tecnico": "silencio",
                "pico_dbfs": None if pico_db < -998 else round(pico_db, 1),
                "rms_dbfs": None if rms_db < -998 else round(rms_db, 1),
                "umbral_pico_dbfs": _UMBRAL_PICO_SIN_SENAL_DBFS,
                "umbral_rms_dbfs": _UMBRAL_RMS_SIN_SENAL_DBFS,
            })


def extraer_senales(audio_path: str, bpm_manual: int | None = None,
                    omitir_armonia: bool = False) -> dict:
    # Carga única: stereo a 22050 Hz (sin límite de duración para no perder estructura)
    y_stereo, sr = librosa.load(audio_path, sr=22050, mono=False)
    es_stereo = y_stereo.ndim == 2 and y_stereo.shape[0] == 2

    # Derivar mono del stereo (evita segunda carga)
    if es_stereo:
        y = np.mean(y_stereo, axis=0)
    else:
        y = y_stereo if y_stereo.ndim == 1 else y_stereo[0]

    # Puerta de entrada: si no hay señal, se corta aquí y no se mide nada.
    # Cualquier análisis sobre silencio produce -inf, divisiones por casi cero
    # y conclusiones sin sentido ("balance grave normal" sobre un archivo mudo).
    _comprobar_senal_analizable(y)

    # Duración calculada del array cargado (evita re-lectura del archivo)
    duracion_seg = librosa.get_duration(y=y, sr=sr)

    # Tempo — manual si el usuario lo declara, si no detección automática.
    #
    # Si no hay pulso detectable (un drone, un pad sostenido, una toma
    # ambiental) NO se inventa un tempo: se publica `bpm = None` y
    # `tempo_detectado = False`. Antes esto era además un crash: `beat_track`
    # devuelve 0 y la línea de abajo dividía entre cero → HTTP 500.
    tempo = None
    tempo_fuente = "no_detectado"
    if bpm_manual and bpm_manual > 0:
        tempo = int(round(bpm_manual))
        tempo_fuente = "manual"
    else:
        try:
            tempo_bruto, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=128)
            tempo_bruto = (float(tempo_bruto[0]) if hasattr(tempo_bruto, "__len__")
                           else float(tempo_bruto))
        except Exception:
            tempo_bruto = 0.0
        # Rango de cordura: fuera de 30-300 BPM la detección no es creíble en
        # este dominio, y `beat_track` devuelve 0 cuando no encuentra pulso.
        if np.isfinite(tempo_bruto) and 30.0 <= tempo_bruto <= 300.0:
            # En electrónica los BPM son enteros: se redondea al más cercano.
            tempo = int(round(tempo_bruto))
            tempo_fuente = "detectado"

    tempo_detectado = tempo is not None

    # RMS por bloques. Con tempo se usan ~8 compases; sin tempo, una ventana
    # fija en SEGUNDOS. El análisis de estructura, contraste y distribución
    # sigue funcionando: solo deja de estar alineado a compás, que es
    # información que en este material no existe de todas formas.
    compases_por_bloque = 8
    beats_por_bloque = compases_por_bloque * 4
    if tempo_detectado:
        duracion_bloque_seg = (60.0 / tempo) * beats_por_bloque
    else:
        # 15 s ≈ 8 compases a 128 BPM: el mismo orden de magnitud que el
        # camino normal, para que los umbrales calibrados sigan valiendo.
        duracion_bloque_seg = _BLOQUE_SIN_TEMPO_SEG
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
    # HPSS + chroma_cqt es la parte más cara del extractor. En la comparación
    # contra referencia no se usa la armonía, así que se puede saltar.
    if omitir_armonia:
        armonia = {
            "key": "", "key_confidence": 0.0, "modo": "", "contenido_tonal": 0.0,
            "consistencia_armonica": 0.0, "notas_dominantes": [], "n_notas_activas": 0,
            "complejidad_armonica": "", "posible_conflicto_tonal": False,
            "ratio_tonal_percusivo": 0.0, "variacion_tonal_por_bloque": [],
        }
    else:
        armonia = _analizar_armonia(y, sr, hop_length, bloques_rms, frames_por_bloque)

    # === Distribución de secciones ===
    # desarrollo_ok: mismo criterio que el descuento de problema_arreglo —
    # un track con desarrollo y contraste medio/alto no debe marcarse por
    # "break sin payoff" (se reserva para bocetos sin desarrollo).
    desarrollo_ok = tiene_desarrollo and contraste_energetico in ["medio", "alto"]
    distribucion = _analizar_distribucion(bloques_rms, desarrollo_ok=desarrollo_ok)

    # Carencia espectral — umbrales recalibrados con 38 sesiones reales
    # En electrónica el kick domina graves, así que medios y agudos siempre están
    # por debajo en promedio. Umbrales anteriores (-46/-56) eran demasiado agresivos,
    # pero -50/-60 perdía tracks con carencia real (16, 23). Punto medio:
    carencia_medios = db_media < -48
    carencia_agudos = db_aguda < -58

    # === Harshness (picos molestos en medios-altos) ===
    harshness = _analizar_harshness(mel_db, mel_freqs)

    # === Metadatos del archivo ===
    # Solo registro (fase 1): ninguna decisión del motor los lee todavía.
    formato = _analizar_formato(audio_path)

    # === Loudness (LUFS) ===
    # Pasamos audio ya cargado para evitar re-lectura desde disco
    # Golpes detectados: hacen falta para saber si las muestras en el techo
    # caen sobre transitorios (firma de un clipper) o sobre material
    # sostenido (síntoma de un problema de ganancia). Ver fase 2B.
    try:
        onsets_seg = librosa.onset.onset_detect(y=y, sr=sr, units="time")
    except Exception:
        onsets_seg = None

    loudness = _analizar_loudness(audio_path, y_preloaded=y, sr_preloaded=sr,
                                  y_stereo_preloaded=y_stereo if es_stereo else None,
                                  formato=formato, onsets_seg=onsets_seg)

    # Taxonomía de picos (fase 2A). Necesita el formato del archivo, así que
    # se calcula aquí y no dentro de _analizar_loudness. Los campos antiguos
    # (`nivel_true_peak`, `aviso_true_peak`) siguen intactos: la interfaz usa
    # los nuevos, los parsers y el histórico siguen viendo los viejos.
    loudness.update(_clasificar_picos(loudness, formato))
    loudness.update(_clasificar_recorte(loudness, formato))

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
        # None cuando no hay pulso detectable: no se inventa un valor.
        "bpm": tempo,
        "tempo_detectado": tempo_detectado,
        "tempo_fuente": tempo_fuente,
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
        "formato": formato,
    }


def _analizar_formato(audio_path: str) -> dict:
    """Metadatos del archivo tal y como llegó, sin interpretarlos.

    FASE 1: esto se REGISTRA y nada más. Ninguna regla, umbral, clasificación
    ni texto depende todavía de estos campos. El objetivo es tener datos
    reales (¿cuánta gente sube 32-bit float? ¿a qué sample rate?) antes de
    decidir en fase 2 qué ramas del diagnóstico merecen existir.

    `storage_bits` vs `pcm_bit_depth`: en un WAV FLOAT de 32 bits los 32 bits
    son el tamaño del contenedor, no un techo de cuantización — ahí no hay
    valor máximo representable en el sentido del punto fijo, y por eso
    `pcm_bit_depth` es None. Confundir ambos es justo lo que lleva a tratar
    un over recuperable como si fuera recorte irreversible.
    """
    extension = os.path.splitext(audio_path or "")[1].lower()
    info_fmt = {
        "archivo_extension": extension,
        "archivo_container": "",
        "archivo_codec": "",
        "archivo_subtype": "",
        "archivo_sample_format": "desconocido",   # integer | float | desconocido
        "archivo_storage_bits": None,
        "archivo_pcm_bit_depth": None,
        "archivo_sample_rate": 0,
        "archivo_canales": 0,
        "archivo_lossy": None,
        "archivo_metadata_source": "desconocida",  # soundfile | extension | desconocida
    }
    try:
        info = sf.info(audio_path)
        subtype = (info.subtype or "").upper()
        es_float = subtype in _SUBTYPES_FLOAT
        es_lossy = subtype in _SUBTYPES_LOSSY
        storage = _SUBTYPE_STORAGE_BITS.get(subtype)
        if es_lossy:
            # En un códec con pérdida no hay ni bit depth de almacenamiento ni
            # techo PCM: lo que se decodifica es coma flotante reconstruida.
            storage = None
            sample_format = "float"
        elif es_float:
            sample_format = "float"
        elif storage is not None:
            sample_format = "integer"
        else:
            sample_format = "desconocido"
        info_fmt.update({
            "archivo_container": info.format or "",
            "archivo_codec": info.subtype_info or subtype,
            "archivo_subtype": subtype,
            "archivo_sample_format": sample_format,
            "archivo_storage_bits": storage,
            # Solo el punto fijo tiene techo de cuantización.
            "archivo_pcm_bit_depth": storage if sample_format == "integer" else None,
            "archivo_sample_rate": int(info.samplerate or 0),
            "archivo_canales": int(info.channels or 0),
            "archivo_lossy": bool(es_lossy),
            "archivo_metadata_source": "soundfile",
        })
    except Exception:
        # Nunca romper el análisis por no poder leer una cabecera. Se degrada
        # a lo único que se sabe con certeza: la extensión.
        info_fmt["archivo_lossy"] = extension in _EXTENSIONES_LOSSY if extension else None
        info_fmt["archivo_metadata_source"] = "extension" if extension else "desconocida"
    return info_fmt


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


# ---------------------------------------------------------------------------
# Fase 2B — muestras a fondo de escala
# ---------------------------------------------------------------------------
# El true peak dice si la ONDA RECONSTRUIDA asoma por encima del techo. Eso
# muchas veces no es un problema: el pico vive entre muestras y no hay nada
# recortado. Lo que de verdad es daño es que a la onda le hayan cortado la
# punta en plano, y eso solo se ve CONTANDO MUESTRAS.
#
# Lo que justifica la fase, medido: hoy dos tracks muy distintos salen con la
# MISMA categoría `true_peak_over` y son indistinguibles en el informe —
#   * uno con el sample peak a -0,15 dBFS y NINGUNA muestra en el techo: el
#     pico vive entre muestras, el máster está intacto, no hay nada que tocar;
#   * otro con 4,3 ms de onda completamente plana: daño real e irreversible.
# La diferencia práctica es "no toques nada" frente a "vuelve a exportar".
#
# LÍMITE, declarado: si el recorte ocurrió antes del bounce y DESPUÉS se bajó
# el nivel, las muestras ya no están en el techo y contar no encuentra nada.
# No se arregla contando mejor — la huella no está en el archivo. El diseño
# original prometía cazar "techo correcto + recorte dentro"; eso es imposible,
# porque el true peak nunca es menor que el sample peak: si hay muestras en el
# techo, el true peak ya está en 0 o por encima.

# Ventana alrededor de un golpe dentro de la cual se considera que una muestra
# en el techo "cae en un transitorio".
_VENTANA_TRANSITORIO_SEG = 0.050
# Muestras consecutivas a partir de las cuales una racha es una meseta.
_MIN_MUESTRAS_MESETA = 3
# Por encima de esta duración la racha ya no es compatible con un clipper
# recortando picos: es material sostenido aplastado.
_RACHA_SOSTENIDA_MS = 1.0
# Y por encima de esta fracción, además, deja de ser puntual.
_PCT_SOSTENIDO = 0.05
# Fracción de muestras en techo que deben caer en golpes para que el patrón
# sea el de un clipper trabajando sobre la percusión.
_CONCENTRACION_TRANSITORIOS = 0.8


def _rachas(mascara: np.ndarray) -> np.ndarray:
    """Longitudes de los tramos consecutivos de True. Vector vacío si no hay."""
    if not mascara.any():
        return np.zeros(0, dtype=np.int64)
    bordes = np.diff(np.concatenate(
        ([0], mascara.astype(np.int8), [0])))
    return np.flatnonzero(bordes == -1) - np.flatnonzero(bordes == 1)


def _lsb_del_formato(formato: dict):
    """Escalón mínimo del archivo, o None si el concepto no aplica.

    En punto fijo el techo existe y el escalón lo fija el bit depth. En coma
    flotante NO HAY TECHO: contar "muestras a fondo de escala" no significa
    nada, y fabricar un techo de 0 por convenio sería volver al error que
    corrigió la fase 2A. Decisión 2 de DISENO_FASE_2B.md.
    """
    fmt = formato or {}
    # El orden importa para el mensaje. Un MP3 se decodifica a coma flotante,
    # así que caería en la rama del float — pero al usuario no le sirve que le
    # hablemos de coma flotante: él subió un MP3. El motivo que le importa es
    # que lo que estamos midiendo no es su máster, es lo que salió del
    # decodificador. Decisión 3 de DISENO_FASE_2B.md.
    if fmt.get("archivo_lossy"):
        return None
    if fmt.get("archivo_sample_format") == "float":
        return None
    bits = fmt.get("archivo_pcm_bit_depth")
    if not bits or bits < 8:
        return None
    return 2.0 ** -(bits - 1)


def _medir_muestras_en_techo(native: np.ndarray, native_sr: int,
                             formato: dict, onsets_seg=None) -> dict:
    """Mediciones OBJETIVAS sobre el array de muestras.

    Todo lo que hay aquí sale de contar. Dos personas con el mismo archivo
    obtienen los mismos números; no depende de ningún umbral discutible. Lo
    interpretable (qué significa una racha de 3 ms) vive en `_clasificar_recorte`.
    """
    salida = {
        "recorte_medible": False,
        "recorte_no_medible_motivo": "",
        "muestras_en_techo_por_canal": [],
        "muestras_en_techo_total": 0,
        "pct_muestras_en_techo": 0.0,
        "racha_maxima_muestras": 0,
        "racha_maxima_ms": 0.0,
        "n_mesetas": 0,
        "canal_afectado": "",
        "concentracion_en_transitorios": None,
        "posicion_maximo_seg": 0.0,
        "distancia_maximo_al_borde_seg": 0.0,
        "true_peak_at_file_edge": False,
        "umbral_techo_dbfs": None,
    }

    lsb = _lsb_del_formato(formato)
    if lsb is None:
        fmt = formato or {}
        if fmt.get("archivo_lossy"):
            motivo = "lossy"
        elif fmt.get("archivo_sample_format") == "float":
            motivo = "coma_flotante"
        else:
            motivo = "bit_depth_desconocido"
        salida["recorte_no_medible_motivo"] = motivo
        return salida
    if native is None or native.size == 0 or native_sr <= 0:
        salida["recorte_no_medible_motivo"] = "sin_audio"
        return salida

    salida["recorte_medible"] = True
    # Se trabaja en la precisión en la que ya está leído el archivo. Pasar a
    # float64 duplicaría la memoria (200+ MB en una pista larga) sin ganar
    # nada: un valor de 24 bits cabe exacto en float32, que tiene 24 bits de
    # mantisa. Por encima de 24 bits el margen de 1 LSB se queda por debajo de
    # la resolución de float32 y el umbral colapsa al fondo de escala exacto,
    # que para esos formatos es justo lo que interesa contar.
    abs_nat = np.abs(native)
    # El margen de 1 LSB es lo que hace que el conteo no dependa del error de
    # cuantización: una muestra escrita a fondo de escala y la inmediatamente
    # inferior son indistinguibles a efectos de "el limitador tocó aquí".
    umbral = abs_nat.dtype.type(1.0 - lsb)
    salida["umbral_techo_dbfs"] = round(20.0 * float(np.log10(float(umbral))), 6)
    en_techo = abs_nat >= umbral

    por_canal = en_techo.sum(axis=0).astype(int).tolist()
    total = int(sum(por_canal))
    salida["muestras_en_techo_por_canal"] = por_canal
    salida["muestras_en_techo_total"] = total
    salida["pct_muestras_en_techo"] = round(
        100.0 * total / float(en_techo.size), 6)

    # Rachas: se miden por canal y se guarda la peor. Una meseta de 40 ms en
    # L es un problema aunque R esté impecable.
    peor_racha = 0
    n_mesetas = 0
    for ch in range(en_techo.shape[1]):
        r = _rachas(en_techo[:, ch])
        if r.size:
            peor_racha = max(peor_racha, int(r.max()))
            n_mesetas += int((r >= _MIN_MUESTRAS_MESETA).sum())
    salida["racha_maxima_muestras"] = peor_racha
    # En ms, que es lo comparable: 20 muestras son 0,45 ms a 44,1 kHz y 0,21 ms
    # a 96 kHz. Los umbrales se ponen sobre esto, nunca sobre el conteo.
    salida["racha_maxima_ms"] = round(1000.0 * peor_racha / native_sr, 4)
    salida["n_mesetas"] = n_mesetas

    if total:
        tocados = [c for c, n in enumerate(por_canal) if n]
        if len(tocados) > 1:
            salida["canal_afectado"] = "ambos"
        elif en_techo.shape[1] >= 2:
            salida["canal_afectado"] = "LR"[tocados[0]] if tocados[0] < 2 else str(tocados[0])
        else:
            salida["canal_afectado"] = "mono"

        if onsets_seg is not None and len(onsets_seg):
            idx = np.flatnonzero(en_techo.any(axis=1))
            t = idx / float(native_sr)
            ons = np.sort(np.asarray(onsets_seg, dtype=np.float64))
            j = np.searchsorted(ons, t)
            izq = np.abs(t - ons[np.clip(j - 1, 0, len(ons) - 1)])
            der = np.abs(ons[np.clip(j, 0, len(ons) - 1)] - t)
            cerca = np.minimum(izq, der) <= _VENTANA_TRANSITORIO_SEG
            salida["concentracion_en_transitorios"] = round(
                float(cerca.mean()), 4)

    plano = int(np.argmax(abs_nat, axis=None) // abs_nat.shape[1])
    pos = plano / float(native_sr)
    dur = len(native) / float(native_sr)
    salida["posicion_maximo_seg"] = round(pos, 4)
    salida["distancia_maximo_al_borde_seg"] = round(min(pos, dur - pos), 4)
    # Se MIDE, no se corrige. En la fase 1.1 quedó comprobado que la
    # sobreoscilación ante un escalón es real y la ven los cuatro métodos: no
    # es un artefacto que haya que suprimir. El campo sirve para poder matizar
    # el texto, no para descontar dB.
    salida["true_peak_at_file_edge"] = bool(plano < 512 or len(native) - plano <= 512)
    return salida


def _clasificar_recorte(medicion: dict, formato: dict) -> dict:
    """Interpreta las mediciones. Aquí sí hay umbrales elegidos, y por eso el
    lenguaje es de probabilidad.

    Dos reglas que vienen de las decisiones cerradas con Alex:

    * NO se afirma intención. Se describe el patrón y con qué es compatible.
    * NO se avisa a todo el mundo. Un clipper haciendo su trabajo no genera
      aviso: un productor que lo usa a propósito no necesita una regañina en
      cada análisis, y si se la damos deja de creerse el resto del informe.

    Y el principio que ordena el copy: cada caso tiene que dejar al productor
    sabiendo algo. Qué se ha medido, qué significa y qué hacer con ello.
    """
    salida = {
        "categoria_recorte": "",
        "severidad_recorte": "info",     # info | atencion
        "titulo_recorte": "",
        "aviso_recorte": "",
    }
    fmt = formato or {}

    if not medicion.get("recorte_medible"):
        motivo = medicion.get("recorte_no_medible_motivo", "")
        if motivo == "lossy":
            salida.update({
                "categoria_recorte": "no_aplica_lossy",
                "titulo_recorte": "Recorte de muestras: hace falta el archivo original",
                "aviso_recorte": (
                    "No se cuentan muestras recortadas en un archivo con pérdida "
                    "(MP3, OGG, AAC). El motivo: lo que analizamos no son tus "
                    "muestras, son las que ha reconstruido el decodificador, y ese "
                    "proceso cambia la forma de onda — puede aplanar picos que "
                    "estaban bien y crear otros que no existían. Acusarte de recortar "
                    "a partir de eso sería injusto. "
                    "Si quieres saber si tu máster tiene recorte real, sube el WAV o "
                    "el AIFF del que salió este archivo."),
            })
        elif motivo == "coma_flotante":
            salida.update({
                "categoria_recorte": "no_aplica_float",
                "titulo_recorte": "Recorte de muestras: no aplica en coma flotante",
                "aviso_recorte": (
                    "No se cuentan muestras recortadas porque en un archivo de coma "
                    "flotante no hay techo que tocar: los valores por encima de 0 se "
                    "guardan tal cual y se recuperan bajando el gain. El recorte "
                    "aparece cuando exportas a PCM (WAV 16/24 bits), que es donde "
                    "esos valores ya no caben. Si quieres este dato, analiza el WAV "
                    "de entrega."),
            })
        else:
            salida.update({
                "categoria_recorte": "no_medible",
                "titulo_recorte": "Recorte de muestras: no se ha podido medir",
                "aviso_recorte": (
                    "No se ha podido determinar la resolución del archivo, y sin "
                    "saber cuál es el valor máximo que admite no se puede contar "
                    "qué muestras lo alcanzan."),
            })
        return salida

    total = medicion["muestras_en_techo_total"]
    racha_ms = medicion["racha_maxima_ms"]
    racha_n = medicion["racha_maxima_muestras"]
    pct = medicion["pct_muestras_en_techo"]
    conc = medicion.get("concentracion_en_transitorios")
    canal = medicion.get("canal_afectado", "")
    es_lossy = bool(fmt.get("archivo_lossy"))

    if total == 0:
        salida.update({
            "categoria_recorte": "sin_muestras_en_techo",
            "titulo_recorte": "Ninguna muestra llega al techo",
            "aviso_recorte": (
                "Ni una sola muestra del archivo alcanza el valor máximo que admite "
                "el formato. Eso descarta el recorte por muestras: la forma de onda "
                "está entera. Ojo, no es lo mismo que el true peak — ese mide la onda "
                "reconstruida entre muestras y puede asomar por encima de 0 sin que "
                "aquí haya nada recortado."),
        })
        return salida

    # Coletilla común: el "de dónde sale" el número, para que el dato enseñe.
    donde = ""
    if canal in ("L", "R"):
        donde = f" Todas están en el canal {canal}, lo que suele apuntar a un elemento concreto mal ajustado más que al máster entero."
    elif canal == "ambos":
        donde = ""

    lossy_nota = ""
    if es_lossy:
        lossy_nota = (
            " Aviso importante: has subido un archivo con pérdida. El decodificador "
            "de MP3 o AAC puede generar muestras a fondo de escala que NO estaban en "
            "tu máster original, así que este recuento no es atribuible a tu mezcla. "
            "Para un dato real, analiza el WAV o AIFF del que salió.")

    # --- Muestras sueltas: el techo se toca, no se recorta -------------------
    if racha_n < _MIN_MUESTRAS_MESETA:
        cuantas = "Hay una muestra que llega" if total == 1 else \
            f"Hay {total} muestras que llegan"
        seguidas = "una sola muestra" if racha_n <= 1 else f"{racha_n} muestras"
        salida.update({
            "categoria_recorte": "techo_tocado",
            "titulo_recorte": "El techo se toca, pero la onda no está recortada",
            "aviso_recorte": (
                f"{cuantas} al máximo del formato, pero "
                f"siempre sueltas: la racha más larga es de {seguidas}. "
                "Para que haya recorte hace falta que varias muestras seguidas se "
                "queden pegadas al techo formando una meseta — es eso lo que aplana "
                "la onda y genera distorsión. Aquí no ocurre: son picos que rozan el "
                "límite y vuelven a bajar." + donde + lossy_nota),
        })
        return salida

    sostenido = (racha_ms > _RACHA_SOSTENIDA_MS and pct > _PCT_SOSTENIDO)
    en_golpes = conc is not None and conc >= _CONCENTRACION_TRANSITORIOS

    # --- Patrón de clipper: corto y en los golpes. No es un aviso -----------
    if en_golpes and not sostenido:
        salida.update({
            "categoria_recorte": "recorte_en_transitorios",
            "titulo_recorte": "Recorte corto y en los golpes: la firma de un clipper",
            "aviso_recorte": (
                f"Hay {total} muestras en el techo formando {medicion['n_mesetas']} "
                f"mesetas, ninguna de más de {racha_ms:.2f} ms, y el "
                f"{conc * 100:.0f}% caen justo sobre golpes de percusión. "
                "Ese patrón es exactamente lo que deja un clipper recortando los "
                "picos de la batería, que es una técnica normal y muy usada en "
                "electrónica: rebaja los transitorios para poder subir el nivel medio "
                "sin que el limitador bombee. Si lo has puesto tú, esto es lo "
                "esperado y no hay nada que corregir. "
                "Lo decimos solo para que sepas que está ahí y hasta dónde llega."
                + lossy_nota),
        })
        return salida

    # --- Recorte sostenido: el caso que sí merece un aviso ------------------
    if sostenido and not es_lossy:
        salida.update({
            "categoria_recorte": "recorte_sostenido",
            "severidad_recorte": "atencion",
            "titulo_recorte": "Hay tramos de onda aplanados",
            "aviso_recorte": (
                f"La racha más larga son {racha_n} muestras seguidas pegadas al techo: "
                f"{racha_ms:.1f} ms de onda completamente plana, y en total el "
                f"{pct:.3f}% de las muestras del archivo están ahí. "
                "Eso ya no encaja con un clipper recortando picos — un clipper actúa "
                "durante décimas de milisegundo sobre transitorios. Un tramo plano de "
                "milisegundos significa que material sostenido (un bajo, un pad, una "
                "nota larga) se ha quedado sin sitio. "
                "Lo que oyes de eso es distorsión armónica añadida, y a diferencia de "
                "un pico alto esto no se arregla después: la información que había en "
                "esa parte de la onda ya no está en el archivo. "
                "Qué hacer: baja el gain de entrada del máster unos dB y vuelve a "
                "exportar desde el proyecto. Si el recorte viene de la mezcla y no del "
                "máster, búscalo en el elemento que suena en ese momento "
                f"(~{medicion['posicion_maximo_seg']:.1f}s). "
                "Y si esto es una decisión estética tuya —distorsión buscada—, "
                "ignóralo: lo marcamos porque no podemos distinguir tu intención, "
                "solo la forma de la onda." + donde),
        })
        return salida

    # --- Recorte breve no concentrado, o lossy sospechoso ------------------
    salida.update({
        "categoria_recorte": "recorte_breve",
        "titulo_recorte": "Recorte puntual",
        "aviso_recorte": (
            f"Hay {medicion['n_mesetas']} meseta(s) de muestras pegadas al techo, la "
            f"más larga de {racha_ms:.2f} ms ({racha_n} muestras). "
            "Son tramos en los que la onda se queda plana en vez de seguir subiendo. "
            "A esta duración el efecto audible es mínimo y es lo que deja cualquier "
            "limitador trabajando cerca del techo. "
            "No hace falta que corrijas nada por esto; si te molesta, un par de dB "
            "menos de entrada en el máster lo quita." + donde + lossy_nota),
    })
    return salida


def _clasificar_picos(loudness: dict, formato: dict) -> dict:
    """Taxonomía de picos (fase 2A). Sustituye a `nivel_true_peak` en la
    interfaz; el campo antiguo se conserva intacto para no romper parsers ni
    la comparabilidad de los análisis históricos.

    Qué se puede afirmar y qué no, que es de lo que iba todo esto:

    * `overs_float_recuperables` — AFIRMABLE. Sabemos que el archivo es coma
      flotante y que hay muestras por encima de 0 dBFS. En float eso no
      recorta la onda: el valor está guardado tal cual y se recupera bajando
      el gain. NO se puede afirmar que haya daño.
    * `true_peak_over` — AFIRMABLE que el pico reconstruido pasa de 0 dBTP.
      NO demuestra que haya muestras recortadas: para eso haría falta contar
      muestras a fondo de escala, que es fase 2B.
    * `margen_streaming` — no es un fallo. Es una recomendación de margen.
    * `ok` — el margen recomendado está cubierto. No dice nada sobre si hay
      recorte dentro de la señal.
    """
    # Se clasifica sobre el valor REDONDEADO a 1 decimal, que es el que se
    # enseña. Si se decidiera sobre el crudo, un track a -0,9997 dBTP se
    # mostraría como "-1,0 dBTP" y a la vez se le diría que está por encima
    # de -1: el número visible contradiría a la categoría.
    def _mostrable(v):
        r = round(v, 1)
        return 0.0 if abs(r) < 0.05 else r   # evita el "-0.0"

    # `true_peak_dbtp` NO se toca: sigue siendo la medición cruda. Lo que se
    # cuantiza es una variable aparte, que es la que decide la categoría y la
    # que se enseña. Las dos viajan en la respuesta.
    tp = _mostrable(loudness.get("true_peak_dbtp", -99.0))
    sp = _mostrable(loudness.get("sample_peak_dbfs", -99.0))
    fmt = formato or {}
    es_float = fmt.get("archivo_sample_format") == "float"
    es_lossy = bool(fmt.get("archivo_lossy"))
    picos_fiables = loudness.get("sample_peak_source") == "archivo_nativo"

    salida = {
        "categoria_picos": "",
        "severidad_picos": "",       # info | atencion
        "titulo_picos": "",
        "aviso_picos": "",
        "nota_lossy_picos": "",
        # Valor cuantizado a 0,1 dB con el que se decide la taxonomía y que
        # se muestra al usuario. NO sustituye a `true_peak_dbtp`.
        "true_peak_classification_value": tp if tp > -99.0 else None,
        "sample_peak_classification_value": sp if sp > -99.0 else None,
        "peak_taxonomy_version": PEAK_TAXONOMY_VERSION,
    }
    if tp <= -99.0:
        salida["peak_taxonomy_version"] = None
        return salida

    # Coletilla para formatos con pérdida: el pico medido es el del audio
    # DECODIFICADO, que no tiene por qué ser el del máster original.
    if es_lossy:
        salida["nota_lossy_picos"] = (
            "Has subido un archivo con pérdida (MP3, OGG…). Parte de estos picos "
            "puede venir de la propia codificación o de la decodificación, no de "
            "tu máster: la codificación con pérdida puede generar picos entre muestras "
            "que no estaban en el original. Para un dato exacto, analiza el WAV o "
            "AIFF del que salió."
        )

    # --- A. Overs en coma flotante: recuperables, no son daño ---------------
    if es_float and picos_fiables and sp > 0.0:
        salida.update({
            "categoria_picos": "overs_float_recuperables",
            "severidad_picos": "atencion",
            "titulo_picos": "Picos por encima de 0 dBFS en un archivo de coma flotante",
            "aviso_picos": (
                f"El archivo llega a {sp:+.1f} dBFS de pico de muestra, por encima de 0. "
                "Es un archivo de coma flotante ({}), y en ese formato los valores por "
                "encima de 0 se guardan tal cual: la onda no se ha recortado por estar "
                "ahí. Se recuperan bajando el gain. Lo que sí hay que hacer es reducirlos "
                "antes de exportar a PCM (WAV 16/24 bits) o de distribuir, porque en punto "
                "fijo esos valores ya no caben y ahí sí se recortarían. Con este dato solo "
                "no se puede afirmar que el máster esté dañado."
            ).format(fmt.get("archivo_subtype", "float")),
        })
        return salida

    # --- B. Pico reconstruido por encima del techo -------------------------
    if tp > 0.0:
        salida.update({
            "categoria_picos": "true_peak_over",
            "severidad_picos": "atencion",
            "titulo_picos": "Picos reconstruidos por encima del techo",
            "aviso_picos": (
                f"El true peak llega a {tp:+.1f} dBTP, por encima de 0. Son picos que "
                "aparecen al reconstruir la onda entre muestras. "
                "Esto no demuestra que las muestras de tu archivo estén recortadas: "
                "el sample peak está en {:+.1f} dBFS. "
                "Sí implica riesgo de distorsión en la reproducción — el conversor del "
                "oyente puede no tener margen para esos picos — y al codificar a MP3 o "
                "AAC, que puede generar picos adicionales. "
                "Qué hacer: baja el ceiling del limiter (prueba -1 dBTP) y vuelve a "
                "analizar para ver cuánto se mueve."
            ).format(sp) if sp > -99.0 else (
                f"El true peak llega a {tp:+.1f} dBTP, por encima de 0. Son picos que "
                "aparecen al reconstruir la onda entre muestras, y no demuestran por sí "
                "solos que las muestras del archivo estén recortadas. Sí implica riesgo "
                "de distorsión al reproducir o al codificar a formatos con pérdida. "
                "Qué hacer: baja el ceiling del limiter (prueba -1 dBTP) y reanaliza."
            ),
        })
        return salida

    # --- C. Entre -1 y 0: margen recomendado, no un error ------------------
    if tp > -1.0:
        salida.update({
            "categoria_picos": "margen_streaming",
            "severidad_picos": "info",
            "titulo_picos": "Margen por debajo de la recomendación de streaming",
            "aviso_picos": (
                f"El true peak está en {tp:+.1f} dBTP: por debajo de 0, pero por encima "
                "de -1. No es un error. Es una recomendación de margen — las "
                "plataformas sugieren dejar el techo en -1 dBTP porque la codificación "
                "con pérdida puede generar picos adicionales y conviene dejarles sitio. "
                "Si vas a distribuir en streaming, bajar el ceiling a -1 dBTP te da ese "
                "colchón. Si es un máster para club o para pinchar, puede quedarse así."
            ),
        })
        return salida

    # --- D. Margen cubierto -------------------------------------------------
    salida.update({
        "categoria_picos": "ok",
        "severidad_picos": "info",
        "titulo_picos": "Margen de picos correcto",
        "aviso_picos": (
            f"El true peak está en {tp:+.1f} dBTP, dentro del margen de -1 dBTP que "
            "recomiendan las plataformas. Ojo a qué significa esto y qué no: habla del "
            "techo del archivo, no de lo que pase dentro de la señal. Un track puede "
            "haber pasado por un clipper o un limitador agresivo antes del bounce y "
            "seguir teniendo el techo perfectamente puesto."
        ),
    })
    return salida


def _analizar_loudness(audio_path: str, y_preloaded=None, sr_preloaded=None,
                       y_stereo_preloaded=None, formato=None, onsets_seg=None) -> dict:
    """
    Mide loudness según ITU-R BS.1770 (LUFS).
    Usa audio precargado si está disponible para evitar re-lectura de disco.
    Retorna: LUFS integrado, short-term max, rango, y nivel relativo.

    Sobre el true peak — qué parte de la norma se implementa realmente:
    referencia objetivo ITU-R BS.1770-5 (2023), Anexo 2 "Sampling-rate
    conversion for the measurement of true-peak level". De ahí se implementa
    el sobremuestreo y la toma del máximo absoluto sobre la señal
    reconstruida, canal a canal, quedándose con el mayor de los canales.
    NO se implementan: el filtro FIR polifásico concreto que especifica la
    norma (aquí se usa el resampler genérico soxr_hq), la atenuación previa
    de 12,04 dB (innecesaria trabajando en coma flotante) ni el filtro
    paso-bajo posterior. Es una aproximación al método, no el método literal;
    por eso `true_peak_validated` arranca en False y solo puede pasar a True
    tras superar backend/tests/validar_true_peak.py.

    Dos desviaciones deliberadas respecto a la letra de la norma, las dos
    medidas contra la reconstrucción exacta en tests/test_reconstruccion.py:

    * Se sobremuestrea **8x, no 4x**. El 4x de la norma deja un error de
      rejilla de hasta 0,11 dB con material realista, porque el máximo cae
      entre los puntos calculados. A 8x baja a 0,004 dB.
    * No se usa el FIR de 12 taps del anexo 2. Se probó: tiene rizado de
      +0,12 dB en la banda de paso y cae 0,79 dB cerca de Nyquist, lo que lo
      convierte en el peor de los candidatos evaluados. soxr_hq es plano
      hasta el 90% de Nyquist.
    """
    resultado = {
        "lufs_integrado": -99.0,
        "lufs_short_term_max": -99.0,
        "rango_loudness": 0.0,
        # --- Picos ---
        # Ambos se guardan SIN redondear: el redondeo pertenece a la
        # presentación y a la compatibilidad de clasificación de la fase 1.
        "true_peak_dbtp": -99.0,      # pico reconstruido, dBTP
        "sample_peak_dbfs": -99.0,    # máximo absoluto de las muestras, dBFS
        # --- Estado del método de medición (no del archivo) ---
        "sample_peak_source": "no_disponible",   # archivo_nativo | audio_remuestreado_22k | no_disponible
        "true_peak_method": "no_disponible",     # soxr_hq_8x | sample_peak_22k_fallback | no_disponible
        "true_peak_oversampling": 0,             # 8 | 1 | 0  (4 en análisis <= v0.5.71)
        "true_peak_ground_truth_validation_passed": TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED,
        "true_peak_internal_validation_passed": TRUE_PEAK_INTERNAL_VALIDATION_PASSED,
        # Informativo desde v0.5.73: documenta la distancia a un medidor
        # comercial, no decide. Ver la nota del principio del módulo.
        "true_peak_external_validation_passed": TRUE_PEAK_EXTERNAL_VALIDATION_PASSED,
        "true_peak_validated": _TRUE_PEAK_VALIDATED,
        "peak_measurement_sample_rate": 0,       # sr al que se midieron los picos
        "peak_measurement_channels": 0,          # nº de canales medidos
        # --- Clasificación y textos (sin cambios en fase 1) ---
        "nivel": "",                  # "bajo", "moderado", "alto", "muy_alto"
        "referencia": "",             # texto con contexto
        "consejo_master": "",         # texto accionable según nivel
        "saturacion_dinamica": "",    # "ok"|"moderada"|"elevada"|"extrema"
        "aviso_saturacion": "",       # texto solo cuando saturación elevada/extrema
        "nivel_true_peak": "",        # "ok"|"streaming"|"clipping" según severidad
        "aviso_true_peak": "",        # texto accionable cuando excede umbrales
        # --- Fase 2B: muestras a fondo de escala -------------------------
        # Se rellenan en el bloque de picos; si el archivo no se pudo releer
        # a rate nativo se quedan así y `recorte_medible` marca el porqué.
        **_medir_muestras_en_techo(None, 0, formato),
    }

    try:
        # Usar audio precargado si disponible, si no cargar desde disco
        if y_preloaded is not None and sr_preloaded is not None:
            rate = sr_preloaded
            if y_stereo_preloaded is not None:
                # Stereo: transponer de (2, N) a (N, 2) para pyloudnorm
                data = y_stereo_preloaded.T
            else:
                # Mono: se mide como UN canal. Duplicarlo a dos (que es lo que
                # se hacía hasta v0.5.70) hace que la suma de canales de
                # BS.1770 cuente la energía dos veces y devuelva 10·log10(2) =
                # +3,01 LU de más frente a cualquier medidor de referencia.
                # Los análisis mono anteriores a v0.5.71 llevan ese sesgo.
                data = y_preloaded
        else:
            # Mismo criterio que arriba: un archivo mono se mide como un canal.
            data, rate = sf.read(audio_path)

        meter = pyln.Meter(rate)
        resultado["peak_measurement_sample_rate"] = int(rate)
        resultado["peak_measurement_channels"] = 1 if data.ndim == 1 else int(data.shape[1])

        # LUFS integrado (todo el track)
        # pyloudnorm devuelve -inf con silencio absoluto. `_comprobar_senal_
        # analizable` ya debería haber cortado antes, pero esta red evita que
        # un -inf llegue jamás a la respuesta: Starlette serializa con
        # allow_nan=False y devolvería un 500 en vez de un error legible.
        lufs_i = float(meter.integrated_loudness(data))
        resultado["lufs_integrado"] = round(lufs_i, 1) if np.isfinite(lufs_i) else -99.0

        # True Peak (dBTP) — ITU-R BS.1770 exige medirlo sobre el archivo a su
        # sample rate nativo, con sobremuestreo. Reusar el audio ya
        # resampleado a 22050 introduce overshoot del filtro de antialiasing
        # y falsea el valor (lo eleva 2-3 dB típicos).
        # Por eso releemos el archivo aquí desde disco, fuera del flujo
        # general que sí puede trabajar a 22050.
        try:
            native, native_sr = sf.read(audio_path, always_2d=True, dtype="float32")
            # Sample peak primero (referencia exacta sobre samples del archivo)
            sample_peak_lin = float(np.max(np.abs(native)))
            sample_peak_db = 20.0 * float(np.log10(sample_peak_lin)) if sample_peak_lin > 1e-9 else -99.0

            # Sobremuestreo 8x con filtro polifásico de alta calidad, canal a
            # canal y a sample rate nativo.
            #
            # Por qué 8x y no el 4x de la norma: sobremuestrear da PUNTOS, y el
            # máximo real cae entre ellos. Con 4x el error de rejilla llega a
            # 0,11 dB en material realista; con 8x baja a 0,004 dB. Por encima
            # de 8x ya no aporta nada, y cuesta el doble. Medido en
            # tests/test_reconstruccion.py contra la reconstrucción exacta.
            #
            # Lo que 8x NO arregla: soxr_hq borra el contenido por encima del
            # 90% de Nyquist, así que en masters muy saturados se queda ~0,39 dB
            # corto. Eso es error del FILTRO, no de la rejilla, y no lo cambia
            # ningún factor de sobremuestreo.
            tp_per_channel = []
            for ch in range(native.shape[1]):
                up = librosa.resample(
                    native[:, ch],
                    orig_sr=native_sr, target_sr=native_sr * OVERSAMPLING_PICOS,
                    res_type="soxr_hq",
                )
                tp_per_channel.append(float(np.max(np.abs(up))))
            tp_lin = max(tp_per_channel) if tp_per_channel else 0.0
            tp_db = 20.0 * float(np.log10(tp_lin)) if tp_lin > 1e-9 else -99.0

            # Sanity: el true peak nunca puede ser MENOR que el sample peak.
            # Si por artefacto el oversampleado da menos, nos quedamos con el
            # sample peak (cota inferior segura). OJO: esto hace que el test
            # `true_peak >= sample_peak` sea un invariante forzado por el
            # código, no una validación del algoritmo.
            resultado["true_peak_dbtp"] = float(max(tp_db, sample_peak_db))
            resultado["sample_peak_dbfs"] = float(sample_peak_db)
            resultado["sample_peak_source"] = "archivo_nativo"
            resultado["true_peak_method"] = f"soxr_hq_{OVERSAMPLING_PICOS}x"
            resultado["true_peak_oversampling"] = OVERSAMPLING_PICOS
            resultado["peak_measurement_sample_rate"] = int(native_sr)
            resultado["peak_measurement_channels"] = int(native.shape[1])

            # Fase 2B: contar muestras a fondo de escala. Se hace aquí porque
            # es donde ya está leído el array nativo — reutilizarlo cuesta
            # ~10-30 ms en una pista de 6 min, frente a releer el archivo.
            resultado.update(_medir_muestras_en_techo(
                native, native_sr, formato, onsets_seg=onsets_seg))
        except Exception:
            # Fallback: el archivo no se pudo releer a sample rate nativo.
            # Lo único que queda es el audio ya remuestreado a 22 kHz, que NO
            # es ni el true peak ni el sample peak del archivo: el filtro del
            # remuestreo introduce overshoot. Se publica como cota aproximada
            # y se marca el origen para que nadie lo confunda con una medida
            # buena. El sample peak se deja sin valor antes que dar uno falso.
            peak_lin = float(np.max(np.abs(data)))
            if peak_lin > 1e-9:
                resultado["true_peak_dbtp"] = 20.0 * float(np.log10(peak_lin))
            resultado["sample_peak_dbfs"] = -99.0
            resultado["sample_peak_source"] = "no_disponible"
            resultado["true_peak_method"] = "sample_peak_22k_fallback"
            resultado["true_peak_oversampling"] = 1

        # Aviso de true peak según severidad. Umbrales basados en estándares
        # de industria, no en datos de Mentotrack (no necesitan calibrado).
        # - > 0 dBTP: clipping digital real, peor caso. Distorsión audible en
        #   cualquier reproducción que use bit depth fijo.
        # - > -1 dBTP: por encima del ceiling recomendado para streaming. Los
        #   codecs lossy (AAC, MP3, Opus) generan inter-sample peaks adicionales
        #   al comprimir y pueden saturar el reproductor del oyente.
        # - <= -1 dBTP: zona segura para streaming.
        #
        # ===================== DEUDA DE FASE 1 =====================
        # COMPATIBILIDAD TEMPORAL: hasta v0.5.70 el true peak se guardaba ya
        # redondeado a 1 decimal y la clasificación se decidía sobre ese valor
        # redondeado. Desde v0.5.71 el valor se conserva con precisión
        # completa, pero la clasificación SIGUE tomándose sobre el redondeado
        # para que ningún análisis cambie de categoría en esta fase (un track
        # a +0,04 dBTP pasaría de "streaming" a "clipping" solo por dejar de
        # redondear, y eso es un cambio de clasificación).
        # PENDIENTE FASE 2: decidir el umbral sobre `true_peak_dbtp` sin
        # redondear, junto con la nueva taxonomía de picos. Al hacerlo hay que
        # regenerar backend/tests/golden_loudness.json de forma consciente.
        # ===========================================================
        tp_val = round(resultado["true_peak_dbtp"], 1)
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


def _analizar_distribucion(bloques_rms: list, desarrollo_ok: bool = False) -> dict:
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

    # inicio_abrupto / sin_outro: DESACTIVADOS (2026-06-15, insight de Alex).
    # La energía RMS no distingue un intro/outro de groove (percusión+bajo, que
    # ya está por encima de la media del track) de "empezar/terminar en el drop".
    # Un track bien estructurado que construye por adición (perc+bajo → +hook →
    # +vocal) tiene energía alta desde el inicio y el motor lo leía como "sin
    # intro/outro para pinchar" → falso positivo sistemático en tracks acabados.
    # Se quedan en False: la "idea incompleta" de verdad se detecta por duración
    # corta + pocos bloques + falta de desarrollo, no por esta heurística.
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
                # GATE (2026-06-15, insight de Alex): si el track YA tiene
                # desarrollo + contraste claros (los mismos que dan el descuento
                # en problema_arreglo), no lo marcamos: un track acabado con
                # arreglo desarrollado puede tener un break "plano" en RMS sin que
                # sea un defecto, y la energía media por bloque no basta para
                # afirmar que "no paga". Reservamos el aviso para bocetos sin
                # desarrollo (drop + parón y poco más), que es el caso de insight 4.
                if ratio < 1.05 and not desarrollo_ok:
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
