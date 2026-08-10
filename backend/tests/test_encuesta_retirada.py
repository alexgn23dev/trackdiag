"""La encuesta de comunidad, retirada — pero sin borrar nada.

Alex la retiró el 2026-08-10 con una condición explícita: *"no borres los
datos recabados hasta ahora, ya que quizás en un futuro lo retomamos"*.

Eso son dos exigencias que tiran en direcciones opuestas y por eso hay tests:

  * RETIRADA de verdad. No basta con esconder el botón: mientras los endpoints
    de escritura sigan abiertos, una pestaña vieja puede seguir votando y el
    conjunto de datos no tendría fecha de cierre.
  * INTACTA la lectura. Las respuestas, la tabla y la pestaña del dashboard
    tienen que seguir ahí, y volver a encenderla debe ser una variable de
    entorno, no un rollback.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fuente_main():
    with open(os.path.join(RAIZ, "main.py"), encoding="utf-8") as f:
        return f.read()


class TestEstaApagadaPorDefecto(unittest.TestCase):
    def test_el_defecto_de_la_variable_es_apagado(self):
        codigo = _fuente_main()
        self.assertIn('os.environ.get("ENCUESTA_CTA_ACTIVA", "0")', codigo,
                      "el CTA debe arrancar apagado sin depender de Railway")

    def test_sin_variable_de_entorno_queda_apagada(self):
        previo = os.environ.pop("ENCUESTA_CTA_ACTIVA", None)
        try:
            os.environ.setdefault("JWT_SECRET", "test")
            os.environ.setdefault("ADMIN_KEY", "test")
            for mod in [m for m in list(sys.modules) if m == "main"]:
                del sys.modules[mod]
            import main
            self.assertFalse(main._ENCUESTA_CTA_ACTIVA)
        finally:
            if previo is not None:
                os.environ["ENCUESTA_CTA_ACTIVA"] = previo


class TestNoSeAdmitenRespuestasNuevas(unittest.TestCase):
    """Esconder el botón no basta: hay que cerrar la puerta."""

    ESCRITURAS = ["encuesta_voto", "encuesta_comentario",
                  "encuesta_voto_auth", "encuesta_comentario_auth"]

    def test_las_cuatro_escrituras_estan_cerradas(self):
        codigo = _fuente_main()
        for nombre in self.ESCRITURAS:
            i = codigo.find(f"async def {nombre}(")
            self.assertGreater(i, 0, f"no existe {nombre}")
            cuerpo = codigo[i:i + 700]
            self.assertIn("if not _ENCUESTA_CTA_ACTIVA:", cuerpo,
                          f"{nombre} sigue admitiendo escrituras")

    def test_responden_410_y_no_un_error_feo(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi.testclient no disponible")
        os.environ.setdefault("JWT_SECRET", "test")
        os.environ.setdefault("ADMIN_KEY", "test")
        os.environ.pop("ENCUESTA_CTA_ACTIVA", None)
        for mod in [m for m in list(sys.modules) if m == "main"]:
            del sys.modules[mod]
        import main
        with TestClient(main.app) as c:
            r = c.post("/api/encuesta/voto", json={"t": "x", "o": "todo"})
            self.assertEqual(r.status_code, 410)
            self.assertTrue(r.json().get("cerrada"))
            self.assertIn("Gracias", r.json().get("error", ""))

    def test_la_pagina_del_email_dice_que_esta_cerrada(self):
        """Los enlaces de junio siguen llegando hasta que caduque el token.
        Mejor decirlo que enseñar botones que ya no registran nada."""
        codigo = _fuente_main()
        i = codigo.find("async def encuesta_page(")
        cuerpo = codigo[i:i + 1600]
        self.assertIn("if not _ENCUESTA_CTA_ACTIVA:", cuerpo)
        self.assertIn("ya está cerrada", cuerpo)


class TestLosDatosSiguenAhi(unittest.TestCase):
    """La otra mitad del encargo, y la que es fácil romper por descuido."""

    def test_no_hay_ningun_borrado(self):
        codigo = _fuente_main().lower()
        for patron in ("delete from encuesta", "drop table encuesta",
                       "truncate encuesta"):
            self.assertNotIn(patron, codigo, f"aparece '{patron}'")
        with open(os.path.join(RAIZ, "repositories.py"), encoding="utf-8") as f:
            repo = f.read().lower()
        for patron in ("delete from encuesta", "drop table encuesta"):
            self.assertNotIn(patron, repo, f"aparece '{patron}' en repositories")

    def test_no_hay_migracion_que_tire_la_tabla(self):
        alembic = os.path.join(RAIZ, "alembic", "versions")
        if not os.path.isdir(alembic):
            self.skipTest("sin migraciones")
        for nombre in os.listdir(alembic):
            if not nombre.endswith(".py"):
                continue
            with open(os.path.join(alembic, nombre), encoding="utf-8") as f:
                txt = f.read().lower()
            if "encuesta" in txt:
                self.assertNotIn("drop_table", txt, nombre)

    def test_la_lectura_de_resultados_no_esta_gateada(self):
        """El dashboard tiene que poder seguir enseñando lo recogido."""
        codigo = _fuente_main()
        i = codigo.find("async def admin_encuesta(")
        self.assertGreater(i, 0)
        self.assertNotIn("if not _ENCUESTA_CTA_ACTIVA:", codigo[i:i + 700],
                         "los resultados deben poder consultarse aunque esté "
                         "retirada: es justo para lo que se conservan")

    def test_la_pestana_del_dashboard_sigue_existiendo(self):
        panel = os.path.join(os.path.dirname(RAIZ), "frontend", "dashboard.html")
        with open(panel, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("'encuesta', 'Encuesta'", html.replace('"', "'"))
        self.assertIn("/api/admin/encuesta", html)


class TestSePuedeRetomar(unittest.TestCase):
    def test_encenderla_es_una_variable_de_entorno(self):
        os.environ.setdefault("JWT_SECRET", "test")
        os.environ.setdefault("ADMIN_KEY", "test")
        os.environ["ENCUESTA_CTA_ACTIVA"] = "1"
        try:
            for mod in [m for m in list(sys.modules) if m == "main"]:
                del sys.modules[mod]
            import main
            self.assertTrue(main._ENCUESTA_CTA_ACTIVA,
                            "retomarla no debe exigir un rollback de código")
        finally:
            os.environ.pop("ENCUESTA_CTA_ACTIVA", None)
            for mod in [m for m in list(sys.modules) if m == "main"]:
                del sys.modules[mod]

    def test_el_componente_del_frontend_sigue_en_su_sitio(self):
        """Se oculta solo porque /api/encuesta/estado devuelve mostrar:false.
        Borrarlo obligaría a reescribirlo para retomar la encuesta."""
        index = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")
        with open(index, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("function EncuestaCTA(", html)
        self.assertIn("/api/encuesta/estado", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
