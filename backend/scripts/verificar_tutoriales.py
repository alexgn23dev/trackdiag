"""Comprueba que los tutoriales de YouTube del informe siguen existiendo.

    python backend/scripts/verificar_tutoriales.py

Por qué existe: en agosto de 2026 se descubrió que **13 de los 22 enlaces
estaban rotos**. No los habían borrado — el canal los resubió con otro ID, así
que el enlace guardado dejó de valer. Entre mayo y agosto, **33 de los 147
clicks** fueron a un "vídeo no disponible": uno de cada cinco.

Nadie se enteró porque no había forma de enterarse. Esto la da.

NO se mete en el CI: depende de YouTube y de la red, y un test que falla por
causas ajenas al commit acaba ignorándose. Es para lanzarlo a mano de vez en
cuando, o desde un cron si algún día interesa.

Devuelve 1 si algún enlace está roto, para poder encadenarlo.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
INDEX = RAIZ / "frontend" / "index.html"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
AUTOR_ESPERADO = "Producción Online"


def tutoriales():
    """Devuelve [(categoria, titulo, url)] leyendo TUTORIALES_MAP."""
    html = INDEX.read_text(encoding="utf-8")
    i = html.find("const TUTORIALES_MAP = {")
    if i < 0:
        print("No se encuentra TUTORIALES_MAP en index.html", file=sys.stderr)
        sys.exit(2)
    bloque = html[i:html.find("\n    };", i)]
    salida, categoria = [], "?"
    for linea in bloque.splitlines():
        m = re.match(r"\s*(\w+): \[", linea)
        if m:
            categoria = m.group(1)
        for titulo, url in re.findall(r"\{ titulo: '([^']*)', url: '([^']*)'", linea):
            salida.append((categoria, titulo, url))
    return salida


def comprobar(url):
    """(ok, detalle). oembed dice si el vídeo existe y es público."""
    m = re.search(r"[?&]v=([\w-]{11})", url)
    if not m:
        return False, "no parece una URL de vídeo"
    api = ("https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v="
           f"{m.group(1)}&format=json")
    try:
        req = urllib.request.Request(api, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            info = json.load(r)
    except urllib.error.HTTPError as e:
        return False, ("404 — borrado o privado" if e.code == 404
                       else f"HTTP {e.code}")
    except Exception as e:
        return False, f"{type(e).__name__} (¿sin red?)"
    if info.get("author_name") != AUTOR_ESPERADO:
        return False, f"el autor es «{info.get('author_name')}»"
    return True, info.get("title", "")


def main():
    lista = tutoriales()
    print(f"Comprobando {len(lista)} enlaces de TUTORIALES_MAP…\n")
    rotos, desfasados = [], []
    for categoria, titulo, url in lista:
        ok, detalle = comprobar(url)
        if not ok:
            rotos.append((categoria, titulo, url, detalle))
            print(f"  ROTO   [{categoria}] {titulo[:48]}\n         {url}  → {detalle}")
        else:
            # El título del canal puede haber cambiado. No es un fallo, pero
            # conviene saberlo: es el texto que ve el usuario.
            if detalle and detalle.strip() != titulo.strip():
                desfasados.append((categoria, titulo, detalle))
            print(f"  ok     [{categoria}] {titulo[:48]}")

    print(f"\n{len(lista) - len(rotos)}/{len(lista)} enlaces vivos")
    if desfasados:
        print(f"\n{len(desfasados)} con el título cambiado en el canal "
              f"(no es un fallo, pero es el texto que lee el usuario):")
        for categoria, nuestro, suyo in desfasados:
            print(f"  [{categoria}]\n    nuestro: {nuestro}\n    canal:   {suyo}")
    if rotos:
        print(f"\n{len(rotos)} ROTOS. Casi siempre es que el canal los ha "
              f"resubido con otro ID: búscalos por título en el canal y "
              f"actualiza la URL en frontend/index.html.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
