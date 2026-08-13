"""`enmascaramiento_bajo`: solo puntúa lo que discrimina.

Calibración de ago-2026 (docs/calibracion-enmascaramiento.md). El bonus por
`diff_sub_low > 4` se retiró porque disparaba en el 38.8 % de la música
publicada y el 37.5 % de los tracks de usuario — ratio 0.97x, ninguna
capacidad de distinguir. Era la vía nº 1 por la que discos ya editados
alcanzaban el umbral de esta regla.

Lo que aquí se protege NO es "el sub no importa", sino la regla de la casa
aplicada al motor: **una señal que se dispara igual en música publicada que en
la de usuario no es evidencia de defecto**, y no puede sumar puntos de
diagnóstico. Si alguien la reintroduce con otro corte, que sea con una medida
que discrimine — y con los números delante.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.reglas import UMBRAL_MINIMO_CONFIANZA, evaluar_diagnosticos  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_BASE = None


def _senales_base():
    """Señales REALES de un audio sintético neutro.

    Construir el dict a mano es frágil (las reglas leen decenas de claves).
    Se extraen de verdad una vez y luego cada test sobrescribe solo el campo
    que está probando.
    """
    global _BASE
    if _BASE is None:
        import tempfile
        import warnings
        import numpy as np
        import soundfile as sf
        warnings.filterwarnings("ignore")
        from engine.extractor import extraer_senales
        sr = 22050
        t = np.arange(int(sr * 20)) / sr
        rng = np.random.default_rng(5)
        y = 0.22 * rng.standard_normal(len(t))
        y *= 0.35 + 0.65 * (np.sin(2 * np.pi * t / 4) > 0)     # bloques
        y += 0.18 * np.sin(2 * np.pi * 110 * t) + 0.06 * np.sin(2 * np.pi * 700 * t)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, y.astype(np.float32), sr)
            ruta = f.name
        try:
            _BASE = extraer_senales(ruta, omitir_armonia=True)
        finally:
            os.unlink(ruta)
    import copy
    return copy.deepcopy(_BASE)


def _senales(bandas=None, **over):
    """Base real con las bandas y señales que pida el test."""
    s = _senales_base()
    if bandas:
        s["espectro_bandas"] = dict(bandas)
    s.update(over)
    return s


CONTEXTO = {"genero": "techno", "fase": "casi_listo", "objetivo": "sellos",
            "experiencia": "2-5", "dificultad_habitual": "mezcla",
            "bloqueo_percibido": ""}


def _score(senales):
    scores, _ = evaluar_diagnosticos(senales, CONTEXTO)
    return scores.get("enmascaramiento_bajo", 0)


class TestElSubNoPuntua(unittest.TestCase):
    def test_un_sub_alto_por_si_solo_no_suma(self):
        """Antes: +1. Ahora: nada — se dispara igual en música publicada."""
        neutro = _score(_senales(diff_sub_low=0.0))
        con_sub = _score(_senales(diff_sub_low=9.0))
        self.assertEqual(con_sub, neutro,
                         "el sub volvió a puntuar en enmascaramiento_bajo")

    def test_el_sub_no_completa_el_umbral_con_una_senal_floja(self):
        """La combinación que más falsos positivos daba: espectral+1 (la banda
        de graves 9 dB sobre los low-mid, dentro de lo normal en lo publicado)
        más el bonus del sub. Sumaban 2 = umbral. Ya no."""
        s = _senales(
            bandas={"sub": -31.0, "graves": -40.0, "low_mid": -49.0,
                             "mid": -52.0, "presencia": -58.0, "air": -64.0},
            diff_sub_low=9.0,
        )
        self.assertLess(_score(s), UMBRAL_MINIMO_CONFIANZA,
                        "dos señales flojas siguen apilándose hasta el umbral")

    def test_la_razon_del_rumble_ya_no_se_emite(self):
        _, detalles = evaluar_diagnosticos(
            _senales(diff_sub_low=9.0), CONTEXTO)
        razones = " ".join(detalles.get("enmascaramiento_bajo", []))
        self.assertNotIn("rumble", razones)


class TestLoQueSiDiscriminaSigueEnPie(unittest.TestCase):
    """El umbral espectral NO se toca: medido, es el mejor componente de la
    regla (2.35x). La calibración solo retiró lo que no distinguía."""

    def test_la_diferencia_espectral_fuerte_sigue_diagnosticando(self):
        s = _senales(bandas={"sub": -40.0, "graves": -34.0, "low_mid": -48.0,
                                      "mid": -52.0, "presencia": -58.0, "air": -64.0})
        self.assertGreaterEqual(_score(s), UMBRAL_MINIMO_CONFIANZA,
                                "14 dB de diferencia debe seguir siendo diagnóstico")

    def test_el_corte_de_12_db_sigue_donde_estaba(self):
        src = open(os.path.join(RAIZ, "engine", "reglas.py"), encoding="utf-8").read()
        i = src.index("scores[\"enmascaramiento_bajo\"]")
        bloque = src[max(0, i - 6000):i]
        self.assertIn("diff_graves_lowmid > 12", bloque)
        self.assertIn("diff_graves_lowmid > 8", bloque)

    def test_la_densidad_sigue_corroborando(self):
        """densidad baja + graves 11 dB sobre los low-mid: 1+1 = umbral. Es el
        segundo mejor componente (2.06x) y se queda."""
        s = _senales(
            bandas={"sub": -40.0, "graves": -37.0, "low_mid": -48.0,
                             "mid": -52.0, "presencia": -58.0, "air": -64.0},
            densidad_global="baja", densidad_espectral=0.01,
        )
        self.assertGreaterEqual(_score(s), UMBRAL_MINIMO_CONFIANZA)


class TestLaDecisionEstaDocumentada(unittest.TestCase):
    def test_el_porque_esta_junto_al_codigo(self):
        src = open(os.path.join(RAIZ, "engine", "reglas.py"), encoding="utf-8").read()
        self.assertIn("0.97x", src, "el número que justifica la retirada")
        self.assertIn("docs/calibracion-enmascaramiento.md", src)

    def test_existe_la_nota_de_calibracion(self):
        """Solo en el repo: la imagen de producción copia backend/ y frontend/,
        no docs/, así que allí este test se salta. El guard que de verdad
        importa —los números junto al código— sí corre en los dos sitios."""
        doc = os.path.join(os.path.dirname(RAIZ), "docs", "calibracion-enmascaramiento.md")
        if not os.path.exists(doc):
            self.skipTest("docs/ no viaja en la imagen de producción")
        texto = open(doc, encoding="utf-8").read()
        # Las dos caras: la hipótesis refutada y la causa real.
        self.assertIn("2.35x", texto)   # el umbral espectral SÍ discrimina
        self.assertIn("0.97x", texto)   # el sub no
        self.assertIn("322", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
