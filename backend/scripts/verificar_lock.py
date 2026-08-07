"""Comprueba que el build es reproducible. Se ejecuta DENTRO del Dockerfile.

Falla —y con ello falla el build— si:

  1. Alguna versión instalada no coincide con `requirements.lock.txt`.
  2. El lock no cubre alguna dependencia declarada en `requirements.txt`.
  3. Una dependencia directa está declarada sin `==` (podría resolver otra
     versión en el siguiente build sin que nadie se entere).
  4. Falta instalado algo que el lock declara.

Por qué existe: `pip install -r requirements.txt` con rangos abiertos puede
traer versiones distintas en dos builds del mismo commit. En este motor eso
cambia los números que ve el usuario — `soxr` calcula el sobremuestreo del
true peak. El lock lo fija y esto verifica que se está usando de verdad.

    python scripts/verificar_lock.py [--lock RUTA] [--req RUTA]
"""

import argparse
import os
import re
import sys

try:
    import importlib.metadata as md
except ImportError:  # pragma: no cover
    import importlib_metadata as md


def _normalizar(nombre: str) -> str:
    """PEP 503: los nombres de paquete son insensibles a - _ . y a mayúsculas."""
    return re.sub(r"[-_.]+", "-", nombre).strip().lower()


def _leer_requisitos(ruta: str) -> list:
    """Devuelve [(nombre_original, operador, version)] de un requirements."""
    fuera = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.split("#", 1)[0].strip()
            if not linea or linea.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)?\s*([^\s;]+)?", linea)
            if m:
                fuera.append((m.group(1), m.group(2) or "", m.group(3) or ""))
    return fuera


def main() -> int:
    aqui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", default=os.path.join(aqui, "requirements.lock.txt"))
    ap.add_argument("--req", default=os.path.join(aqui, "requirements.txt"))
    args = ap.parse_args()

    if not os.path.exists(args.lock):
        print(f"FALLA: no existe el lock ({args.lock}). El build no es reproducible.")
        return 1

    lock = _leer_requisitos(args.lock)
    req = _leer_requisitos(args.req)
    lock_por_nombre = {_normalizar(n): v for n, op, v in lock if op == "=="}
    problemas = []

    # 1. Toda dependencia directa tiene que estar pineada con ==
    sin_pinear = [n for n, op, v in req if op != "=="]
    for nombre in sin_pinear:
        problemas.append(
            f"[declarada sin ==] {nombre} en requirements.txt: podría resolver "
            f"otra versión en el próximo build")

    # 2. El lock tiene que cubrir todas las directas, y con la misma versión
    for nombre, op, version in req:
        clave = _normalizar(nombre)
        if clave not in lock_por_nombre:
            problemas.append(
                f"[lock desactualizado] {nombre} está en requirements.txt pero "
                f"no en el lock: regenera el lock")
        elif op == "==" and lock_por_nombre[clave] != version:
            problemas.append(
                f"[lock desactualizado] {nombre}: requirements dice {version}, "
                f"el lock dice {lock_por_nombre[clave]}")

    # 3. Lo instalado tiene que ser exactamente lo que dice el lock
    faltan, distintas = [], []
    for clave, esperada in sorted(lock_por_nombre.items()):
        try:
            instalada = md.version(clave)
        except md.PackageNotFoundError:
            faltan.append(f"[no instalada] {clave}=={esperada}")
            continue
        if _normalizar(instalada) != _normalizar(esperada):
            distintas.append(f"[versión distinta] {clave}: lock {esperada}, instalada {instalada}")
    problemas.extend(faltan)
    problemas.extend(distintas)

    print(f"lock: {args.lock}")
    print(f"  paquetes en el lock       : {len(lock_por_nombre)}")
    print(f"  dependencias directas     : {len(req)}")
    print(f"  transitivas cubiertas     : {len(lock_por_nombre) - len(req)}")

    if problemas:
        print(f"\nBUILD NO REPRODUCIBLE ({len(problemas)} problemas):")
        for p in problemas:
            print("  -", p)
        print("\nRegenera el lock con:")
        print("  docker build -t mentotrack:test . && \\")
        print("  docker run --rm mentotrack:test pip freeze > backend/requirements.lock.txt")
        return 1

    print("\nOK: lo instalado coincide exactamente con el lock, y el lock cubre "
          "todas las dependencias declaradas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
