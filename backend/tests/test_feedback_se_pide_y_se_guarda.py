"""El informe pide feedback, y el primer clic ya lo guarda.

## Qué pasó (ago-2026)

La tasa de respuesta cayó del **14,1 %** de los análisis (semana del 11-may) al
**0,7 %** (semana del 17-ago). Dos causas encadenadas, las dos invisibles desde
dentro:

1. **El widget desapareció del informe.** Al pasar la vista v2 a por defecto
   (13-ago), los extras del Resumen llevaban `feedback: null` — se quitó
   pensando que la barra flotante bastaba, pero la vista clásica tenía LAS DOS
   cosas. Medido: **2,95 % → 0,31 %** de respuestas (p = 0,007), 1 respuesta
   guardada en 319 análisis.

2. **Pulsar Sí/Parcial/No no guardaba nada.** Solo hacía `setFeedbackStep(1)`.
   El `fue_util` se escribía únicamente al enviar el formulario de detalle, y
   justo al lado había un «Saltar» que descartaba la respuesta. Quien contestaba
   y cerraba la pestaña contaba como que no había contestado. Esto no lo trajo
   el rediseño: llevaba ahí desde el principio y explica por qué la tasa nunca
   pasó del 14 % ni en su mejor momento.

## Por qué hace falta un guard

Es un fallo que **no se nota**. No rompe nada, no sale en ningún log, y la única
señal es una métrica que hay que ir a mirar a propósito. Alex tardó unos dos
meses en notarlo, y por el camino se perdió el feedback que calibra el motor.
Un test es más barato que volver a darse cuenta tarde.

## Qué NO comprueba

Que la gente responda. Comprueba que se le pregunta y que, si contesta, se
guarda.
"""

import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")


def _fuente():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


class TestSePideEnLasDosVistas(unittest.TestCase):
    def setUp(self):
        self.html = _fuente()

    def test_la_vista_v2_pinta_el_widget_en_el_informe(self):
        """El caso exacto que rompió la recogida: `feedback: null`."""
        i = self.html.index("<V2TabResumen r={r} extras={{")
        j = self.html.index("}} />", i)
        extras = self.html[i:j]
        self.assertNotIn("feedback: null", extras,
                         "el widget de feedback ha vuelto a desaparecer de la v2")
        self.assertIn("feedback: <div className=\"v2-feedback\">{bloqueFeedback}</div>", extras)

    def test_la_vista_clasica_lo_sigue_pintando(self):
        i = self.html.index("const bloqueFeedback = (")
        self.assertGreater(self.html.count("{bloqueFeedback}", i), 1,
                           "bloqueFeedback tiene que pintarse en las DOS vistas")

    def test_la_barra_flotante_se_pinta_en_las_dos_vistas(self):
        i = self.html.index("const barraFeedback = (")
        self.assertEqual(self.html.count("{barraFeedback}", i), 2,
                         "la barra flotante debe pintarse en v2 y en clásica")


class TestElPrimerClicYaGuarda(unittest.TestCase):
    """Sí/Parcial/No tiene que escribir `fue_util` inmediatamente. El detalle
    posterior es opcional y completa la misma fila (el UPDATE del backend hace
    COALESCE, así que no pisa lo ya guardado)."""

    def setUp(self):
        self.html = _fuente()

    def test_existe_el_guardado_inmediato(self):
        i = self.html.index("const guardarVeredicto = (valor) =>")
        j = self.html.index("const elegirVeredicto", i)
        cuerpo = self.html[i:j]
        self.assertIn("/api/sheets/feedback", cuerpo)
        self.assertIn("fue_util: etiqueta", cuerpo)
        self.assertIn("keepalive: true", cuerpo,
                      "sin keepalive el POST muere si cierran la pestaña, que es "
                      "justo el caso que este arreglo quiere cubrir")

    def test_los_tres_botones_del_widget_pasan_por_ahi(self):
        for valor in ("si", "masomenos", "no"):
            self.assertIn(f"onClick={{() => elegirVeredicto('{valor}')}}", self.html,
                          f"el botón «{valor}» del widget no guarda el veredicto")

    def test_la_barra_flotante_tambien_guarda(self):
        i = self.html.index("const responderDesdeSticky = (valor) =>")
        j = self.html.index("};", i)
        self.assertIn("elegirVeredicto(valor)", self.html[i:j])

    def test_ningun_boton_de_veredicto_se_queda_solo_en_setFeedbackStep(self):
        """La forma exacta del fallo original: avanzar de paso sin guardar."""
        sospechosos = re.findall(
            r"setFeedbackCoincide\('(?:si|masomenos|no)'\);\s*setFeedbackStep\(1\);", self.html)
        self.assertEqual(sospechosos, [],
                         "hay un botón que cambia de paso sin guardar el veredicto")

    def test_el_backend_no_pisa_el_comentario_al_reguardar(self):
        """El guardado en dos fases depende de esto: el segundo POST trae
        comentario, el primero no, y ninguno debe borrar lo del otro."""
        with open(os.path.join(RAIZ, "repositories.py"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("async def update_analisis_feedback(")
        j = src.index("@with_retry()", i)
        self.assertIn("COALESCE($1, fue_util)", src[i:j])
        self.assertIn("COALESCE($2, comentario)", src[i:j])


class TestLosTresBotonesPesanLoMismo(unittest.TestCase):
    """`bg-green-900/40` y `bg-yellow-900/30` sobre fondo oscuro se leían como
    texto suelto, mientras `bg-gray-800` sí parecía un botón: la interfaz
    destacaba la respuesta negativa."""

    def setUp(self):
        self.html = _fuente()

    def _zona_feedback(self):
        """Solo la barra flotante y el widget. Fuera de aquí `bg-yellow-900/30`
        es legítimo: lo usan las insignias de estado, que no son botones y
        forman familia con `bg-red-900/30` y `bg-blue-900/30`."""
        i = self.html.index("const barraFeedback = (")
        j = self.html.index("{feedbackStep === 1 &&", i)
        return self.html[i:j]

    def test_no_vuelven_los_fondos_que_no_se_veian(self):
        zona = self._zona_feedback()
        for clase in ("bg-green-900/40", "bg-yellow-900/30", "bg-gray-800"):
            self.assertNotIn(clase, zona,
                             f"{clase} desequilibra los botones de veredicto")

    def test_los_tres_llevan_borde_y_fondo_explicitos(self):
        for color in ("rgba(37,244,100,0.35)", "rgba(250,204,21,0.35)", "rgba(160,160,160,0.35)"):
            self.assertGreaterEqual(self.html.count(color), 2,
                                    f"falta el borde {color} en la barra o en la tarjeta")


class TestLaDecisionEstaDocumentada(unittest.TestCase):
    def test_existe_la_nota(self):
        doc = os.path.join(os.path.dirname(RAIZ), "docs", "feedback-como-se-pide.md")
        if not os.path.exists(doc):
            self.skipTest("docs/ no viaja en la imagen de producción")
        with open(doc, encoding="utf-8") as f:
            texto = f.read()
        for dato in ("14,1 %", "0,31 %", "COALESCE"):
            self.assertIn(dato, texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
