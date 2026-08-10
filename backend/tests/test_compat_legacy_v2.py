"""Convivencia de análisis legacy (taxonomía v1) y nuevos (v2).

En Postgres van a convivir 3.000 análisis escritos con el vocabulario viejo
—donde "clipping" significaba `true_peak > 0`— y los nuevos, con la taxonomía
v2. Los parsers tienen que saber cuál están leyendo.

La regla, y es la que ordena todo este fichero: **un análisis antiguo no se
traduce a la taxonomía nueva**. El texto legacy no distingue un over de true
peak de un archivo float con overs recuperables, que es justo lo que v2
separa. Traducirlo sería inventar el dato que falta.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "estudio_historico"))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(RAIZ)

# --- Informes de muestra, tal cual quedan guardados en la base -------------

INFORME_LEGACY = """--- MEZCLA ---
BPM: 128 | Duración: 5:32
Balance grave: normal
Densidad: media
Loudness: -8.2 LUFS (alto) | Pico: -6.1 LUFS | Rango: 4.2 LU
True peak: +0.5 dBTP (clipping)
Mono compat: excelente
"""

INFORME_LEGACY_SIN_TP = """--- MEZCLA ---
BPM: 124 | Duración: 4:10
Loudness: -11.0 LUFS (moderado) | Pico: -9.0 LUFS | Rango: 6.0 LU
Mono compat: buena
"""

INFORME_V2 = """--- MEZCLA ---
BPM: 128 | Duración: 5:32
Balance grave: normal
Densidad: media
Loudness: -8.2 LUFS (alto) | Pico: -6.1 LUFS | Rango: 4.2 LU
True peak: +0.5 dBTP
Sample peak: -0.8 dBFS
Categoría de picos: true_peak_over
Taxonomía de picos: v2
Mono compat: excelente
"""

INFORME_V2_FLOAT = """--- MEZCLA ---
BPM: no detectado | Duración: 6:02
True peak: +4.5 dBTP
Sample peak: +3.0 dBFS
Categoría de picos: overs_float_recuperables
Taxonomía de picos: v2
"""


from engine.picos_parser import etiqueta_comparable, leer_picos as _leer_picos  # noqa: E402


class TestParserDelEstudio(unittest.TestCase):
    """Prioridad: v2 si existe, legacy si no."""

    def test_v2_se_reconoce_como_v2(self):
        p = _leer_picos(INFORME_V2)
        self.assertEqual(p["fuente"], "v2")
        self.assertEqual(p["categoria"], "true_peak_over")
        self.assertEqual(p["tp"], 0.5)
        self.assertEqual(p["sp"], -0.8)
        self.assertIsNone(p["nivel_legacy"])

    def test_legacy_se_reconoce_como_legacy(self):
        p = _leer_picos(INFORME_LEGACY)
        self.assertEqual(p["fuente"], "legacy")
        self.assertEqual(p["nivel_legacy"], "clipping")
        self.assertEqual(p["tp"], 0.5)
        self.assertIsNone(p["categoria"],
                          "un análisis legacy NO se traduce a la taxonomía nueva")
        self.assertIsNone(p["sp"], "los análisis viejos no traen sample peak")

    def test_legacy_sin_true_peak(self):
        p = _leer_picos(INFORME_LEGACY_SIN_TP)
        self.assertEqual(p["fuente"], "ninguna")
        self.assertIsNone(p["tp"])

    def test_float_v2(self):
        p = _leer_picos(INFORME_V2_FLOAT)
        self.assertEqual(p["categoria"], "overs_float_recuperables")
        self.assertEqual(p["sp"], 3.0)

    def test_el_mismo_true_peak_no_se_clasifica_igual(self):
        """+0,5 dBTP era «clipping» en v1 y es «true_peak_over» en v2. Mezclar
        las dos etiquetas en una serie daría un número sin significado."""
        v1 = _leer_picos(INFORME_LEGACY)
        v2 = _leer_picos(INFORME_V2)
        self.assertEqual(v1["tp"], v2["tp"])
        self.assertNotEqual(v1["fuente"], v2["fuente"])
        self.assertNotEqual(v1["nivel_legacy"], v2["categoria"])

    def test_un_lote_mezclado_se_separa_por_fuente(self):
        lote = [INFORME_LEGACY, INFORME_V2, INFORME_LEGACY_SIN_TP,
                INFORME_V2_FLOAT, INFORME_LEGACY]
        fuentes = [_leer_picos(i)["fuente"] for i in lote]
        self.assertEqual(fuentes, ["legacy", "v2", "ninguna", "v2", "legacy"])
        con_dato = [f for f in fuentes if f != "ninguna"]
        self.assertEqual(len(con_dato), 4)


class TestParserDelDashboard(unittest.TestCase):
    """El dashboard aplica la misma prioridad y lo dice en pantalla."""

    def setUp(self):
        with open(os.path.join(REPO, "frontend", "dashboard.html"), encoding="utf-8") as f:
            self.html = f.read()

    def test_busca_primero_la_categoria_v2(self):
        i_cat = self.html.find("Categoría de picos:")
        i_leg = self.html.find("dBTP\\s*\\\\((\\\\w+)\\\\)")
        self.assertNotEqual(i_cat, -1, "el dashboard no busca la categoría v2")
        if i_leg != -1:
            self.assertLess(i_cat, i_leg, "v2 tiene que evaluarse antes que legacy")

    def test_distingue_las_dos_fuentes(self):
        for marca in ("picos.fuente = 'v2'", "picos.fuente = 'legacy'"):
            self.assertIn(marca, self.html)

    def test_avisa_en_pantalla_de_que_un_dato_es_legacy(self):
        self.assertIn("dato legacy", self.html,
                      "hay que poder distinguir de un vistazo qué taxonomía se mira")

    def test_no_traduce_legacy_a_v2(self):
        bloque = self.html[self.html.find("const picos = "):]
        bloque = bloque[:bloque.find("// Mono compat")]
        for categoria in ("true_peak_over", "overs_float_recuperables", "margen_streaming"):
            self.assertNotIn(categoria, bloque,
                             "el dashboard no puede inventar una categoría v2 "
                             "a partir de un texto legacy")


class TestInformeNuevo(unittest.TestCase):
    """Los análisis nuevos ya no escriben «(clipping)»."""

    def setUp(self):
        with open(os.path.join(REPO, "frontend", "index.html"), encoding="utf-8") as f:
            self.html = f.read()

    def test_con_taxonomia_la_linea_va_limpia(self):
        self.assertIn("`True peak: ${_tp.toFixed(1)} dBTP\\n`", self.html)

    def test_se_escriben_las_tres_lineas(self):
        for linea in ("True peak: ", "Sample peak: ", "Categoría de picos: ",
                      "Taxonomía de picos: v"):
            self.assertIn(linea, self.html, f"falta la línea «{linea}»")

    def test_se_persisten_los_campos_estructurados(self):
        bloque = self.html[self.html.find("const senales = {"):]
        bloque = bloque[:bloque.find("};")]
        for campo in ("true_peak_dbtp", "sample_peak_dbfs", "categoria_picos",
                      "peak_taxonomy_version", "peak_algorithm_version",
                      "analysis_engine_version"):
            self.assertIn(f"{campo}:", bloque, f"falta {campo} en `senales`")

    def test_el_campo_legacy_se_sigue_guardando(self):
        """Para que un parser antiguo no se quede sin nada que leer."""
        bloque = self.html[self.html.find("const senales = {"):]
        bloque = bloque[:bloque.find("};")]
        self.assertIn("nivel_true_peak:", bloque)


class TestVersionesDeTaxonomia(unittest.TestCase):
    """La versión es lo que permite leer un análisis viejo sin malinterpretarlo.

    v1 → ok | streaming | clipping           (llamaba clipping a un over)
    v2 → + overs_float_recuperables, y `true_peak_over` en vez de "clipping"
    v3 → parte `true_peak_over` en dos: entre 0 y +0,3 dBTP se describe sin
         afirmar, porque esa frontera es más fina de lo que la medida resuelve
    """

    def test_la_version_es_3(self):
        from engine.extractor import PEAK_TAXONOMY_VERSION
        self.assertEqual(PEAK_TAXONOMY_VERSION, 3)

    def test_subir_de_categoria_obliga_a_subir_la_version(self):
        """Si alguien añade una categoría sin tocar la versión, dos análisis
        con vocabularios distintos quedarían marcados igual."""
        from engine.extractor import PEAK_TAXONOMY_VERSION
        conocidas = {"ok", "margen_streaming", "true_peak_en_el_limite",
                     "true_peak_over", "overs_float_recuperables"}
        ruta = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "extractor.py")
        with open(ruta, encoding="utf-8") as f:
            codigo = f.read()
        emitidas = set(re.findall(r'"categoria_picos": "([a-z_]+)"', codigo))
        self.assertEqual(emitidas, conocidas,
                         f"el código emite categorías que la v{PEAK_TAXONOMY_VERSION} "
                         "no declara (o al revés)")

    def test_viaja_en_el_analisis(self):
        import tempfile
        from engine.extractor import extraer_senales
        from tests import fixtures as fx
        m = fx.generar(tempfile.mkdtemp(), solo=["pulso_claro_128"])
        lo = extraer_senales(m["pulso_claro_128"]["ruta"], omitir_armonia=True)["loudness"]
        self.assertEqual(lo["peak_taxonomy_version"], 3)
        self.assertIsNotNone(lo["true_peak_classification_value"])

    def test_la_medicion_cruda_no_se_sobrescribe(self):
        """`true_peak_dbtp` es la medición; el valor de clasificación es otro
        campo. Si se pisaran, se perdería la precisión para siempre."""
        import tempfile
        from engine.extractor import extraer_senales
        from tests import fixtures as fx
        m = fx.generar(tempfile.mkdtemp(), solo=["wav24_pico_menos1"])
        lo = extraer_senales(m["wav24_pico_menos1"]["ruta"], omitir_armonia=True)["loudness"]
        crudo = lo["true_peak_dbtp"]
        clasificacion = lo["true_peak_classification_value"]
        self.assertNotEqual(crudo, clasificacion,
                            "el fixture tiene decimales: los dos campos deben diferir")
        self.assertAlmostEqual(round(crudo, 1), clasificacion, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
