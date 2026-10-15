"""Paletas de color: las de la camara UNI-T (256 colores RGB cada una).

Sacadas de fotos de la propia camara (la barra de color de cada foto).
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

# id interno -> nombre para mostrar, en el orden de los menus
NOMBRES = {
    "iron": "Hierro",
    "rainbow": "Arcoiris",
    "rainbow_hc": "Arcoiris alto contraste",
    "white_hot": "Blanco caliente",
    "black_hot": "Negro caliente",
    "red_hot": "Rojo caliente",
    "lava": "Lava",
    "highlight_5p": "Resaltar extremos 5%",
    "highlight_10p": "Resaltar extremos 10%",
}

POR_DEFECTO = "iron"


@lru_cache(maxsize=None)
def _datos():
    with open(Path(__file__).with_name("palettes.json")) as f:
        return {k: np.array(v, dtype=np.uint8) for k, v in json.load(f).items()}


def disponibles():
    return list(NOMBRES)


def get(nombre, invertir=False):
    """Array (256, 3) uint8. Indice 0 = temperatura mas fria."""
    datos = _datos()
    if nombre == "black_hot":
        lut = datos["white_hot"][::-1]
    elif nombre in datos:
        lut = datos[nombre]
    else:
        raise KeyError("Paleta desconocida: %s" % nombre)
    return np.ascontiguousarray(lut[::-1] if invertir else lut)
