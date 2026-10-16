"""Comparacion lado a lado de dos fotos del mismo lugar en distintas fechas.

Las dos se ven con la misma paleta, el mismo rango y, en modo camara, el
mismo reparto de colores: un color es la misma temperatura en las dos.
"""
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ..core.library import fecha_visible
from ..core.thermal_image import rango_auto_conjunto
from . import theme
from .viewer import ThermalViewer, fmt_temp
from .widgets import TarjetaDato, boton, etiqueta, marco


def _fecha(img):
    f = img.meta.fecha
    return (f.strftime("%d/%m/%Y"), f.strftime("%H:%M")) if f else ("Sin fecha", "")


def _tiempo_entre(a, b):
    """'Pasaron 49 días' entre las fechas de dos imagenes, o ''."""
    fa, fb = a.meta.fecha, b.meta.fecha
    if not (fa and fb):
        return ""
    dias = abs((fb.date() - fa.date()).days)
    if dias == 0:
        return "Misma fecha"
    if dias < 60:
        return "Pasaron %d día%s" % (dias, "" if dias == 1 else "s")
    meses = round(dias / 30.44)
    if meses < 24:
        return "Pasaron %d meses (%d días)" % (meses, dias)
    return "Pasaron %.1f años (%d días)" % (dias / 365.25, dias)


class _Columna(QWidget):
    """Una de las dos fotos: fecha grande arriba, visor y datos abajo."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        cab = QHBoxLayout()
        cab.setSpacing(10)
        self.fecha = etiqueta("", "grande")
        self.hora = etiqueta("", "suave")
        cab.addWidget(self.fecha)
        cab.addWidget(self.hora, 0, Qt.AlignBottom)
        cab.addStretch(1)
        v.addLayout(cab)
        self.archivo = etiqueta("", "suave")
        v.addWidget(self.archivo)

        self.viewer = ThermalViewer()
        v.addWidget(self.viewer, 1)

        datos = QGridLayout()
        datos.setSpacing(8)
        self.tmax = TarjetaDato("Máxima", "max")
        self.tmedia = TarjetaDato("Media")
        self.tmin = TarjetaDato("Mínima", "min")
        for i, t in enumerate((self.tmax, self.tmedia, self.tmin)):
            datos.addWidget(t, 0, i)
        v.addLayout(datos)

    def mostrar(self, img, rango, referencia=None):
        """`referencia` es la otra foto: si esta, se muestra cuanto cambio."""
        fecha, hora = _fecha(img)
        self.fecha.setText(fecha)
        self.hora.setText(hora)
        self.archivo.setText(img.path.name if img.path else "")
        self.viewer.mostrar(img, rango)
        valores = {"max": img.maximo().temp, "media": img.media(), "min": img.minimo().temp}
        previos = None
        if referencia is not None:
            previos = {"max": referencia.maximo().temp, "media": referencia.media(),
                       "min": referencia.minimo().temp}
        for clave, tarjeta in (("max", self.tmax), ("media", self.tmedia), ("min", self.tmin)):
            texto = fmt_temp(valores[clave])
            if previos is not None:
                d = valores[clave] - previos[clave]
                # Que la maxima suba es lo que puede indicar un problema
                color = theme.color("aviso") if (clave == "max" and d >= 1.0) else \
                    theme.color("texto_suave")
                texto += ("&nbsp;<span style='font-size:13px; color:%s'>%+.1f °C</span>"
                          % (color, d))
            tarjeta.set(texto)


class VistaComparacion(QWidget):
    """Dos fotos lado a lado; la mas vieja a la izquierda.

    Senales:
      rangoCambiado(lo, hi)  al soltar la barra de color de cualquiera
      cerrar()               el usuario pidio volver a una sola foto
    """

    rangoCambiado = Signal(float, float)
    cerrar = Signal()

    def __init__(self):
        super().__init__()
        self.imagenes = []
        fondo = marco("panel", self)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(fondo)
        v = QVBoxLayout(fondo)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)

        barra = QHBoxLayout()
        self.titulo = etiqueta("Comparación", "titulo")
        self.lapso = etiqueta("", "suave")
        barra.addWidget(self.titulo)
        barra.addSpacing(12)
        barra.addWidget(self.lapso)
        barra.addStretch(1)
        b = boton("Cerrar comparación", "mdi6.close", tooltip="Volver a ver una sola foto (Esc)")
        b.clicked.connect(self.cerrar)
        barra.addWidget(b)
        v.addLayout(barra)

        fila = QHBoxLayout()
        fila.setSpacing(16)
        self.columnas = (_Columna(), _Columna())
        for c in self.columnas:
            fila.addWidget(c, 1)
            c.viewer.rangoCambiado.connect(self._rango_de_una)
        v.addLayout(fila, 1)

    @property
    def viewers(self):
        return [c.viewer for c in self.columnas]

    def mostrar(self, img_a, img_b, rango=None):
        """Ordena por fecha: la mas vieja queda a la izquierda."""
        a, b = sorted((img_a, img_b), key=lambda i: (i.meta.fecha is None, i.meta.fecha))
        self.imagenes = [a, b]
        rango = rango or rango_auto_conjunto(self.imagenes)
        juntas = np.concatenate([a.temps.ravel(), b.temps.ravel()])
        for viewer in self.viewers:
            viewer.set_reparto(juntas)
        self.columnas[0].mostrar(a, rango)
        self.columnas[1].mostrar(b, rango, referencia=a)
        # Si las dos estan en la misma carpeta, esa carpeta es el lugar
        carpetas = {i.path.parent for i in self.imagenes if i.path}
        carpeta = fecha_visible(carpetas.pop().name) if len(carpetas) == 1 else ""
        self.titulo.setText("Comparación — %s" % carpeta if carpeta else "Comparación")
        self.lapso.setText(_tiempo_entre(a, b))

    def set_rango(self, lo, hi):
        for viewer in self.viewers:
            viewer.set_rango(lo, hi)

    def rango(self):
        return self.viewers[0].rango()

    def rango_auto(self):
        return rango_auto_conjunto(self.imagenes)

    def _rango_de_una(self, lo, hi):
        for viewer in self.viewers:
            if viewer.rango() != (lo, hi):
                viewer.set_rango(lo, hi)
        self.rangoCambiado.emit(lo, hi)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.cerrar.emit()
            return
        super().keyPressEvent(ev)
