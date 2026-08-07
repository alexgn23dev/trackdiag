"""Taxonomía de picos — fase 2A.

Lo que se corrige aquí es semántico, no numérico: los mismos números de
siempre, pero dejando de afirmar cosas que no se pueden demostrar con ellos.

El test más importante de este fichero es `TestNoSobreafirma`: comprueba que
el copy no dice "clipea" sobre un over de true peak, que es exactamente el
error que arrastraba el producto.
"""

import os
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import _analizar_formato, _clasificar_picos  # noqa: E402
from tests import capturar_golden as cg  # noqa: E402
from tests import fixtures as fx  # noqa: E402

_DIR = tempfile.mkdtemp(prefix="mentotrack_2a_")
_MANIFIESTO = None


def setUpModule():
    global _MANIFIESTO
    _MANIFIESTO = fx.generar(_DIR)


def clasificar(nombre):
    ruta = _MANIFIESTO[nombre]["ruta"]
    return _clasificar_picos(cg.medir_completo(ruta), _analizar_formato(ruta))


class TestFloat(unittest.TestCase):
    """A. Un float con overs NO es clipping."""

    def test_categoria(self):
        self.assertEqual(clasificar("wav32f_sobre_0")["categoria_picos"],
                         "overs_float_recuperables")

    def test_el_texto_dice_lo_que_debe(self):
        aviso = clasificar("wav32f_sobre_0")["aviso_picos"]
        self.assertIn("por encima de 0", aviso)
        self.assertIn("coma flotante", aviso)
        self.assertIn("no se ha recortado", aviso)
        self.assertIn("antes de exportar a PCM", aviso)
        self.assertIn("no se puede afirmar", aviso)

    def test_el_texto_no_afirma_dano(self):
        aviso = clasificar("wav32f_sobre_0")["aviso_picos"].lower()
        for prohibido in ("clipea", "clipping", "distorsión audible", "dañado el máster"):
            self.assertNotIn(prohibido, aviso, f"el copy de float no puede decir «{prohibido}»")

    def test_un_float_sin_overs_no_entra_en_esta_categoria(self):
        c = clasificar("wav64d_pico_menos1")   # DOUBLE con pico a -1 dBFS
        self.assertNotEqual(c["categoria_picos"], "overs_float_recuperables")

    def test_un_pcm_con_overs_de_true_peak_no_entra_en_esta_categoria(self):
        c = clasificar("wav24_muestras_0dbfs")
        self.assertEqual(c["categoria_picos"], "true_peak_over")


class TestTruePeakOver(unittest.TestCase):
    """B. Pico reconstruido sobre 0 sin evidencia de muestras recortadas."""

    def test_categoria(self):
        for nombre in ("wav24_pico_menos1", "wav24_clipping_evidente",
                       "isp_fs4_sobre_0"):
            self.assertEqual(clasificar(nombre)["categoria_picos"], "true_peak_over", nombre)

    def test_el_texto_dice_lo_que_debe(self):
        aviso = clasificar("wav24_pico_menos1")["aviso_picos"]
        self.assertIn("reconstruir la onda entre muestras", aviso)
        self.assertIn("no demuestra", aviso)
        self.assertIn("riesgo de distorsión", aviso)
        self.assertIn("ceiling", aviso)
        self.assertIn("vuelve a analizar", aviso.lower() + " " + aviso)

    def test_reporta_el_sample_peak_como_contraste(self):
        """Decir «el sample peak está en -1,0» es lo que sostiene el «no
        demuestra que esté recortado»."""
        self.assertIn("sample peak", clasificar("wav24_pico_menos1")["aviso_picos"])


class TestMargenStreaming(unittest.TestCase):
    """C. Entre -1 y 0: recomendación de margen, no error."""

    def test_categoria(self):
        for nombre in ("wav24_96000_pico_menos1", "wav24_crest_bajo", "mp3_320"):
            self.assertEqual(clasificar(nombre)["categoria_picos"], "margen_streaming", nombre)

    def test_es_informativo_no_alarma(self):
        self.assertEqual(clasificar("wav24_crest_bajo")["severidad_picos"], "info")

    def test_el_texto_deja_claro_que_no_es_un_fallo(self):
        aviso = clasificar("wav24_crest_bajo")["aviso_picos"]
        self.assertIn("No es un error", aviso)
        self.assertIn("recomendación de margen", aviso)

    def test_no_afirma_ausencia_de_clipping(self):
        """Que el techo esté por debajo de 0 no demuestra que no haya recorte
        dentro de la señal. Afirmarlo sería el mismo error, del revés."""
        aviso = clasificar("wav24_clip_una_muestra")["aviso_picos"].lower()
        self.assertNotIn("no hay clipping", aviso)
        self.assertNotIn("sin clipping", aviso)


class TestLossy(unittest.TestCase):
    """D. En formatos con pérdida, parte del pico puede ser del códec."""

    def test_mp3_lleva_la_nota(self):
        nota = clasificar("mp3_320")["nota_lossy_picos"]
        self.assertTrue(nota)
        self.assertIn("codificación", nota)
        self.assertIn("WAV", nota)

    def test_un_wav_no_lleva_la_nota(self):
        self.assertEqual(clasificar("wav24_pico_menos1")["nota_lossy_picos"], "")


class TestNoSobreafirma(unittest.TestCase):
    """Ningún texto de la taxonomía nueva puede afirmar clipping."""

    PROHIBIDAS = ["clipea digitalmente", "el máster clipea", "clipping digital",
                  "habrá distorsión audible"]

    def test_ningun_fixture_produce_una_afirmacion_de_clipping(self):
        for nombre in _MANIFIESTO:
            if nombre == "wav24_silencio":
                continue
            c = clasificar(nombre)
            texto = f"{c['titulo_picos']} {c['aviso_picos']}".lower()
            for frase in self.PROHIBIDAS:
                self.assertNotIn(frase, texto,
                                 f"{nombre} afirma «{frase}» sin haber contado muestras")

    # Afirmaciones sobre la PRESENCIA o la AUSENCIA de recorte. Ninguna se
    # puede sostener con el true peak solo: para eso hay que contar muestras
    # a fondo de escala, que es fase 2B. Nombrar la herramienta ("un clipper")
    # sí está permitido: es vocabulario, no una afirmación sobre el archivo.
    AFIRMACIONES = [
        "hay clipping", "no hay clipping", "sin clipping", "está clipado",
        "tu track clipea", "el archivo clipea", "clipea digitalmente",
        "está recortado", "no está recortado", "hay recorte", "no hay recorte",
    ]

    def test_no_afirma_ni_niega_el_recorte(self):
        for nombre in _MANIFIESTO:
            if nombre == "wav24_silencio":
                continue
            aviso = clasificar(nombre)["aviso_picos"].lower()
            for frase in self.AFIRMACIONES:
                self.assertNotIn(
                    frase, aviso,
                    f"{nombre}: «{frase}» no se puede sostener con el true peak solo")


class TestCoherenciaConLoMostrado(unittest.TestCase):
    def test_la_categoria_se_decide_sobre_el_valor_que_se_ensena(self):
        """Un track a -0,9997 dBTP se muestra como -1,0: no puede decirse a la
        vez que está por encima de -1."""
        sr = 44100
        x = fx._seno(1000.0, sr, 2.0)
        x = x * (10 ** (-0.9997 / 20)) / float(np.max(np.abs(x)))
        ruta = os.path.join(_DIR, "borde_m1.wav")
        sf.write(ruta, np.column_stack([x, x]), sr, subtype="FLOAT")
        lo = cg.medir_completo(ruta)
        c = _clasificar_picos(lo, _analizar_formato(ruta))
        mostrado = round(lo["true_peak_dbtp"], 1)
        if mostrado <= -1.0:
            self.assertEqual(c["categoria_picos"], "ok")
        self.assertIn(f"{mostrado:+.1f}", c["aviso_picos"])

    def test_no_se_muestra_menos_cero(self):
        for nombre in _MANIFIESTO:
            if nombre == "wav24_silencio":
                continue
            self.assertNotIn("-0.0", clasificar(nombre)["aviso_picos"],
                             f"{nombre}: «-0.0» es un artefacto de formato")


class TestCompatibilidad(unittest.TestCase):
    """Los campos antiguos siguen intactos: parsers e histórico no se rompen."""

    def test_nivel_true_peak_sigue_calculandose(self):
        for nombre in ("wav24_pico_menos1", "wav32f_sobre_0", "mp3_320"):
            lo = cg.medir_completo(_MANIFIESTO[nombre]["ruta"])
            self.assertIn(lo["nivel_true_peak"], ("ok", "streaming", "clipping"), nombre)
            self.assertTrue(lo["aviso_true_peak"] or lo["nivel_true_peak"] == "ok", nombre)

    def test_las_fronteras_numericas_no_se_mueven(self):
        """La única reclasificación permitida en 2A es la del float. En todo
        lo demás, categoría nueva y nivel antiguo tienen que corresponderse."""
        equivalencia = {"ok": "ok", "margen_streaming": "streaming",
                        "true_peak_over": "clipping"}
        for nombre in _MANIFIESTO:
            if nombre in ("wav24_silencio",) or nombre.startswith("dc_"):
                continue
            ruta = _MANIFIESTO[nombre]["ruta"]
            lo = cg.medir_completo(ruta)
            c = _clasificar_picos(lo, _analizar_formato(ruta))
            if c["categoria_picos"] == "overs_float_recuperables":
                self.assertEqual(lo["nivel_true_peak"], "clipping",
                                 f"{nombre}: es justo el caso que 2A reclasifica")
                continue
            self.assertEqual(equivalencia[c["categoria_picos"]], lo["nivel_true_peak"],
                             f"{nombre}: la frontera se ha movido sin querer")

    def test_el_frontend_conserva_el_campo_antiguo(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
            html = f.read()
        bloque = html[html.find("const senales = {"):]
        bloque = bloque[:bloque.find("};")]
        self.assertIn("nivel_true_peak:", bloque, "el campo antiguo debe seguir guardándose")
        self.assertIn("categoria_picos:", bloque)

    def test_el_frontend_ya_no_pinta_clipping_digital(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("True peak: clipping digital", html)
        self.assertIn("aviso_picos", html)

    def test_un_analisis_antiguo_sigue_mostrando_algo(self):
        """Sin `aviso_picos`, la interfaz cae al texto antiguo en vez de
        quedarse en blanco."""
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn(") : d.loudness.aviso_true_peak ? (", html)


class TestFueraDeAlcance(unittest.TestCase):
    """2A no toca nada más. Si esto falla, se ha colado un cambio."""

    def test_reglas_no_conoce_la_taxonomia(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fichero in ("engine/reglas.py", "engine/contextualizador.py",
                        "engine/templates.py"):
            with open(os.path.join(raiz, fichero), encoding="utf-8") as f:
                contenido = f.read()
            for clave in ("categoria_picos", "true_peak_over",
                          "overs_float_recuperables", "true_peak"):
                self.assertNotIn(clave, contenido, f"{fichero} usa {clave}")

    def test_el_checklist_de_sello_no_cambia(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
            html = f.read()
        ini = html.find("// Item 1: Balance grave en rango")
        bloque = html[ini:html.find("checklistSummary", ini)]
        for clave in ("categoria_picos", "true_peak", "sample_peak"):
            self.assertNotIn(clave, bloque,
                             "el checklist de sello está fuera del alcance de 2A")


if __name__ == "__main__":
    unittest.main(verbosity=2)
