"""Modelo de imagen termica, independiente del formato y de la interfaz."""
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from . import palettes
from .uti760x import TempConverter, Uti760xFile

_RE_FECHA_NOMBRE = re.compile(r"(\d{14})")


@dataclass
class Punto:
    fila: int
    col: int
    temp: float


@dataclass
class Metadatos:
    modelo: str
    numero_serie: str
    fecha: datetime | None
    emisividad: float | None
    temp_reflejada: float | None
    temp_ambiente: float | None
    humedad: float | None
    distancia_m: float | None
    temp_sensor: float | None


def _fecha_desde_nombre(nombre):
    """IMG20260611212820HD.jpg -> 2026-06-11 21:28:20, o None."""
    m = _RE_FECHA_NOMBRE.search(nombre)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None


class ThermalImage:
    """Matriz de temperaturas en C + metadatos.

    `temps` es float32 (alto, ancho), fila 0 = arriba.
    `incertidumbre_c` es el error tipico de la conversion a grados.
    """

    def __init__(self, temps, meta, path=None, fuera_de_rango=False,
                 incertidumbre_c=TempConverter.ERROR_TIPICO_C, visible_jpeg=None):
        self.temps = np.asarray(temps, dtype=np.float32)
        self.meta = meta
        self.path = Path(path) if path else None
        self.fuera_de_rango = fuera_de_rango
        self.incertidumbre_c = incertidumbre_c
        self.visible_jpeg = visible_jpeg

    @classmethod
    def abrir(cls, path):
        f = Uti760xFile(path)
        raw = f.temp_raw()
        p = f.params
        nombre = f.meta.get("name") or Path(path).name
        fecha = _fecha_desde_nombre(nombre)
        if fecha is None and f.meta.get("saveDate"):
            fecha = datetime.fromtimestamp(f.meta["saveDate"] / 1000)
        meta = Metadatos(
            modelo=f.model,
            numero_serie=f.meta.get("SN", ""),
            fecha=fecha,
            emisividad=p.get("ems"),
            temp_reflejada=p.get("reflexTemp"),
            temp_ambiente=p.get("tempAir"),
            humedad=p.get("hum"),
            distancia_m=p.get("distance"),
            temp_sensor=p.get("realFPA"),
        )
        return cls(
            TempConverter.to_celsius(raw), meta, path=path,
            fuera_de_rango=TempConverter.fuera_de_rango(int(raw.min()), int(raw.max())),
            visible_jpeg=f.visible_jpeg(),
        )

    # -- geometria ---------------------------------------------------------
    @property
    def alto(self):
        return self.temps.shape[0]

    @property
    def ancho(self):
        return self.temps.shape[1]

    def temp_en(self, fila, col):
        """Temperatura del pixel, o None si cae fuera de la imagen."""
        if 0 <= fila < self.alto and 0 <= col < self.ancho:
            return float(self.temps[fila, col])
        return None

    # -- estadistica -------------------------------------------------------
    def maximo(self):
        f, c = np.unravel_index(np.argmax(self.temps), self.temps.shape)
        return Punto(int(f), int(c), float(self.temps[f, c]))

    def minimo(self):
        f, c = np.unravel_index(np.argmin(self.temps), self.temps.shape)
        return Punto(int(f), int(c), float(self.temps[f, c]))

    def centro(self):
        f, c = self.alto // 2, self.ancho // 2
        return Punto(f, c, float(self.temps[f, c]))

    def media(self):
        return float(self.temps.mean())

    def rango_auto(self):
        """(min, max) de la imagen completa."""
        return float(self.temps.min()), float(self.temps.max())

    # -- render ------------------------------------------------------------
    def render(self, paleta=palettes.POR_DEFECTO, rango=None, invertir=False):
        """Imagen RGB uint8 (alto, ancho, 3) con la paleta aplicada.

        Lo que queda fuera de `rango` se satura al color del extremo.
        """
        lo, hi = rango or self.rango_auto()
        lut = palettes.get(paleta, invertir)
        span = max(hi - lo, 1e-6)
        idx = np.clip((self.temps - lo) / span * (len(lut) - 1), 0, len(lut) - 1)
        return lut[idx.astype(np.intp)]
