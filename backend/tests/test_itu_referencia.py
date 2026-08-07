"""Contraste contra el FIR de referencia de ITU-R BS.1770-5, Anexo 2.

El FIR de referencia NO es el algoritmo de producción: sirve para comparar
soxr_hq_4x contra algo que sigue la letra de la norma. Las diferencias
encontradas se documentan en RESULTADOS_VALIDACION.md.
"""

import os
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import capturar_golden as cg  # noqa: E402
from tests import estudio_continua as ec  # noqa: E402
from tests import fixtures as fx  # noqa: E402
from tests import itu_bs1770 as itu  # noqa: E402

_DIR = tempfile.mkdtemp(prefix="mentotrack_itu_")
_MANIFIESTO = None

# Margen entre soxr_hq_4x y el FIR de la ITU sobre material de banda limitada
# (música real). Medido: con el espectro recortado a 10 kHz los dos coinciden
# dentro de 0,013 dB; a 15 kHz, dentro de 0,03.
TOL_BANDA_LIMITADA = 0.10
# Con energía pegada a Nyquist los dos divergen en direcciones opuestas
# respecto a la reconstrucción ideal, y no es un fallo de ninguno: el FIR de
# 12 taps por fase de la norma atenúa esa zona, soxr_hq la conserva y deja
# pasar algo de imagen. Ver RESULTADOS_VALIDACION.md.
TOL_BANDA_COMPLETA = 0.40
# En señales con discontinuidad la diferencia depende del tratamiento de
# bordes de cada filtro y es legítimamente mayor.
TOL_DISCONTINUA = 1.00


def setUpModule():
    global _MANIFIESTO
    _MANIFIESTO = fx.generar(_DIR)


class TestCoeficientes(unittest.TestCase):
    """Si un coeficiente estuviera mal transcrito, el banco perdería sus
    propiedades estructurales."""

    def test_simetria_entre_fases(self):
        chk = itu.verificar_coeficientes()
        self.assertTrue(chk["simetria_ok"],
                        f"el filtro prototipo debe ser simétrico: {chk}")
        self.assertEqual(chk["simetria_fase0_fase3"], 0.0)
        self.assertEqual(chk["simetria_fase1_fase2"], 0.0)

    def test_ganancia_en_continua(self):
        chk = itu.verificar_coeficientes()
        self.assertTrue(chk["dc_ok"], f"ganancias DC fuera de rango: {chk}")

    def test_dimensiones(self):
        self.assertEqual(itu.COEFICIENTES_FASES.shape, (4, 12),
                         "el banco del anexo 2 es de 4 fases x 12 taps")


class TestSenalesEstables(unittest.TestCase):
    """Sin discontinuidades, soxr y el FIR de la ITU deben coincidir —
    siempre que la señal no tenga energía pegada a Nyquist."""

    def test_banda_limitada_convergen(self):
        """El caso realista: música con el espectro recortado a 15 kHz."""
        ruta = _MANIFIESTO["wav24_bandlimitada_15k"]["ruta"]
        soxr = cg.medir_completo(ruta)["true_peak_dbtp"]
        ref = itu.true_peak_desde_archivo(ruta, "cero")
        self.assertAlmostEqual(
            soxr, ref, delta=TOL_BANDA_LIMITADA,
            msg=f"banda limitada: soxr {soxr:.3f} vs ITU {ref:.3f}")

    def test_el_fir_de_la_itu_lee_por_debajo_con_energia_en_nyquist(self):
        """Los fixtures sintéticos llevan ruido hasta Nyquist. Ahí el FIR de
        12 taps por fase de la norma atenúa la banda alta y lee por DEBAJO de
        la reconstrucción ideal, de forma sistemática. No es un fallo de
        ninguno de los dos: es la diferencia entre un filtro corto normativo y
        uno largo. El test fija el signo para que un cambio de librería salte."""
        for nombre in ("wav24_pico_menos1", "wav16_pico_menos1",
                       "flac24_pico_menos1", "wav24_tp_entre_m1_y_0",
                       "wav24_limitado_sin_clip", "wav24_crest_bajo"):
            ruta = _MANIFIESTO[nombre]["ruta"]
            ref = itu.true_peak_desde_archivo(ruta, "cero")
            ideal = ec.tp_fft(ruta)
            self.assertLess(ref, ideal + 0.05,
                            f"{nombre}: el FIR de la ITU lee de menos, no de más")
            self.assertGreater(ref, ideal - 1.0,
                               f"{nombre}: divergencia mayor de la documentada")

    def test_soxr_se_mantiene_cerca_de_la_reconstruccion_ideal(self):
        """El algoritmo de producción, contra la interpolación sinc exacta."""
        for nombre in ("wav24_pico_menos1", "wav16_pico_menos1",
                       "flac24_pico_menos1", "wav24_tp_entre_m1_y_0",
                       "wav24_bandlimitada_15k", "wav24_48000_pico_menos1"):
            ruta = _MANIFIESTO[nombre]["ruta"]
            soxr = cg.medir_completo(ruta)["true_peak_dbtp"]
            ideal = ec.tp_fft(ruta)
            self.assertAlmostEqual(
                soxr, ideal, delta=TOL_BANDA_COMPLETA,
                msg=f"{nombre}: soxr {soxr:.3f} vs ideal {ideal:.3f}")

    def test_48k_convergen(self):
        """A 48 kHz, con la misma señal, soxr e ideal coinciden."""
        ruta = _MANIFIESTO["wav24_48000_pico_menos1"]["ruta"]
        soxr = cg.medir_completo(ruta)["true_peak_dbtp"]
        self.assertAlmostEqual(soxr, ec.tp_fft(ruta), delta=0.10)


class TestIntersamplePeaks(unittest.TestCase):
    """El caso analítico: ambos deben acercarse a +2,81 dBTP."""

    def test_isp_en_los_tres_sample_rates(self):
        for nombre in ("isp_fs4_sobre_0", "isp_fs4_48000", "isp_fs4_96000"):
            spec = _MANIFIESTO[nombre]
            analitico = spec["tp_analitico"]
            soxr = cg.medir_completo(spec["ruta"])["true_peak_dbtp"]
            ref = itu.true_peak_desde_archivo(spec["ruta"], "cero")
            self.assertAlmostEqual(soxr, analitico, delta=0.5, msg=f"{nombre} soxr")
            self.assertAlmostEqual(ref, analitico, delta=0.5, msg=f"{nombre} ITU")

    def test_ambos_detectan_que_hay_pico_entre_muestras(self):
        """Sin oversampling se leería -0,2 dBFS; los dos deben ver ~+2,8."""
        spec = _MANIFIESTO["isp_fs4_sobre_0"]
        soxr = cg.medir_completo(spec["ruta"])["true_peak_dbtp"]
        ref = itu.true_peak_desde_archivo(spec["ruta"], "cero")
        self.assertGreater(soxr, 2.0)
        self.assertGreater(ref, 2.0)


class TestBordesAbruptos(unittest.TestCase):
    """La sobreoscilación ante un escalón es real, no un artefacto nuestro."""

    def test_todos_los_metodos_sobrepasan_ante_un_escalon_interno(self):
        """Escalón DENTRO del archivo: no hay ambigüedad sobre qué hay fuera,
        así que si los cuatro métodos sobrepasan, es la señal, no el filtro."""
        ruta = _MANIFIESTO["dc_salto_interno_menos6"]["ruta"]
        sample_peak = -6.0
        medidas = {
            "soxr": cg.medir_completo(ruta)["true_peak_dbtp"],
            "itu": itu.true_peak_desde_archivo(ruta, "cero"),
            "fft": ec.tp_fft(ruta),
        }
        for nombre, valor in medidas.items():
            self.assertGreater(
                valor, sample_peak + 0.5,
                f"{nombre} no ve la sobreoscilación del escalón: {valor:.3f}")

    def test_soxr_e_itu_coinciden_en_el_escalon_interno(self):
        ruta = _MANIFIESTO["dc_salto_interno_menos6"]["ruta"]
        soxr = cg.medir_completo(ruta)["true_peak_dbtp"]
        ref = itu.true_peak_desde_archivo(ruta, "cero")
        self.assertAlmostEqual(soxr, ref, delta=TOL_DISCONTINUA,
                               msg=f"soxr {soxr:.3f} vs ITU {ref:.3f}")

    def test_en_regimen_estable_soxr_da_el_valor_analitico(self):
        """Descartando el asentamiento, la continua mide su sample peak."""
        ruta = _MANIFIESTO["dc_estable_menos6"]["ruta"]
        self.assertAlmostEqual(ec.tp_soxr(ruta, descartar_asentamiento=True),
                               -6.0, delta=0.05)

    def test_la_diferencia_en_el_borde_del_archivo_es_de_extension(self):
        """En el borde del ARCHIVO la discrepancia viene de qué asume cada
        implementación fuera, no de la calidad del filtro."""
        ruta = _MANIFIESTO["dc_bordes_menos6"]["ruta"]
        con_ceros = itu.true_peak_desde_archivo(ruta, "cero")
        extendido = itu.true_peak_desde_archivo(ruta, "extender")
        self.assertGreater(con_ceros - extendido, 0.5,
                           "asumir silencio fuera del archivo debe generar el escalón")
        self.assertAlmostEqual(extendido, -6.0, delta=0.05,
                               msg="extendiendo la señal no hay escalón: debe dar -6")


class TestCanales(unittest.TestCase):

    def test_mono_y_estereo(self):
        for nombre in ("wav24_mono", "wav24_pico_menos1"):
            ruta = _MANIFIESTO[nombre]["ruta"]
            soxr = cg.medir_completo(ruta)["true_peak_dbtp"]
            ref = itu.true_peak_desde_archivo(ruta, "cero")
            self.assertAlmostEqual(soxr, ref, delta=TOL_BANDA_COMPLETA, msg=nombre)

    def test_el_true_peak_no_depende_del_numero_de_canales(self):
        """Mono y su duplicado a estéreo tienen el mismo pico (a diferencia
        del LUFS, que sí suma canales)."""
        mono = cg.medir_completo(_MANIFIESTO["wav24_mono"]["ruta"])["true_peak_dbtp"]
        est = cg.medir_completo(_MANIFIESTO["wav24_pico_menos1"]["ruta"])["true_peak_dbtp"]
        self.assertAlmostEqual(mono, est, delta=0.01)

    def test_pico_en_un_solo_canal(self):
        """Con L recortado y R a -6, el true peak debe ser el de L en ambos."""
        ruta = _MANIFIESTO["wav24_clip_solo_L"]["ruta"]
        picos = itu.por_canal(sf.read(ruta, always_2d=True, dtype="float64")[0], "cero")
        self.assertGreater(picos[0], picos[1],
                           "el canal izquierdo es el que lleva el recorte")
        soxr = cg.medir_completo(ruta)["true_peak_dbtp"]
        ref = 20 * np.log10(max(picos))
        self.assertAlmostEqual(soxr, ref, delta=TOL_DISCONTINUA)

    def test_el_maximo_es_entre_canales_no_la_media(self):
        sr = 44100
        n = sr
        fuerte = np.full(n, 0.5)
        flojo = np.full(n, 0.01)
        picos = itu.por_canal(np.column_stack([fuerte, flojo]), "extender")
        self.assertAlmostEqual(20 * np.log10(max(picos)), -6.0, delta=0.1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
