"""Paletas de color de la camara UNI-T UTi760x (256 colores RGB cada una).

Sacadas de fotos de la propia camara: la barra de color que dibuja en cada
foto, comparada con la imagen en gris que colorea (herramientas/paletas/ tiene los
scripts y los datos). Asi el programa muestra los mismos colores que la
pantalla de la camara.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

# id interno -> nombre para mostrar, en el orden de los menus
NOMBRES = {
    "iron": "Hierro",
    "rainbow": "Arcoíris",
    "rainbow_hc": "Arcoíris alto contraste",
    "lava": "Lava",
    "white_hot": "Blanco caliente",
    "black_hot": "Negro caliente",
    "highlight": "Grises con alerta roja",
    "red": "Rojo",
    "green": "Verde",
    "blue": "Azul",
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
    if nombre not in datos:
        raise KeyError("Paleta desconocida: %s" % nombre)
    lut = datos[nombre]
    return np.ascontiguousarray(lut[::-1] if invertir else lut)
