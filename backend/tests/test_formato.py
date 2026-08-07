"""Tests de los metadatos del archivo (fase 1: solo registro).

Lo que más importa aquí es la separación entre `archivo_storage_bits` y
`archivo_pcm_bit_depth`: en FLOAT/DOUBLE los bits son el tamaño del
contenedor, no un techo de cuantización, y confundirlos es lo que lleva a
tratar un over recuperable como recorte irreversible.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import _analizar_formato  # noqa: E402
from tests import fixtures as fx  # noqa: E402

_DIR = tempfile.mkdtemp(prefix="mentotrack_formato_")
_MANIFIESTO = None


def setUpModule():
    global _MANIFIESTO
    _MANIFIESTO = fx.generar(_DIR)


class TestSubtypes(unittest.TestCase):

    def test_pcm16(self):
        f = _analizar_formato(_MANIFIESTO["wav16_pico_menos1"]["ruta"])
        self.assertEqual(f["archivo_subtype"], "PCM_16")
        self.assertEqual(f["archivo_sample_format"], "integer")
        self.assertEqual(f["archivo_storage_bits"], 16)
        self.assertEqual(f["archivo_pcm_bit_depth"], 16)
        self.assertFalse(f["archivo_lossy"])
        self.assertEqual(f["archivo_metadata_source"], "soundfile")

    def test_pcm24(self):
        f = _analizar_formato(_MANIFIESTO["wav24_pico_menos1"]["ruta"])
        self.assertEqual(f["archivo_subtype"], "PCM_24")
        self.assertEqual(f["archivo_sample_format"], "integer")
        self.assertEqual(f["archivo_storage_bits"], 24)
        self.assertEqual(f["archivo_pcm_bit_depth"], 24)

    def test_float32_no_tiene_techo_pcm(self):
        f = _analizar_formato(_MANIFIESTO["wav32f_sobre_0"]["ruta"])
        self.assertEqual(f["archivo_subtype"], "FLOAT")
        self.assertEqual(f["archivo_sample_format"], "float")
        self.assertEqual(f["archivo_storage_bits"], 32)
        self.assertIsNone(f["archivo_pcm_bit_depth"],
                          "un FLOAT de 32 bits no tiene bit depth PCM")

    def test_double64(self):
        f = _analizar_formato(_MANIFIESTO["wav64d_pico_menos1"]["ruta"])
        self.assertEqual(f["archivo_subtype"], "DOUBLE")
        self.assertEqual(f["archivo_sample_format"], "float")
        self.assertEqual(f["archivo_storage_bits"], 64)
        self.assertIsNone(f["archivo_pcm_bit_depth"])

    def test_flac(self):
        f = _analizar_formato(_MANIFIESTO["flac24_pico_menos1"]["ruta"])
        self.assertEqual(f["archivo_container"], "FLAC")
        self.assertEqual(f["archivo_sample_format"], "integer")
        self.assertEqual(f["archivo_pcm_bit_depth"], 24)
        self.assertFalse(f["archivo_lossy"])

    def test_mp3(self):
        if "mp3_320" not in _MANIFIESTO:
            self.skipTest("no se pudo generar el MP3 (¿ffmpeg?)")
        f = _analizar_formato(_MANIFIESTO["mp3_320"]["ruta"])
        if f["archivo_metadata_source"] != "soundfile":
            self.skipTest("esta build de libsndfile no lee MP3")
        self.assertTrue(f["archivo_lossy"])
        self.assertIsNone(f["archivo_pcm_bit_depth"],
                          "un códec con pérdida no tiene techo PCM")
        self.assertIsNone(f["archivo_storage_bits"])


class TestSampleRateYCanales(unittest.TestCase):
    def test_sample_rate_y_canales(self):
        casos = [("wav24_pico_menos1", 44100, 2), ("wav24_48000_pico_menos1", 48000, 2),
                 ("wav24_96000_pico_menos1", 96000, 2), ("wav24_mono", 44100, 1)]
        for nombre, sr, ch in casos:
            f = _analizar_formato(_MANIFIESTO[nombre]["ruta"])
            self.assertEqual(f["archivo_sample_rate"], sr, nombre)
            self.assertEqual(f["archivo_canales"], ch, nombre)


class TestDegradacion(unittest.TestCase):
    def test_archivo_ilegible_cae_a_extension(self):
        ruta = os.path.join(_DIR, "roto.mp3")
        with open(ruta, "wb") as fh:
            fh.write(b"no soy audio")
        f = _analizar_formato(ruta)
        self.assertEqual(f["archivo_metadata_source"], "extension")
        self.assertEqual(f["archivo_extension"], ".mp3")
        self.assertTrue(f["archivo_lossy"], "por extensión, .mp3 es lossy")
        self.assertIsNone(f["archivo_pcm_bit_depth"])

    def test_sin_extension_ni_cabecera_no_revienta(self):
        ruta = os.path.join(_DIR, "sinextension")
        with open(ruta, "wb") as fh:
            fh.write(b"\x00" * 32)
        f = _analizar_formato(ruta)
        self.assertEqual(f["archivo_metadata_source"], "desconocida")
        self.assertIsNone(f["archivo_lossy"])

    def test_contrato_de_claves_siempre_completo(self):
        esperadas = {
            "archivo_extension", "archivo_container", "archivo_codec",
            "archivo_subtype", "archivo_sample_format", "archivo_storage_bits",
            "archivo_pcm_bit_depth", "archivo_sample_rate", "archivo_canales",
            "archivo_lossy", "archivo_metadata_source",
        }
        for ruta in (_MANIFIESTO["wav24_pico_menos1"]["ruta"], "/no/existe.wav"):
            self.assertEqual(set(_analizar_formato(ruta)), esperadas, ruta)


class TestNoAfectaAlDiagnostico(unittest.TestCase):
    """Fase 1: los metadatos se registran pero no los lee nadie."""

    def test_ninguna_regla_lee_los_campos_de_formato(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fichero in ("engine/reglas.py", "engine/contextualizador.py",
                        "engine/templates.py", "engine/comparador.py"):
            with open(os.path.join(raiz, fichero), encoding="utf-8") as fh:
                contenido = fh.read()
            for clave in ("archivo_subtype", "archivo_sample_format",
                          "archivo_pcm_bit_depth", "archivo_lossy", '["formato"]'):
                self.assertNotIn(clave, contenido,
                                 f"{fichero} usa {clave}: en fase 1 solo se registra")


if __name__ == "__main__":
    unittest.main(verbosity=2)
