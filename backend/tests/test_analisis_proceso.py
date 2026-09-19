"""El análisis de audio corre en un proceso aparte (analisis_proceso).

Por qué existe: dentro del proceso del servidor, la memoria de librosa/numpy
no volvía al sistema al terminar cada análisis (fragmentación de glibc entre
hilos). En Railway la RAM subía de ~0,8 GB a más de 2 GB al mes y solo bajaba
al redesplegar. Con un proceso hijo por análisis, el sistema recupera toda la
memoria y el timeout mata el análisis de verdad.

Estos tests cubren el transporte (resultado, excepción con su clase, timeout,
proceso muerto) y que la extracción real funciona por ese camino.
"""

import asyncio
import glob
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analisis_proceso as ap  # noqa: E402

ECO = "tests.tareas_hijo:eco"


class TestEjecutaEnOtroProceso(unittest.TestCase):

    def test_el_resultado_vuelve_con_sus_tipos(self):
        r = ap.ejecutar_sync(ECO, "ruta.wav", bpm_manual=120, timeout=60)
        self.assertNotEqual(r["pid"], os.getpid(), "tiene que correr en otro proceso")
        self.assertEqual(r["args"], ["ruta.wav"])
        self.assertEqual(r["kwargs"], {"bpm_manual": 120})
        import numpy as np
        self.assertIsInstance(r["np"], np.floating, "los tipos numpy del extractor deben conservarse")

    def test_la_excepcion_del_motor_llega_con_su_clase(self):
        from engine.extractor import AudioSinSenalAnalizable
        with self.assertRaises(AudioSinSenalAnalizable) as cm:
            ap.ejecutar_sync("tests.tareas_hijo:sin_senal", timeout=60)
        self.assertEqual(cm.exception.motivo, "silencio absoluto")
        self.assertEqual(cm.exception.detalle, {"pico_dbfs": -120.0})

    def test_el_timeout_mata_el_proceso(self):
        t0 = time.monotonic()
        with self.assertRaises(asyncio.TimeoutError):   # lo que capturan los endpoints
            ap.ejecutar_sync("tests.tareas_hijo:dormir", 30, timeout=1)
        self.assertLess(time.monotonic() - t0, 10, "no debe esperar a que el hijo acabe")

    def test_si_el_proceso_muere_se_sabe(self):
        with self.assertRaises(ap.AnalisisFallido) as cm:
            ap.ejecutar_sync("tests.tareas_hijo:morir", 137, timeout=60)
        self.assertIn("137", str(cm.exception))

    def test_un_resultado_no_serializable_no_deja_colgado_al_padre(self):
        with self.assertRaises(ap.AnalisisFallido):
            ap.ejecutar_sync("tests.tareas_hijo:no_serializable", timeout=60)

    def test_version_asincrona(self):
        r = asyncio.run(ap.ejecutar(ECO, 1, timeout=60))
        self.assertEqual(r["args"], [1])

    def test_no_deja_archivos_temporales(self):
        patron = os.path.join(tempfile.gettempdir(), "mentotrack_hijo_*")
        antes = set(glob.glob(patron))
        ap.ejecutar_sync(ECO, timeout=60)
        with self.assertRaises(asyncio.TimeoutError):
            ap.ejecutar_sync("tests.tareas_hijo:dormir", 30, timeout=1)
        self.assertEqual(set(glob.glob(patron)) - antes, set())


class TestExtraccionRealEnElHijo(unittest.TestCase):
    """El camino real: engine.extractor y la forma de onda de comunidad."""

    @classmethod
    def setUpClass(cls):
        try:
            import numpy as np
            import soundfile as sf
        except ImportError:
            raise unittest.SkipTest("numpy/soundfile no disponibles")
        sr, dur = 44100, 10.0
        rng = np.random.default_rng(3)
        t = np.arange(int(sr * dur)) / sr
        # Kick sintético a 128 BPM sobre ruido: señal analizable, con tempo.
        kick = np.sin(2 * np.pi * 55 * t) * np.exp(-((t * 128 / 60) % 1.0) * 12)
        x = 0.5 * kick + 0.05 * rng.standard_normal(len(t))
        cls.dir = tempfile.mkdtemp(prefix="mentotrack_hijo_test_")
        cls.ruta = os.path.join(cls.dir, "kick.wav")
        sf.write(cls.ruta, np.stack([x, x], axis=1), sr, subtype="PCM_24")

    def test_extraer_senales(self):
        senales = ap.ejecutar_sync(ap.EXTRAER_SENALES, self.ruta, bpm_manual=128, timeout=180)
        self.assertIsInstance(senales, dict)
        self.assertIn("bloques_rms", senales)

    def test_forma_de_onda(self):
        picos, dur = ap.ejecutar_sync(ap.CALCULAR_WAVEFORM, self.ruta, timeout=120)
        self.assertEqual(len(picos), 400)
        self.assertAlmostEqual(dur, 10.0, places=1)
        self.assertLessEqual(max(picos), 1.0)


class TestLosContratosEstanEscritos(unittest.TestCase):

    def test_main_no_analiza_dentro_del_servidor(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "main.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("_extraer_senales", src,
                         "la extracción no puede volver a correr en el proceso del servidor")
        self.assertNotIn("_calcular_waveform", src)
        self.assertGreaterEqual(src.count("analisis_proceso.ejecutar("), 4,
                                "track, referencia, features de Relesit y forma de onda")


if __name__ == "__main__":
    unittest.main(verbosity=2)
