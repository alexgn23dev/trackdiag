"""El BPM que damos tiene que ser el BPM real, no el bin del tempograma.

El fallo (ago-2026, reportado por un usuario): `librosa.beat.beat_track`
estima el tempo sobre bins DISCRETOS y a 22 050 Hz esos bins caen en 112.3,
117.5, 123.0, 129.2, 136.0, 143.6, 152.0, 161.5, 172.3… Medido sobre
producción: **el 95 % de los BPM que dábamos caían en esa rejilla y ninguno
en un BPM de productor**. El valor más repetido era 129 — el 40 % de los
análisis — y nadie produce a 129: es el bin donde caen 128 y 130.

Para quien trabaja en un DAW y sabe que su track va a 128, leer "129 BPM" es
motivo suficiente para dejar de fiarse de todo lo demás. Es el mismo tipo de
daño que el LUFS que no cuadraba con su medidor.

El arreglo no toca la detección de beats, solo la medida del periodo: se
ajusta una recta a los tiempos de los beats que `beat_track` ya encontró y la
pendiente da el tempo sin cuantizar. Con tres guardas, porque en el 58 % de
los tracks reales el ajuste NO mejora nada y ahí no se toca (ver
`_refinar_tempo`).
"""

import os
import sys
import tempfile
import unittest
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from engine.extractor import _refinar_tempo, extraer_senales  # noqa: E402

SR = 22050


def _loop(bpm, dur=60):
    """4x4 de club: kick a negras, hat a contratiempo, bajo a corcheas."""
    n = int(SR * dur)
    y = np.zeros(n)
    spb = 60.0 / bpm
    tk = np.arange(int(SR * 0.12)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(np.linspace(120, 45, len(tk))) / SR) * np.exp(-tk * 26)
    largo_h = int(SR * 0.05)
    h = (np.random.default_rng(1).standard_normal(largo_h)
         * np.exp(-np.arange(largo_h) / SR * 90) * 0.25)
    for i in range(int(dur / spb)):
        p = int(i * spb * SR)
        if p + len(kick) < n:
            y[p:p + len(kick)] += kick * 0.9
        ph = int((i + 0.5) * spb * SR)
        if ph + len(h) < n:
            y[ph:ph + len(h)] += h
    tt = np.arange(n) / SR
    y += 0.18 * np.sin(2 * np.pi * 55 * tt) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * tt / spb * 2)))
    return (y / np.max(np.abs(y)) * 0.7).astype(np.float32)


def _bpm_de(bpm_real, **kw):
    import soundfile as sf
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, _loop(bpm_real), SR)
        ruta = f.name
    try:
        return extraer_senales(ruta, omitir_armonia=True, **kw)
    finally:
        os.unlink(ruta)


class TestElBpmEsElReal(unittest.TestCase):
    """Con tempo constante y pulso claro —o sea, electrónica de club— el BPM
    que publicamos tiene que ser exacto. Antes de este arreglo, 8 de estos 13
    salían mal (hasta 3.6 BPM de error)."""

    TEMPOS = [120, 124, 125, 128, 130, 132, 135, 138, 140, 145, 150, 160, 174]

    def test_todos_exactos(self):
        fallos = []
        for bpm in self.TEMPOS:
            s = _bpm_de(bpm)
            if s["bpm"] != bpm:
                fallos.append((bpm, s["bpm"]))
        self.assertEqual(fallos, [], f"BPM mal detectados (real, dado): {fallos}")

    def test_128_y_130_dejan_de_ser_el_mismo_numero(self):
        """El caso concreto que más daño hacía: los dos tempos más comunes del
        género caían en el mismo bin (129) y salían idénticos."""
        self.assertNotEqual(_bpm_de(128)["bpm"], _bpm_de(130)["bpm"])
        self.assertEqual(_bpm_de(128)["bpm"], 128)
        self.assertEqual(_bpm_de(130)["bpm"], 130)

    def test_se_marca_que_viene_del_refinado(self):
        """Para poder medir en producción cuánto se aplica."""
        self.assertTrue(_bpm_de(128)["tempo_refinado"])


class TestLasGuardasProtegen(unittest.TestCase):
    """El refinado solo sustituye al valor bruto cuando puede demostrarlo."""

    def test_sin_beats_suficientes_no_se_toca(self):
        for frames in (None, np.array([]), np.arange(10)):
            t, ref = _refinar_tempo(128.0, frames, SR)
            self.assertEqual(t, 128.0)
            self.assertFalse(ref)

    def test_con_tempo_inestable_no_se_toca(self):
        """Beats muy irregulares → residuo alto → se conserva el bruto. En
        música real esto es el 58 % de los casos, y ahí el ajuste describe un
        track con tempo variable, no un tempo mejor medido."""
        rng = np.random.default_rng(3)
        base = np.arange(0, 120, 0.47)                      # ~128 BPM
        ruido = base + rng.normal(0, 0.06, len(base))       # ±60 ms: inestable
        frames = np.round(ruido * SR / 512).astype(int)
        t, ref = _refinar_tempo(128.0, frames, SR)
        self.assertFalse(ref, "se aceptó un ajuste sobre beats inestables")
        self.assertEqual(t, 128.0)

    def test_nunca_cambia_de_nivel_metrico(self):
        """Si el ajuste propusiera la mitad o el doble, algo ha ido mal: esto
        corrige cuantización (máximo medido 2.2 %), no re-interpreta el pulso."""
        # beats a ~64 BPM perfectos, pero el bruto dice 128: el refinado
        # propondría la mitad → se descarta.
        tiempos = np.arange(0, 120, 60.0 / 64)
        frames = np.round(tiempos * SR / 512).astype(int)
        t, ref = _refinar_tempo(128.0, frames, SR)
        self.assertFalse(ref)
        self.assertEqual(t, 128.0)

    def test_el_bpm_manual_manda_y_no_se_refina(self):
        s = _bpm_de(128, bpm_manual=140)
        self.assertEqual(s["bpm"], 140)
        self.assertEqual(s["tempo_fuente"], "manual")
        self.assertFalse(s["tempo_refinado"])


class TestElPorqueEstaEscrito(unittest.TestCase):
    def test_los_numeros_de_la_medicion_estan_junto_al_codigo(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "extractor.py"), encoding="utf-8").read()
        self.assertIn("129", src)        # el bin que salía en el 40 % de los análisis
        self.assertIn("95 %", src)       # cuántos caían en la rejilla
        self.assertIn("0.015", src)      # el filtro que decide


if __name__ == "__main__":
    unittest.main(verbosity=2)
