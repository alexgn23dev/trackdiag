"""El formulario no puede diagnosticar por sí solo.

El fallo que se arregla (docs/feedback-jun-ago-2026.md §3.1): escribir "kick"
o "bajo" en `bloqueo_percibido` sumaba +2 en `enmascaramiento_bajo` y en
`exceso_lowend`, y con el umbral de diagnóstico en 2, las palabras del usuario
BASTABAN solas — un informe real salió con una única "evidencia": la frase del
propio usuario. Además el matching era por substring: "trabajo" disparaba
"bajo" y "subida" disparaba "sub".

Desde v0.5.94 el eco está capado a +1 (siempre hace falta al menos una señal
física del audio) y el matching es por palabra. Aquí se comprueba de las dos
formas: la unidad del helper y el motor entero corriendo sobre el mismo audio
con y sin eco en el formulario.
"""

import os
import sys
import tempfile
import unittest
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from engine.reglas import (  # noqa: E402
    UMBRAL_MINIMO_CONFIANZA,
    _menciona,
    evaluar_diagnosticos,
)

ECO = "no doy con el bajo y el kick, se come todo"
REGLAS_CON_ECO = ("enmascaramiento_bajo", "exceso_lowend")


class TestElMatchingEsPorPalabra(unittest.TestCase):
    def test_substrings_que_antes_disparaban(self):
        """Los tres falsos positivos del bug: trabajo/abajo ("bajo") y
        subida ("sub")."""
        self.assertFalse(_menciona("me cuesta mucho trabajo", ["bajo"]))
        self.assertFalse(_menciona("mira abajo a la izquierda", ["bajo"]))
        self.assertFalse(_menciona("la subida del break", ["sub"]))

    def test_las_menciones_reales_siguen_contando(self):
        self.assertTrue(_menciona("el bajo se come al kick", ["bajo"]))
        self.assertTrue(_menciona("el sub está descontrolado", ["sub"]))
        self.assertTrue(_menciona("me falta low end", ["low end"]))

    def test_los_prefijos_declarados_funcionan(self):
        """"enmasc-" es un prefijo a propósito: cubre las conjugaciones."""
        self.assertTrue(_menciona("está todo enmascarado", ["enmasc-"]))
        self.assertTrue(_menciona("el pad enmascara la voz", ["enmasc-"]))


class TestElEcoNoDiagnosticaSolo(unittest.TestCase):
    """El motor entero, dos veces sobre el MISMO audio: la única diferencia es
    lo que el usuario escribió. Las reglas de graves no pueden cruzar el umbral
    solo por eso."""

    @classmethod
    def setUpClass(cls):
        import soundfile as sf
        from engine.extractor import extraer_senales

        # Audio sin problema físico de graves: ruido de espectro plano con un
        # poco de estructura para que el extractor tenga algo que medir.
        sr = 22050
        t = np.arange(int(sr * 12)) / sr
        rng = np.random.default_rng(11)
        y = 0.25 * rng.standard_normal(len(t))
        y *= 0.4 + 0.6 * (np.sin(2 * np.pi * t / 3) > 0)   # bloques de energía
        y += 0.05 * np.sin(2 * np.pi * 440 * t)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, y.astype(np.float32), sr)
            cls.ruta = f.name
        cls.senales = extraer_senales(cls.ruta)

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.ruta)

    def _contexto(self, bloqueo):
        return {
            "genero": "techno", "fase": "casi_listo", "objetivo": "sellos",
            "experiencia": "2-5", "dificultad_habitual": "mezcla",
            "bloqueo_percibido": bloqueo,
        }

    def test_el_eco_suma_como_mucho_uno(self):
        sin_eco, _ = evaluar_diagnosticos(self.senales, self._contexto(""))
        con_eco, _ = evaluar_diagnosticos(self.senales, self._contexto(ECO))
        for regla in REGLAS_CON_ECO:
            delta = con_eco.get(regla, 0) - sin_eco.get(regla, 0)
            self.assertLessEqual(
                delta, 1,
                f"{regla}: el formulario sumó {delta} puntos — el cap es 1")

    def test_sin_senal_fisica_no_cruza_el_umbral(self):
        """En este audio no hay problema de graves. Con el eco más cargado
        posible, ninguna regla de graves puede alcanzar el umbral si sin eco
        estaba a cero: las palabras nunca bastan."""
        sin_eco, _ = evaluar_diagnosticos(self.senales, self._contexto(""))
        con_eco, _ = evaluar_diagnosticos(self.senales, self._contexto(ECO))
        for regla in REGLAS_CON_ECO:
            if sin_eco.get(regla, 0) <= 0:
                self.assertLess(
                    con_eco.get(regla, 0), UMBRAL_MINIMO_CONFIANZA,
                    f"{regla} cruzó el umbral solo con palabras del formulario")


class TestElCapEstaEscrito(unittest.TestCase):
    """Guards estáticos: que el cap no se pueda deshacer sin enterarse."""

    def setUp(self):
        self.src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "reglas.py"), encoding="utf-8").read()

    def test_no_queda_eco_de_dos_puntos_en_las_reglas_de_graves(self):
        self.assertNotIn('score += 2; razones.append("El usuario percibe problemas en graves")', self.src)
        i = self.src.index("palabras_masking")
        bloque = self.src[i:i + 700]
        self.assertIn("score += 1", bloque)
        self.assertNotIn("score += 2", bloque)

    def test_las_dos_reglas_usan_el_matching_por_palabra(self):
        self.assertGreaterEqual(self.src.count("_menciona(bloqueo,"), 2)
