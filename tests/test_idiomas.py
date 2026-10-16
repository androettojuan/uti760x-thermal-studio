"""Que cada texto marcado para traducir tenga traduccion en cada idioma, con
los mismos marcadores de formato (%d, %s, %(nombre)s) que el original."""
import ast
import json
import re
from pathlib import Path

import pytest

from thermal_studio import i18n

RAIZ = Path(__file__).resolve().parent.parent / "thermal_studio"
MARCADOR = re.compile(r"%(\([a-z_]+\))?[-+ #0]*\d*(\.\d+)?[sdfr%]")


def claves():
    """Textos literales pasados a tr() y a plural() en todo el programa."""
    out = set()
    for f in RAIZ.rglob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Name):
                continue
            args = n.args if n.func.id == "tr" else n.args[1:] if n.func.id == "plural" else []
            out.update(a.value for a in args
                       if isinstance(a, ast.Constant) and isinstance(a.value, str))
    return out


def marcadores(texto):
    return sorted(m.group(0) for m in MARCADOR.finditer(texto))


@pytest.mark.parametrize("idioma", [i18n.INGLES, i18n.PORTUGUES])
def test_todo_traducido_con_los_mismos_marcadores(idioma):
    cat = json.loads((RAIZ / "idiomas" / ("%s.json" % idioma)).read_text(encoding="utf-8"))
    faltan = sorted(k for k in claves() if k not in cat)
    assert not faltan, "Faltan %d traducciones: %s" % (len(faltan), faltan[:5])
    mal = [k for k in claves() if marcadores(k) != marcadores(cat[k])]
    assert not mal, "Marcadores distintos en: %s" % mal[:5]
    sobran = sorted(set(cat) - claves())
    assert not sobran, "Traducciones de textos que ya no existen: %s" % sobran[:5]


def test_numeros_y_fechas_segun_idioma():
    from datetime import datetime
    d = datetime(2026, 10, 16, 22, 53)
    try:
        i18n.set_idioma(i18n.ESPANOL)
        assert i18n.temp(31.5) == "31,5 °C" and i18n.fecha(d) == "16/10/2026"
        assert i18n.temp(4.7, signo=True) == "+4,7 °C"
        i18n.set_idioma(i18n.INGLES)
        assert i18n.temp(31.5) == "31.5 °C" and i18n.fecha_hora(d) == "2026-10-16 22:53"
        assert i18n.separador_csv() == ","
        assert i18n.plural(1, "%d foto", "%d fotos") % 1 == "1 photo"
        i18n.set_idioma(i18n.PORTUGUES)
        assert i18n.temp(-9.0) == "-9,0 °C" and i18n.tr("Abrir imagen…") != "Abrir imagen…"
    finally:
        i18n.set_idioma(i18n.ESPANOL)
