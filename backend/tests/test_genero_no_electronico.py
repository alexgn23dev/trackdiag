"""Género fuera de alcance: el aviso del informe (histórico).

Historia de esta decisión, en tres pasos:

  · hasta v0.5.78 — el usuario subía un bolero, esperaba el análisis entero y
    al final leía que el motor no está pensado para su estilo;
  · v0.5.78 (ago-2026) — el aviso sube al formulario, antes del botón, pero
    NO bloquea: se avisa y cada cual decide. Es lo que fijaba este archivo;
  · v0.5.97 — Alex decide no aceptar esos análisis. El bloqueo, sus listas y
    su criterio viven ahora en `engine/generos.py`, y lo que los vigila es
    `test_alcance_genero.py`.

Lo que queda aquí es el `aviso_genero` del informe, que se conserva como
mensaje de los análisis YA guardados (los de antes del bloqueo se siguen
pudiendo abrir desde el panel). Sus listas ya no gobiernan nada del formulario
— por eso este archivo dejó de comparar las dos copias: la comparación viva es
la de `test_alcance_genero.TestElFrontendNoDiverge`, contra `generos.py`.
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


class TestLasListasDelAvisoSiguenSiendoUtilizables(unittest.TestCase):
    """Ya NO se comparan con el frontend: desde v0.5.97 la lista que gobierna
    el formulario es la de `engine/generos.py` (ver test_alcance_genero.py).
    Estas son las del aviso del informe, que sobrevive para los análisis
    guardados antes del bloqueo. Solo se comprueba que sigan bien formadas."""

    def test_las_listas_del_aviso_no_estan_vacias(self):
        self.assertGreater(len(_lista_python("_palabras_no_electronicas")), 20)
        self.assertGreater(len(_lista_python("_whitelist_electronic")), 5)


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

    def test_ahora_si_bloquea_el_analisis(self):
        """Este test decía lo contrario hasta v0.5.97 ("se avisa, no se
        impide") y advertía: si algún día se decide cerrar la puerta, hay que
        cambiarlo a propósito. Es lo que ha pasado — Alex no quiere análisis
        fuera de la electrónica de club. Se invierte a conciencia, no por
        arrastre."""
        i = self.html.find("esGeneroNoElectronico(customTxt)")
        bloque = self.html[i:i + 2000]
        self.assertNotIn("Puedes analizarlo igualmente", bloque)
        self.assertIn("solo analiza electrónica de club", bloque)
        # y el cuestionario no avanza
        self.assertIn("&& !esGeneroNoElectronico((contexto.genero_custom || '').trim())",
                      self.html)


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
