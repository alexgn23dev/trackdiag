"""Qué mide realmente cada medidor de true peak.

Estos tests existen para contestar las dos preguntas que dejó abierta la
fase 2A y que bloqueaban la 2B (ver DISENO_FASE_2B.md, prioridad 0):

  1. ¿Por qué el FIR de la norma se descuelga en el fixture del recorte solo
     en L?
  2. ¿Qué pasa a sample rates altos?

La respuesta a las dos sale de tener por fin una referencia que no es otra
implementación con sus propios compromisos, sino la definición: la
reconstrucción sinc exacta. Los tests la verifican primero contra la teoría y
la usan después para acotar el error de cada candidato.

Conclusión que congelan estos tests, y que CONTRADICE el plan aprobado de la
fase 2B: sustituir soxr_hq_8x por el FIR de 12 taps de la norma empeoraría la
medición, no la mejoraría.
"""

import math
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import fixtures as fx                    # noqa: E402
from tests import itu_bs1770 as itu                 # noqa: E402
from tests import reconstruccion_exacta as ex       # noqa: E402

SR = 44100


def _db(v):
    return 20.0 * math.log10(max(float(v), 1e-12))


def _soxr(x, sr, factor):
    import librosa
    up = librosa.resample(np.asarray(x, dtype=np.float32), orig_sr=sr,
                          target_sr=sr * factor, res_type="soxr_hq")
    return _db(np.max(np.abs(up)))


def _itu(x, sr=SR):
    return _db(max(itu.por_canal(np.asarray(x)[:, None], "cero")))


def _banda(corte_hz, sr=SR, dur=3.0, pico_db=-1.0):
    """Material musical limitado en banda: lo que de verdad sale de un DAW."""
    from scipy.signal import butter, sosfiltfilt
    rng = np.random.default_rng(fx.SEED)
    x = fx._musical(sr, dur, rng)
    if corte_hz < sr / 2:
        sos = butter(8, corte_hz, btype="low", fs=sr, output="sos")
        x = sosfiltfilt(sos, x)
    return fx._escalar_a_sample_peak(x, pico_db)


class TestLaReferenciaEsDeFiar(unittest.TestCase):
    """Antes de juzgar a nadie con ella, hay que demostrar que es correcta."""

    def test_reproduce_el_valor_analitico(self):
        """Seno a fs/4 desfasado 45°: el true peak está exactamente
        20·log10(√2) por encima del sample peak. Lo dice la trigonometría,
        no una implementación."""
        x = fx._escalar_a_sample_peak(
            fx._seno(SR / 4.0, SR, 3.0, fase=np.pi / 4.0), -0.2)
        self.assertAlmostEqual(ex.pico_exacto(x), -0.2 + fx.ISP_FS4_DELTA_DB,
                               delta=0.002)

    def test_es_plana_en_frecuencia(self):
        """Un seno de amplitud 1 tiene pico 0 dB a cualquier frecuencia.
        La referencia lo devuelve; ningún filtro real lo hace."""
        resp = ex.respuesta_por_frecuencia(
            lambda x, sr: _db(np.max(np.abs(ex.recorte_util(
                ex.reconstruir(x, 8))))))
        for fila in resp:
            self.assertLess(abs(fila["error_db"]), 0.002,
                            f"{fila['hz']:.0f} Hz: {fila['error_db']:+.4f} dB")

    def test_converge(self):
        """Si el resultado dependiera del factor, no sería 'exacto'."""
        x = _banda(18000)
        base = ex.pico_exacto(x, factor=8)
        for factor in (16, 32):
            self.assertAlmostEqual(ex.pico_exacto(x, factor=factor), base,
                                   delta=0.002, msg=f"factor {factor}")

    def test_nunca_queda_por_debajo_del_sample_peak(self):
        """La reconstrucción pasa por las muestras: su máximo no puede ser
        menor que el mayor valor muestreado. Es la comprobación más barata
        de que un medidor no está mintiendo."""
        for corte in (8000, 16000, 20000):
            x = _banda(corte)
            self.assertGreaterEqual(ex.pico_exacto(x) + 1e-6,
                                    _db(np.max(np.abs(x))), f"corte {corte}")

    def test_por_bloques_da_lo_mismo_que_de_una_vez(self):
        x = _banda(18000, dur=6.0)
        self.assertAlmostEqual(ex.pico_exacto_por_bloques(x, factor=8),
                               ex.pico_exacto(x, factor=8), delta=0.002)


class TestElFirDeLaNormaNoEsLaVerdad(unittest.TestCase):
    """Pregunta abierta 1: por qué el FIR se descuelga con material recortado.

    No es un fallo de transcripción ni un caso raro: es su respuesta en
    frecuencia. 12 taps por fase no dan para más.
    """

    def test_tiene_rizado_en_la_banda_de_paso(self):
        """Lee de MÁS en frecuencias medias. Por eso puede sobreestimar."""
        resp = ex.respuesta_por_frecuencia(
            lambda x, sr: _db(np.max(np.abs(ex.recorte_util(
                itu._sobremuestrear_canal(x, "extender"))))),
            frecuencias=[5000, 10000])
        for fila in resp:
            self.assertGreater(fila["error_db"], 0.05,
                               f"{fila['hz']:.0f} Hz debería leer alto")

    def test_cae_cerca_de_nyquist(self):
        """Lee de MENOS arriba. Por eso subestima el material saturado, que
        es justo el que llena esa zona del espectro."""
        resp = ex.respuesta_por_frecuencia(
            lambda x, sr: _db(np.max(np.abs(ex.recorte_util(
                itu._sobremuestrear_canal(x, "extender"))))),
            frecuencias=[20000, 22000])
        self.assertLess(resp[0]["error_db"], -0.3)
        self.assertLess(resp[1]["error_db"], -0.6)

    def test_por_eso_falla_el_fixture_del_recorte(self):
        """El caso concreto que bloqueaba la fase 2B. Un recorte duro llena
        el espectro hasta Nyquist, y ahí el FIR ya no llega."""
        d = tempfile.mkdtemp(prefix="rec_fir_")
        man = fx.generar(d, solo=["wav24_clip_solo_L"])
        import soundfile as sf
        data, _ = sf.read(man["wav24_clip_solo_L"]["ruta"],
                          always_2d=True, dtype="float64")
        izq = data[:, 0]
        exacto = ex.pico_exacto(izq)
        self.assertLess(_itu(izq) - exacto, -0.5,
                        "el FIR debería quedarse muy corto en este material")
        self.assertGreater(_soxr(izq, SR, 4) - exacto, -0.4,
                           "soxr se queda corto, pero mucho menos")


class TestSoxrEsMejorQueElFir(unittest.TestCase):
    """La conclusión que invierte el plan de la fase 2B.

    Se compara sobre material realista — limitado en banda, como cualquier
    bounce — que es donde la precisión decide de verdad: la frontera entre
    'margen de streaming' y 'por encima del techo' está en 0 dBTP.
    """

    CORTES = (8000, 12000, 16000, 18000, 19000, 20000)

    def _errores(self, medidor):
        return [medidor(_banda(c), SR) - ex.pico_exacto(_banda(c))
                for c in self.CORTES]

    def test_en_material_realista_soxr_gana(self):
        peor_itu = max(abs(e) for e in self._errores(lambda x, sr: _itu(x, sr)))
        peor_soxr = max(abs(e) for e in
                        self._errores(lambda x, sr: _soxr(x, sr, 4)))
        self.assertLess(peor_soxr, 0.15)
        self.assertLess(peor_itu, 0.15)
        # Los dos son aceptables a 4x; el FIR no mejora con nada.
        self.assertGreater(peor_itu, 0.05,
                           "el rizado del FIR debería verse incluso aquí")

    def test_con_energia_en_nyquist_el_fir_es_mucho_peor(self):
        d = tempfile.mkdtemp(prefix="rec_cmp_")
        casos = ["wav24_pico_menos1", "wav24_clip_solo_L",
                 "wav24_clipping_evidente"]
        man = fx.generar(d, solo=casos)
        import soundfile as sf
        peor_itu = peor_soxr = 0.0
        for nombre in casos:
            data, _ = sf.read(man[nombre]["ruta"], always_2d=True, dtype="float64")
            x = data[:, 0]
            ref = ex.pico_exacto(x)
            peor_itu = max(peor_itu, abs(_itu(x) - ref))
            peor_soxr = max(peor_soxr, abs(_soxr(x, SR, 4) - ref))
        self.assertGreater(peor_itu, 0.6, "el FIR se descuelga")
        self.assertLess(peor_soxr, 0.4)
        self.assertLess(peor_soxr, peor_itu,
                        "cambiar a el FIR empeoraría la medición")


class TestLaRejillaDe4xSeQuedaCorta(unittest.TestCase):
    """El hallazgo accionable: parte del error de producción NO es del filtro,
    es de resolución. 4x da cuatro puntos por muestra y el máximo cae entre
    ellos. Se arregla sobremuestreando más, sin cambiar de filtro.
    """

    def test_a_8x_el_error_practicamente_desaparece(self):
        peor4 = peor8 = 0.0
        for corte in (12000, 16000, 18000):
            x = _banda(corte)
            ref = ex.pico_exacto(x)
            peor4 = max(peor4, abs(_soxr(x, SR, 4) - ref))
            peor8 = max(peor8, abs(_soxr(x, SR, 8) - ref))
        self.assertGreater(peor4, 0.05, "a 4x hay un error medible")
        self.assertLess(peor8, 0.02, "a 8x deja de haberlo")

    def test_mas_de_8x_ya_no_aporta(self):
        x = _banda(16000)
        self.assertAlmostEqual(_soxr(x, SR, 8), _soxr(x, SR, 16), delta=0.01)

    def test_con_energia_en_nyquist_subir_el_factor_no_arregla_nada(self):
        """Ahí el error es del filtro, no de la rejilla: soxr borra lo que
        hay por encima de ~20 kHz y eso no lo recupera ninguna resolución."""
        d = tempfile.mkdtemp(prefix="rec_rej_")
        man = fx.generar(d, solo=["wav24_clipping_evidente"])
        import soundfile as sf
        data, _ = sf.read(man["wav24_clipping_evidente"]["ruta"],
                          always_2d=True, dtype="float64")
        x = data[:, 0]
        self.assertAlmostEqual(_soxr(x, SR, 4), _soxr(x, SR, 16), delta=0.01)


class TestSampleRatesAltos(unittest.TestCase):
    """Pregunta abierta 2. A 88,2 kHz o más el problema desaparece solo: hay
    tantas muestras que apenas queda pico entre ellas."""

    def test_el_pico_entre_muestras_se_hace_despreciable(self):
        for sr in (88200, 96000):
            x = _banda(18000, sr=sr)
            margen = ex.pico_exacto(x) - _db(np.max(np.abs(x)))
            self.assertLess(margen, 0.05,
                            f"a {sr} Hz apenas debería haber pico entre muestras")

    def test_los_dos_medidores_coinciden_a_rates_altos(self):
        for sr in (88200, 96000):
            x = _banda(18000, sr=sr)
            ref = ex.pico_exacto(x)
            self.assertAlmostEqual(_soxr(x, sr, 4), ref, delta=0.05, msg=str(sr))
            self.assertAlmostEqual(_itu(x, sr), ref, delta=0.05, msg=str(sr))

    def test_el_fixture_05_es_patologico_no_representativo(self):
        """Un tono a exactamente fs/4 de 96 kHz son 24 kHz: por encima de lo
        audible y de lo que produce cualquier instrumento. Que las
        implementaciones discrepen ahí no dice nada sobre música real."""
        x = fx._escalar_a_sample_peak(
            fx._seno(96000 / 4.0, 96000, 1.0, fase=np.pi / 4.0), -0.2)
        self.assertAlmostEqual(ex.pico_exacto(x), -0.2 + fx.ISP_FS4_DELTA_DB,
                               delta=0.01)
        # El material realista al mismo rate no tiene nada de eso
        self.assertLess(ex.pico_exacto(_banda(18000, sr=96000))
                        - _db(np.max(np.abs(_banda(18000, sr=96000)))), 0.05)


class TestElFactorDeProduccion(unittest.TestCase):
    """Por qué 8x y no otro. v0.5.72."""

    def test_produccion_sobremuestrea_8x(self):
        from engine.extractor import OVERSAMPLING_PICOS
        self.assertEqual(OVERSAMPLING_PICOS, 8)

    def test_la_version_del_algoritmo_nombra_el_factor(self):
        """Si alguien cambia el factor sin tocar la versión, dos análisis
        distintos quedarían marcados como medidos igual."""
        from engine.extractor import OVERSAMPLING_PICOS
        from engine.versiones import PEAK_ALGORITHM_VERSION
        self.assertIn(f"{OVERSAMPLING_PICOS}x", PEAK_ALGORITHM_VERSION)

    def test_8x_es_donde_el_error_de_rejilla_deja_de_verse(self):
        peores = {}
        for factor in (4, 8, 16):
            peores[factor] = max(
                abs(_soxr(_banda(c), SR, factor) - ex.pico_exacto(_banda(c)))
                for c in (12000, 16000, 18000))
        self.assertGreater(peores[4], 0.05, "a 4x el error es visible")
        self.assertLess(peores[8], 0.02, "a 8x ya no")
        # Y 16x no compra nada más, mientras que cuesta el doble.
        self.assertLess(abs(peores[16] - peores[8]), 0.02)

    def test_en_el_borde_del_archivo_ningun_factor_converge(self):
        """El aviso importante, para que nadie lea el golden como una
        regresión: cuando el máximo cae en el borde, el valor depende de qué
        se asuma FUERA del archivo, y salta con el factor sin tendencia.
        Un escalón dentro del archivo sí es estable."""
        d = tempfile.mkdtemp(prefix="rec_borde_")
        man = fx.generar(d, solo=["dc_estable_menos6", "dc_salto_interno_menos6"])
        import soundfile as sf

        def _valores(nombre):
            data, sr = sf.read(man[nombre]["ruta"], always_2d=True, dtype="float64")
            return [_soxr(data[:, 0], sr, f) for f in (4, 8, 16, 24)]

        borde = _valores("dc_estable_menos6")
        self.assertGreater(max(borde) - min(borde), 0.2,
                           "en el borde el valor debería saltar con el factor")
        dentro = _valores("dc_salto_interno_menos6")
        self.assertLess(max(dentro) - min(dentro), 0.02,
                        "dentro del archivo debería ser estable")


class TestElMedidorDeProduccionSigueSiendoElBueno(unittest.TestCase):
    """Cierre: el algoritmo que hay desplegado no es el problema."""

    def test_produccion_usa_soxr_no_el_fir(self):
        from engine.versiones import PEAK_ALGORITHM_VERSION
        self.assertIn("soxr", PEAK_ALGORITHM_VERSION)

    def test_el_guardarraíl_del_sample_peak_rescata_el_caso_del_impulso(self):
        """Una sola muestra a fondo de escala tiene energía hasta Nyquist;
        soxr la suaviza y leería por debajo del propio sample peak. El
        `max(tp, sp)` de extractor.py lo impide."""
        d = tempfile.mkdtemp(prefix="rec_imp_")
        man = fx.generar(d, solo=["wav24_clip_una_muestra"])
        import soundfile as sf
        data, _ = sf.read(man["wav24_clip_una_muestra"]["ruta"],
                          always_2d=True, dtype="float64")
        x = data[:, 0]
        sp = _db(np.max(np.abs(x)))
        self.assertLess(_soxr(x, SR, 4), sp - 0.2,
                        "sin guardarraíl soxr leería por debajo del sample peak")
        from engine.extractor import extraer_senales
        lo = extraer_senales(man["wav24_clip_una_muestra"]["ruta"],
                             omitir_armonia=True)["loudness"]
        self.assertGreaterEqual(lo["true_peak_dbtp"] + 1e-6,
                                lo["sample_peak_dbfs"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
