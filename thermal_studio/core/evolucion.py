"""Evolucion de un lugar en el tiempo: una fila por foto de la carpeta.

Las mediciones se siguen por nombre: si en cada ronda el inspector marca un
area "Fase R", la serie "Fase R" une las de todas las fechas. Asi se ve si
una conexion se viene calentando, sobre todo por su Delta T contra la
referencia, que cambia poco entre estaciones.
"""
from dataclasses import dataclass, field
from datetime import datetime

from .mediciones import resultados


@dataclass
class FilaEvolucion:
    ruta: object                 # Path de la foto
    fecha: datetime | None
    maxima: float                # de toda la imagen
    mediciones: dict = field(default_factory=dict)  # nombre -> (maxima, delta_t o None)
    referencia: str | None = None
    notas: str = ""
    limites: tuple | None = None   # lo que mide la camara en el modo de la foto

    @property
    def mayor_delta(self):
        deltas = [d for _, d in self.mediciones.values() if d is not None]
        return max(deltas, key=abs) if deltas else None


def fila(ruta, img, mediciones):
    filas = resultados(mediciones, img.temps)
    return FilaEvolucion(
        ruta=ruta, fecha=img.meta.fecha, maxima=img.maximo().temp,
        mediciones={r.nombre: (r.maxima, r.delta_t) for r in filas},
        referencia=mediciones.referencia, notas=mediciones.notas.strip(),
        limites=getattr(img, "limites", None))


def ordenar(filas):
    """Por fecha; las que no tienen fecha, al final."""
    return sorted(filas, key=lambda f: (f.fecha is None, f.fecha or datetime.min))


def series(filas):
    """{nombre: [(fecha, maxima, delta_t), ...]} de las mediciones que aparecen
    en alguna foto con fecha, en orden de fecha. Las de la serie que aparecen
    en una sola foto tambien se incluyen (un punto suelto)."""
    out = {}
    for f in ordenar(filas):
        if f.fecha is None:
            continue
        for nombre, (maxima, delta) in f.mediciones.items():
            out.setdefault(nombre, []).append((f.fecha, maxima, delta))
    return out
