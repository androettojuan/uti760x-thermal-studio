"""Idiomas: textos, numeros y fechas segun el idioma elegido.

El texto en castellano del codigo es la clave: `_("Abrir")` devuelve la
traduccion del idioma activo (thermal_studio/idiomas/<codigo>.json), o el
mismo texto si es castellano o si falta. Python puro, sin Qt, para que
core/ lo pueda usar.

El idioma se elige al instalar (el instalador lo guarda en la configuracion)
y se puede cambiar en Ver > Idioma; se aplica al volver a abrir el programa.
"""
import json
import locale
from functools import lru_cache
from pathlib import Path

ESPANOL, INGLES, PORTUGUES = "es", "en", "pt"
IDIOMAS = {ESPANOL: "Español", INGLES: "English", PORTUGUES: "Português (Brasil)"}
POR_DEFECTO = ESPANOL

# Formatos por idioma. En ingles, fecha ISO: dd/mm y mm/dd se confunden.
_DECIMAL = {ESPANOL: ",", INGLES: ".", PORTUGUES: ","}
_FECHA = {ESPANOL: "%d/%m/%Y", INGLES: "%Y-%m-%d", PORTUGUES: "%d/%m/%Y"}
# Separador de columnas de los CSV, para que Excel de cada idioma los abra directo
_CSV = {ESPANOL: ";", INGLES: ",", PORTUGUES: ";"}

_actual = POR_DEFECTO


def idioma_del_sistema():
    """es/en/pt segun el idioma del sistema operativo; castellano si es otro."""
    try:
        codigo = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "").lower()
    except (ValueError, AttributeError):
        codigo = ""
    for c in IDIOMAS:
        if codigo.startswith(c):
            return c
    return POR_DEFECTO


def set_idioma(codigo):
    global _actual
    _actual = codigo if codigo in IDIOMAS else POR_DEFECTO


def idioma():
    return _actual


@lru_cache(maxsize=None)
def catalogo(codigo):
    """{texto en castellano: traduccion} del idioma, vacio para castellano."""
    if codigo == ESPANOL:
        return {}
    try:
        with open(Path(__file__).parent / "idiomas" / ("%s.json" % codigo), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _(texto):
    return catalogo(_actual).get(texto, texto) if _actual != ESPANOL else texto


# -- numeros y fechas ------------------------------------------------------
def num(v, dec=1, signo=False):
    """Numero con el separador decimal del idioma; '—' si es None."""
    if v is None:
        return "—"
    t = ("%+.*f" if signo else "%.*f") % (dec, v)
    return t.replace(".", _DECIMAL[_actual])


def temp(v, dec=1, signo=False):
    """'31,5 °C' (o '31.5 °C' en ingles); '—' si es None."""
    return "—" if v is None else num(v, dec, signo) + " °C"


def fecha(dt):
    return dt.strftime(_FECHA[_actual]) if dt else "—"


def fecha_hora(dt, segundos=False):
    if not dt:
        return "—"
    return dt.strftime(_FECHA[_actual] + (" %H:%M:%S" if segundos else " %H:%M"))


def formato_fecha():
    """Formato strftime de la fecha (para nombres de archivo, ejes, etc.)."""
    return _FECHA[_actual]


def separador_csv():
    return _CSV[_actual]


# En el codigo se usa tr(): `_` ya se usa como variable descartable
tr = _


def plural(n, singular, plural_):
    """Elige la frase (con su %d) segun la cantidad, ya traducida:
    plural(n, "%d foto nueva", "%d fotos nuevas") % n."""
    return tr(singular) if n == 1 else tr(plural_)
