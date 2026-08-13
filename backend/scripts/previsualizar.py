"""Ver el informe de Mentotrack sin subir nada.

    python backend/scripts/previsualizar.py "ruta/al/track.wav"
    python backend/scripts/previsualizar.py --carpeta "carpeta con tracks"
    python backend/scripts/previsualizar.py                  # repite los últimos

Abre el navegador con **el informe de verdad**: el mismo `DiagnosticoScreen` de
`frontend/index.html`, vivo e interactivo (las pestañas funcionan), alimentado
por el motor real. No hay subida, no hay Railway, no hay formulario.

## Por qué existe

El ciclo de revisar un cambio era: exportar un bounce, arrastrarlo, rellenar el
cuestionario, esperar el análisis, mirar. Minutos por vuelta, y casi todo ese
tiempo se va en cosas que no se están revisando.

Aquí el análisis se hace **una vez por track** y se guarda. A partir de ahí,
tocar `index.html` y refrescar el navegador es instantáneo: el HTML se lee del
disco en cada petición, así que se ve el cambio sin reanalizar nada.

## Cuándo se reanaliza solo

Cuando cambia algo de `backend/engine/`. La caché guarda la huella de esos
ficheros: si tocas el extractor o las reglas, se rehace sin que tengas que
acordarte. Con `--reanalizar` se fuerza.

## Qué NO es

No es la app entera: no hay login, ni panel, ni guardado. Es la pantalla del
informe, que es lo que se itera. Los botones que llamarían al servidor
(feedback, tutoriales) responden en vacío para que nada reviente ni escriba.
"""

import argparse
import hashlib
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent          # backend/
REPO = RAIZ.parent
FRONT = REPO / "frontend"
CACHE = RAIZ / ".cache_previsualizacion"
RECIENTES = CACHE / "_recientes.json"
EXTENSIONES = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".ogg"}

sys.path.insert(0, str(RAIZ))

CONTEXTO_POR_DEFECTO = {
    "genero": "techno",
    "genero_custom": "",
    "fase": "casi_listo",
    "objetivo": "sellos",
    "experiencia": "2-5",
    "dificultad_habitual": "mezcla",
    "bloqueo_percibido": "",
    "referencia": "",
    "tiempo_disponible": "",
}


# --------------------------------------------------------------------------
# Caché
# --------------------------------------------------------------------------
def huella_motor() -> str:
    """Huella de `backend/engine/`. Si cambia, la caché caduca sola.

    Se usa el contenido y no la fecha: un `git checkout` de ida y vuelta deja
    fechas nuevas con el mismo código, y reanalizar 30 tracks para nada duele.
    """
    h = hashlib.sha1()
    for p in sorted((RAIZ / "engine").glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def huella_audio(ruta: Path) -> str:
    """Huella del archivo sin leerlo entero: tamaño + los extremos.

    Un track de 80 MB tarda en hashearse del todo y no hace falta: dos archivos
    distintos con el mismo tamaño y los mismos 2 MB de los bordes no van a
    aparecer en una carpeta de bounces.
    """
    tam = ruta.stat().st_size
    h = hashlib.sha1(str(tam).encode())
    with open(ruta, "rb") as f:
        h.update(f.read(1 << 20))
        if tam > 2 << 20:
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read())
    return h.hexdigest()[:16]


def analizar(ruta: Path, contexto: dict, forzar: bool) -> dict:
    """Diagnóstico del track, de la caché o del motor."""
    CACHE.mkdir(exist_ok=True)
    clave = f"{huella_audio(ruta)}-{huella_motor()}"
    destino = CACHE / f"{clave}.json"
    if destino.exists() and not forzar:
        try:
            return json.loads(destino.read_text(encoding="utf-8"))
        except Exception:
            pass    # caché corrupta: se rehace

    from engine.diagnostico import generar_diagnostico
    from engine.extractor import extraer_senales

    t0 = time.time()
    senales = extraer_senales(str(ruta))
    resultado = generar_diagnostico(senales, contexto)
    resultado.setdefault("versiones", {})["backend_version"] = "local"
    resultado["_previsualizacion"] = {
        "archivo": ruta.name,
        "segundos": round(time.time() - t0, 1),
        "motor": huella_motor(),
    }
    destino.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    return resultado


# --------------------------------------------------------------------------
# La página: el index.html real con el arranque cambiado
# --------------------------------------------------------------------------
def pagina(indice: int, tracks: list, datos: list, v2: bool,
           pestana: str = "") -> bytes:
    """Sirve `frontend/index.html` tal cual, cambiando UNA línea.

    La línea es la que monta la app entera; en su lugar se monta directamente la
    pantalla del informe. Todo lo demás —componentes, estilos, versión— es el
    archivo real leído del disco en esta misma petición, así que cualquier
    edición se ve al refrescar.
    """
    html = (FRONT / "index.html").read_text(encoding="utf-8")

    arranque = "ReactDOM.render(<App />, document.getElementById('root'));"
    if arranque not in html:
        raise SystemExit(
            "No encuentro la línea de arranque en index.html. Si la has "
            "cambiado, actualiza la constante `arranque` en este script."
        )

    props = {
        "resultado": datos[indice],
        "contexto": CONTEXTO_POR_DEFECTO,
        "userEmail": "previsualizacion@local",
        "opciones": {"generos": [], "fases": [], "objetivos": []},
        "nombreProyecto": Path(tracks[indice]).stem,
        "comunidadOk": False,
        "proyectoNombreResuelto": Path(tracks[indice]).stem,
        "versionActual": 1,
        "proyectoIdActual": None,
        "sesionIniciada": False,
    }
    montaje = f"""
        (function () {{
            const props = Object.assign({{}}, {json.dumps(props, ensure_ascii=False)}, {{
                file: {{ name: {json.dumps(Path(tracks[indice]).name)} }},
                onReset: () => (window.location = '/'),
                onIrAPerfil: () => {{}},
                onVerComparativa: () => {{}},
                onAbrirPanel: () => {{}},
            }});
            ReactDOM.render(<DiagnosticoScreen {{...props}} />, document.getElementById('root'));
        }})();
    """
    html = html.replace(arranque, montaje)

    # Abrir directamente en una pestaña concreta. Sin esto hay que hacer clic
    # cada vez que se refresca, que es justo el rato que esta herramienta ahorra.
    if pestana:
        viejo = "const [v2Tab, setV2Tab] = useState('resumen');"
        if viejo in html:
            html = html.replace(
                viejo,
                f"const [v2Tab, setV2Tab] = useState('{pestana}');", 1)

    # La vista v2 se resuelve una vez al montar, leyendo la URL. Se deja fijada
    # aquí para que el selector de abajo pueda cambiarla sin depender de eso.
    marca_v2 = "1" if v2 else "0"
    barra = f"""
<script>
  try {{ sessionStorage.setItem('mt_v2', '{marca_v2}'); }} catch (e) {{}}
  // Silencia las llamadas al servidor: esto es una previsualización, no debe
  // escribir nada en ningún sitio.
  (function () {{
    const real = window.fetch;
    window.fetch = function (u, o) {{
      if (String(u).includes('/api/')) {{
        return Promise.resolve(new Response('{{}}', {{
          status: 200, headers: {{ 'Content-Type': 'application/json' }} }}));
      }}
      return real.apply(this, arguments);
    }};
  }})();
</script>
<style>
  #previsualizador {{
    position: fixed; left: 12px; bottom: 12px; z-index: 99999;
    display: flex; align-items: center; gap: 8px;
    background: rgba(18,18,18,.94); border: 1px solid #333; border-radius: 8px;
    padding: 6px 10px; font: 500 11px/1.4 system-ui, sans-serif; color: #999;
    backdrop-filter: blur(6px); box-shadow: 0 4px 18px rgba(0,0,0,.5);
  }}
  #previsualizador a, #previsualizador button {{
    color: #ccc; text-decoration: none; background: #2a2a2a; border: 1px solid #3a3a3a;
    border-radius: 5px; padding: 3px 8px; cursor: pointer; font: inherit;
  }}
  #previsualizador a:hover, #previsualizador button:hover {{ background: #383838; color: #fff; }}
  #previsualizador .n {{ color: #6f6f6f; }}
  @media print {{ #previsualizador {{ display: none; }} }}
</style>
<div id="previsualizador">
  <a href="/ver/{max(0, indice - 1)}?v2={marca_v2}" title="Anterior">&#8592;</a>
  <span class="n">{indice + 1}/{len(tracks)}</span>
  <strong style="color:#ddd;max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
    {Path(tracks[indice]).name}</strong>
  <a href="/ver/{min(len(tracks) - 1, indice + 1)}?v2={marca_v2}" title="Siguiente">&#8594;</a>
  <a href="/ver/{indice}?v2={'0' if v2 else '1'}">{'clásica' if v2 else 'v2'}</a>
  <a href="/">lista</a>
</div>
"""
    return (html.replace("</body>", barra + "</body>")).encode("utf-8")


def marco_movil(src: str, ancho: int) -> bytes:
    """Envuelve cualquier página del mismo origen en un iframe de ancho fijo.

    Chrome impone aquí una ventana mínima de ~500 px, así que `--window-size`
    no sirve para comprobar móvil. Un iframe SÍ crea su propio viewport: las
    media queries responden a su ancho, y como va servido del mismo origen se
    puede además medir desbordes desde fuera.
    """
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Móvil {ancho}px</title><style>
 body{{background:#000;margin:0;padding:14px;font:12px system-ui;color:#777}}
 iframe{{width:{ancho}px;height:2400px;border:1px solid #333;background:#151515;display:block}}
 .n{{margin-bottom:8px}}
</style></head><body>
<div class="n">viewport del iframe: {ancho} px · <span id="MEDIDA">midiendo…</span></div>
<iframe id="f" src="{src}"></iframe>
<script>
document.getElementById('f').addEventListener('load', function () {{
  setTimeout(function () {{
    var d = this.contentDocument, w = d.documentElement.clientWidth, malos = [];
    d.querySelectorAll('*').forEach(function (el) {{
      var r = el.getBoundingClientRect();
      if (r.width > 0 && (r.right > w + 1 || r.left < -1)
          && !malos.some(function (m) {{ return m.contains(el); }})) malos.push(el);
    }});
    document.getElementById('MEDIDA').textContent =
      'client=' + w + ' scroll=' + d.documentElement.scrollWidth + ' | ' +
      (malos.length ? malos.slice(0, 5).map(function (e) {{
        var r = e.getBoundingClientRect();
        return e.tagName + '.' + (e.className || '').toString().slice(0, 30) +
               '[' + Math.round(r.left) + '→' + Math.round(r.right) + ']';
      }}).join(' ;; ') : 'NADA SE SALE');
  }}.bind(this), 2200);
}});
</script></body></html>""".encode("utf-8")


def portada(tracks: list, datos: list) -> bytes:
    filas = []
    for i, t in enumerate(tracks):
        d = datos[i]
        pr = (d.get("diagnostico_principal") or {}).get("titulo", "—")
        est = d.get("estado_track", "—")
        seg = (d.get("_previsualizacion") or {}).get("segundos", "—")
        filas.append(
            f'<tr><td class="n">{i + 1}</td>'
            f'<td><a href="/ver/{i}?v2=1">{Path(t).name}</a></td>'
            f'<td class="e">{est}</td><td class="p">{pr}</td>'
            f'<td class="n">{seg}s</td></tr>')
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Previsualizar informes · Mentotrack</title><style>
 body{{background:#0f0f0f;color:#ddd;font:14px/1.6 system-ui,sans-serif;padding:32px;margin:0}}
 .caja{{max-width:1000px;margin:auto}}
 h1{{font-size:16px;letter-spacing:.08em;text-transform:uppercase;color:#999;font-weight:700;margin:0 0 4px}}
 p.sub{{color:#6f6f6f;margin:0 0 22px;font-size:12px}}
 table{{border-collapse:collapse;width:100%}}
 td,th{{padding:8px 10px;border-bottom:1px solid #242424;text-align:left;vertical-align:top}}
 th{{color:#6f6f6f;font-size:10px;letter-spacing:.1em;text-transform:uppercase;font-weight:700}}
 a{{color:#c4a6ff;text-decoration:none}} a:hover{{text-decoration:underline}}
 .n{{color:#5a5a5a;font-variant-numeric:tabular-nums;white-space:nowrap}}
 .e{{color:#25F464;font-size:12px}} .p{{color:#9a9a9a;font-size:12px}}
 code{{background:#1c1c1c;padding:2px 6px;border-radius:4px;color:#bbb;font-size:12px}}
</style></head><body><div class="caja">
<h1>Previsualizar informes</h1>
<p class="sub">{len(tracks)} tracks analizados. Editar <code>frontend/index.html</code> y refrescar
basta — solo se reanaliza si cambia <code>backend/engine/</code>.</p>
<table><tr><th></th><th>Track</th><th>Estado</th><th>Diagnóstico principal</th><th>Análisis</th></tr>
{''.join(filas)}</table></div></body></html>""".encode("utf-8")


# --------------------------------------------------------------------------
def servir(tracks, datos, puerto):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(FRONT), **k)

        def log_message(self, *a):
            pass    # sin ruido en la consola

        def _enviar(self, cuerpo, tipo="text/html; charset=utf-8"):
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            partes = urllib.parse.urlparse(self.path)
            ruta = partes.path
            if ruta == "/":
                return self._enviar(portada(tracks, datos))
            if ruta.startswith("/ver/"):
                try:
                    i = max(0, min(len(tracks) - 1, int(ruta.split("/")[2])))
                except (ValueError, IndexError):
                    i = 0
                q = urllib.parse.parse_qs(partes.query)
                pes = (q.get("tab", [""])[0] or "").strip().lower()
                if pes not in ("", "resumen", "plan", "mezcla", "master", "detalle"):
                    pes = ""
                return self._enviar(pagina(i, tracks, datos,
                                           q.get("v2", ["1"])[0] != "0", pes))
            if ruta.startswith("/movil/"):
                try:
                    i = max(0, min(len(tracks) - 1, int(ruta.split("/")[2])))
                except (ValueError, IndexError):
                    i = 0
                q = urllib.parse.parse_qs(partes.query)
                try:
                    ancho = max(280, min(900, int(q.get("w", ["390"])[0])))
                except ValueError:
                    ancho = 390
                pes = (q.get("tab", [""])[0] or "").strip().lower()
                if pes not in ("", "resumen", "plan", "mezcla", "master", "detalle"):
                    pes = ""
                src = f"/ver/{i}?v2=1" + (f"&tab={pes}" if pes else "")
                return self._enviar(marco_movil(src, ancho))
            if ruta == "/home":
                # La portada REAL: index.html tal cual, con App montada y los
                # /api/* respondiendo vacío. Antes se siembra un historial
                # local para que el enlace "Ver historial (N)" se vea, que
                # forma parte del diseño y con localStorage virgen no sale.
                cuerpo = ("""<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body><script>
 try { localStorage.setItem('mentotrack_historial', JSON.stringify(
     Array.from({length: 50}, function (_, i) { return { id: 'previs-' + i }; }))); } catch (e) {}
 location.replace('/index.html');
</script></body></html>""").encode("utf-8")
                return self._enviar(cuerpo)
            if ruta == "/homemovil":
                q = urllib.parse.parse_qs(partes.query)
                try:
                    ancho = max(280, min(900, int(q.get("w", ["390"])[0])))
                except ValueError:
                    ancho = 390
                return self._enviar(marco_movil("/home", ancho))
            if ruta == "/api/portada/avatares":
                # Muestra representativa para poder ver la portada real: dos
                # "fotos" que no existen (el onError del frontend enseña la
                # inicial) y dos iniciales. El total imita al de producción.
                cuerpo = json.dumps({
                    "avatares": [{"foto": None, "inicial": l} for l in "AMRD"],
                    "total": 967,
                }).encode("utf-8")
                return self._enviar(cuerpo, "application/json")
            if ruta.startswith("/api/"):
                return self._enviar(b"{}", "application/json")
            return super().do_GET()    # el resto de frontend/: logo, fuentes, css

        def do_POST(self):
            self._enviar(b"{}", "application/json")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", puerto), Handler) as srv:
        url = f"http://127.0.0.1:{puerto}/"
        print(f"\n  Listo → {url}")
        print("  Edita frontend/index.html y refresca. Ctrl-C para salir.")
        print("  Truco: ?tab=mezcla abre esa pestaña · /movil/0?w=390 simula móvil.")
        print("  La portada: /home (real, con API vacía) · /homemovil?w=390.\n")
        threading.Timer(0.7, lambda: webbrowser.open(url + "ver/0?v2=1")).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n  Adiós.")


def recopilar(entradas, carpeta):
    rutas = []
    for e in list(entradas) + ([carpeta] if carpeta else []):
        p = Path(e).expanduser()
        if p.is_dir():
            rutas += [q for q in sorted(p.iterdir())
                      if q.suffix.lower() in EXTENSIONES]
        elif p.is_file() and p.suffix.lower() in EXTENSIONES:
            rutas.append(p)
        elif p.exists():
            print(f"  (ignorado, no es audio que Mentotrack acepte: {p.name})")
        else:
            print(f"  (no existe: {e})")
    return rutas


def main():
    ap = argparse.ArgumentParser(
        description="Ver el informe de Mentotrack sin subir nada.")
    ap.add_argument("tracks", nargs="*", help="archivos o carpetas de audio")
    ap.add_argument("--carpeta", help="analiza todo el audio de esta carpeta")
    ap.add_argument("--reanalizar", action="store_true",
                    help="ignora la caché y vuelve a medir")
    ap.add_argument("--puerto", type=int, default=8765)
    args = ap.parse_args()

    rutas = recopilar(args.tracks, args.carpeta)
    if not rutas and RECIENTES.exists():
        rutas = [Path(p) for p in json.loads(RECIENTES.read_text()) if Path(p).exists()]
        if rutas:
            print(f"Sin argumentos: repito los {len(rutas)} últimos.")
    if not rutas:
        ap.error("no hay tracks. Pasa un archivo, o --carpeta con una carpeta.")

    CACHE.mkdir(exist_ok=True)
    RECIENTES.write_text(json.dumps([str(p) for p in rutas]), encoding="utf-8")

    datos, buenos = [], []
    for i, r in enumerate(rutas, 1):
        marca = f"  [{i}/{len(rutas)}] {r.name[:52]}"
        print(f"{marca} …", end="", flush=True)
        try:
            t0 = time.time()
            d = analizar(r, CONTEXTO_POR_DEFECTO, args.reanalizar)
            tarda = time.time() - t0
            print(f"\r{marca}  {'caché' if tarda < 0.4 else f'{tarda:.0f}s'}      ")
            datos.append(d)
            buenos.append(str(r))
        except Exception as e:
            print(f"\r{marca}  FALLA: {type(e).__name__}: {str(e)[:60]}   ")

    if not datos:
        raise SystemExit("Ningún track se pudo analizar.")
    servir(buenos, datos, args.puerto)


if __name__ == "__main__":
    main()
