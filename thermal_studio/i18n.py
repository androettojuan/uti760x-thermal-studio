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


# -- unidad de temperatura -----------------------------------------------
# Todo el programa calcula en Celsius; la unidad elegida solo cambia lo que se
# muestra o exporta. Ojo: una temperatura y una diferencia (Delta T, rango,
# precision) se convierten distinto: 4,7 C de diferencia son 8,5 F, sin +32.
CELSIUS, FAHRENHEIT = "C", "F"
_unidad = CELSIUS


def set_unidad(u):
    global _unidad
    _unidad = FAHRENHEIT if u == FAHRENHEIT else CELSIUS


def unidad():
    return _unidad


def simbolo():
    return "°F" if _unidad == FAHRENHEIT else "°C"


def a_unidad(v, diferencia=False):
    """Celsius -> unidad elegida. Acepta numeros o arrays de numpy."""
    if v is None or _unidad == CELSIUS:
        return v
    return v * 1.8 if diferencia else v * 1.8 + 32


def de_unidad(v, diferencia=False):
    """Unidad elegida -> Celsius (por ejemplo, lo que se escribe en el rango)."""
    if v is None or _unidad == CELSIUS:
        return v
    return v / 1.8 if diferencia else (v - 32) / 1.8


def valor(v, dec=1, signo=False, diferencia=None, limites=None):
    """Numero de una temperatura, sin la unidad: '31,5' (o '88,5' en °F).

    `limites` (min, max en Celsius) es lo que la camara mide en el modo de la
    foto: fuera de eso se muestra como la camara, '<-20,0' o '>125,0', y no un
    numero estimado con una precision que no tiene. Las diferencias no se
    recortan.
    """
    if v is None:
        return "—"
    dif = signo if diferencia is None else diferencia
    if limites is not None and not dif:
        lo, hi = limites
        if v < lo:
            return "<" + num(a_unidad(lo), dec)
        if v > hi:
            return ">" + num(a_unidad(hi), dec)
    return num(a_unidad(v, dif), dec, signo)


def temp(v, dec=1, signo=False, diferencia=None, limites=None):
    """'31,5 °C' en la unidad y con el decimal del idioma; '—' si es None.

    Con signo, se toma como diferencia (cambio, Delta T) salvo que se diga
    otra cosa; una diferencia sin signo se pide con diferencia=True. Ver
    `valor` para `limites`.
    """
    if v is None:
        return "—"
    return valor(v, dec, signo, diferencia, limites) + " " + simbolo()


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
