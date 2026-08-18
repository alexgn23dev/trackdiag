"""El rediseño del diagnóstico (v2) y su interruptor.

Desde v0.5.92 la v2 es la vista POR DEFECTO (antes vivía detrás de `?v2=1` y
ningún flujo de producción la enlazaba: nadie la veía). `mt_v2` guarda ahora el
opt-out: `?v2=0` o el botón "Vista clásica" lo activan para la sesión, `?v2=1`
lo limpia. Siguen existiendo DOS caminos de render y romper uno no rompe el
otro — de ahí estos tests.

Son comprobaciones sobre el código fuente, no sobre el navegador. Lo que sí se
ejecuta de verdad es `docs/rediseno/verificar.cjs` sobre el prototipo, y la
prueba manual: abrir la app tras un análisis (y con `?v2=0`, la clásica).
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
        """`?v2=0` marca el opt-out de sesión: sin él, quien quisiera la
        clásica no tendría forma de pedirla."""
        i = self.html.find("function usarVistaV2(")
        cuerpo = self.html[i:i + 800]
        self.assertIn("setItem('mt_v2', '0')", cuerpo)
        self.assertIn("return false", cuerpo)

    def test_arranca_encendida(self):
        """Sin parámetro y sin opt-out, la vista es la v2 — es el defecto
        desde v0.5.92. El fallo que se arregló: estaba desplegada pero ningún
        flujo la enlazaba, así que el rediseño entero era invisible."""
        i = self.html.find("function usarVistaV2(")
        cuerpo = self.html[i:i + 800]
        self.assertIn("sessionStorage.getItem('mt_v2') !== '0'", cuerpo)
        self.assertIn("catch (e) { return true; }", cuerpo)

    def test_hay_salida_desde_la_propia_vista(self):
        """Un usuario que aterrice en v2 tiene que poder volver sin saber que
        existe un parámetro de URL — y desde la clásica, regresar."""
        self.assertIn("Vista clásica", self.html)
        self.assertIn("Probar la vista nueva", self.html)

    def test_el_lufs_de_la_seccion_mas_fuerte_se_ensena(self):
        """Dos «No» del feedback fueron solo porque el LUFS integrado no cuadra
        con lo que enseña el medidor del DAW (que suele ser el máximo de la
        sección más fuerte). La cifra que los reconcilia ya se medía; ahora
        tiene que estar en pantalla en las DOS vistas, con su explicación."""
        self.assertEqual(self.html.count("En tu sección más fuerte"), 2,
                         "la fila del short-term tiene que estar en v2 y en clásica")
        self.assertIn("lufs_short_term_max", self.html)

    def test_el_alcance_esta_declarado_en_ambas_vistas(self):
        """Casi la mitad de los «Parcial» eran expectativas de análisis de
        composición/armonía/vocales — que nunca prometimos pero tampoco
        negábamos. El alcance se declara en el pie de las dos vistas."""
        self.assertEqual(self.html.count("No evalúa armonía, melodía, composición"), 2)

    def test_la_v2_ensena_la_comparacion_con_referencia(self):
        """Era el único hueco de paridad con la clásica, y de los que duelen:
        dos usuarios subieron referencia y no vieron nada. Con la v2 por
        defecto, este hueco sería una regresión para todos."""
        self.assertIn("function V2Comparacion(", self.html)
        i = self.html.find("function V2TabResumen(")
        cuerpo = self.html[i:i + 3000]
        self.assertIn("<V2Comparacion comp={r.comparacion_referencia} />", cuerpo)

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
        sello", no el plan de acción. Por eso vive en la cabecera, encima de
        las pestañas: es la columna derecha del bloque del veredicto, y cuando
        el track no está para sello ese mismo hueco lo ocupa el tutorial
        recomendado — nunca queda vacío ni baja de ahí."""
        self.assertIn("const tarjetaRelesit", self.v2)
        # Relesit alimenta la columna derecha de la cabecera…
        self.assertIn("const bloqueDerechoV2 = tarjetaRelesit ||", self.v2)
        # …que se pinta antes de las pestañas.
        i = self.v2.find("{bloqueDerechoV2}")
        j = self.v2.find("V2_TABS.map")
        self.assertGreater(i, 0, "no se pinta la columna derecha de la cabecera")
        self.assertLess(i, j, "la cabecera tiene que ir ANTES de las pestañas")

    def test_ese_hueco_nunca_queda_vacio(self):
        """Si el track no está para sello, la columna derecha la ocupa el CTA
        del curso (decisión de Alex, ago-2026: la derivación sube a la
        cabecera y los tutoriales se quedan abajo). Antes ahí iba un tutorial
        destacado, que dependía de que hubiera tutoriales para ese
        diagnóstico; el CTA no depende de datos, así que el hueco está
        siempre lleno y la cabecera no se descuadra."""
        i = self.v2.find("const bloqueDerechoV2 = tarjetaRelesit ||")
        bloque = self.v2[i:i + 400]
        self.assertIn("<CursoCTA", bloque)
        self.assertIn('clase="h-full"', bloque)
        # Y la lista de abajo ya no se salta ningún destacado.
        self.assertIn("const listaTutorialesV2 = allTutoriales.slice(0, 3);", self.v2)
        self.assertNotIn("V2TutorialDestacado", self.html,
                         "quedó el componente huérfano del vídeo destacado")

    def test_hay_barra_de_navegacion_propia(self):
        """El botón flotante "Mi panel" se encimaba al contenido en cuanto la
        ventana se estrechaba. La v2 lleva barra propia y el flotante se oculta."""
        self.assertIn("function V2Nav(", self.html)
        self.assertIn("<V2Nav", self.v2)
        self.assertIn("!(screen === 'diagnostico' && usarVistaV2())", self.html)

    def test_la_barra_lleva_las_cuatro_acciones(self):
        """El CTA dice "Nuevo análisis" en pantalla ancha y solo "Nuevo" en
        móvil: con el texto completo se salía de la pantalla y había que
        arrastrar la barra para llegar a la acción principal."""
        i = self.html.find("function V2Nav(")
        cuerpo = self.html[i:i + 2500]
        for accion in ("Mis proyectos", "Ideas", "Nuevo"):
            self.assertIn(accion, cuerpo, accion)
        self.assertIn('Nuevo<span className="hidden sm:inline"> análisis</span>', cuerpo)

    def test_el_cierre_es_el_mismo_que_la_clasica(self):
        """Para que el footer global del sitio quede igual en las dos."""
        self.assertIn("Mentotrack no almacena el archivo de tu canción", self.v2)

    def test_las_tarjetas_de_derivacion_son_los_componentes_reales(self):
        """La v2 no reimplementa las tarjetas: usa las mismas que la clásica.

        Desde ago-2026 la del curso pasa por `CursoCTA`, que decide entre el
        Máster y la campaña temporal de Headroom — una indirección, no una
        tarjeta nueva: las dos vistas siguen enseñando lo mismo."""
        self.assertIn("<RelesitCTA", self.v2)
        self.assertIn("<CursoCTA", self.v2)
        self.assertIn("function CursoCTA(", self.html)
        # Y la clásica usa exactamente la misma, no una copia.
        self.assertEqual(self.html.count("<CursoCTA"), 2)

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


class TestLaCampanaDeCurso(unittest.TestCase):
    """El CTA de curso es un enlace comercial: si se rompe, se pierde tráfico
    en silencio — nadie recibe un error, simplemente nadie llega.

    Campaña temporal (ago-2026): durante unas semanas apunta al curso de
    Headroom y Gain Staging en vez de al Máster.
    """

    def setUp(self):
        self.html = fuente()

    def test_el_enlace_es_exactamente_el_que_dio_alex(self):
        """Sin UTMs colgados: la landing ya es específica de Mentotrack."""
        self.assertIn(
            "const HEADROOM_URL = 'https://producciononline.com/headroom-mentotrack';",
            self.html)

    def test_volver_al_master_es_cambiar_una_palabra(self):
        """La campaña se acaba en unas semanas. MasterCTA tiene que seguir
        entero para que la vuelta no sea una migración."""
        self.assertIn("const CTA_CURSO = 'headroom';", self.html)
        self.assertIn("function MasterCTA(", self.html)
        self.assertIn("CTA_CURSO === 'headroom' ? <HeadroomCTA", self.html)

    def test_el_clic_y_la_impresion_se_registran(self):
        """Sin esto la campaña no se puede evaluar, que es justo para lo que
        se pone un CTA temporal."""
        for evento in ("cta_headroom_visto", "cta_headroom_clicked",
                       "headroom_visto", "headroom_clicked"):
            self.assertIn(evento, self.html, evento)

    def test_el_dashboard_puede_verlo(self):
        raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dash = open(os.path.join(raiz, "frontend", "dashboard.html"), encoding="utf-8").read()
        self.assertIn("headroom_visto", dash)
        self.assertIn("headroom_clicked", dash)
        self.assertIn("<CursoResumenCard />", dash)
