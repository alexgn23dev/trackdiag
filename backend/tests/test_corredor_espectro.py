"""El corredor de referencia del gráfico de balance espectral.

Es la banda sombreada que dice "aquí cae la música ya editada". Es la pieza que
convierte el gráfico en un diagnóstico: sin ella el usuario ve su curva pero no
tiene con qué compararla, y la palabra "equilibrado" no tiene respaldo.

Precisamente por eso es la pieza más fácil de estropear sin enterarse. Estos
tests vigilan tres cosas:

  1. Que el dato esté bien formado y sea reproducible desde el corpus
     (`backend/scripts/calibrar_corredor.py`), sin duplicados: el corpus trae
     5 temas repetidos con distinto track_id y contarlos varias veces les daría
     un peso que no les corresponde.
  2. Que el gráfico y el veredicto salgan de la MISMA función. El fallo que se
     venía de arreglar era exactamente ese: el rótulo decía "graves elevado"
     mientras la curva se veía recta, porque cada uno leía una medida distinta.
  3. Que no se le dé al corredor más autoridad de la que tiene. Separa poco —
     87 % de previews de catálogo contra 79 % de tracks de usuario — y el
     código tiene que seguir tratándolo como contexto, no como aprobado.

Son comprobaciones sobre el código fuente: la lógica vive en JavaScript. Lo que
sí se ejecuta de verdad es el script de calibración, y la prueba manual con
`previsualizar.py`.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")

# Los centros ISO de tercio de octava hasta 12.5 kHz.
CENTROS_ESPERADOS = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315,
                     400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150,
                     4000, 5000, 6300, 8000, 10000, 12500]


def fuente():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def bandas():
    """Las filas de V2_CORREDOR: (hz, p5, p25, p50, p75, p95)."""
    h = fuente()
    i = h.index("const V2_CORREDOR")
    j = h.index("];", i)
    pat = (r"\{ hz: ([\d.]+), lo: (-?[\d.]+), lo2: (-?[\d.]+), "
           r"med: (-?[\d.]+), hi2: (-?[\d.]+), hi: (-?[\d.]+) \}")
    return [tuple(float(v) for v in m) for m in re.findall(pat, h[i:j])]


class TestElDatoEstaBienFormado(unittest.TestCase):
    def setUp(self):
        self.b = bandas()

    def test_estan_las_bandas_que_tienen_que_estar(self):
        self.assertEqual([x[0] for x in self.b], CENTROS_ESPERADOS)

    def test_los_percentiles_estan_ordenados(self):
        """Los cinco, en orden. Si se cruzaran, el corredor se dibujaría del
        revés y nadie lo notaría a simple vista."""
        for hz, p5, p25, p50, p75, p95 in self.b:
            self.assertLess(p5, p25, f"en {hz} Hz")
            self.assertLess(p25, p50, f"en {hz} Hz")
            self.assertLess(p50, p75, f"en {hz} Hz")
            self.assertLess(p75, p95, f"en {hz} Hz")

    def test_la_banda_interior_cabe_dentro_de_la_exterior(self):
        """El 25-75 se dibuja encima del 5-95 para dar profundidad. Si fuera
        más ancha en alguna banda, el efecto se vería como un escalón."""
        for hz, p5, p25, p50, p75, p95 in self.b:
            self.assertLess(p75 - p25, p95 - p5, f"en {hz} Hz")

    def test_se_corta_en_12_5_khz_y_no_en_16(self):
        """No es un descuido. El corpus son MP3: en 16 kHz el corredor se
        ensancha a 20.7 dB y en 20 kHz a 64, porque ahí describe al compresor y
        no a los sellos. Dibujarlo sería vender como referencia el ruido del
        códec."""
        self.assertEqual(max(x[0] for x in self.b), 12500)

    def test_ninguna_banda_es_absurdamente_ancha(self):
        """Un corredor de 30 dB no informa de nada: cabe todo dentro."""
        for hz, lo, _p25, med, _p75, hi in self.b:
            if hz >= 50:     # por debajo de 50 Hz la dispersión real es enorme
                self.assertLess(hi - lo, 22.0,
                                f"el corredor mide {hi - lo:.1f} dB en {hz} Hz")

    def test_el_cero_es_el_cuerpo_del_tema_y_no_el_pico(self):
        """Anclar al pico dejaba un punto ciego serio: el 87 % de los temas pica
        entre 50 y 80 Hz, así que ahí TODOS valían 0 por construcción y el
        corredor no podía detectar exceso de grave justo donde más importa
        (medido: en 50 Hz la mediana y el p95 valían los dos 0.0).

        Con el 0 en el cuerpo del tema (200 Hz - 2 kHz) hay margen por arriba en
        toda la zona grave, que es lo que vigila este test."""
        por_hz = {x[0]: (x[3], x[5]) for x in self.b}
        for hz in (40, 50, 63, 80, 100):
            med, hi = por_hz[hz]
            self.assertGreater(hi - med, 3.0,
                               f"en {hz} Hz solo hay {hi - med:.1f} dB de margen "
                               f"sobre la mediana: el exceso de grave sería "
                               f"indetectable")
        cuerpo = [x[3] for x in self.b if 200 <= x[0] <= 2000]
        self.assertLess(abs(sum(cuerpo) / len(cuerpo)), 2.5,
                        "el 0 de la escala no está donde dice estar")

    def test_el_pico_del_corredor_esta_en_el_grave(self):
        por_hz = {x[0]: x[3] for x in self.b}
        cima = max(por_hz, key=lambda k: por_hz[k])
        self.assertIn(cima, (40, 50, 63, 80), f"la mediana pica en {cima} Hz")

    def test_es_reproducible_desde_el_corpus(self):
        """El bloque tiene que decir de dónde sale, o dentro de un año nadie
        sabrá si se puede tocar."""
        h = fuente()
        cabecera = h[h.index("// Corredor de referencia"):h.index("const V2_CORREDOR")]
        self.assertIn("322", cabecera)
        self.assertIn("26 sellos", cabecera)
        self.assertTrue(os.path.exists(
            os.path.join(RAIZ, "scripts", "calibrar_corredor.py")),
            "falta el script que lo regenera")


class TestElGraficoYElVeredictoNoPuedenDivergir(unittest.TestCase):
    """El fallo original: el rótulo y la curva salían de medidas distintas."""

    def setUp(self):
        self.h = fuente()

    def test_hay_una_sola_funcion_que_construye_los_puntos(self):
        self.assertIn("function v2PuntosEspectro(", self.h)
        self.assertEqual(self.h.count("function v2PuntosEspectro("), 1)

    def test_la_usan_los_dos(self):
        """El componente para dibujar y el veredicto para juzgar."""
        # dentro de V2Espectro2
        i = self.h.index("function V2Espectro2(")
        j = self.h.index("function V2Escalones(", i)
        self.assertIn("v2PuntosEspectro(", self.h[i:j])
        # y dentro del veredicto
        i = self.h.index("function v2VeredictoEspectro(")
        self.assertIn("v2PuntosEspectro(", self.h[i:i + 500])

    def test_la_referencia_de_nivel_es_una_sola_funcion(self):
        """Si el gráfico anclara el 0 en un sitio y el veredicto en otro, la
        curva podría verse dentro del corredor mientras el rótulo dice que se
        sale. Es el mismo fallo de antes con otra cara."""
        self.assertIn("function v2Referencia(", self.h)
        self.assertEqual(self.h.count("function v2Referencia("), 1)
        self.assertIn("const V2_CUERPO = [200, 2000];", self.h)
        i = self.h.index("function v2VeredictoEspectro(")
        self.assertIn("v2Referencia(pts)", self.h[i:i + 400])
        i = self.h.index("function V2Espectro2(")
        j = self.h.index("function V2Escalones(", i)
        self.assertIn("v2Referencia(puntos)", self.h[i:j])

    def test_la_inclinacion_es_una_constante_compartida(self):
        """Si el gráfico y el veredicto inclinaran distinto, volverían a
        contradecirse. La inclinación vive en v2PuntosEspectro, que usan los
        dos, y no puede haber una segunda copia suelta por ahí."""
        self.assertIn("const V2_TILT = 1.5;", self.h)
        self.assertEqual(self.h.count("const V2_TILT ="), 1)
        i = self.h.index("function v2PuntosEspectro(")
        self.assertIn("V2_TILT", self.h[i:i + 900])
        # y el componente NO puede tener su propia inclinación
        i = self.h.index("function V2Espectro2(")
        j = self.h.index("/** Medidor de un estado", i)
        self.assertNotIn("const TILT =", self.h[i:j])

    def test_el_veredicto_no_pasa_por_un_efecto(self):
        """Con useEffect la tarjeta se pintaba una vez sin veredicto y otra con
        él: parpadeo, y además invisible al render de servidor."""
        i = self.h.index("function V2TabMezcla(")
        j = self.h.index("function V2TabMaster(", i)
        cuerpo = self.h[i:j]
        self.assertIn("const veredicto = v2VeredictoEspectro(", cuerpo)
        self.assertNotIn("onVeredicto", cuerpo)

    def test_la_insignia_sale_del_veredicto_y_no_de_la_regla_vieja(self):
        i = self.h.index("function V2TabMezcla(")
        j = self.h.index("function V2TabMaster(", i)
        cuerpo = self.h[i:j]
        self.assertIn("veredicto.dentro ? 'ok' : 'aviso'", cuerpo)
        # pero la vieja sigue de respaldo por si no hay espectro fino
        self.assertIn("v2TonoEstado('balance_grave'", cuerpo)


class TestLaReglaEsHonesta(unittest.TestCase):
    def setUp(self):
        self.h = fuente()

    def test_la_regla_es_de_rachas_y_esta_justificada(self):
        """Exigir no salirse nunca marcaría como raro al 67 % de los discos
        publicados: con 29 bandas y un corredor 5-95, salirse en alguna es
        estadística, no un defecto."""
        self.assertIn("const V2_RACHA_MINIMA = 4;", self.h)
        i = self.h.index("const V2_RACHA_MINIMA")
        contexto = self.h[max(0, i - 1400):i]
        self.assertIn("racha", contexto.lower())
        # y el reparto medido, escrito donde se pueda auditar
        self.assertIn("87 %", contexto)
        self.assertIn("79 %", contexto)

    def test_se_declara_que_separa_poco(self):
        """Si alguien lee solo el código, tiene que enterarse de que esto no es
        un clasificador de calidad: son 8 puntos de separación."""
        i = self.h.index("const V2_RACHA_MINIMA")
        contexto = self.h[max(0, i - 1800):i]
        self.assertIn("contexto", contexto.lower())
        self.assertIn("POCOS", contexto)

    def test_el_limite_esta_escrito_donde_el_usuario_lo_ve(self):
        """La insignia dice RESULTADO / EQUILIBRADO, que es lo que Alex ha
        especificado. Con solo 8 puntos de separación entre discos editados y
        temas de usuario, eso puede leerse como "tu tema está bien" — que no es
        lo que se ha medido. La contrapartida obligatoria es que el límite esté
        escrito en la pantalla, no solo en un comentario del código."""
        self.assertIn("no si tu tema está bien", self.h)
        self.assertIn("87 %", self.h)
        self.assertIn("79 % de los temas", self.h)
        # y el sesgo del corpus, que es lo que le importa a quien sube un
        # género que no está representado
        self.assertIn("techno duro, trance ni drum", self.h)

    def test_el_veredicto_ignora_lo_que_esta_por_encima_de_12_5_khz(self):
        """La curva se dibuja hasta 16 kHz, pero el corredor solo llega a 12.5.
        Arriba el corpus está condicionado por el códec —cada archivo corta
        entre 16 y 20 kHz según su encoder— así que un diagnóstico apoyado ahí
        mediría al compresor.

        La garantía es estructural: `ref` se construye desde V2_CORREDOR, que
        no tiene esas bandas, y una banda sin entrada devuelve 0 desviación.
        Este test vigila las dos mitades de esa garantía."""
        b = bandas()
        self.assertEqual(max(x[0] for x in b), 12500,
                         "el corredor llega más arriba de lo que debería")
        i = self.h.index("function v2CompararCorredor(")
        cuerpo = self.h[i:i + 1200]
        # sin entrada en el corredor → 0, es decir, no cuenta como desviación
        self.assertIn("if (!c) return 0;", cuerpo)
        # y la curva sí llega a 16 kHz: son cosas distintas a propósito
        self.assertIn("const V2_TOPE_DIBUJO = 16000;", self.h)

    def test_el_veredicto_ignora_lo_que_esta_por_debajo_de_50_hz(self):
        """Ahí el corredor mide entre 21 y 28 dB: cabe casi cualquier cosa, y
        además filtrar por debajo de 30 Hz es una decisión correcta y muy común.
        Un aviso en esa zona era ruido — el primer track de prueba salía
        "revisar" por eso."""
        self.assertIn("const V2_VEREDICTO_DESDE = 50;", self.h)
        i = self.h.index("function v2CompararCorredor(")
        cuerpo = self.h[i:i + 2200]
        self.assertIn("V2_VEREDICTO_DESDE", cuerpo)
        # pero el corredor SÍ se sigue dibujando ahí abajo
        i = self.h.index("const corr = pond ? null :")
        self.assertNotIn("V2_VEREDICTO_DESDE", self.h[i:i + 900])

    def test_una_racha_necesita_el_mismo_signo(self):
        """Cuatro bandas fuera, dos por arriba y dos por abajo, no describen una
        zona: describen una curva movida."""
        i = self.h.index("function v2CompararCorredor(")
        cuerpo = self.h[i:i + 2000]
        self.assertIn("Math.sign", cuerpo)

    def test_el_corredor_no_se_dibuja_en_la_vista_ponderada(self):
        """Se construyó sobre la medida sin ponderar. Superponerlo a la curva
        con ponderación A compararía dos cosas distintas."""
        i = self.h.index("function V2Espectro2(")
        j = self.h.index("function V2Escalones(", i)
        cuerpo = self.h[i:j]
        self.assertIn("const comp = pond ? null : veredicto;", cuerpo)
        self.assertIn("const corr = pond ? null :", cuerpo)

    def test_el_texto_al_usuario_dice_con_que_se_compara(self):
        """Decir "dentro del rango" sin decir de qué rango no significa nada.
        Y tiene que decir QUÉ son: previews de catálogo, no másters, y con el
        sesgo declarado — es la advertencia que necesita quien sube un género
        que no está en el corpus."""
        self.assertIn("322 previews de catálogo de 26 sellos", self.h)
        self.assertIn("sobre todo progressive y house", self.h)

    def test_el_veredicto_describe_en_vez_de_prescribir(self):
        """"Sobra en los graves" implica que hay que bajarlos. Lo único medido
        es que están por encima del 95 % de una colección concreta, y con 8
        puntos de separación entre discos publicados y temas de usuario eso no
        autoriza a recetar nada."""
        self.assertNotIn("'sobra' : 'falta'", self.h)
        self.assertIn("por encima del 95 %", self.h)
        self.assertIn("por debajo del 5 %", self.h)
        # y la insignia no dicta: dice dónde cae
        i = self.h.index("function V2TabMezcla(")
        j = self.h.index("function V2TabMaster(", i)
        self.assertIn("veredicto.dentro ? 'Dentro' : 'Fuera'", self.h[i:j])


class TestElDibujoNoSeDeforma(unittest.TestCase):
    """El SVG se estira con preserveAspectRatio='none': cualquier forma que
    dependa de ser redonda, y cualquier texto, tiene que ir en HTML."""

    def test_el_marcador_del_aviso_no_es_un_circle_del_svg(self):
        h = fuente()
        i = h.index("function V2Espectro2(")
        j = h.index("function V2Escalones(", i)
        self.assertNotIn("<circle", h[i:j],
                         "un <circle> aquí saldría ovalado")
        self.assertIn("borderRadius: '50%'", h[i:j])


if __name__ == "__main__":
    unittest.main(verbosity=2)
