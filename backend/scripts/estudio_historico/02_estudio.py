#!/usr/bin/env python3
"""Paso 2 del estudio histórico: ejecuta TODO el análisis sobre estudio.db
(generado por 01_extraer.py) y lo imprime por secciones numeradas.

Cada cifra de estudio-historico-mentotrack.md sale de una sección de este
script (la sección se referencia en el doc como §N).

Uso:  python3 02_estudio.py
"""
import collections
import itertools
import json
import math
import os
import re
import sqlite3
import statistics as st
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
# Ruta del volcado local (ESTUDIO_DB); por defecto junto al script. El volcado
# contiene emails: mantenerlo fuera del repo o gitignored, nunca commitearlo.
db = sqlite3.connect(os.environ.get("ESTUDIO_DB", os.path.join(AQUI, "estudio.db")))
db.row_factory = sqlite3.Row

INTERNOS = {"alexgn23@gmail.com", "alex@producciononline.com", "producciononline.blog@gmail.com"}
FASES = {"Creo que está casi listo": "casi_listo", "Arreglo cerrado, ajustando mezcla": "ajustando_mezcla",
         "Arreglo en progreso": "arreglo", "Idea inicial / loop": "idea"}
OBJETIVOS = {"Todo lo anterior": "todo", "Enviar demo a sellos": "sellos",
             "Publicar y tocar en sesión": "pinchar", "Practicar y aprender": "aprender"}
EXPERIENCIAS = {"Menos de 6 meses": "lt6m", "6 meses a 2 años": "6m_2a",
                "2 a 5 años": "2a_5a", "Más de 5 años": "gt5a"}
DIFICULTADES = {"Que la mezcla suene bien": "mezcla", "Terminar tracks": "terminar",
                "Todo me cuesta": "todo", "Estructurar las ideas": "estructura",
                "Encontrar buenos sonidos": "sonidos"}
MEZCLA_DX = {"carencia_espectral", "harshness_mezcla", "exceso_lowend", "exceso_densidad", "enmascaramiento_bajo"}
ESTRUCT_DX = {"problema_arreglo", "poco_contraste", "falta_impacto", "break_sin_payoff",
              "arreglo_repetitivo", "mezcla_prematura", "track_verde"}
TP_RE = re.compile(r"True peak:\s*(-?[\d.]+)\s*dBTP\s*\((\w+)\)")


def seccion(n, titulo):
    print(f"\n{'='*72}\n§{n} {titulo}\n{'='*72}")


# ---------------------------------------------------------------- §0 higiene
seccion(0, "HIGIENE DE DATOS")
total = db.execute("SELECT COUNT(*) c FROM analisis").fetchone()["c"]
print(f"Total bruto: {total}")

db.execute("DROP TABLE IF EXISTS exclusiones")
db.execute("CREATE TABLE exclusiones (id TEXT PRIMARY KEY, motivo TEXT)")
for r in db.execute("SELECT id, email, diagnostico FROM analisis").fetchall():
    if r["email"] in INTERNOS:
        db.execute("INSERT OR REPLACE INTO exclusiones VALUES (?,?)", (r["id"], "interno"))
    elif not r["diagnostico"]:
        db.execute("INSERT OR REPLACE INTO exclusiones VALUES (?,?)", (r["id"], "fallido_diag_vacio"))

# Duplicados: mismo email + misma huella de audio (bpm, lufs, db_grave,
# duración, key) con <=30 min de separación -> re-subida del mismo bounce.
rows = db.execute("""SELECT id, email, ts, senales FROM analisis
    WHERE diagnostico IS NOT NULL AND diagnostico != ''
      AND senales IS NOT NULL AND senales != 'null'
    ORDER BY email, ts""").fetchall()
prev, dupes = {}, set()
for r in rows:
    s = json.loads(r["senales"])
    k = (r["email"], s.get("bpm"), s.get("lufs_integrado"), s.get("db_grave"),
         s.get("duracion"), s.get("key"))
    t = datetime.fromisoformat(r["ts"])
    if k in prev and (t - prev[k]).total_seconds() <= 1800:
        dupes.add(r["id"])
    prev[k] = t
for i in dupes:
    db.execute("INSERT OR IGNORE INTO exclusiones VALUES (?,?)", (i, "dupe_30min"))
db.commit()
for m in ["interno", "fallido_diag_vacio", "dupe_30min"]:
    c = db.execute("SELECT COUNT(*) c FROM exclusiones WHERE motivo=?", (m,)).fetchone()["c"]
    print(f"  excluidos [{m}]: {c}")
N = db.execute("SELECT COUNT(*) c FROM analisis WHERE id NOT IN (SELECT id FROM exclusiones)").fetchone()["c"]
print(f">>> N LIMPIO: {N}")

# ------------------------------------------------------------- tabla plana
def dur_seg(d):
    if not d or not isinstance(d, str) or ":" not in d:
        return None
    try:
        m, s = d.split(":")
        return int(m) * 60 + int(s)
    except ValueError:
        return None

db.execute("DROP TABLE IF EXISTS flat")
db.execute("""CREATE TABLE flat (
    id TEXT PRIMARY KEY, usuario_id TEXT, email TEXT, ts TEXT, mes TEXT,
    proyecto_id TEXT, version_num INTEGER,
    fase TEXT, objetivo TEXT, genero TEXT, experiencia TEXT, dificultad TEXT,
    diag TEXT, diag_sec TEXT, estado TEXT, madurez TEXT,
    lufs REAL, rango_loudness REAL, true_peak REAL, tp_nivel TEXT,
    diff_grave_media REAL, balance_grave TEXT, densidad TEXT,
    bpm REAL, duracion_seg REAL, contraste TEXT,
    correlacion_lr REAL, nivel_loudness TEXT, scores TEXT, fue_util TEXT)""")
for r in db.execute("SELECT * FROM analisis WHERE id NOT IN (SELECT id FROM exclusiones)"):
    f = json.loads(r["formulario"])
    s = json.loads(r["senales"])
    gen = f.get("genero", "")
    tp, tpn = None, None
    m = TP_RE.search(r["diagnostico"] or "")
    if m:
        tp, tpn = float(m.group(1)), m.group(2)
    db.execute("INSERT INTO flat VALUES (" + ",".join("?" * 30) + ")", (
        r["id"], r["usuario_id"], r["email"], r["ts"], r["ts"][:7],
        r["proyecto_id"], r["version_num"],
        FASES.get(f.get("fase")), OBJETIVOS.get(f.get("objetivo")),
        "Otro" if gen.startswith("Otro") else gen,
        EXPERIENCIAS.get(f.get("experiencia")), DIFICULTADES.get(f.get("dificultad_habitual")),
        s.get("diag_principal"), s.get("diag_secundario"), s.get("estado"), s.get("madurez"),
        s.get("lufs_integrado"), s.get("rango_loudness"), tp, tpn,
        s.get("diff_grave_media"), s.get("balance_grave"), s.get("densidad"),
        s.get("bpm"), dur_seg(s.get("duracion")), s.get("contraste"),
        s.get("correlacion_lr"), s.get("nivel_loudness"),
        json.dumps(s.get("scores") or {}), r["fue_util"]))
db.execute("DROP TABLE IF EXISTS orden")
db.execute("""CREATE TABLE orden AS
    SELECT id, ROW_NUMBER() OVER (PARTITION BY email ORDER BY ts) rn FROM flat""")
db.commit()

# ------------------------------------------------------- §1 descriptivos
seccion(1, "DISTRIBUCIÓN DE DIAGNÓSTICOS Y ESTADO")
for r in db.execute("SELECT diag, COUNT(*) c FROM flat GROUP BY diag ORDER BY c DESC"):
    print(f"  {r['diag']:22} {r['c']:5}  {100*r['c']/N:5.1f}%")
print("estado:")
for r in db.execute("SELECT estado, COUNT(*) c FROM flat GROUP BY estado ORDER BY c DESC"):
    print(f"  {r['estado']:22} {r['c']:5}  {100*r['c']/N:5.1f}%")

seccion(2, "CO-OCURRENCIA (hipótesis con score>=2; lift observado/esperado)")
single, pair = collections.Counter(), collections.Counter()
for r in db.execute("SELECT scores FROM flat"):
    act = {k for k, v in json.loads(r["scores"]).items()
           if isinstance(v, (int, float)) and v >= 2 and k != "sin_diagnostico"}
    for a in act:
        single[a] += 1
    for a, b in itertools.combinations(sorted(act), 2):
        pair[(a, b)] += 1
lifts = [(c / (single[a] * single[b] / N), a, b, c) for (a, b), c in pair.items() if c >= 50]
for lift, a, b, c in sorted(lifts, reverse=True)[:10]:
    print(f"  lift {lift:4.2f}  {a} + {b}  (n={c})")

seccion(3, "MÉTRICAS TÉCNICAS (dónde se concentra la masa)")
def dist(col, cuts, unidad):
    vals = sorted(r[0] for r in db.execute(f"SELECT {col} FROM flat WHERE {col} IS NOT NULL"))
    n = len(vals)
    q = lambda p: vals[int(p * n)]
    print(f"  {col} (n={n}) mediana={q(.5):.1f}{unidad} p25={q(.25):.1f} p75={q(.75):.1f}")
    for lo, hi, label in cuts:
        c = sum(1 for v in vals if (lo is None or v >= lo) and (hi is None or v < hi))
        print(f"    {label:34} {c:5}  {100*c/n:5.1f}%")
dist("lufs", [(None,-14,"< -14 LUFS"), (-14,-10,"-14 a -10"), (-10,-8,"-10 a -8"),
              (-8,-6,"-8 a -6"), (-6,None,">= -6")], " LUFS")
dist("true_peak", [(None,-1,"< -1 dBTP (ok streaming)"), (-1,0,"-1 a 0 (sobre ceiling)"),
                   (0,None,">= 0 (clipping)")], " dBTP")
dist("rango_loudness", [(None,3,"< 3 LU"), (3,6,"3-6 LU"), (6,10,"6-10 LU"), (10,None,">= 10 LU")], " LU")
for col in ["balance_grave", "densidad", "contraste"]:
    row = db.execute(f"SELECT {col} v, COUNT(*) c FROM flat GROUP BY {col} ORDER BY c DESC").fetchall()
    tot = sum(r["c"] for r in row)
    print("  " + col + ": " + " | ".join(f"{r['v']} {100*r['c']/tot:.0f}%" for r in row))

seccion(4, "EVOLUCIÓN TEMPORAL (¡leer con el confound de motor_version!)")
meses = [r["mes"] for r in db.execute("SELECT DISTINCT mes FROM flat WHERE mes>='2026-05' ORDER BY mes")]
ns = {m: db.execute("SELECT COUNT(*) c FROM flat WHERE mes=?", (m,)).fetchone()["c"] for m in meses}
print("  n por mes:", ns)
for d in [r["diag"] for r in db.execute("SELECT diag, COUNT(*) c FROM flat GROUP BY diag ORDER BY c DESC LIMIT 6")]:
    line = f"  {d:22}"
    for m in meses:
        c = db.execute("SELECT COUNT(*) c FROM flat WHERE mes=? AND diag=?", (m, d)).fetchone()["c"]
        line += f" {100*c/ns[m]:5.1f}%"
    print(line)
for r in db.execute("""SELECT substr(a.ts,1,7) mes, MIN(a.motor_version) vmin, MAX(a.motor_version) vmax
    FROM analisis a WHERE a.id NOT IN (SELECT id FROM exclusiones) GROUP BY mes ORDER BY mes"""):
    print(f"  {r['mes']}: motor {r['vmin']} → {r['vmax']}")

# ------------------------------------------- §5 brecha de autopercepción
seccion(5, "BRECHA DE AUTOPERCEPCIÓN")
print("Definición D1: fase declarada = 'Creo que está casi listo' y el motor")
print("encuentra un bloqueo principal (diag_principal != sin_diagnostico).")
row = db.execute("""SELECT COUNT(*) n, SUM(CASE WHEN diag != 'sin_diagnostico' THEN 1 ELSE 0 END) s
    FROM flat WHERE fase='casi_listo'""").fetchone()
print(f"  D1 global: {row['s']}/{row['n']} = {100*row['s']/row['n']:.1f}%")
print(f"  % de análisis subidos como 'casi listo': {100*row['n']/N:.1f}%")
row = db.execute("""SELECT COUNT(*) n,
    SUM(CASE WHEN diag NOT IN ('sin_diagnostico','enmascaramiento_bajo') THEN 1 ELSE 0 END) s
    FROM flat WHERE fase='casi_listo'""").fetchone()
print(f"  D1 ajustada (sin enmascaramiento_bajo, hipótesis post-estudio-613): {100*row['s']/row['n']:.1f}%")
row = db.execute("""SELECT COUNT(*) n, SUM(CASE WHEN diag != 'sin_diagnostico' THEN 1 ELSE 0 END) s
    FROM (SELECT diag, fase FROM flat ORDER BY ts LIMIT 613) WHERE fase='casi_listo'""").fetchone()
print(f"  Réplica primeros 613 limpios: {row['s']}/{row['n']} = {100*row['s']/row['n']:.1f}%")
g = [r["g"] for r in db.execute("""SELECT AVG(CASE WHEN diag != 'sin_diagnostico' THEN 100.0 ELSE 0 END) g
    FROM flat WHERE fase='casi_listo' GROUP BY email""")]
print(f"  Ponderada 1 usuario = 1 voto: {st.mean(g):.1f}% ({len(g)} usuarios)")
print("Control por fase declarada (% con bloqueo):")
for r in db.execute("""SELECT fase, COUNT(*) n, SUM(CASE WHEN diag != 'sin_diagnostico' THEN 1 ELSE 0 END) s
    FROM flat GROUP BY fase ORDER BY n DESC"""):
    print(f"  {r['fase']:18} n={r['n']:5}  {100*r['s']/r['n']:5.1f}%")
print("Fase declarada x madurez del audio (% avanzado):")
for r in db.execute("""SELECT fase, COUNT(*) n, SUM(CASE WHEN madurez='avanzado' THEN 1 ELSE 0 END) s
    FROM flat GROUP BY fase ORDER BY n DESC"""):
    print(f"  {r['fase']:18} {100*r['s']/r['n']:5.1f}%")
print("Segmentos (casi_listo, D1):")
for col in ["objetivo", "experiencia", "dificultad", "mes"]:
    for r in db.execute(f"""SELECT {col} v, COUNT(*) n,
            SUM(CASE WHEN diag != 'sin_diagnostico' THEN 1 ELSE 0 END) s
        FROM flat WHERE fase='casi_listo' GROUP BY {col} ORDER BY n DESC"""):
        print(f"  {col}={str(r['v']):18} n={r['n']:5}  {100*r['s']/r['n']:5.1f}%")
for lo, hi, lab in [(1, 1, "1º análisis"), (2, 4, "2º-4º"), (5, 9999, "5º+")]:
    row = db.execute("""SELECT COUNT(*) n, SUM(CASE WHEN f.diag != 'sin_diagnostico' THEN 1 ELSE 0 END) s
        FROM flat f JOIN orden o ON o.id=f.id
        WHERE f.fase='casi_listo' AND o.rn BETWEEN ? AND ?""", (lo, hi)).fetchone()
    print(f"  nº análisis del usuario {lab:12} n={row['n']:5}  {100*row['s']/row['n']:5.1f}%")
row = db.execute("""SELECT COUNT(*) n,
    SUM(CASE WHEN diag='sin_diagnostico' AND madurez='avanzado' THEN 1 ELSE 0 END) s
    FROM flat WHERE fase IN ('idea','arreglo')""").fetchone()
print(f"Brecha inversa (fase temprana declarada, audio limpio+avanzado): {row['s']}/{row['n']} = {100*row['s']/row['n']:.1f}%")

# ------------------------------------------------- §6 comportamiento de uso
seccion(6, "COMPORTAMIENTO DE USO")
rows = db.execute("SELECT email, COUNT(*) c FROM flat GROUP BY email").fetchall()
usuarios = len(rows)
one = sum(1 for r in rows if r["c"] == 1)
print(f"  usuarios: {usuarios} | one-shot: {one} ({100*one/usuarios:.1f}%) | repiten: {usuarios-one} ({100*(usuarios-one)/usuarios:.1f}%)")
top = db.execute("SELECT SUM(c) s FROM (SELECT COUNT(*) c FROM flat GROUP BY email ORDER BY c DESC LIMIT 17)").fetchone()["s"]
print(f"  top 17 usuarios (2.2%): {top} análisis = {100*top/N:.1f}% del total")
gaps = []
for r in rows:
    if r["c"] < 2:
        continue
    ts = [datetime.fromisoformat(x["ts"]) for x in db.execute(
        "SELECT ts FROM flat WHERE email=? ORDER BY ts", (r["email"],))]
    gaps += [(b - a).total_seconds() / 3600 for a, b in zip(ts, ts[1:])]
gaps.sort()
print(f"  tiempo entre análisis (n={len(gaps)}): mediana {gaps[len(gaps)//2]:.1f}h | "
      f"<1h {100*sum(1 for g in gaps if g<1)/len(gaps):.1f}% | >7d {100*sum(1 for g in gaps if g>168)/len(gaps):.1f}%")
pares = db.execute("""SELECT a.diag d1, b.diag d2, a.lufs l1, b.lufs l2,
        a.true_peak t1, b.true_peak t2, a.madurez m1, b.madurez m2, a.ts ts1, b.ts ts2
    FROM flat a JOIN flat b ON a.proyecto_id=b.proyecto_id AND a.proyecto_id IS NOT NULL
        AND b.version_num=a.version_num+1 AND a.version_num=1""").fetchall()
con_diag = sum(1 for p in pares if p["d1"] != "sin_diagnostico")
cambia = sum(1 for p in pares if p["d1"] != "sin_diagnostico" and p["d2"] != p["d1"])
limpio = sum(1 for p in pares if p["d1"] != "sin_diagnostico" and p["d2"] == "sin_diagnostico")
tp_pairs = [(p["t1"], p["t2"]) for p in pares if p["t1"] is not None and p["t2"] is not None]
print(f"  pares v1→v2 mismo proyecto: {len(pares)} (v1 con bloqueo: {con_diag})")
print(f"    bloqueo principal cambia: {cambia} ({100*cambia/con_diag:.1f}%) | sale limpio: {limpio} ({100*limpio/con_diag:.1f}%)")
print(f"    clipping v1: {sum(1 for a,b in tp_pairs if a>=0)}/{len(tp_pairs)} → v2: {sum(1 for a,b in tp_pairs if b>=0)}/{len(tp_pairs)}")
dl = [p["l2"] - p["l1"] for p in pares if p["l1"] is not None and p["l2"] is not None]
gv = sorted((datetime.fromisoformat(p["ts2"]) - datetime.fromisoformat(p["ts1"])).total_seconds()/3600 for p in pares)
print(f"    ΔLUFS mediana {st.median(dl):+.1f} dB | tiempo v1→v2 mediana {gv[len(gv)//2]:.1f}h")

# ------------------------------------------------- §7 contraintuitivos
seccion(7, "PATRONES CONTRAINTUITIVOS")
print("7a. Experiencia vs clipping (true peak >= 0 dBTP):")
datos = {}
for r in db.execute("""SELECT experiencia e, COUNT(*) n, SUM(CASE WHEN true_peak >= 0 THEN 1 ELSE 0 END) c
    FROM flat WHERE true_peak IS NOT NULL GROUP BY e"""):
    datos[r["e"]] = (r["n"], r["c"])
for e in ["lt6m", "6m_2a", "2a_5a", "gt5a"]:
    n, c = datos[e]
    print(f"  {e:6} n={n:4}  clipping={100*c/n:.1f}%")
n1, c1 = datos["lt6m"]; n2, c2 = datos["gt5a"]
p = (c1 + c2) / (n1 + n2)
z = (c2/n2 - c1/n1) / math.sqrt(p*(1-p)*(1/n1+1/n2))
print(f"  z lt6m vs gt5a = {z:.1f}")
print("7b. Dificultad declarada vs dominio del diagnóstico (filas con bloqueo):")
for r in db.execute("SELECT dificultad d, COUNT(*) n FROM flat WHERE diag != 'sin_diagnostico' GROUP BY d ORDER BY n DESC"):
    nm = db.execute(f"SELECT COUNT(*) c FROM flat WHERE dificultad=? AND diag IN ({','.join('?'*len(MEZCLA_DX))})",
                    [r["d"]] + list(MEZCLA_DX)).fetchone()["c"]
    ne = db.execute(f"SELECT COUNT(*) c FROM flat WHERE dificultad=? AND diag IN ({','.join('?'*len(ESTRUCT_DX))})",
                    [r["d"]] + list(ESTRUCT_DX)).fetchone()["c"]
    print(f"  {r['d']:12} n={r['n']:4}  dx_mezcla={100*nm/r['n']:.1f}%  dx_estructura={100*ne/r['n']:.1f}%")
print("7c. Género vs clipping / brecha (top 6 por n):")
for r in db.execute("SELECT genero g, COUNT(*) n FROM flat GROUP BY g ORDER BY n DESC LIMIT 6"):
    clip = db.execute("""SELECT COUNT(*) n, SUM(CASE WHEN true_peak>=0 THEN 1 ELSE 0 END) c
        FROM flat WHERE genero=? AND true_peak IS NOT NULL""", (r["g"],)).fetchone()
    br = db.execute("""SELECT COUNT(*) n, SUM(CASE WHEN diag != 'sin_diagnostico' THEN 1 ELSE 0 END) s
        FROM flat WHERE genero=? AND fase='casi_listo'""", (r["g"],)).fetchone()
    print(f"  {r['g']:18} clipping={100*clip['c']/clip['n']:.1f}% (n={clip['n']})  brecha={100*br['s']/br['n']:.1f}% (n={br['n']})")
print("7d. fue_util por diagnóstico (poca muestra, no publicable):")
for r in db.execute("""SELECT diag, COUNT(*) n,
        SUM(CASE WHEN fue_util='Sí' THEN 1 ELSE 0 END) s
    FROM flat WHERE fue_util IS NOT NULL AND fue_util != '' GROUP BY diag HAVING n >= 20 ORDER BY n DESC"""):
    print(f"  {r['diag']:22} n={r['n']:3}  'Sí'={100*r['s']/r['n']:.1f}%")
print("\nFIN. Cifras citadas en estudio-historico-mentotrack.md")
