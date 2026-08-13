"""¿El género escrito a mano entra en el alcance de Mentotrack?

Mentotrack analiza **electrónica de club**: el corredor espectral se calibró
con previews de sellos de club, las reglas de estructura dan por supuestas las
convenciones de una pista de club, y las referencias de loudness son de club.
Fuera de ahí el motor no mide peor — mide *otra cosa*, y da consejos que no
aplican. Desde v0.5.97 esos análisis se rechazan en vez de darlos con un aviso
al pie (decisión de producto de Alex, ago-2026).

El campo libre "Otro" sigue existiendo, y es útil: sirve para subgéneros
concretos (hardgroove, schranz, uk garage, guaracha…) y para electrónica que
no está en el desplegable. Lo que no entra es rock, jazz, flamenco, reggae,
trap, balkan, pop, reggaetón y compañía.

## El criterio, y por qué es asimétrico

    marcador ELECTRÓNICO → acepta
    si no, marcador NO ELECTRÓNICO → rechaza
    si no se reconoce nada → acepta

Las tres decisiones empujan hacia ACEPTAR, a propósito: **el error caro es
rechazar a alguien que sí hace electrónica**. Un falso rechazo es una puerta
cerrada en la cara; un falso aceptado solo produce un informe flojo con su
aviso. Por eso además:

  · la lista electrónica casa por **subcadena** (así "electronico" activa
    "electronic" y "afrohouse" activa "house");
  · la lista no electrónica casa por **palabra completa** (así "rap" no salta
    dentro de "rapsodia" ni "pop" dentro de otra palabra).

Y por eso el orden importa: "afro house, urban, pop" y "edm, disco, funky,
pop" contienen "pop", pero son electrónica y se aceptan porque el marcador
electrónico se mira primero. Medido sobre los 196 géneros distintos que la
gente ha escrito de verdad en producción.
"""

import re
import unicodedata

# Marcadores de electrónica. Casan por SUBCADENA — cuanto más generosa sea
# esta lista, menos falsos rechazos.
GENEROS_ELECTRONICOS = [
    "tech", "techno", "tekno", "house", "trance", "electro", "electronic",
    "edm", "dance", "rave", "club", "minimal", "deep", "dub techno",
    "dnb", "d&b", "drum", "jungle", "neurofunk", "breakbeat", "breaks",
    "garage", "dubstep", "bass music", "midtempo", "bassline",
    "hardstyle", "hardcore", "hardteck", "hardgroove", "gabber", "schranz",
    "makina", "newstyle", "bounce", "hard dance", "psy", "goa", "acid",
    "progressive", "progresive", "progesive", "disco", "italo", "idm", "ebm",
    "industrial", "glitch", "complextro", "big room", "future", "synthwave",
    "vaporwave", "phonk", "ambient", "downtempo", "amapiano", "guaracha",
    "hypnotic", "peak time", "raw", "groove", "melodic", "organic",
    "eurodance", "hi-nrg", "hi nrg", "circuit", "afro house", "afrohouse",
]

# Fuera de alcance. Casan por PALABRA COMPLETA — que "rap" no salte dentro de
# otra palabra. Construida con lo que la gente escribe de verdad en el campo
# libre (196 valores distintos en producción), no de memoria.
GENEROS_NO_ELECTRONICOS = [
    # urbano
    "rap", "hip hop", "hip-hop", "hiphop", "boombap", "boom bap", "drill",
    "trap", "rnb", "r&b", "neo soul", "grime",
    # latino / tropical
    "reggaeton", "reggaetón", "reggeton", "regueton", "dembow", "perreo",
    "reparto", "cumbia", "vallenato", "merengue", "bachata", "salsa",
    "mambo", "rumba", "tango", "samba", "bossa", "bosa nova", "bolero",
    "balada", "mariachi", "ranchera", "banda", "corrido", "chacarera",
    # rock y derivados
    "rock", "metal", "metalcore", "punk", "grunge", "hardcore punk",
    # raíces / acústico
    "jazz", "swing", "blues", "soul", "gospel", "góspel",
    "country", "folk", "folclore", "bluegrass", "acustic", "acústic",
    "reggae", "ska", "dancehall", "flamenco", "fandango",
    "classical", "clásica", "clasica", "clásico", "clasico",
    "sinfónic", "sinfonic", "opera", "ópera", "vals", "paso doble", "polka",
    "celta", "afrobeat", "afrobeats", "balkan", "balcan",
    # pop y otros
    "pop", "kpop", "k-pop", "j-pop", "hyperpop", "indie", "worship",
    "new age", "anime", "soundtrack", "ost",
]


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def marcador_electronico(texto: str):
    """Primer marcador de electrónica encontrado, o None. Casa por subcadena."""
    t = _sin_tildes(texto)
    return next((k for k in GENEROS_ELECTRONICOS if _sin_tildes(k) in t), None)


def marcador_no_electronico(texto: str):
    """Primer marcador fuera de alcance, o None. Casa por palabra completa."""
    t = _sin_tildes(texto)
    for k in GENEROS_NO_ELECTRONICOS:
        patron = r"(?<![a-z0-9])" + re.escape(_sin_tildes(k)) + r"(?![a-z0-9])"
        if re.search(patron, t):
            return k
    return None


def fuera_de_alcance(genero: str, genero_custom: str):
    """(True, término) si este análisis no debe hacerse.

    Solo se juzga el campo libre de "Otro": los géneros del desplegable son
    todos de club por construcción. Si el campo va vacío no se juzga nada —
    el formulario ya lo exige, y aquí no se inventa un rechazo por un dato
    que falta.
    """
    if (genero or "").strip().lower() != "otro":
        return False, None
    custom = (genero_custom or "").strip()
    if len(custom) < 2:
        return False, None
    if marcador_electronico(custom):
        return False, None
    termino = marcador_no_electronico(custom)
    return (True, termino) if termino else (False, None)


MENSAJE_FUERA_DE_ALCANCE = (
    "Mentotrack analiza música electrónica de club: house, techno, trance y "
    "sus derivados. Todo lo que medimos —el rango de referencia del balance, "
    "las normas de estructura, los niveles de loudness— está calibrado con "
    "música de club, así que con «{genero}» te daríamos consejos que no "
    "aplican a tu estilo. Preferimos decírtelo antes que darte un diagnóstico "
    "en el que no puedes confiar.\n\n"
    "Si te hemos entendido mal y sí produces electrónica, escribe el género "
    "con el nombre que uses en tu escena (por ejemplo: hardgroove, uk garage, "
    "nu disco, drum and bass) y vuelve a intentarlo."
)
