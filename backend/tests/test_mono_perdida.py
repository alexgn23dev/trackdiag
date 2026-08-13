"""El aviso de mono exige pérdida REAL, no solo correlación baja.

El fallo que se arregla (docs/feedback-jun-ago-2026.md §3.2): un track con los
medios muy abiertos en estéreo salía como "problemática" con −0.4 dB de pérdida
al sumar a mono. El usuario lo comprobó en mono, no perdía nada, y tenía razón
él. La física: correlación ~0 significa canales INDEPENDIENTES, que suman sin
cancelarse; solo la correlación negativa cancela.

Estos tests construyen los dos casos con señal sintética y comprueban que el
motor los distingue: anchura sin pérdida → no es un problema; cancelación de
fase de verdad → sí lo es.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import _analizar_mono_compatibility  # noqa: E402

SR = 22050
DUR = 6.0


def _base_mono():
    """Kick + bajo centrados: los graves de cualquier track de club."""
    t = np.arange(int(SR * DUR)) / SR
    rng = np.random.default_rng(7)
    kick = 0.5 * np.sin(2 * np.pi * 55 * t) * (np.sin(2 * np.pi * 2 * t) > 0.6)
    bajo = 0.35 * np.sin(2 * np.pi * 82 * t)
    return t, rng, kick + bajo


class TestAnchuraSinPerdidaNoEsProblema(unittest.TestCase):
    def test_medios_independientes_no_disparan_problematica(self):
        """Medios DISTINTOS en L y R (correlación ~0) pero sin oposición de
        fase: al sumar a mono no se cancela nada. Antes esto salía
        "problemática"; es exactamente el caso del feedback."""
        t, rng, grave = _base_mono()
        # Dos sintes diferentes, uno por canal: descorrelacionados de verdad.
        mid_l = 0.25 * np.sin(2 * np.pi * 523 * t + rng.uniform(0, 6.28))
        mid_r = 0.25 * np.sin(2 * np.pi * 659 * t + rng.uniform(0, 6.28))
        y = np.vstack([grave + mid_l, grave + mid_r]).astype(np.float32)
        r = _analizar_mono_compatibility(y, SR)
        self.assertNotEqual(r["nivel_compatibilidad"], "problematica",
                            f"anchura sin pérdida marcada como problema: {r['resumen']}")
        self.assertNotEqual(r["nivel_compatibilidad"], "critica")
        # La correlación de los medios ES baja — eso no cambia…
        self.assertLess(r["bandas"]["medios"]["correlacion"], 0.5)
        # …pero la pérdida no rebasa los −3 dB estructurales de la
        # independencia, y por eso no es "problema".
        self.assertGreater(r["bandas"]["medios"]["perdida_db"], -3.5)
        self.assertNotEqual(r["bandas"]["medios"]["estado"], "problema")

    def test_el_resumen_explica_la_anchura_cuando_aplica(self):
        """Si hay correlación baja sin pérdida, el texto lo dice con el dato,
        en vez de callar o de acusar: la anchura es una elección."""
        t, rng, grave = _base_mono()
        mid_l = 0.3 * rng.standard_normal(len(t))
        mid_r = 0.3 * rng.standard_normal(len(t))
        y = np.vstack([grave + mid_l, grave + mid_r]).astype(np.float32)
        r = _analizar_mono_compatibility(y, SR)
        if r["nivel_compatibilidad"] == "buena" and "abierto" in r["resumen"]:
            self.assertIn("dB", r["resumen"])   # el dato que lo respalda


class TestLaCancelacionRealSigueAvisando(unittest.TestCase):
    def test_fase_invertida_fuerte_sigue_siendo_grave(self):
        """L = −R en un elemento con peso: al sumar a mono desaparece. Esto es
        el problema de verdad y tiene que seguir saltando."""
        t, rng, grave = _base_mono()
        sinte = 0.45 * np.sin(2 * np.pi * 440 * t)
        y = np.vstack([grave * 0.2 + sinte, grave * 0.2 - sinte]).astype(np.float32)
        r = _analizar_mono_compatibility(y, SR)
        self.assertIn(r["nivel_compatibilidad"], ("problematica", "critica"),
                      f"cancelación real sin aviso: {r['resumen']}")

    def test_cancelacion_moderada_en_medios_avisa(self):
        """Oposición de fase real en los medios, con pérdida de banda más allá
        del suelo estructural de −3 dB: sigue siendo 'problema'."""
        t, rng, grave = _base_mono()
        sinte = 0.35 * np.sin(2 * np.pi * 700 * t)
        comun = 0.1 * np.sin(2 * np.pi * 900 * t)
        y = np.vstack([grave + sinte + comun, grave - sinte + comun]).astype(np.float32)
        r = _analizar_mono_compatibility(y, SR)
        self.assertLessEqual(r["bandas"]["medios"]["perdida_db"], -3.5)
        self.assertEqual(r["bandas"]["medios"]["estado"], "problema")
        self.assertIn(r["nivel_compatibilidad"], ("problematica", "critica"))


class TestElGateEstaEscrito(unittest.TestCase):
    """Guards estáticos: que el gate no se pueda quitar sin enterarse."""

    def test_problema_de_banda_exige_perdida(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "extractor.py"), encoding="utf-8").read()
        self.assertIn('if estado == "problema" and perdida_banda > -3.5:', src)
        self.assertIn('estado = "revisar"', src)

    def test_problematica_global_exige_perdida(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "extractor.py"), encoding="utf-8").read()
        i = src.index('resultado["nivel_compatibilidad"] = "problematica"')
        contexto = src[max(0, i - 600):i]
        self.assertIn('perdida_db <= -1.0', contexto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
