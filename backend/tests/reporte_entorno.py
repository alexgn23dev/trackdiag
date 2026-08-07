"""Reporte de entorno + toda la batería, en un solo comando.

Pensado para ejecutarse DENTRO de la imagen de producción y poder comparar el
resultado con el del entorno local:

    python tests/reporte_entorno.py

Devuelve código 0 solo si pasan los tests unitarios y la validación de true
peak. Imprime primero las versiones, para que el reporte sirva de evidencia
de con qué se obtuvieron los números.
"""

import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.versiones import algoritmos, dependencias, ffmpeg_version  # noqa: E402


def _seccion(titulo):
    print("\n" + "=" * 72)
    print(titulo)
    print("=" * 72)


def main():
    _seccion("ENTORNO")
    deps = dependencias()
    for k, v in deps.items():
        print(f"  {k:14} {v}")
    print(f"  {'ffmpeg':14} {ffmpeg_version()}")
    print(f"  {'plataforma':14} {sys.platform}")

    _seccion("ALGORITMOS")
    algos = algoritmos()
    for k, v in algos.items():
        print(f"  {k:28} {v}")
    try:
        from engine.extractor import _TRUE_PEAK_VALIDATED
        print(f"  {'true_peak_validated':28} {_TRUE_PEAK_VALIDATED}")
    except Exception:
        pass

    _seccion("COEFICIENTES DEL FIR DE REFERENCIA (ITU-R BS.1770-5, anexo 2)")
    from tests import itu_bs1770 as itu
    chk = itu.verificar_coeficientes()
    for k, v in chk.items():
        print(f"  {k:26} {v}")

    _seccion("TESTS UNITARIOS")
    cargador = unittest.TestLoader()
    raiz = os.path.dirname(os.path.abspath(__file__))
    suite = cargador.discover(start_dir=raiz, top_level_dir=os.path.dirname(raiz))
    buffer = io.StringIO()
    resultado = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
    print(buffer.getvalue()[-4000:])
    tests_ok = resultado.wasSuccessful()
    print(f"  → {resultado.testsRun} tests, "
          f"{len(resultado.failures)} fallos, {len(resultado.errors)} errores")

    _seccion("VALIDACIÓN DE TRUE PEAK")
    from tests import validar_true_peak as vtp
    import tempfile
    inf = vtp.validar(os.path.join(tempfile.gettempdir(), "mentotrack_fixtures"))
    print(f"  ffmpeg: {inf['ffmpeg_version'] or 'NO DISPONIBLE'}")
    print(f"  propagación del pico global: {'OK' if inf['ffmpeg_propagacion_ok'] else 'SOSPECHOSA'}")
    print(f"  veredicto: {inf['veredicto']}")
    for f in inf["fallos"]:
        print("   -", f)
    validacion_ok = inf["veredicto"] == "PASA"

    _seccion("ESTUDIO DE LA CONTINUA")
    from tests import estudio_continua as ec
    for fila in ec.estudiar(os.path.join(tempfile.gettempdir(), "mentotrack_fixtures")):
        print(f"  {fila['fixture']} ({fila['regimen']})")
        for metodo, valor in fila["global"].items():
            estable = fila["sin_asentamiento"].get(metodo)
            vs = f"{valor:8.3f}" if isinstance(valor, float) else "     — "
            es = f"{estable:8.3f}" if isinstance(estable, float) else "     — "
            print(f"     {metodo:22} global {vs}   sin asentamiento {es}")

    _seccion("RESUMEN")
    print(json.dumps({
        "tests_ok": tests_ok,
        "validacion_true_peak_ok": validacion_ok,
        "algoritmos": algos,
        "dependencias": deps,
        "ffmpeg": ffmpeg_version(),
    }, indent=2, ensure_ascii=False))

    return 0 if (tests_ok and validacion_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
