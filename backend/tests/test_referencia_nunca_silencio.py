"""Si el usuario adjuntó una referencia, el informe SIEMPRE dice algo de ella.

Dos quejas del feedback (docs/feedback-jun-ago-2026.md §3.6): un usuario subió
referencia y el informe no llevaba ni la comparación ni un error — falló en
silencio. Rutas por las que podía pasar y que aquí quedan selladas:

  1. La referencia no valida (formato/magic bytes): antes tumbaba la petición
     ENTERA con un 4xx; si el usuario reintentaba sin referencia, no quedaba
     rastro de que lo intentó. Ahora degrada: el diagnóstico sale, y
     `comparacion_referencia.error` cuenta qué pasó.
  2. El texto del informe guardado en DB omitía el caso de error, así que un
     fallo de referencia era invisible también para nosotros.

El contrato que fija este archivo: llega `audio_ref` ⇒ la respuesta lleva
`comparacion_referencia` (con diferencias o con error), y el análisis del
usuario NUNCA muere por culpa de la referencia.
"""

import os
import sys
import tempfile
import unittest
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

SR = 22050


def _wav_valido():
    import soundfile as sf
    t = np.arange(int(SR * 12)) / SR
    rng = np.random.default_rng(3)
    y = 0.25 * rng.standard_normal(len(t)) * (0.4 + 0.6 * (np.sin(2 * np.pi * t / 3) > 0))
    y += 0.05 * np.sin(2 * np.pi * 220 * t)
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(f.name, y.astype(np.float32), SR)
    return f.name


class TestReferenciaNuncaEnSilencio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("fastapi.testclient no disponible")
        os.environ.setdefault("JWT_SECRET", "test")
        os.environ.setdefault("ADMIN_KEY", "test")
        cls.ruta = _wav_valido()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.ruta)

    def _post(self, cliente, files):
        return cliente.post("/api/diagnostico", files=files,
                            data={"genero": "techno", "fase": "casi_listo",
                                  "objetivo": "sellos", "experiencia": "2-5",
                                  "dificultad_habitual": "mezcla"})

    def test_referencia_corrupta_degrada_y_lo_cuenta(self):
        """Un .mp3 que no es audio (magic bytes de ejecutable): el diagnóstico
        del usuario sale igual (200) y la comparación lleva el motivo."""
        from fastapi.testclient import TestClient
        import main
        with TestClient(main.app) as cliente, open(self.ruta, "rb") as fh:
            r = self._post(cliente, {
                "audio": ("track.wav", fh, "audio/wav"),
                "audio_ref": ("referencia.mp3", b"MZ\x90\x00" + b"\x00" * 64, "audio/mpeg"),
            })
        self.assertEqual(r.status_code, 200, r.text[:300])
        cuerpo = r.json()
        self.assertIn("datos_audio", cuerpo, "el análisis del usuario tiene que salir")
        comp = cuerpo.get("comparacion_referencia")
        self.assertIsInstance(comp, dict, "adjuntar referencia obliga a responder por ella")
        self.assertIn("error", comp)
        self.assertIn("Tu diagnóstico se generó igualmente", comp["error"])

    def test_referencia_vacia_degrada_y_lo_cuenta(self):
        from fastapi.testclient import TestClient
        import main
        with TestClient(main.app) as cliente, open(self.ruta, "rb") as fh:
            r = self._post(cliente, {
                "audio": ("track.wav", fh, "audio/wav"),
                "audio_ref": ("referencia.wav", b"", "audio/wav"),
            })
        self.assertEqual(r.status_code, 200, r.text[:300])
        comp = r.json().get("comparacion_referencia")
        self.assertIsInstance(comp, dict)
        self.assertIn("error", comp)


class TestLosContratosEstanEscritos(unittest.TestCase):
    """Guards estáticos sobre las dos fuentes."""

    def test_la_validacion_de_la_referencia_no_tumba_la_peticion(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
        i = src.index('_validar_audio_upload(audio_ref.filename')
        bloque = src[i:i + 1400]
        self.assertNotIn("return err", bloque,
                         "la referencia no puede tumbar el análisis del usuario")
        self.assertIn("comparacion_error", bloque)
        self.assertIn("tiene_ref = False", bloque)

    def test_el_informe_guardado_escribe_tambien_el_error(self):
        idx = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "frontend", "index.html")
        html = open(idx, encoding="utf-8").read()
        self.assertIn("COMPARACIÓN CON REFERENCIA: ERROR —", html)

    def test_todos_los_fallos_de_referencia_quedan_logueados(self):
        """Cada ruta de fallo imprime un rastro grepeable en los logs de
        Railway — sin esto, el caso [25] fue imposible de diagnosticar."""
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
        self.assertIn('print(f"[REF] rechazada en validación', src)
        self.assertIn('print(f"[REF] referencia sin señal analizable', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
