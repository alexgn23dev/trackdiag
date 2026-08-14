"""Tempo no detectable.

Antes, `beat_track` devolvía 0 con material sin pulso y la línea siguiente
dividía entre el tempo: ZeroDivisionError → HTTP 500. Un drone, un pad
sostenido o una toma ambiental rompían el análisis.

La corrección NO es poner 120 por defecto. Publicar un tempo inventado es
peor que no publicar ninguno: el usuario vería "120 BPM detectados" sobre un
archivo del que no se ha medido nada.
"""

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.diagnostico import generar_diagnostico  # noqa: E402
from engine.extractor import extraer_senales  # noqa: E402
from tests import fixtures as fx  # noqa: E402

_DIR = tempfile.mkdtemp(prefix="mentotrack_tempo_")
_SIN_PULSO = ["sin_pulso_drone", "sin_pulso_seno", "sin_pulso_pad"]
_TODOS = _SIN_PULSO + ["pulso_ambiguo", "pulso_claro_128"]
_MANIFIESTO = None
_CACHE = {}

CONTEXTO = {"genero": "ambient", "genero_custom": "", "fase": "casi_listo",
            "objetivo": "aprender", "experiencia": "2-5",
            "dificultad_habitual": "mezcla", "bloqueo_percibido": ""}


def setUpModule():
    global _MANIFIESTO
    _MANIFIESTO = fx.generar(_DIR, solo=_TODOS)


def senales(nombre):
    if nombre not in _CACHE:
        _CACHE[nombre] = extraer_senales(_MANIFIESTO[nombre]["ruta"], omitir_armonia=True)
    return _CACHE[nombre]


class TestNoRevienta(unittest.TestCase):
    def test_ningun_material_provoca_excepcion(self):
        for nombre in _TODOS:
            try:
                senales(nombre)
            except Exception as e:      # pragma: no cover
                self.fail(f"{nombre}: {type(e).__name__}: {e}")

    def test_el_diagnostico_completo_tampoco(self):
        for nombre in _SIN_PULSO:
            r = generar_diagnostico(senales(nombre), CONTEXTO)
            self.assertIn("diagnostico_principal", r)

    def test_la_respuesta_es_serializable(self):
        """Sin esto sería un 500 igualmente, solo que más tarde."""
        from starlette.responses import JSONResponse
        for nombre in _SIN_PULSO:
            r = generar_diagnostico(senales(nombre), CONTEXTO)
            JSONResponse(r).render(r)


class TestNoInventaTempo(unittest.TestCase):
    def test_sin_pulso_claro_el_bpm_es_null(self):
        for nombre in ("sin_pulso_drone", "sin_pulso_seno"):
            s = senales(nombre)
            self.assertIsNone(s["bpm"], f"{nombre}: no debe publicarse un BPM")
            self.assertFalse(s["tempo_detectado"], nombre)
            self.assertEqual(s["tempo_fuente"], "no_detectado", nombre)

    def test_nunca_aparece_un_120_por_defecto(self):
        for nombre in _TODOS:
            s = senales(nombre)
            if s["bpm"] is None:
                continue
            # Si hay valor, tiene que venir de la detección o del usuario
            self.assertIn(s["tempo_fuente"], ("detectado", "manual"), nombre)

    def test_bpm_y_tempo_detectado_son_coherentes(self):
        """La invariante que hace que la interfaz nunca mienta."""
        for nombre in _TODOS:
            s = senales(nombre)
            self.assertEqual(s["bpm"] is not None, s["tempo_detectado"], nombre)

    def test_con_pulso_claro_si_detecta_y_acierta(self):
        s = senales("pulso_claro_128")
        self.assertTrue(s["tempo_detectado"])
        self.assertIsNotNone(s["bpm"])
        # El fixture es un kick 4x4 a 128 BPM. Se admite el doble/mitad, que es
        # la ambigüedad clásica de cualquier detector.
        self.assertTrue(any(abs(s["bpm"] - c) <= 3 for c in (64, 128, 256)),
                        f"esperado ~128 (o doble/mitad), medido {s['bpm']}")

    def test_bpm_manual_se_marca_como_manual(self):
        s = extraer_senales(_MANIFIESTO["sin_pulso_drone"]["ruta"],
                            bpm_manual=124, omitir_armonia=True)
        self.assertEqual(s["bpm"], 124)
        self.assertTrue(s["tempo_detectado"])
        self.assertEqual(s["tempo_fuente"], "manual")

    def test_un_tempo_absurdo_se_descarta(self):
        """Fuera de 30-300 BPM la detección no es creíble en este dominio."""
        from engine import extractor
        self.assertEqual(extractor._BLOQUE_SIN_TEMPO_SEG, 15.0)
        ruta = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(ruta, "engine", "extractor.py"), encoding="utf-8") as f:
            codigo = f.read()
        self.assertIn("30.0 <= tempo_bruto <= 300.0", codigo)


class TestElAnalisisSigueSiendoUtil(unittest.TestCase):
    """Sin tempo, lo que se puede medir en segundos se sigue midiendo."""

    def test_las_senales_estructurales_existen(self):
        for nombre in _SIN_PULSO:
            s = senales(nombre)
            for campo in ("n_bloques", "bloques_rms", "varianza_energia",
                          "contraste_energetico", "rango_dinamico",
                          "densidad_global", "distribucion"):
                self.assertIn(campo, s, f"{nombre}: falta {campo}")
            self.assertGreaterEqual(s["n_bloques"], 1, nombre)

    def test_el_loudness_se_mide_igual(self):
        for nombre in _SIN_PULSO:
            lo = senales(nombre)["loudness"]
            self.assertTrue(math.isfinite(lo["lufs_integrado"]), nombre)
            self.assertNotEqual(lo["lufs_integrado"], -99.0, nombre)
            self.assertTrue(math.isfinite(lo["true_peak_dbtp"]), nombre)

    def test_la_taxonomia_de_picos_funciona_sin_tempo(self):
        for nombre in _SIN_PULSO:
            self.assertTrue(senales(nombre)["loudness"]["categoria_picos"], nombre)


class TestMetricasQueDependenDelBpm(unittest.TestCase):
    """Ninguna métrica del informe depende ya del BPM.

    Hasta v0.5.98 la referencia en compases ("A 128 BPM, 8 compases duran
    ~15s") solo se omitía cuando no había pulso. Desde v0.5.99 no se emite
    NUNCA: el BPM solo es fiable en el 15 % de los tracks de usuario, y un
    dato derivado hereda ese error además de disimularlo — el usuario ve
    segundos y no ve de dónde salen. Ver docs/bpm-por-que-no-se-ensena.md."""

    def test_la_referencia_en_compases_no_se_emite_nunca(self):
        for caso in ("sin_pulso_drone", "pulso_claro_128"):
            r = generar_diagnostico(senales(caso), dict(CONTEXTO, genero="techno"))
            self.assertEqual(r.get("referencia_temporal", ""), "", caso)

    def test_ningun_texto_del_informe_afirma_un_bpm(self):
        """El diagnóstico entero, no solo la referencia temporal."""
        r = generar_diagnostico(senales("pulso_claro_128"),
                                dict(CONTEXTO, genero="techno"))
        textos = []
        for k in ("referencia_temporal", "nota_contextual", "nota_motivacional"):
            if r.get(k):
                textos.append(str(r[k]))
        for lista in ("prioridades", "tips_genero", "sugerencias_estructura"):
            textos += [str(x) for x in (r.get(lista) or [])]
        for t in textos:
            self.assertNotIn("BPM", t, f"el informe sigue afirmando un BPM: {t[:120]}")

    def test_el_bpm_viaja_como_null_hasta_la_respuesta(self):
        r = generar_diagnostico(senales("sin_pulso_drone"), CONTEXTO)
        self.assertIsNone(r["datos_audio"]["bpm"])
        self.assertFalse(r["datos_audio"]["tempo_detectado"])

    def test_la_comparacion_contra_referencia_no_revienta(self):
        from engine.comparador import comparar_senales
        c = comparar_senales(senales("sin_pulso_drone"),
                             senales("pulso_claro_128"), CONTEXTO)
        self.assertIn("diferencias", c)
        for aviso in c.get("avisos", []):
            self.assertNotIn("None BPM", aviso)
            self.assertNotIn("0 BPM", aviso)


class TestInterfaz(unittest.TestCase):
    def test_el_informe_no_escribe_un_bpm_inventado(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("da.bpm != null ? da.bpm : 'no detectado'", html)
        self.assertNotIn("BPM: ${da.bpm || '?'}", html)

    def test_se_persiste_si_el_tempo_se_detecto(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(raiz, "frontend", "index.html"), encoding="utf-8") as f:
            html = f.read()
        bloque = html[html.find("const senales = {"):]
        bloque = bloque[:bloque.find("};")]
        self.assertIn("tempo_detectado:", bloque)
        self.assertIn("tempo_fuente:", bloque)


if __name__ == "__main__":
    unittest.main(verbosity=2)
