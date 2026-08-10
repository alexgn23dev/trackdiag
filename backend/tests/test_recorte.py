"""Fase 2B — contar muestras a fondo de escala.

El true peak dice si la ONDA RECONSTRUIDA asoma por encima del techo, y eso
muchas veces no es un problema: el pico vive entre muestras. Lo que sí es daño
es que a la onda le hayan cortado la punta en plano, y eso solo se ve
contando muestras.

Estos tests protegen tres cosas, por orden de importancia:

  1. Que las mediciones objetivas sean correctas — se comprueban contra
     fixtures cuyo recorte se construye a propósito, así que el número
     esperado se conoce.
  2. Que NO se acuse a nadie sin base: ni en coma flotante (no hay techo), ni
     en archivos con pérdida (las muestras son del decodificador), ni cuando
     el patrón es el de un clipper haciendo su trabajo.
  3. Que el texto ENSEÑE. Decisión de producto de Alex: "la idea siempre es
     formarle también". Un aviso que solo etiqueta está incompleto.
"""

import os
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import (  # noqa: E402
    _clasificar_recorte, _lsb_del_formato, _medir_muestras_en_techo, _rachas,
    extraer_senales,
)
from tests import fixtures as fx  # noqa: E402

SR = 44100
_DIR = tempfile.mkdtemp(prefix="mentotrack_recorte_")
_CASOS = ["wav24_pico_menos1", "wav24_muestras_0dbfs", "wav24_clipping_evidente",
          "wav24_clip_una_muestra", "wav24_clip_sostenido", "wav24_clip_solo_L",
          "wav32f_sobre_0", "wav16_pico_menos1", "mp3_320"]
_MANIFIESTO = None
_CACHE = {}

FMT_24 = {"archivo_sample_format": "int", "archivo_pcm_bit_depth": 24,
          "archivo_lossy": False}


def setUpModule():
    global _MANIFIESTO
    _MANIFIESTO = fx.generar(_DIR, solo=_CASOS)


def medir(nombre):
    if nombre not in _CACHE:
        _CACHE[nombre] = extraer_senales(_MANIFIESTO[nombre]["ruta"],
                                         omitir_armonia=True)["loudness"]
    return _CACHE[nombre]


def construir(canal_izq, canal_der=None, subtype="PCM_24", sr=SR):
    """Escribe un WAV con muestras controladas y devuelve su medición."""
    der = canal_izq if canal_der is None else canal_der
    ruta = os.path.join(tempfile.mkdtemp(), "c.wav")
    sf.write(ruta, np.column_stack([canal_izq, der]), sr, subtype=subtype)
    nat, nsr = sf.read(ruta, always_2d=True, dtype="float32")
    bits = {"PCM_16": 16, "PCM_24": 24}.get(subtype)
    fmt = {"archivo_sample_format": "int", "archivo_pcm_bit_depth": bits,
           "archivo_lossy": False}
    return _medir_muestras_en_techo(nat, nsr, fmt)


class TestRachas(unittest.TestCase):
    """La primitiva de la que depende todo lo demás."""

    def test_vacio(self):
        self.assertEqual(len(_rachas(np.zeros(10, dtype=bool))), 0)

    def test_una_racha(self):
        m = np.array([0, 0, 1, 1, 1, 0, 0], dtype=bool)
        self.assertEqual(list(_rachas(m)), [3])

    def test_varias(self):
        m = np.array([1, 1, 0, 1, 0, 0, 1, 1, 1, 1], dtype=bool)
        self.assertEqual(list(_rachas(m)), [2, 1, 4])

    def test_pegadas_a_los_extremos(self):
        """El caso que rompe las implementaciones ingenuas."""
        self.assertEqual(list(_rachas(np.ones(5, dtype=bool))), [5])
        m = np.array([1, 0, 0, 1], dtype=bool)
        self.assertEqual(list(_rachas(m)), [1, 1])


class TestUmbralDelTecho(unittest.TestCase):
    """Decisión 1: el escalón lo fija el bit depth real del archivo."""

    def test_escala_con_el_bit_depth(self):
        self.assertAlmostEqual(_lsb_del_formato(
            {"archivo_sample_format": "int", "archivo_pcm_bit_depth": 16}),
            2.0 ** -15)
        self.assertAlmostEqual(_lsb_del_formato(FMT_24), 2.0 ** -23)

    def test_coma_flotante_no_tiene_techo(self):
        self.assertIsNone(_lsb_del_formato(
            {"archivo_sample_format": "float", "archivo_pcm_bit_depth": None}))

    def test_lossy_gana_a_todo(self):
        """Un MP3 se decodifica a float, pero el motivo que le importa al
        usuario es que subió un MP3, no la representación interna."""
        self.assertIsNone(_lsb_del_formato(
            {"archivo_sample_format": "float", "archivo_lossy": True}))
        r = _medir_muestras_en_techo(None, 0,
                                     {"archivo_sample_format": "float",
                                      "archivo_lossy": True})
        self.assertEqual(r["recorte_no_medible_motivo"], "lossy")

    def test_sin_bit_depth_no_se_inventa(self):
        self.assertIsNone(_lsb_del_formato({"archivo_sample_format": "int"}))


class TestMedicionesObjetivas(unittest.TestCase):
    """Se cuenta sobre señales cuyo recorte se construye a propósito, así que
    el número correcto se conoce de antemano."""

    def test_cuenta_exactamente_las_muestras_que_hay(self):
        x = np.zeros(1000, dtype=np.float64)
        x[100:107] = 1.0          # 7 seguidas
        x[500] = -1.0             # 1 suelta
        r = construir(x)
        # Dos canales idénticos: 8 por canal, 16 en total
        self.assertEqual(r["muestras_en_techo_por_canal"], [8, 8])
        self.assertEqual(r["muestras_en_techo_total"], 16)
        self.assertEqual(r["racha_maxima_muestras"], 7)

    def test_la_racha_en_ms_depende_del_sample_rate(self):
        x = np.zeros(2000, dtype=np.float64)
        x[10:54] = 1.0            # 44 muestras
        a = construir(x, sr=44100)
        b = construir(x, sr=96000)
        self.assertEqual(a["racha_maxima_muestras"], b["racha_maxima_muestras"])
        self.assertAlmostEqual(a["racha_maxima_ms"], 1000 * 44 / 44100, places=3)
        self.assertAlmostEqual(b["racha_maxima_ms"], 1000 * 44 / 96000, places=3)
        self.assertLess(b["racha_maxima_ms"], a["racha_maxima_ms"],
                        "el mismo número de muestras dura menos a 96 kHz")

    def test_el_porcentaje_es_sobre_el_total_de_muestras(self):
        x = np.zeros(1000, dtype=np.float64)
        x[:10] = 1.0
        r = construir(x)
        self.assertAlmostEqual(r["pct_muestras_en_techo"], 1.0, places=4)

    def test_cuenta_mesetas_no_muestras_sueltas(self):
        x = np.zeros(1000, dtype=np.float64)
        x[10:14] = 1.0            # meseta
        x[100:104] = 1.0          # meseta
        x[200] = 1.0              # suelta, no cuenta
        x[300:302] = 1.0          # 2 seguidas, por debajo del mínimo
        self.assertEqual(construir(x)["n_mesetas"], 2 * 2)   # por dos canales

    def test_identifica_el_canal(self):
        limpio = np.zeros(1000, dtype=np.float64)
        sucio = limpio.copy()
        sucio[10:20] = 1.0
        self.assertEqual(construir(sucio, limpio)["canal_afectado"], "L")
        self.assertEqual(construir(limpio, sucio)["canal_afectado"], "R")
        self.assertEqual(construir(sucio, sucio)["canal_afectado"], "ambos")

    def test_localiza_el_maximo(self):
        x = np.zeros(SR, dtype=np.float64)
        x[SR // 2] = 1.0
        r = construir(x)
        self.assertAlmostEqual(r["posicion_maximo_seg"], 0.5, places=3)
        self.assertFalse(r["true_peak_at_file_edge"])

    def test_marca_el_maximo_en_el_borde(self):
        """Se MIDE, no se corrige. En la fase 1.1 quedó comprobado que la
        sobreoscilación de un escalón es real."""
        x = np.zeros(SR, dtype=np.float64)
        x[3] = 1.0
        self.assertTrue(construir(x)["true_peak_at_file_edge"])

    def test_un_archivo_limpio_no_cuenta_nada(self):
        x = np.full(1000, 0.5)
        r = construir(x)
        self.assertEqual(r["muestras_en_techo_total"], 0)
        self.assertEqual(r["racha_maxima_ms"], 0.0)
        self.assertEqual(r["canal_afectado"], "")

    def test_un_16_bits_no_cuenta_lo_mismo_que_un_24(self):
        """El umbral es relativo al formato: un valor a 1 LSB del techo de 24
        bits está muy lejos del techo de 16."""
        x = np.zeros(1000, dtype=np.float64)
        x[10:20] = 1.0 - 2.0 ** -20      # entre el LSB de 24 y el de 16
        self.assertEqual(construir(x, subtype="PCM_24")["muestras_en_techo_total"], 0)
        self.assertGreater(construir(x, subtype="PCM_16")["muestras_en_techo_total"], 0)


class TestConcentracionEnTransitorios(unittest.TestCase):
    def test_recorte_sobre_golpes_da_concentracion_alta(self):
        x = np.zeros(SR * 2, dtype=np.float64)
        golpes = [0.5, 1.0, 1.5]
        for g in golpes:
            i = int(g * SR)
            x[i:i + 5] = 1.0
        nat = np.column_stack([x, x]).astype(np.float32)
        r = _medir_muestras_en_techo(nat, SR, FMT_24, onsets_seg=np.array(golpes))
        self.assertGreaterEqual(r["concentracion_en_transitorios"], 0.99)

    def test_recorte_lejos_de_los_golpes_da_concentracion_baja(self):
        x = np.zeros(SR * 2, dtype=np.float64)
        x[int(1.2 * SR):int(1.2 * SR) + 500] = 1.0
        nat = np.column_stack([x, x]).astype(np.float32)
        r = _medir_muestras_en_techo(nat, SR, FMT_24,
                                     onsets_seg=np.array([0.1, 0.4, 0.7]))
        self.assertLess(r["concentracion_en_transitorios"], 0.05)

    def test_sin_onsets_no_se_inventa_el_dato(self):
        x = np.zeros(1000, dtype=np.float64)
        x[10:20] = 1.0
        nat = np.column_stack([x, x]).astype(np.float32)
        self.assertIsNone(_medir_muestras_en_techo(
            nat, SR, FMT_24, onsets_seg=None)["concentracion_en_transitorios"])


class TestNoAcusarSinBase(unittest.TestCase):
    """El corazón de la fase. Lo que NO se debe decir."""

    def test_coma_flotante_no_se_mide(self):
        lo = medir("wav32f_sobre_0")
        self.assertEqual(lo["categoria_recorte"], "no_aplica_float")
        self.assertFalse(lo["recorte_medible"])
        self.assertEqual(lo["severidad_recorte"], "info")

    def test_lossy_no_se_mide_y_lo_explica_por_lo_que_es(self):
        lo = medir("mp3_320")
        self.assertEqual(lo["categoria_recorte"], "no_aplica_lossy")
        aviso = lo["aviso_recorte"].lower()
        self.assertIn("decodificador", aviso)
        self.assertIn("wav", aviso)
        self.assertNotIn("coma flotante", aviso,
                         "al usuario de un MP3 no le sirve saber la "
                         "representación interna: le sirve saber que suba el WAV")

    def test_un_pico_que_toca_el_techo_no_es_recorte(self):
        """Normalizar a 0 dBFS toca el techo sin aplanar nada. Decir que eso
        es clipping era justo el error que corrigió la fase 2A."""
        lo = medir("wav24_muestras_0dbfs")
        self.assertEqual(lo["categoria_recorte"], "techo_tocado")
        self.assertEqual(lo["severidad_recorte"], "info")
        # El título tiene que NEGAR el recorte, no afirmarlo. Comprobar que no
        # aparece la palabra sería demasiado burdo: "no está recortada" la usa.
        self.assertIn("no está recortada", lo["titulo_recorte"].lower())
        self.assertIn("meseta", lo["aviso_recorte"].lower(),
                      "hay que explicar qué le falta para ser recorte")

    def test_ninguna_categoria_informativa_lleva_severidad_de_aviso(self):
        for nombre in _CASOS:
            lo = medir(nombre)
            if lo["categoria_recorte"] != "recorte_sostenido":
                self.assertEqual(lo["severidad_recorte"], "info",
                                 f"{nombre}: solo el recorte sostenido avisa")

    def test_nunca_se_afirma_la_intencion(self):
        prohibidas = ("has recortado", "lo has hecho mal", "error tuyo",
                      "está mal masterizado", "no sabes")
        for nombre in _CASOS:
            aviso = medir(nombre)["aviso_recorte"].lower()
            for frase in prohibidas:
                self.assertNotIn(frase, aviso, f"{nombre}: '{frase}'")

    def test_el_clipper_deliberado_no_genera_aviso(self):
        """Un clipper en la batería es técnica normal. Si le damos una
        regañina cada vez, deja de creerse el resto del informe."""
        x = np.zeros(SR * 4, dtype=np.float64)
        golpes = np.arange(0.25, 4.0, 0.25)
        for g in golpes:
            i = int(g * SR)
            x[i:i + 6] = 1.0                       # 0,14 ms: pico recortado
            x[i + 6:i + 400] = 0.4
        ruta = os.path.join(tempfile.mkdtemp(), "clip.wav")
        sf.write(ruta, np.column_stack([x, x]), SR, subtype="PCM_24")
        nat, nsr = sf.read(ruta, always_2d=True, dtype="float32")
        med = _medir_muestras_en_techo(nat, nsr, FMT_24, onsets_seg=golpes)
        cls = _clasificar_recorte(med, FMT_24)
        self.assertEqual(cls["categoria_recorte"], "recorte_en_transitorios")
        self.assertEqual(cls["severidad_recorte"], "info")
        self.assertIn("clipper", cls["aviso_recorte"].lower())


class TestElCasoQueJustificaLaFase(unittest.TestCase):
    """Material sostenido aplastado: eso sí es daño, y hoy era invisible."""

    def test_recorte_largo_sobre_material_sostenido_si_avisa(self):
        lo = medir("wav24_clip_sostenido")
        self.assertEqual(lo["categoria_recorte"], "recorte_sostenido")
        self.assertEqual(lo["severidad_recorte"], "atencion")
        self.assertGreater(lo["racha_maxima_ms"], 1.0)

    def test_el_clipping_duro_se_detecta(self):
        lo = medir("wav24_clipping_evidente")
        self.assertEqual(lo["categoria_recorte"], "recorte_sostenido")
        self.assertGreater(lo["muestras_en_techo_total"], 1000)

    def test_separa_dos_tracks_que_la_2a_ve_iguales(self):
        """LA razón de ser de la fase, medida.

        Los dos casos salen como `true_peak_over` en la taxonomía de la 2A:
        indistinguibles en el informe de hoy. Uno tiene el máster intacto y el
        pico viviendo entre muestras; el otro tiene la onda aplastada. Es la
        diferencia entre "no toques nada" y "vuelve a exportar".
        """
        rng = np.random.default_rng(fx.SEED)
        base = fx._musical(SR, 6.0, rng)

        def analizar(x, nombre):
            ruta = os.path.join(tempfile.mkdtemp(), f"{nombre}.wav")
            sf.write(ruta, np.column_stack([x, x]), SR, subtype="PCM_24")
            return extraer_senales(ruta, omitir_armonia=True)["loudness"]

        puro = analizar(fx._escalar_a_sample_peak(base, -0.15), "puro")
        roto = analizar(np.clip(base * 4.0, -1.0, 1.0), "roto")

        # La 2A no los distingue...
        self.assertEqual(puro["categoria_picos"], "true_peak_over")
        self.assertEqual(roto["categoria_picos"], "true_peak_over")
        # ...y la 2B sí.
        self.assertEqual(puro["categoria_recorte"], "sin_muestras_en_techo")
        self.assertEqual(puro["severidad_recorte"], "info")
        self.assertEqual(roto["categoria_recorte"], "recorte_sostenido")
        self.assertEqual(roto["severidad_recorte"], "atencion")

    def test_el_recorte_normalizado_a_la_baja_NO_se_detecta(self):
        """Límite declarado, con test propio para que nadie lo olvide.

        Si el recorte ocurrió antes del bounce y después se bajó el nivel, las
        muestras ya no están en el techo y contar no encuentra nada. No es un
        fallo que se pueda arreglar contando mejor: la huella no está en el
        archivo. Haría falta análisis de forma de onda o de armónicos de
        intermodulación, que no está en el alcance de ninguna fase.

        Este test existe para que, si algún día alguien afirma que la 2B cubre
        este caso, falle."""
        rng = np.random.default_rng(fx.SEED)
        x = np.clip(fx._musical(SR, 6.0, rng) * 4.0, -1.0, 1.0) * 0.5
        ruta = os.path.join(tempfile.mkdtemp(), "bajado.wav")
        sf.write(ruta, np.column_stack([x, x]), SR, subtype="PCM_24")
        lo = extraer_senales(ruta, omitir_armonia=True)["loudness"]
        self.assertEqual(lo["categoria_recorte"], "sin_muestras_en_techo")
        self.assertEqual(lo["muestras_en_techo_total"], 0)

    def test_no_puede_haber_recorte_con_el_techo_holgado(self):
        """Invariante que hace imposible la fila que el diseño daba por buena.

        El true peak nunca es menor que el sample peak. Si hay muestras en el
        techo, el sample peak está en 0 dBFS, así que el true peak está en 0 o
        por encima: la categoría de la 2A NUNCA puede ser `ok`. El diseño
        original prometía cazar "techo correcto + recorte dentro" y eso no
        existe."""
        for nombre in _CASOS:
            lo = medir(nombre)
            if lo.get("muestras_en_techo_total", 0) > 0:
                self.assertNotEqual(
                    lo["categoria_picos"], "ok",
                    f"{nombre}: con muestras en el techo la 2A no puede decir 'ok'")


class TestElTextoEnsena(unittest.TestCase):
    """Decisión de producto: "la idea siempre es formarle también".

    Cada caso tiene que dejar al productor sabiendo qué se ha medido y qué
    significa, no solo con una etiqueta.
    """

    def test_todos_los_casos_explican_algo(self):
        for nombre in _CASOS:
            lo = medir(nombre)
            self.assertTrue(lo["titulo_recorte"], nombre)
            self.assertGreater(len(lo["aviso_recorte"]), 180,
                               f"{nombre}: el aviso es demasiado escueto para enseñar")

    def test_el_aviso_grave_dice_que_no_tiene_arreglo_posterior(self):
        """Es la diferencia práctica más importante frente a un pico alto, y
        la que cambia lo que el productor hace a continuación."""
        aviso = medir("wav24_clip_sostenido")["aviso_recorte"].lower()
        self.assertIn("no se arregla", aviso)
        self.assertIn("exporta", aviso)

    def test_se_distingue_del_true_peak(self):
        """La confusión más probable del usuario: creer que esto y el true
        peak son lo mismo."""
        aviso = medir("wav24_pico_menos1")["aviso_recorte"].lower()
        self.assertIn("true peak", aviso)

    def test_ningun_aviso_lleva_markdown(self):
        """El frontend pinta estos textos tal cual, sin procesar markdown: unos
        asteriscos de negrita se verían como asteriscos. Pasó en la v0.5.74."""
        for nombre in _CASOS:
            lo = medir(nombre)
            for campo in ("titulo_recorte", "aviso_recorte"):
                texto = lo[campo]
                for marca in ("**", "__", "`"):
                    self.assertNotIn(marca, texto, f"{nombre}.{campo}: '{marca}'")

    def test_los_avisos_llevan_los_numeros_medidos(self):
        for nombre in ("wav24_clip_sostenido", "wav24_clipping_evidente"):
            lo = medir(nombre)
            self.assertIn("ms", lo["aviso_recorte"])
            self.assertIn(str(lo["racha_maxima_muestras"]), lo["aviso_recorte"],
                          f"{nombre}: el aviso debería citar lo medido")


class TestContratoYRendimiento(unittest.TestCase):
    def test_los_campos_llegan_al_diagnostico(self):
        from engine.diagnostico import generar_diagnostico
        ctx = {"genero": "techno", "genero_custom": "", "fase": "casi_listo",
               "objetivo": "sellos", "experiencia": "2-5",
               "dificultad_habitual": "mezcla", "bloqueo_percibido": ""}
        s = extraer_senales(_MANIFIESTO["wav24_clip_sostenido"]["ruta"],
                            omitir_armonia=True)
        lo = generar_diagnostico(s, ctx)["datos_audio"]["loudness"]
        for campo in ("categoria_recorte", "severidad_recorte", "aviso_recorte",
                      "muestras_en_techo_total", "racha_maxima_ms", "n_mesetas"):
            self.assertIn(campo, lo)

    def test_la_respuesta_sigue_siendo_serializable(self):
        import json
        for nombre in _CASOS:
            json.dumps(medir(nombre), allow_nan=False)

    def test_el_frontend_persiste_lo_esencial(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
            html = f.read()
        bloque = html[html.find("const senales = {"):]
        bloque = bloque[:bloque.find("};")]
        for campo in ("categoria_recorte", "muestras_en_techo_total",
                      "racha_maxima_ms", "n_mesetas"):
            self.assertIn(f"{campo}:", bloque, f"falta {campo}")

    def test_el_coste_es_despreciable(self):
        """Se calcula sobre el array que ya está leído para el true peak."""
        import time
        rng = np.random.default_rng(fx.SEED)
        x = fx._escalar_a_sample_peak(fx._musical(SR, 60.0, rng), -0.5)
        ruta = os.path.join(tempfile.mkdtemp(), "larga.wav")
        sf.write(ruta, np.column_stack([x, x]), SR, subtype="PCM_24")
        nat, nsr = sf.read(ruta, always_2d=True, dtype="float32")
        t0 = time.perf_counter()
        _medir_muestras_en_techo(nat, nsr, FMT_24, onsets_seg=np.arange(0, 60, 0.4))
        dt = time.perf_counter() - t0
        self.assertLess(dt, 1.0, f"1 min de audio tardó {dt * 1000:.0f} ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
