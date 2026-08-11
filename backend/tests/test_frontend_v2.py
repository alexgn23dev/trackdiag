"""El rediseño del diagnóstico (v2) y su interruptor.

La vista nueva convive con la clásica detrás de `?v2=1`. Eso es deliberado:
permite encenderla, mirarla en producción con tráfico real y apagarla sin
revertir un commit. Pero también significa que hay DOS caminos de render y que
romper uno no rompe el otro — de ahí estos tests.

Son comprobaciones sobre el código fuente, no sobre el navegador. Lo que sí se
ejecuta de verdad es `docs/rediseno/verificar.cjs` sobre el prototipo, y la
prueba manual: abrir la app con `?v2=1` tras un análisis.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")


def fuente():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


class TestElInterruptor(unittest.TestCase):
    def setUp(self):
        self.html = fuente()

    def test_existe_y_lee_la_url(self):
        self.assertIn("function usarVistaV2(", self.html)
        i = self.html.find("function usarVistaV2(")
        cuerpo = self.html[i:i + 600]
        self.assertIn("URLSearchParams", cuerpo)
        self.assertIn("'v2'", cuerpo)

    def test_se_puede_apagar_explicitamente(self):
        """Sin un `?v2=0` que borre la sesión, quien la encendiera una vez se
        quedaría atrapado en la vista nueva."""
        i = self.html.find("function usarVistaV2(")
        cuerpo = self.html[i:i + 600]
        self.assertIn("=== '0'", cuerpo)
        self.assertIn("removeItem", cuerpo)

    def test_arranca_apagada(self):
        """Sin parámetro y sin sesión, la vista es la clásica."""
        i = self.html.find("function usarVistaV2(")
        cuerpo = self.html[i:i + 600]
        self.assertIn("sessionStorage.getItem('mt_v2') === '1'", cuerpo)

    def test_hay_salida_desde_la_propia_vista(self):
        """Un usuario que aterrice en v2 tiene que poder volver sin saber que
        existe un parámetro de URL."""
        self.assertIn("Vista clásica", self.html)

    def test_se_resuelve_una_sola_vez(self):
        """Si se recalculara en cada render, la vista podría cambiar a mitad de
        sesión."""
        self.assertIn("const [v2Activo] = useState(usarVistaV2)", self.html)


class TestLasDosVistasSiguenExistiendo(unittest.TestCase):
    def setUp(self):
        self.html = fuente()

    def test_la_clasica_no_se_ha_tocado(self):
        """Marcas inequívocas de la vista de siempre."""
        for marca in ('className="max-w-2xl mx-auto"',
                      "{/* ===== RESUMEN VISUAL ===== */}",
                      "Ver tutoriales recomendados"):
            self.assertIn(marca, self.html, marca)

    def test_la_v2_esta_completa(self):
        for comp in ("V2TabResumen", "V2TabPlan", "V2TabMezcla",
                     "V2TabMaster", "V2TabDetalle", "V2_TABS"):
            self.assertIn(f"function {comp}" if comp.startswith("V2Tab") else comp,
                          self.html, comp)

    def test_la_v2_usa_el_ancho(self):
        i = self.html.find("if (v2Activo) {")
        self.assertGreater(i, 0, "no existe la rama v2")
        self.assertIn("max-w-7xl", self.html[i:i + 12000])


class TestNoDuplicaLoQueYaFunciona(unittest.TestCase):
    """El riesgo de una vista alternativa es acabar con dos copias de la misma
    lógica que divergen. Estos tests comprueban que la v2 REUTILIZA."""

    def setUp(self):
        self.html = fuente()
        i = self.html.find("if (v2Activo) {")
        # Hasta el final real de la rama, no un número fijo: la v2 ha crecido y
        # un corte corto dejaba fuera lo que hay al final (la barra flotante).
        j = self.html.find("\n        return (\n            <div className=\"min-h-screen py-12", i)
        self.v2 = self.html[i:j if j > i else i + 20000]

    def test_el_widget_de_calibracion_es_el_mismo(self):
        """Ambos se extrajeron a variables para que los usen las dos vistas.

        La v2 NO lo pinta en tarjeta: Alex lo prefiere como en la clásica, en
        la barra flotante de abajo. Pero la barra es el mismo componente."""
        self.assertIn("const bloqueFeedback = (", self.html)
        self.assertIn("const barraFeedback = (", self.html)
        self.assertIn("{barraFeedback}", self.v2)
        # La clásica pinta los dos; la v2 solo la barra.
        self.assertEqual(self.html.count("{bloqueFeedback}"), 1)
        self.assertEqual(self.html.count("{barraFeedback}"), 2)

    def test_el_feedback_no_va_en_tarjeta_en_la_v2(self):
        """Decisión de Alex tras probarlo: la tarjeta estorbaba."""
        self.assertIn("feedback: null", self.v2)

    def test_relesit_va_arriba_cuando_el_track_esta_fino(self):
        """Si no hay nada urgente que arreglar, lo principal es "búscale
        sello", no el plan de acción. Por eso sube sobre las pestañas."""
        self.assertIn("const tarjetaRelesit", self.v2)
        i = self.v2.find("{tarjetaRelesit}")
        j = self.v2.find("V2_TABS.map")
        self.assertGreater(i, 0, "no se pinta la tarjeta de Relesit")
        self.assertLess(i, j, "Relesit tiene que ir ANTES de las pestañas")

    def test_hay_barra_de_navegacion_propia(self):
        """El botón flotante "Mi panel" se encimaba al contenido en cuanto la
        ventana se estrechaba. La v2 lleva barra propia y el flotante se oculta."""
        self.assertIn("function V2Nav(", self.html)
        self.assertIn("<V2Nav", self.v2)
        self.assertIn("!(screen === 'diagnostico' && usarVistaV2())", self.html)

    def test_la_barra_lleva_las_cuatro_acciones(self):
        i = self.html.find("function V2Nav(")
        cuerpo = self.html[i:i + 2500]
        for accion in ("Mis proyectos", "Ideas", "Nuevo análisis"):
            self.assertIn(accion, cuerpo, accion)

    def test_el_cierre_es_el_mismo_que_la_clasica(self):
        """Para que el footer global del sitio quede igual en las dos."""
        self.assertIn("Mentotrack no almacena el archivo de tu canción", self.v2)

    def test_las_tarjetas_de_derivacion_son_los_componentes_reales(self):
        self.assertIn("<RelesitCTA", self.v2)
        self.assertIn("<MasterCTA", self.v2)

    def test_la_regla_de_derivacion_no_cambia(self):
        """Una tarjeta y solo una, con el mismo criterio que la clásica."""
        self.assertIn("diagId === 'sin_diagnostico' || r.estado_track === 'avanzado'", self.v2)

    def test_compartir_en_comunidad_sigue_disponible(self):
        self.assertIn("<CompartirComunidad", self.v2)

    def test_el_click_en_tutorial_se_sigue_registrando(self):
        """Es la métrica con la que se decidirá si sacarlos de detrás del botón
        ha servido de algo."""
        self.assertIn("/api/sheets/tutorial-click", self.v2)
        self.assertIn("trackEvent('tutorial_clicked'", self.v2)


class TestElTextoNoSePierde(unittest.TestCase):
    """El rediseño recorta lo que se VE de golpe, no lo que se dice."""

    def setUp(self):
        self.html = fuente()

    def test_el_partidor_existe_y_tiene_tope(self):
        self.assertIn("function v2Partir(", self.html)
        i = self.html.find("function v2Partir(")
        cuerpo = self.html[i:i + 1200]
        # El corte por punto, y la red para las frases encadenadas con ';'
        self.assertIn("lastIndexOf('; ')", cuerpo)

    def test_cada_desplegable_deja_ver_el_resto(self):
        self.assertIn("function V2Desplegable(", self.html)
        i = self.html.find("function V2Desplegable(")
        cuerpo = self.html[i:i + 1200]
        self.assertIn("Saber más", cuerpo)
        self.assertIn("Ocultar", cuerpo)


class TestSinEmojisEnLaV2(unittest.TestCase):
    """Decisión de estilo: la vista nueva no lleva emojis. La clásica sí, y se
    queda como está."""

    def test_la_rama_v2_no_tiene_emojis(self):
        html = fuente()
        i = html.find("if (v2Activo) {")
        v2 = html[i:i + 12000]
        emojis = re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", v2)
        self.assertEqual(emojis, [], f"emojis en la v2: {set(emojis)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
