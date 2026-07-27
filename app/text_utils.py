import re

# Siglas que deben preservarse en mayúsculas sin importar su posición en el título.
# Extender esta lista a mano cuando aparezca una sigla nueva.
ACRONIMOS = {
    "DBT", "TCC", "CBT", "TDAH", "PNL", "IA", "ONU", "OMS", "ADN", "VIH", "TOC", "PTSD",
}

_SENTENCE_SPLIT = re.compile(r"([.!?:]\s+)")
# Iniciales pegadas con puntos y sin espacios (ej. "P.I.M.P.", "U.S.A.") — se tratan
# como una unidad y se preservan en mayúsculas, en vez de partirse por palabra.
_INICIALES_CON_PUNTOS = re.compile(r"^([A-Za-z]\.){2,}[A-Za-z]?\.?$")


def _necesita_normalizacion(titulo: str) -> bool:
    letras = [c for c in titulo if c.isalpha()]
    if not letras:
        return False
    return all(c.isupper() for c in letras) or all(c.islower() for c in letras)


def _capitalizar_primera_letra(s: str) -> str:
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
    return s


def normalizar_titulo(titulo: str) -> str:
    """
    Pasa un título a "case de oración" (mayúscula solo al inicio de cada oración),
    preservando las siglas conocidas en ACRONIMOS. Solo toca títulos que están
    completamente en mayúsculas o completamente en minúsculas — un título que ya
    tiene mayúsculas/minúsculas mezcladas se deja intacto para no destruir un
    casing ya correcto (ej. "Homo Deus. Breve historia del mañana").
    """
    titulo = " ".join(titulo.strip().split())
    if not titulo or not _necesita_normalizacion(titulo):
        return titulo

    partes = _SENTENCE_SPLIT.split(titulo)
    resultado = []
    for parte in partes:
        if _SENTENCE_SPLIT.fullmatch(parte):
            resultado.append(parte)
            continue
        palabras = []
        for palabra in parte.split(" "):
            if _INICIALES_CON_PUNTOS.match(palabra):
                palabras.append(palabra.upper())
                continue
            core = palabra.strip("¿?¡!.,;:()\"'“”")
            if core and core.upper() in ACRONIMOS:
                palabras.append(palabra.upper())
            else:
                palabras.append(palabra.lower())
        resultado.append(_capitalizar_primera_letra(" ".join(palabras)))
    return "".join(resultado)
