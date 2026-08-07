"""Generador determinista de ficheros de audio de prueba.

Todos los fixtures se construyen con semilla fija: dos ejecuciones producen
bytes idénticos. Eso permite congelar un golden y compararlo más tarde.

Cada fixture declara, cuando se puede, su TRUE PEAK ANALÍTICO — el valor que
sale de la teoría, no de ninguna implementación. Es el único juez válido
cuando Mentotrack y un medidor externo discrepan.

Caso analítico de referencia (`isp_fs4`): una sinusoide a fs/4 muestreada con
desfase de 45° cae siempre en ±A/√2. El sample peak es A/√2 y el pico real de
la onda continua es A, así que el true peak está exactamente 20·log10(√2) =
+3,0103 dB por encima del sample peak, con independencia de quién lo mida.
"""

import os
import subprocess

import numpy as np
import soundfile as sf

SR_DEFAULT = 44100
DUR_DEFAULT = 3.0
SEED = 20260806

# Diferencia teórica true peak − sample peak para el seno a fs/4 desfasado 45°
ISP_FS4_DELTA_DB = 20.0 * np.log10(np.sqrt(2.0))  # +3.0103 dB


def _db_a_lin(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def _seno(freq: float, sr: int, dur: float, fase: float = 0.0) -> np.ndarray:
    t = np.arange(int(sr * dur), dtype=np.float64) / sr
    return np.sin(2.0 * np.pi * freq * t + fase)


def _ruido_rosa(sr: int, dur: float, rng: np.random.Generator) -> np.ndarray:
    """Ruido rosa por filtrado de Voss-McCartney simplificado (FFT 1/f)."""
    n = int(sr * dur)
    blanco = rng.standard_normal(n)
    espectro = np.fft.rfft(blanco)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    espectro /= np.sqrt(freqs)
    rosa = np.fft.irfft(espectro, n)
    return rosa / (np.max(np.abs(rosa)) + 1e-12)


def _musical(sr: int, dur: float, rng: np.random.Generator) -> np.ndarray:
    """Señal pseudo-musical: kick 4x4 + bajo + hats + ruido rosa de fondo.

    No pretende sonar bien; pretende tener transitorios, contenido de banda
    ancha y una envolvente variable, que es lo que hace no trivial la medida
    de true peak y de loudness.
    """
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    x = np.zeros(n)
    # Kick 4x4 a 128 BPM
    periodo = 60.0 / 128.0
    for golpe in np.arange(0.0, dur, periodo):
        i0 = int(golpe * sr)
        largo = int(0.18 * sr)
        if i0 + largo > n:
            break
        env = np.exp(-np.linspace(0, 9, largo))
        barrido = np.linspace(110.0, 45.0, largo)
        fase = 2.0 * np.pi * np.cumsum(barrido) / sr
        x[i0:i0 + largo] += 0.9 * env * np.sin(fase)
    # Bajo continuo
    x += 0.25 * _seno(55.0, sr, dur)
    # Hats en corcheas
    for golpe in np.arange(periodo / 2.0, dur, periodo):
        i0 = int(golpe * sr)
        largo = int(0.04 * sr)
        if i0 + largo > n:
            break
        env = np.exp(-np.linspace(0, 14, largo))
        x[i0:i0 + largo] += 0.35 * env * rng.standard_normal(largo)
    # Fondo
    x += 0.06 * _ruido_rosa(sr, dur, rng)
    # Envolvente por secciones para que el LRA no sea plano
    seccion = 1.0 + 0.35 * np.sin(2.0 * np.pi * t / max(dur, 1e-9))
    x *= seccion
    return x / (np.max(np.abs(x)) + 1e-12)


def _a_estereo(x: np.ndarray) -> np.ndarray:
    return np.column_stack([x, x])


def _escalar_a_sample_peak(x: np.ndarray, db: float) -> np.ndarray:
    pico = float(np.max(np.abs(x)))
    if pico <= 0:
        return x
    return x * (_db_a_lin(db) / pico)


# ---------------------------------------------------------------------------
# Catálogo de fixtures
# ---------------------------------------------------------------------------
# Cada entrada: nombre -> dict con
#   build(rng)  -> (data, sr, subtype, formato)
#   tp_analitico -> float | None   (dBTP teórico, si se conoce)
#   sp_esperado  -> float | None   (dBFS teórico del sample peak)
#   notas        -> str

def _catalogo():
    cat = {}

    def reg(nombre, fn, tp_analitico=None, sp_esperado=None, notas="", **kw):
        cat[nombre] = dict(build=fn, tp_analitico=tp_analitico,
                           sp_esperado=sp_esperado, notas=notas, **kw)

    # --- 1. Punto fijo, pico holgado -------------------------------------
    reg("wav24_pico_menos1",
        lambda rng: (_a_estereo(_escalar_a_sample_peak(
            _musical(SR_DEFAULT, DUR_DEFAULT, rng), -1.0)), SR_DEFAULT, "PCM_24", "WAV"),
        sp_esperado=-1.0,
        notas="WAV 24-bit con sample peak a -1 dBFS. Caso sano.")

    # --- 2. Muestras exactamente a fondo de escala ------------------------
    def _fs_exacto(rng):
        x = _escalar_a_sample_peak(_musical(SR_DEFAULT, DUR_DEFAULT, rng), 0.0)
        return _a_estereo(x), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_muestras_0dbfs", _fs_exacto, sp_esperado=0.0,
        notas="Normalizado exacto a 0 dBFS: toca el techo sin recortar la onda.")

    # --- 3. Clipping evidente --------------------------------------------
    def _clip_duro(rng):
        x = _musical(SR_DEFAULT, DUR_DEFAULT, rng) * 3.0
        return _a_estereo(np.clip(x, -1.0, 1.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_clipping_evidente", _clip_duro, sp_esperado=0.0,
        notas="x3 y recorte duro: flat tops largos en los dos canales.")

    # --- 4. Clipping de una sola muestra ----------------------------------
    def _clip_1(rng):
        x = _escalar_a_sample_peak(_musical(SR_DEFAULT, DUR_DEFAULT, rng), -3.0)
        x[len(x) // 2] = 1.0
        return _a_estereo(x), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_clip_una_muestra", _clip_1, sp_esperado=0.0,
        notas="Una única muestra en el techo sobre material holgado.")

    # --- 5. Clipping sostenido (2 s) --------------------------------------
    def _clip_sostenido(rng):
        x = _escalar_a_sample_peak(_musical(SR_DEFAULT, 5.0, rng), -3.0)
        i0 = int(1.0 * SR_DEFAULT)
        i1 = i0 + int(2.0 * SR_DEFAULT)
        bloque = _seno(220.0, SR_DEFAULT, 2.0) * 2.5
        x[i0:i1] = np.clip(bloque[:i1 - i0], -1.0, 1.0)
        return _a_estereo(x), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_clip_sostenido", _clip_sostenido, sp_esperado=0.0,
        notas="Bloque de 2 s completamente saturado.")

    # --- 6. Inter-sample peak SIN sample clipping (caso analítico) --------
    def _isp(rng):
        # Seno a fs/4 con desfase 45°: muestras en ±A/raiz(2)
        x = _seno(SR_DEFAULT / 4.0, SR_DEFAULT, DUR_DEFAULT, fase=np.pi / 4.0)
        x = _escalar_a_sample_peak(x, -0.2)   # sample peak -0.2 dBFS
        return _a_estereo(x), SR_DEFAULT, "PCM_24", "WAV"
    reg("isp_fs4_sobre_0", _isp,
        tp_analitico=-0.2 + ISP_FS4_DELTA_DB,   # ≈ +2.81 dBTP
        sp_esperado=-0.2,
        patologico=True,
        notas="Seno a fs/4 desfasado 45°. TP teórico = SP + 3.0103 dB. "
              "Ninguna muestra toca el techo.")

    # --- 7. True peak entre -1 y 0 ----------------------------------------
    reg("wav24_tp_entre_m1_y_0",
        lambda rng: (_a_estereo(_escalar_a_sample_peak(
            _musical(SR_DEFAULT, DUR_DEFAULT, rng), -0.6)), SR_DEFAULT, "PCM_24", "WAV"),
        sp_esperado=-0.6,
        notas="Zona de recomendación de streaming.")

    # --- 8. 32-bit float por encima de 0 dBFS -----------------------------
    def _float_over(rng):
        x = _escalar_a_sample_peak(_musical(SR_DEFAULT, DUR_DEFAULT, rng), 0.0)
        return _a_estereo(x * _db_a_lin(3.0)), SR_DEFAULT, "FLOAT", "WAV"
    reg("wav32f_sobre_0", _float_over, sp_esperado=3.0,
        notas="WAV 32-bit float con picos a +3 dBFS: overs recuperables.")

    # --- 9. 64-bit double -------------------------------------------------
    reg("wav64d_pico_menos1",
        lambda rng: (_a_estereo(_escalar_a_sample_peak(
            _musical(SR_DEFAULT, DUR_DEFAULT, rng), -1.0)), SR_DEFAULT, "DOUBLE", "WAV"),
        sp_esperado=-1.0,
        notas="WAV 64-bit double.")

    # --- 10. FLAC ---------------------------------------------------------
    reg("flac24_pico_menos1",
        lambda rng: (_a_estereo(_escalar_a_sample_peak(
            _musical(SR_DEFAULT, DUR_DEFAULT, rng), -1.0)), SR_DEFAULT, "PCM_24", "FLAC"),
        sp_esperado=-1.0,
        notas="FLAC 24-bit, lossless en contenedor distinto.")

    # --- 11. PCM_16 -------------------------------------------------------
    reg("wav16_pico_menos1",
        lambda rng: (_a_estereo(_escalar_a_sample_peak(
            _musical(SR_DEFAULT, DUR_DEFAULT, rng), -1.0)), SR_DEFAULT, "PCM_16", "WAV"),
        sp_esperado=-1.0,
        notas="WAV 16-bit.")

    # --- 12. Mono ---------------------------------------------------------
    reg("wav24_mono",
        lambda rng: (_escalar_a_sample_peak(
            _musical(SR_DEFAULT, DUR_DEFAULT, rng), -1.0), SR_DEFAULT, "PCM_24", "WAV"),
        sp_esperado=-1.0, mono=True,
        notas="Mono real de un canal. Objetivo del test de LUFS.")

    # --- 13. Clipping solo en el canal izquierdo --------------------------
    def _clip_solo_L(rng):
        x = _escalar_a_sample_peak(_musical(SR_DEFAULT, DUR_DEFAULT, rng), -6.0)
        izq = np.clip(x * 4.0, -1.0, 1.0)
        return np.column_stack([izq, x]), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_clip_solo_L", _clip_solo_L, sp_esperado=0.0,
        notas="Recorte severo en L, derecho intacto a -6 dBFS.")

    # --- 14. Continua: tres variantes para separar señal de artefacto ------
    # El true peak de una continua es su sample peak: no hay nada entre
    # muestras. Pero un archivo finito tiene bordes, y lo que un interpolador
    # haga ahí depende de qué asuma fuera del archivo. Por eso la prueba se
    # parte en tres en lugar de exigir -6 dBTP en todos los casos.

    # (A) Régimen estable: continua en todo el archivo. El objetivo de
    #     -6 dBTP solo es exigible en la región central, tras el asentamiento.
    def _dc_estable(rng):
        n = int(SR_DEFAULT * 4.0)
        return _a_estereo(np.full(n, _db_a_lin(-6.0))), SR_DEFAULT, "PCM_24", "WAV"
    reg("dc_estable_menos6", _dc_estable,
        tp_analitico=None, tp_regimen_estable=-6.0, sp_esperado=-6.0,
        regimen="estable",
        notas="Continua a -6 dBFS durante 4 s. El objetivo de -6 dBTP aplica a "
              "la región central, no al máximo global.")

    # (B1) Salto DENTRO del archivo: silencio → continua → silencio. La
    #      discontinuidad es real y todos los métodos ven la misma señal, sin
    #      depender de qué se asuma fuera del archivo.
    def _dc_salto_interno(rng):
        n_sil = int(SR_DEFAULT * 0.5)
        n_dc = int(SR_DEFAULT * 3.0)
        x = np.concatenate([np.zeros(n_sil), np.full(n_dc, _db_a_lin(-6.0)),
                            np.zeros(n_sil)])
        return _a_estereo(x), SR_DEFAULT, "PCM_24", "WAV"
    reg("dc_salto_interno_menos6", _dc_salto_interno,
        tp_analitico=None, tp_regimen_estable=-6.0, sp_esperado=-6.0,
        regimen="borde_abrupto",
        notas="Silencio → continua -6 dBFS → silencio. El escalón está dentro "
              "del archivo: no hay ambigüedad sobre qué pasa fuera, así que la "
              "sobreoscilación es la respuesta real del filtro al escalón.")

    # (B2) Salto en el BORDE del archivo: empieza y acaba de golpe a nivel
    #      pleno. Aquí el resultado sí depende de la extensión que asuma cada
    #      implementación, así que NO se le pone objetivo analítico.
    def _dc_bordes(rng):
        n = int(SR_DEFAULT * DUR_DEFAULT)
        return _a_estereo(np.full(n, _db_a_lin(-6.0))), SR_DEFAULT, "PCM_24", "WAV"
    reg("dc_bordes_menos6", _dc_bordes,
        tp_analitico=None, tp_regimen_estable=-6.0, sp_esperado=-6.0,
        regimen="borde_archivo",
        notas="Continua que arranca y termina abruptamente en el borde del "
              "archivo. Sin objetivo analítico: el valor depende de qué asuma "
              "cada interpolador fuera del archivo.")

    # --- 15. Limitado agresivo sin llegar al techo ------------------------
    def _limitado(rng):
        x = _musical(SR_DEFAULT, DUR_DEFAULT, rng)
        x = np.tanh(x * 4.0) / np.tanh(4.0)
        return _a_estereo(_escalar_a_sample_peak(x, -1.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_limitado_sin_clip", _limitado, sp_esperado=-1.0,
        notas="Saturación blanda con ceiling a -1: dinámica aplastada, sin recorte.")

    # --- 15b. Banda limitada a 15 kHz -------------------------------------
    # `_musical` mete ráfagas de ruido blanco (los hats) con energía hasta
    # Nyquist. Eso NO se parece a música real, y cerca de Nyquist cada
    # interpolador se comporta distinto: soxr lee de más, el FIR de la ITU lee
    # de menos. Este fixture recorta a 15 kHz para tener el caso realista, en
    # el que todos los métodos deben coincidir.
    def _banda_limitada(rng):
        from scipy.signal import butter, sosfiltfilt
        x = _musical(SR_DEFAULT, DUR_DEFAULT, rng)
        sos = butter(8, 15000, "lp", fs=SR_DEFAULT, output="sos")
        x = sosfiltfilt(sos, x)
        return (_a_estereo(_escalar_a_sample_peak(x, -1.0)),
                SR_DEFAULT, "PCM_24", "WAV")
    reg("wav24_bandlimitada_15k", _banda_limitada, sp_esperado=-1.0,
        banda_limitada=True,
        notas="Material con el espectro recortado a 15 kHz, como la música "
              "real. Sin energía pegada a Nyquist, todos los métodos de "
              "medida de true peak convergen.")

    # --- 16. Crest factor bajo (onda cuadrada) ----------------------------
    def _cuadrada(rng):
        x = np.sign(_seno(110.0, SR_DEFAULT, DUR_DEFAULT))
        return _a_estereo(_escalar_a_sample_peak(x, -3.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_crest_bajo", _cuadrada, sp_esperado=-3.0,
        notas="Onda cuadrada: crest factor mínimo sin clipping.")

    # --- 17-19. Otros sample rates ----------------------------------------
    for sr in (48000, 96000):
        reg(f"wav24_{sr}_pico_menos1",
            (lambda s: (lambda rng: (_a_estereo(_escalar_a_sample_peak(
                _musical(s, DUR_DEFAULT, rng), -1.0)), s, "PCM_24", "WAV")))(sr),
            sp_esperado=-1.0,
            notas=f"WAV 24-bit a {sr} Hz.")
        reg(f"isp_fs4_{sr}",
            (lambda s: (lambda rng: (_a_estereo(_escalar_a_sample_peak(
                _seno(s / 4.0, s, DUR_DEFAULT, fase=np.pi / 4.0), -0.2)),
                s, "PCM_24", "WAV")))(sr),
            tp_analitico=-0.2 + ISP_FS4_DELTA_DB, sp_esperado=-0.2,
            patologico=True,
            notas=f"Caso analítico de inter-sample peak a {sr} Hz.")

    # --- 19b. Material sin pulso detectable --------------------------------
    # `beat_track` devuelve 0 BPM con estas señales. Antes eso era una división
    # entre cero → HTTP 500. Ahora se publica bpm = None y el análisis sigue
    # con una ventana de bloque en segundos.
    def _drone(rng):
        n = int(SR_DEFAULT * 12.0)
        t = np.arange(n) / SR_DEFAULT
        # Tres parciales con batido lento y un barrido de filtro simulado
        x = (np.sin(2 * np.pi * 55 * t) + 0.6 * np.sin(2 * np.pi * 82.5 * t)
             + 0.4 * np.sin(2 * np.pi * 110.3 * t))
        x *= 1.0 + 0.15 * np.sin(2 * np.pi * 0.05 * t)
        return _a_estereo(_escalar_a_sample_peak(x, -3.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("sin_pulso_drone", _drone, sp_esperado=-3.0, sin_pulso=True,
        notas="Drone de parciales graves con batido lento. Sin transitorios: "
              "no hay pulso que detectar.")

    def _seno_sostenido(rng):
        x = _seno(1000.0, SR_DEFAULT, 12.0)
        return _a_estereo(_escalar_a_sample_peak(x, -6.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("sin_pulso_seno", _seno_sostenido, sp_esperado=-6.0, sin_pulso=True,
        notas="Seno de 1 kHz sostenido. El caso que destapó el ZeroDivisionError.")

    def _pad(rng):
        n = int(SR_DEFAULT * 14.0)
        t = np.arange(n) / SR_DEFAULT
        x = np.zeros(n)
        for f in (220.0, 261.6, 329.6, 392.0):        # acorde de La menor 7
            x += np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
        # Envolvente muy lenta: ataque de 4 s, sin ningún transitorio
        env = np.clip(t / 4.0, 0, 1) * np.clip((14.0 - t) / 4.0, 0, 1)
        x *= env
        x += 0.02 * _ruido_rosa(SR_DEFAULT, 14.0, rng)
        return _a_estereo(_escalar_a_sample_peak(x, -4.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("sin_pulso_pad", _pad, sp_esperado=-4.0, sin_pulso=True,
        notas="Pad de acorde con ataque de 4 s. Sin percusión ni transitorios.")

    def _ambiguo(rng):
        """Golpes espaciados de forma irregular: puede detectarse pulso o no.
        No se afirma cuál de las dos cosas; el test solo exige coherencia."""
        n = int(SR_DEFAULT * 14.0)
        x = 0.05 * _ruido_rosa(SR_DEFAULT, 14.0, rng)
        posicion = 0.4
        while posicion < 13.0:
            i0 = int(posicion * SR_DEFAULT)
            largo = int(0.12 * SR_DEFAULT)
            env = np.exp(-np.linspace(0, 8, largo))
            x[i0:i0 + largo] += 0.8 * env * np.sin(
                2 * np.pi * np.cumsum(np.linspace(140, 60, largo)) / SR_DEFAULT)
            posicion += 0.55 + 0.5 * ((posicion * 7919) % 1.0)   # irregular, determinista
        return _a_estereo(_escalar_a_sample_peak(x, -3.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("pulso_ambiguo", _ambiguo, sp_esperado=-3.0, ambiguo=True,
        notas="Golpes irregulares. Puede salir con o sin pulso: lo que se exige "
              "es que no se invente un BPM y que no reviente.")

    def _con_pulso(rng):
        x = _musical(SR_DEFAULT, 14.0, rng)
        return _a_estereo(_escalar_a_sample_peak(x, -1.0)), SR_DEFAULT, "PCM_24", "WAV"
    reg("pulso_claro_128", _con_pulso, sp_esperado=-1.0, con_pulso=True,
        notas="Kick 4x4 a 128 BPM. Control: aquí sí tiene que detectar tempo.")

    # --- 20. Silencio ------------------------------------------------------
    def _silencio(rng):
        n = int(SR_DEFAULT * DUR_DEFAULT)
        return _a_estereo(np.zeros(n)), SR_DEFAULT, "PCM_24", "WAV"
    reg("wav24_silencio", _silencio,
        notas="Silencio absoluto: comprueba que nada explota ni divide por cero.")

    return cat


CATALOGO = _catalogo()

# Fixtures que se generan con ffmpeg a partir de otro (lossy)
LOSSY = {
    "mp3_320": {"origen": "wav24_pico_menos1", "args": ["-codec:a", "libmp3lame", "-b:a", "320k"],
                "ext": ".mp3", "notas": "MP3 320 kbps derivado del WAV sano."},
}


def generar(destino: str, solo: list | None = None) -> dict:
    """Escribe los fixtures en `destino` y devuelve el manifiesto.

    Determinista: misma semilla → mismos bytes.
    """
    os.makedirs(destino, exist_ok=True)
    manifiesto = {}
    for nombre, spec in CATALOGO.items():
        if solo and nombre not in solo:
            continue
        rng = np.random.default_rng(SEED)
        data, sr, subtype, formato = spec["build"](rng)
        ext = ".flac" if formato == "FLAC" else ".wav"
        ruta = os.path.join(destino, nombre + ext)
        sf.write(ruta, data, sr, subtype=subtype, format=formato)
        manifiesto[nombre] = {
            "ruta": ruta,
            "sr": sr,
            "subtype": subtype,
            "formato": formato,
            "canales": 1 if data.ndim == 1 else data.shape[1],
            "tp_analitico": spec.get("tp_analitico"),
            "tp_regimen_estable": spec.get("tp_regimen_estable"),
            "regimen": spec.get("regimen", ""),
            "sp_esperado": spec.get("sp_esperado"),
            "patologico": bool(spec.get("patologico", False)),
            "sin_pulso": bool(spec.get("sin_pulso", False)),
            "con_pulso": bool(spec.get("con_pulso", False)),
            "ambiguo": bool(spec.get("ambiguo", False)),
            "mono": bool(spec.get("mono", False)),
            "notas": spec.get("notas", ""),
        }

    for nombre, spec in LOSSY.items():
        if solo and nombre not in solo:
            continue
        origen = manifiesto.get(spec["origen"])
        if not origen:
            continue
        ruta = os.path.join(destino, nombre + spec["ext"])
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", origen["ruta"]] + spec["args"] + [ruta]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        manifiesto[nombre] = {
            "ruta": ruta, "sr": origen["sr"], "subtype": "MPEG_LAYER_III",
            "formato": "MP3", "canales": 2, "tp_analitico": None,
            "sp_esperado": None, "patologico": False, "mono": False,
            "lossy": True, "notas": spec["notas"],
        }
    return manifiesto


if __name__ == "__main__":
    import json
    import sys
    destino = sys.argv[1] if len(sys.argv) > 1 else "/tmp/mentotrack_fixtures"
    m = generar(destino)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "ruta"}
                      for k, v in m.items()}, indent=2, ensure_ascii=False))
    print(f"\n{len(m)} fixtures en {destino}", file=sys.stderr)
