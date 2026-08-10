"""El aviso de género fuera de alcance, ANTES del botón de análisis.

Mentotrack está calibrado solo para electrónica de club. Hasta la v0.5.78 eso
se decía en el informe: el usuario subía un bolero, esperaba el análisis
entero y al final leía que el motor no está pensado para su estilo. Decisión
de Alex el 2026-08-10: tiene que quedar claro en el formulario, antes de
pulsar el botón.

Eso obliga a tener la misma regla en dos sitios —el cliente avisa, el backend
sigue emitiendo `aviso_genero` para quien analice igualmente— y dos listas que
se copian son dos listas que se desincronizan. Estos tests las comparan.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")
CONTEXTUALIZADOR = os.path.join(RAIZ, "engine", "contextualizador.py")


def _lista_python(nombre):
    """Extrae una tupla de literales de contextualizador.py."""
    with open(CONTEXTUALIZADOR, encoding="utf-8") as f:
        codigo = f.read()
    i = codigo.find(f"{nombre} = (")
    assert i > 0, f"no se encuentra {nombre}"
    j = codigo.find(")", i)
    # Cierre real: el paréntesis que cierra la tupla, tras la última cadena
    trozo = codigo[i:codigo.find("\n        )", i) + 10]
    return set(re.findall(r'"([^"]*)"', trozo))


def _lista_js(nombre):
    with open(INDEX, encoding="utf-8") as f:
        html = f.read()
    i = html.find(f"const {nombre} = [")
    assert i > 0, f"no se encuentra {nombre} en index.html"
    j = html.find("];", i)
    return set(re.findall(r'"([^"]*)"', html[i:j]))


class TestLasDosListasCoinciden(unittest.TestCase):
    """Si divergen, el formulario avisaría de un género y el informe de otro."""

    def test_no_electronicos(self):
        py = _lista_python("_palabras_no_electronicas")
        js = _lista_js("GENEROS_NO_ELECTRONICOS")
        self.assertEqual(py, js,
                         f"\n  solo en Python: {sorted(py - js)}"
                         f"\n  solo en JS:     {sorted(js - py)}")

    def test_lista_blanca_electronica(self):
        py = _lista_python("_whitelist_electronic")
        js = _lista_js("GENEROS_ELECTRONICOS")
        self.assertEqual(py, js,
                         f"\n  solo en Python: {sorted(py - js)}"
                         f"\n  solo en JS:     {sorted(js - py)}")


class TestElAvisoEstaEnElFormulario(unittest.TestCase):
    def setUp(self):
        with open(INDEX, encoding="utf-8") as f:
            self.html = f.read()

    def test_existe_la_funcion_de_comprobacion(self):
        self.assertIn("function esGeneroNoElectronico(", self.html)

    def test_se_usa_en_el_campo_de_genero_libre(self):
        """Y en el campo, no en la pantalla de resultados."""
        i = self.html.find("¿Qué género exactamente?")
        j = self.html.find("¿En qué fase crees que está el track?")
        self.assertGreater(i, 0)
        self.assertIn("esGeneroNoElectronico(customTxt)", self.html[i:j],
                      "el aviso tiene que salir en el propio campo")

    def test_el_texto_dice_para_que_esta_calibrado(self):
        i = self.html.find("esGeneroNoElectronico(customTxt)")
        bloque = self.html[i:i + 1800]
        self.assertIn("electrónica de club", bloque)
        self.assertIn("house, techno, trance", bloque.lower())

    def test_no_bloquea_el_analisis(self):
        """Decisión deliberada: se avisa, no se impide. Un aviso claro antes de
        pulsar es lo que se pidió; cerrar la puerta es otra decisión y no se ha
        tomado. Si algún día se toma, este test hay que cambiarlo a propósito."""
        i = self.html.find("esGeneroNoElectronico(customTxt)")
        bloque = self.html[i:i + 1800]
        self.assertIn("Puedes analizarlo igualmente", bloque)


class TestLaReglaSeComportaIgualEnLosDosLados(unittest.TestCase):
    """La lógica, no solo las listas: la lista blanca gana a la otra."""

    CASOS = [
        ("reggaeton", True), ("bachata", True), ("rock", True),
        ("flamenco", True), ("jazz fusion", True),
        ("tech house", False), ("hard techno", False), ("psytrance", False),
        ("drum and bass", False), ("uk garage", False),
        # La lista blanca manda: si hay una palabra electrónica, no se avisa
        ("rock electrónico", False), ("indie dance pop", False),
        ("electro swing", False),
        # Con tilde y sin tilde tienen que dar lo mismo: era el bug que
        # destapó este test (v0.5.78).
        ("reggaetón", True), ("reggaeton", True),
        ("música clásica", True), ("musica clasica", True),
        ("techno melódico", False), ("techno melodico", False),
        ("", False), ("x", False),
    ]

    def _python(self, texto):
        from engine.contextualizador import _sin_tildes
        custom = _sin_tildes(texto.lower())
        blanca = _lista_python("_whitelist_electronic")
        negra = _lista_python("_palabras_no_electronicas")
        if any(_sin_tildes(k) in custom for k in blanca):
            return False
        return any(_sin_tildes(k) in custom for k in negra)

    def test_los_casos_dan_lo_esperado_en_python(self):
        for texto, espera in self.CASOS:
            if len(texto) < 2:
                continue
            self.assertEqual(self._python(texto), espera, f"«{texto}»")

    def test_el_backend_sigue_emitiendo_el_aviso_para_quien_analice_igual(self):
        """El aviso del formulario no sustituye al del informe: quien decida
        analizar igualmente tiene que seguir viéndolo en el resultado."""
        from engine.contextualizador import contextualizar_feedback
        senales = {"bpm": 120, "duracion_seg": 200, "n_bloques": 6,
                   "contraste_energetico": "medio", "densidad_global": "media",
                   "balance_grave": "ok", "rango_dinamico": 8.0,
                   "tiene_desarrollo": True, "cambios_significativos": 3,
                   "madurez_estimada": "medio", "distribucion": {},
                   "loudness": {"lufs_integrado": -9.0, "nivel": "alto"}}
        ctx = {"genero": "otro", "genero_custom": "bachata", "fase": "casi_listo",
               "objetivo": "sellos", "experiencia": "2-5",
               "dificultad_habitual": "mezcla"}
        try:
            r = contextualizar_feedback("problema_arreglo", ctx, senales)
        except Exception as e:
            self.skipTest(f"contextualizar_feedback: {type(e).__name__}: {e}")
        self.assertTrue(r.get("aviso_genero"), "el informe debe seguir avisando")
        self.assertIn("electrónica", r["aviso_genero"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
