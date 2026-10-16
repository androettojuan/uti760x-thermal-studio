"""Mediciones sobre una imagen termica: puntos, lineas y areas.

Coordenadas en pixeles de la imagen, continuas: x = columna, y = fila, con
(0, 0) en la esquina de arriba a la izquierda del primer pixel. El pixel
(fila f, columna c) ocupa [c, c+1) x [f, f+1).

El Delta T de cada medicion se calcula contra la maxima de la medicion de
referencia: en termografia electrica lo que importa es cuanto mas caliente
esta un componente que otro igual en las mismas condiciones (fase R contra
S), y esa diferencia cambia mucho menos entre verano e invierno que la
temperatura absoluta.
"""
from dataclasses import dataclass, field

import numpy as np

PUNTO = "punto"
LINEA = "linea"
AREA = "area"
TIPOS = (PUNTO, LINEA, AREA)
_PREFIJOS = {PUNTO: "P", LINEA: "L", AREA: "A"}
VERSION_FORMATO = 1


@dataclass
class Medicion:
    tipo: str
    nombre: str
    geom: list  # punto [x, y]; linea [x1, y1, x2, y2]; area [x0, y0, x1, y1]

    def __post_init__(self):
        if self.tipo not in TIPOS:
            raise ValueError("Tipo de medicion desconocido: %s" % self.tipo)
        n = 2 if self.tipo == PUNTO else 4
        if len(self.geom) != n:
            raise ValueError("Una medicion de tipo %s lleva %d coordenadas" % (self.tipo, n))
        self.geom = [float(v) for v in self.geom]


@dataclass
class Estadistica:
    maxima: float
    minima: float
    media: float
    fila_max: int
    col_max: int
    pixeles: int


def _indices_linea(geom, alto, ancho):
    """Filas y columnas de los pixeles que toca la linea, en orden, sin repetir."""
    x1, y1, x2, y2 = geom
    n = int(np.ceil(max(abs(x2 - x1), abs(y2 - y1)))) + 1
    xs = np.clip(np.floor(np.linspace(x1, x2, n)).astype(int), 0, ancho - 1)
    ys = np.clip(np.floor(np.linspace(y1, y2, n)).astype(int), 0, alto - 1)
    pares = np.stack([ys, xs], 1)
    # Sacar repetidos consecutivos (al redondear dos muestras caen en el mismo pixel)
    distinto = np.ones(len(pares), bool)
    distinto[1:] = np.any(pares[1:] != pares[:-1], axis=1)
    pares = pares[distinto]
    return pares[:, 0], pares[:, 1]


def _ventana_area(geom, alto, ancho):
    """(f0, f1, c0, c1) de los pixeles cuyo centro cae dentro del rectangulo.
    Siempre al menos un pixel."""
    x0, y0, x1, y1 = geom
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    c0 = int(np.clip(np.ceil(x0 - 0.5), 0, ancho - 1))
    c1 = int(np.clip(np.floor(x1 - 0.5), c0, ancho - 1)) + 1
    f0 = int(np.clip(np.ceil(y0 - 0.5), 0, alto - 1))
    f1 = int(np.clip(np.floor(y1 - 0.5), f0, alto - 1)) + 1
    return f0, f1, c0, c1


def estadistica(med, temps):
    """Maxima, minima y media de los pixeles que abarca la medicion."""
    alto, ancho = temps.shape
    if med.tipo == PUNTO:
        c = int(np.clip(np.floor(med.geom[0]), 0, ancho - 1))
        f = int(np.clip(np.floor(med.geom[1]), 0, alto - 1))
        t = float(temps[f, c])
        return Estadistica(t, t, t, f, c, 1)
    if med.tipo == LINEA:
        filas, cols = _indices_linea(med.geom, alto, ancho)
        valores = temps[filas, cols]
        i = int(np.argmax(valores))
        return Estadistica(float(valores.max()), float(valores.min()), float(valores.mean()),
                           int(filas[i]), int(cols[i]), len(valores))
    f0, f1, c0, c1 = _ventana_area(med.geom, alto, ancho)
    sub = temps[f0:f1, c0:c1]
    f, c = np.unravel_index(int(np.argmax(sub)), sub.shape)
    return Estadistica(float(sub.max()), float(sub.min()), float(sub.mean()),
                       f0 + int(f), c0 + int(c), sub.size)


def perfil(med, temps):
    """Perfil de temperatura a lo largo de una linea.

    Devuelve (distancia en pixeles desde el primer extremo, temperatura).
    """
    if med.tipo != LINEA:
        raise ValueError("Solo las lineas tienen perfil")
    alto, ancho = temps.shape
    filas, cols = _indices_linea(med.geom, alto, ancho)
    x1, y1 = med.geom[0], med.geom[1]
    dist = np.hypot(cols + 0.5 - x1, filas + 0.5 - y1)
    return dist, temps[filas, cols].astype(float)


@dataclass
class Mediciones:
    """Las mediciones de una foto, con cual es la referencia del Delta T."""

    lista: list = field(default_factory=list)
    referencia: str | None = None  # nombre de la medicion de referencia
    notas: str = ""                # observaciones del inspector sobre la foto

    def vacia(self):
        return not self.lista and not self.notas.strip()

    def nombre_nuevo(self, tipo):
        """P1, P2... / L1... / A1...: el siguiente numero libre de ese tipo."""
        pref = _PREFIJOS[tipo]
        usados = {m.nombre for m in self.lista}
        n = 1
        while "%s%d" % (pref, n) in usados:
            n += 1
        return "%s%d" % (pref, n)

    def agregar(self, tipo, geom):
        m = Medicion(tipo, self.nombre_nuevo(tipo), list(geom))
        self.lista.append(m)
        return m

    def buscar(self, nombre):
        return next((m for m in self.lista if m.nombre == nombre), None)

    def quitar(self, nombre):
        self.lista = [m for m in self.lista if m.nombre != nombre]
        if self.referencia == nombre:
            self.referencia = None

    def renombrar(self, nombre, nuevo):
        """Devuelve False si el nombre nuevo esta vacio o ya existe."""
        nuevo = nuevo.strip()
        if not nuevo or (nuevo != nombre and self.buscar(nuevo)):
            return False
        m = self.buscar(nombre)
        if m is None:
            return False
        m.nombre = nuevo
        if self.referencia == nombre:
            self.referencia = nuevo
        return True

    def delta_t(self, med, temps):
        """Maxima de `med` menos la maxima de la referencia, o None si no hay
        referencia o `med` es la referencia."""
        ref = self.buscar(self.referencia) if self.referencia else None
        if ref is None or ref is med:
            return None
        return estadistica(med, temps).maxima - estadistica(ref, temps).maxima

    # -- guardado ----------------------------------------------------------
    def a_dict(self):
        return {
            "version": VERSION_FORMATO,
            "referencia": self.referencia,
            "notas": self.notas,
            "mediciones": [{"tipo": m.tipo, "nombre": m.nombre, "geom": m.geom}
                           for m in self.lista],
        }

    @classmethod
    def desde_dict(cls, d):
        """Ignora mediciones invalidas en vez de fallar: un archivo a medio
        editar a mano no tiene que impedir abrir la foto."""
        out = cls()
        for item in d.get("mediciones", []):
            try:
                out.lista.append(Medicion(item["tipo"], str(item["nombre"]), item["geom"]))
            except (KeyError, TypeError, ValueError):
                continue
        ref = d.get("referencia")
        out.referencia = ref if out.buscar(ref) else None
        out.notas = d.get("notas") if isinstance(d.get("notas"), str) else ""
        return out


@dataclass
class Resultado:
    """Una fila de la tabla de mediciones, lista para mostrar o exportar."""
    nombre: str
    tipo: str
    maxima: float
    minima: float
    media: float
    delta_t: float | None
    es_referencia: bool


NOMBRES_TIPO = {PUNTO: "Punto", LINEA: "Línea", AREA: "Área"}


def resultados(mediciones, temps):
    """Estadistica y Delta T de cada medicion, en el orden de la lista."""
    out = []
    for m in mediciones.lista:
        e = estadistica(m, temps)
        out.append(Resultado(m.nombre, m.tipo, e.maxima, e.minima, e.media,
                             mediciones.delta_t(m, temps),
                             m.nombre == mediciones.referencia))
    return out
