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
    `rango_alto`: foto en el rango alto de la camara, que no esta calibrado.
    """

    def __init__(self, temps, meta, path=None, fuera_de_rango=False,
                 incertidumbre_c=TempConverter.ERROR_TIPICO_C, visible_jpeg=None,
                 rango_alto=False):
        self.temps = np.asarray(temps, dtype=np.float32)
        self.meta = meta
        self.path = Path(path) if path else None
        self.fuera_de_rango = fuera_de_rango
        self.rango_alto = rango_alto
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
        fpa = p.get("realFPA")
        return cls(
            TempConverter.to_celsius(raw, fpa), meta, path=path,
            fuera_de_rango=TempConverter.fuera_de_rango(int(raw.min()), int(raw.max()), fpa),
            visible_jpeg=f.visible_jpeg(),
            rango_alto=bool(p.get("tempMode")),
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

    # Debajo de esto la camara no mide (muestra "<-20,0"): es cielo, casi siempre.
    PISO_MEDICION_C = -20.0
    # Fraccion mas fria de lo medible que el rango automatico deja saturada,
    # para que los bordes del cielo no se coman la paleta.
    PERCENTIL_BAJO_AUTO = 5.0

    def rango_auto(self):
        """(min, max) para la paleta, pensado para que se vean los detalles.

        Con min..max a secas, un 0.3 % de pixeles a -28 C aplastaba un tablero
        entre 21 y 31 C. Abajo se ignora lo que esta bajo el piso de medicion
        y el 5 % mas frio del resto. Arriba no se recorta nada, para que el
        punto caliente nunca quede saturado junto con lo que lo rodea.
        """
        hi = float(self.temps.max())
        medible = self.temps[self.temps >= self.PISO_MEDICION_C]
        if medible.size == 0:
            medible = self.temps
        lo = float(np.percentile(medible, self.PERCENTIL_BAJO_AUTO))
        return min(lo, hi - 0.1), hi

    # Parte del reparto que sigue siendo lineal al ecualizar, para que un
    # tramo de temperaturas con pocos pixeles no se quede sin colores
    MEZCLA_LINEAL = 0.2

    def posiciones_ecualizadas(self, lo, hi, n=256):
        """Reparto de colores segun el histograma de esta imagen; ver
        `posiciones_ecualizadas` del modulo."""
        return posiciones_ecualizadas(self.temps, lo, hi, n, self.MEZCLA_LINEAL)

    # -- render ------------------------------------------------------------
    def render(self, paleta=palettes.POR_DEFECTO, rango=None, invertir=False,
               posiciones=None):
        """Imagen RGB uint8 (alto, ancho, 3) con la paleta aplicada.

        Lo que queda fuera de `rango` se satura al color del extremo.
        `posiciones` (de posiciones_ecualizadas) reparte los colores como en
        el modo "Como la camara"; sin eso, la escala es lineal.
        """
        lo, hi = rango or self.rango_auto()
        lut = tabla_colores(paleta, invertir, posiciones)
        span = max(hi - lo, 1e-6)
        idx = np.clip((self.temps - lo) / span * (len(lut) - 1), 0, len(lut) - 1)
        return lut[idx.astype(np.intp)]


def posiciones_ecualizadas(temps, lo, hi, n=256, mezcla_lineal=ThermalImage.MEZCLA_LINEAL):
    """Donde poner (0..1 dentro de lo..hi) cada uno de n colores de la paleta.

    Como hace la camara: los colores se reparten segun cuantos pixeles hay
    en cada temperatura, asi lo que ocupa mas imagen recibe mas colores.
    La temperatura de cada pixel no cambia; solo el color que le toca.
    `temps` puede juntar varias imagenes: al comparar, el reparto tiene que
    ser el mismo en todas para que un color sea la misma temperatura.
    Siempre estrictamente creciente.
    """
    lineal = np.linspace(0.0, 1.0, n)
    temps = np.asarray(temps)
    dentro = np.sort(temps[(temps >= lo) & (temps <= hi)], axis=None)
    if hi <= lo or dentro.size < 2:
        return lineal
    # Acumulada del histograma mezclada con la de una escala pareja: la
    # parte lineal la hace estrictamente creciente, asi se puede invertir
    grilla = np.linspace(0.0, 1.0, 4 * n)
    acum = np.searchsorted(dentro, lo + grilla * (hi - lo), side="right") / dentro.size
    acum = (1 - mezcla_lineal) * acum + mezcla_lineal * grilla
    acum = (acum - acum[0]) / (acum[-1] - acum[0])
    pos = np.interp(lineal, acum, grilla)
    pos[0], pos[-1] = 0.0, 1.0
    return pos


def rango_auto_conjunto(imagenes):
    """Rango automatico que abarca a todas: para verlas con la misma escala."""
    rangos = [img.rango_auto() for img in imagenes]
    return min(lo for lo, _ in rangos), max(hi for _, hi in rangos)



def tabla_colores(paleta, invertir=False, posiciones=None, n=256):
    """Tabla (n, 3) uint8 de color por valor normalizado 0..1, como la arma el
    visor: con `posiciones`, el color k de la paleta va en posiciones[k]."""
    lut = palettes.get(paleta, invertir)
    if posiciones is None:
        if len(lut) == n:
            return lut
        posiciones = np.linspace(0.0, 1.0, len(lut))
    x = np.linspace(0.0, 1.0, n)
    return np.stack([np.interp(x, posiciones, lut[:, c]) for c in range(3)],
                    axis=1).round().astype(np.uint8)
