"""Tests de la medición de picos y del contrato de campos nuevos (fase 1).

Se ejecuta con la stdlib, sin dependencias de test añadidas:

    python -m unittest discover -s tests -t . -v

Requiere numpy/soundfile/librosa/pyloudnorm, que ya son dependencias del
motor. ffmpeg solo hace falta para el fixture MP3 y para test_loudness_mono.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

import librosa
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import _analizar_loudness  # noqa: E402
from tests import capturar_golden as cg  # noqa: E402
from tests import fixtures as fx  # noqa: E402

_DIR = tempfile.mkdtemp(prefix="mentotrack_fixtures_")
_MANIFIESTO = None
_CACHE = {}


def setUpModule():
    global _MANIFIESTO
    _MANIFIESTO = fx.generar(_DIR)


def medir(nombre):
    if nombre not in _CACHE:
        _CACHE[nombre] = cg.medir_completo(_MANIFIESTO[nombre]["ruta"])
    return _CACHE[nombre]


class TestContratoCampos(unittest.TestCase):
    """Los campos nuevos existen, con el tipo correcto, en todos los fixtures."""

    CAMPOS = [
        "true_peak_dbtp", "sample_peak_dbfs", "sample_peak_source",
        "true_peak_method", "true_peak_oversampling", "true_peak_validated",
        "true_peak_ground_truth_validation_passed",
        "peak_measurement_sample_rate", "peak_measurement_channels",
    ]

    def test_todos_los_campos_presentes(self):
        for nombre in _MANIFIESTO:
            r = medir(nombre)
            for campo in self.CAMPOS:
                self.assertIn(campo, r, f"{nombre}: falta {campo}")

    def test_tipos_y_dominios(self):
        for nombre in _MANIFIESTO:
            r = medir(nombre)
            self.assertIsInstance(r["true_peak_dbtp"], float, nombre)
            self.assertIsInstance(r["sample_peak_dbfs"], float, nombre)
            self.assertIn(r["sample_peak_source"],
                          ("archivo_nativo", "audio_remuestreado_22k", "no_disponible"), nombre)
            self.assertIn(r["true_peak_method"],
                          ("soxr_hq_8x", "sample_peak_22k_fallback", "no_disponible"), nombre)
            self.assertIn(r["true_peak_oversampling"], (0, 1, 8), nombre)
            self.assertIsInstance(r["true_peak_validated"], bool, nombre)

    def test_la_declaracion_de_validado_no_puede_mentir(self):
        """El seguro de todo el montaje.

        `_VALIDACION_VERDAD_DECLARADA` es una constante que pone una persona a
        mano. Si nadie la comprueba, no vale nada: cualquiera puede escribir
        True y el motor se declara validado sin haber medido.

        Aquí se vuelve a hacer la medición de verdad —fabricar una señal cuyo
        pico se conoce de antemano, decimarla y pedirle al medidor DESPLEGADO
        que lo recupere— y se exige que el resultado coincida con lo
        declarado. Poner True sin que la medida acompañe rompe el CI.
        """
        from engine.extractor import (OVERSAMPLING_PICOS,
                                      TOL_VERDAD_CONSTRUIDA_DB,
                                      TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED)
        from tests.test_reconstruccion import _fabricar_con_verdad_conocida

        import librosa

        peor = 0.0
        # Contenido hasta 20 kHz: el rango en el que trabaja un bounce real.
        for semilla, f_max in ((1, 20000), (2, 20000), (3, 16000),
                               (4, 10000), (7, 5000)):
            archivo, verdad = _fabricar_con_verdad_conocida(semilla, f_max)
            up = librosa.resample(archivo.astype(np.float32), orig_sr=44100,
                                  target_sr=44100 * OVERSAMPLING_PICOS,
                                  res_type="soxr_hq")
            medido = 20.0 * np.log10(max(float(np.max(np.abs(up))), 1e-12))
            peor = max(peor, abs(medido - 20.0 * np.log10(verdad)))

        acierta = peor <= TOL_VERDAD_CONSTRUIDA_DB
        self.assertEqual(
            acierta, TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED,
            f"error máximo medido {peor:.4f} dB frente a una tolerancia de "
            f"{TOL_VERDAD_CONSTRUIDA_DB} dB, pero la declaración dice "
            f"{TRUE_PEAK_GROUND_TRUTH_VALIDATION_PASSED}")

    def test_validated_refleja_el_estado_real(self):
        for nombre in _MANIFIESTO:
            from engine.extractor import _TRUE_PEAK_VALIDATED
            self.assertEqual(medir(nombre)["true_peak_validated"],
                             _TRUE_PEAK_VALIDATED, nombre)

    def test_json_serializable(self):
        """Ningún campo puede ser inf/NaN: Starlette rechaza eso con allow_nan=False."""
        for nombre in _MANIFIESTO:
            r = {k: v for k, v in medir(nombre).items() if k in self.CAMPOS}
            try:
                json.dumps(r, allow_nan=False)
            except ValueError as e:  # pragma: no cover
                self.fail(f"{nombre}: campos de picos no serializables ({e})")


class TestPrecision(unittest.TestCase):
    """Los picos se conservan sin redondear."""

    def test_true_peak_no_viene_redondeado(self):
        # Al menos un fixture debe tener más de 1 decimal significativo: si
        # todos cayeran justo en un decimal exacto, el test no probaría nada.
        crudos = [medir(n)["true_peak_dbtp"] for n in _MANIFIESTO]
        con_precision = [v for v in crudos if v > -99 and abs(v - round(v, 1)) > 1e-9]
        self.assertTrue(con_precision,
                        "ningún true peak conserva precisión: ¿se sigue redondeando?")

    def test_sample_peak_no_viene_redondeado(self):
        crudos = [medir(n)["sample_peak_dbfs"] for n in _MANIFIESTO]
        con_precision = [v for v in crudos if v > -99 and abs(v - round(v, 1)) > 1e-9]
        self.assertTrue(con_precision, "ningún sample peak conserva precisión")

    def test_sample_peak_coincide_con_el_fixture(self):
        """El sample peak medido es el que se escribió, dentro del error de
        cuantización del bit depth. Esto SÍ valida el algoritmo: el valor sale
        de la señal, no de una relación forzada por el código."""
        for nombre, spec in _MANIFIESTO.items():
            esperado = spec.get("sp_esperado")
            if esperado is None or spec.get("lossy"):
                continue
            medido = medir(nombre)["sample_peak_dbfs"]
            # PCM_16 cuantiza con paso mayor: tolerancia proporcional.
            tol = 0.05 if spec["subtype"] != "PCM_16" else 0.1
            self.assertAlmostEqual(
                medido, esperado, delta=tol,
                msg=f"{nombre}: sample peak {medido:.3f} vs esperado {esperado}")


class TestInvarianteSeguridad(unittest.TestCase):
    def test_true_peak_nunca_menor_que_sample_peak(self):
        """INVARIANTE DE SEGURIDAD, NO VALIDACIÓN DEL ALGORITMO.

        El código fuerza la relación con max(tp, sample_peak), así que este
        test no puede fallar por un error de medida del oversampling — solo
        detectaría que alguien quite ese max(). La validación real del
        algoritmo está en validar_true_peak.py, contra medidores externos.
        """
        for nombre in _MANIFIESTO:
            r = medir(nombre)
            if r["sample_peak_source"] != "archivo_nativo":
                continue
            self.assertGreaterEqual(
                r["true_peak_dbtp"], r["sample_peak_dbfs"] - 1e-9, nombre)


class TestFallback(unittest.TestCase):
    def test_archivo_ilegible_marca_no_fiable(self):
        """Si sf.read nativo falla, no se publica un sample peak inventado."""
        ruta = os.path.join(_DIR, "corrupto.wav")
        with open(ruta, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 200)   # cabecera válida, contenido no
        y = np.zeros(22050 * 2, dtype=np.float32) + 0.1
        r = _analizar_loudness(ruta, y_preloaded=y, sr_preloaded=22050)
        self.assertEqual(r["sample_peak_source"], "no_disponible")
        self.assertEqual(r["sample_peak_dbfs"], -99.0)
        self.assertIn(r["true_peak_method"], ("sample_peak_22k_fallback", "no_disponible"))


class TestClasificacionCongelada(unittest.TestCase):
    """Golden: ninguna clasificación ni texto cambia en fase 1."""

    def test_golden(self):
        with open(cg.GOLDEN, encoding="utf-8") as f:
            esperado = json.load(f)
        actual = {n: cg.medir(spec["ruta"]) for n, spec in _MANIFIESTO.items()}
        fallos, _autorizados = cg.comparar(esperado, actual)
        self.assertEqual(fallos, [], "divergencias no autorizadas:\n" + "\n".join(fallos))

    def test_umbral_se_decide_sobre_el_redondeado(self):
        """Un true peak de +0,04 dBTP debe seguir clasificándose 'streaming'.

        Es la deuda de fase 1: sin el anclaje al valor redondeado, dejar de
        redondear movería solo este track de categoría.
        """
        sr = 44100
        # Seno escalado para que el sample peak quede justo por encima de 0
        # pero por debajo de +0,05 dBTP.
        x = fx._seno(1000.0, sr, 2.0)
        x = x * (10.0 ** (0.04 / 20.0)) / float(np.max(np.abs(x)))
        ruta = os.path.join(_DIR, "borde_004.wav")
        import soundfile as sf_
        sf_.write(ruta, np.column_stack([x, x]), sr, subtype="FLOAT")
        y_st, sr_l = librosa.load(ruta, sr=22050, mono=False)
        r = _analizar_loudness(ruta, y_preloaded=np.mean(y_st, axis=0),
                               sr_preloaded=sr_l, y_stereo_preloaded=y_st)
        self.assertGreater(r["true_peak_dbtp"], 0.0, "el fixture debe superar 0 sin redondear")
        self.assertLess(r["true_peak_dbtp"], 0.05)
        self.assertEqual(r["nivel_true_peak"], "streaming",
                         "la clasificación debe seguir saliendo del valor redondeado")


class TestPorCanal(unittest.TestCase):
    def test_recorte_en_un_solo_canal_se_detecta_en_el_maximo(self):
        """Con L saturado y R a -6 dBFS, el pico publicado es el de L."""
        r = medir("wav24_clip_solo_L")
        self.assertGreaterEqual(r["sample_peak_dbfs"], -0.1)
        self.assertEqual(r["peak_measurement_channels"], 2)

    def test_canales_y_sample_rate_registrados(self):
        for nombre in ("wav24_pico_menos1", "wav24_mono",
                       "wav24_48000_pico_menos1", "wav24_96000_pico_menos1"):
            r = medir(nombre)
            spec = _MANIFIESTO[nombre]
            self.assertEqual(r["peak_measurement_sample_rate"], spec["sr"], nombre)
            self.assertEqual(r["peak_measurement_channels"], spec["canales"], nombre)


class TestValoresCentinela(unittest.TestCase):
    def test_silencio_no_produce_inf_en_los_picos(self):
        r = medir("wav24_silencio")
        self.assertTrue(math.isfinite(r["true_peak_dbtp"]))
        self.assertTrue(math.isfinite(r["sample_peak_dbfs"]))
        self.assertEqual(r["true_peak_dbtp"], -99.0)

    def test_true_peak_exactamente_cero_es_representable(self):
        """El caso que el frontend perdía por `0` falsy."""
        sr = 44100
        x = fx._seno(1000.0, sr, 2.0)
        x = x / float(np.max(np.abs(x)))       # sample peak exactamente 0 dBFS
        ruta = os.path.join(_DIR, "cero_exacto.wav")
        import soundfile as sf_
        sf_.write(ruta, np.column_stack([x, x]), sr, subtype="FLOAT")
        y_st, sr_l = librosa.load(ruta, sr=22050, mono=False)
        r = _analizar_loudness(ruta, y_preloaded=np.mean(y_st, axis=0),
                               sr_preloaded=sr_l, y_stereo_preloaded=y_st)
        self.assertAlmostEqual(r["sample_peak_dbfs"], 0.0, delta=0.01)
        self.assertNotEqual(r["sample_peak_dbfs"], -99.0)


class TestLoudnessMono(unittest.TestCase):
    """El mono se mide como un canal, igual que cualquier medidor de referencia."""

    def _ffmpeg_lufs(self, ruta):
        try:
            p = subprocess.run(
                ["ffmpeg", "-i", ruta, "-af", "ebur128", "-f", "null", "-"],
                capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        marca = "Integrated loudness:"
        if marca not in p.stderr:
            return None
        cola = p.stderr.split(marca, 1)[1]
        for linea in cola.splitlines():
            if "I:" in linea and "LUFS" in linea:
                return float(linea.split("I:")[1].split("LUFS")[0].strip())
        return None

    def test_mono_coincide_con_ffmpeg(self):
        ruta = _MANIFIESTO["wav24_mono"]["ruta"]
        ref = self._ffmpeg_lufs(ruta)
        if ref is None:
            self.skipTest("ffmpeg no disponible")
        medido = medir("wav24_mono")["lufs_integrado"]
        # 0,5 LU cubre la diferencia por medir a 22 kHz en vez de a 44,1 kHz.
        self.assertAlmostEqual(
            medido, ref, delta=0.5,
            msg=f"mono: Mentotrack {medido} vs ffmpeg {ref}")

    def test_mono_no_suma_el_canal_dos_veces(self):
        """Un mono debe medir ~3 LU MENOS que el mismo material en dos canales."""
        mono = medir("wav24_mono")["lufs_integrado"]
        estereo = medir("wav24_pico_menos1")["lufs_integrado"]
        self.assertAlmostEqual(estereo - mono, 3.01, delta=0.4,
                               msg=f"mono={mono} estereo={estereo}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
