"""Comparacion lado a lado de dos fotos del mismo lugar en distintas fechas.

Las dos se ven con la misma paleta, el mismo rango y, en modo camara, el
mismo reparto de colores: un color es la misma temperatura en las dos.
"""
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout,
    QHeaderView, QListWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.library import CARPETA_IMPORTADAS, ErrorBiblioteca, fecha_visible
from ..core.mediciones import Mediciones, resultados
from ..core.thermal_image import _fecha_desde_nombre, rango_auto_conjunto
from . import theme
from .library_panel import Galeria
from .mediciones_ui import CapaMediciones
from .thumbnails import TAMANO, CargadorMiniaturas
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
        self.capa = CapaMediciones(self.viewer, editable=False)
        v.addWidget(self.viewer, 1)

        datos = QGridLayout()
        datos.setSpacing(8)
        self.tmax = TarjetaDato("Máxima", "max")
        self.tmedia = TarjetaDato("Media")
        self.tmin = TarjetaDato("Mínima", "min")
        for i, t in enumerate((self.tmax, self.tmedia, self.tmin)):
            datos.addWidget(t, 0, i)
        v.addLayout(datos)

    def mostrar(self, img, rango, referencia=None, mediciones=None):
        """`referencia` es la otra foto: si esta, se muestra cuanto cambio."""
        fecha, hora = _fecha(img)
        self.fecha.setText(fecha)
        self.hora.setText(hora)
        self.archivo.setText(img.path.name if img.path else "")
        self.viewer.mostrar(img, rango)
        self.capa.set_mediciones(mediciones or Mediciones())
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

        # Mediciones con el mismo nombre en las dos fechas
        self.titulo_tabla = etiqueta("MEDICIONES EN LAS DOS FECHAS", "seccion")
        v.addWidget(self.titulo_tabla)
        self.tabla = QTableWidget(0, len(self.COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self.COLUMNAS)
        self.tabla.verticalHeader().hide()
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.NoSelection)
        enc = self.tabla.horizontalHeader()
        enc.setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.tabla)

    COLUMNAS = ("Medición", "Máxima antes", "Máxima ahora", "Cambio", "ΔT antes", "ΔT ahora")

    @property
    def viewers(self):
        return [c.viewer for c in self.columnas]

    def mostrar(self, img_a, img_b, rango=None, leer_mediciones=None):
        """Ordena por fecha: la mas vieja queda a la izquierda.
        `leer_mediciones(img)` da las mediciones guardadas de cada foto."""
        a, b = sorted((img_a, img_b), key=lambda i: (i.meta.fecha is None, i.meta.fecha))
        self.imagenes = [a, b]
        ma, mb = ((leer_mediciones(i) if leer_mediciones else Mediciones()) for i in (a, b))
        rango = rango or rango_auto_conjunto(self.imagenes)
        juntas = np.concatenate([a.temps.ravel(), b.temps.ravel()])
        for viewer in self.viewers:
            viewer.set_reparto(juntas)
        self.columnas[0].mostrar(a, rango, mediciones=ma)
        self.columnas[1].mostrar(b, rango, referencia=a, mediciones=mb)
        self._llenar_tabla(a, ma, b, mb)
        # Si las dos estan en la misma carpeta, esa carpeta es el lugar
        carpetas = {i.path.parent for i in self.imagenes if i.path}
        carpeta = fecha_visible(carpetas.pop().name) if len(carpetas) == 1 else ""
        self.titulo.setText("Comparación — %s" % carpeta if carpeta else "Comparación")
        self.lapso.setText(_tiempo_entre(a, b))

    def _llenar_tabla(self, a, ma, b, mb):
        antes = {r.nombre: r for r in resultados(ma, a.temps)}
        ahora = {r.nombre: r for r in resultados(mb, b.temps)}
        # Primero las que estan en las dos (lo que de verdad se compara)
        nombres = [n for n in ahora if n in antes] + [n for n in ahora if n not in antes] + \
            [n for n in antes if n not in ahora]
        self.tabla.setRowCount(len(nombres))
        for fila, n in enumerate(nombres):
            ra, rb = antes.get(n), ahora.get(n)
            cambio = rb.maxima - ra.maxima if ra and rb else None

            def t(v, signo=False):
                if v is None:
                    return "—"
                return ("%+.1f °C" if signo else "%.1f °C") % v

            def delta(r):
                if r is None:
                    return "—"
                return "referencia" if r.es_referencia else t(r.delta_t, True)
            valores = (n, t(ra and ra.maxima), t(rb and rb.maxima), t(cambio, True),
                       delta(ra), delta(rb))
            for c, texto in enumerate(valores):
                it = QTableWidgetItem(texto)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                subio_delta = (c == 5 and rb and ra and rb.delta_t is not None
                               and ra.delta_t is not None and rb.delta_t - ra.delta_t >= 1.0)
                if (c == 3 and cambio is not None and cambio >= 1.0) or subio_delta:
                    it.setForeground(QColor(theme.color("aviso")))
                self.tabla.setItem(fila, c, it)
        hay = bool(nombres)
        self.tabla.setVisible(hay)
        self.titulo_tabla.setVisible(hay)
        alto = self.tabla.horizontalHeader().height() + 4 + sum(
            self.tabla.rowHeight(f) for f in range(min(len(nombres), 6)))
        self.tabla.setFixedHeight(alto)

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


class DialogoElegirSegunda(QDialog):
    """Elegir con que foto comparar la abierta.

    Arranca en la carpeta de la foto abierta (una carpeta = un lugar), con
    miniaturas; se puede cambiar a cualquier otra carpeta de la biblioteca.
    """

    def __init__(self, biblioteca, actual, nombre_visible, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comparar con…")
        self.resize(760, 560)
        self.bib = biblioteca
        self.actual = Path(actual)
        self.elegida = None
        self.miniaturas = CargadorMiniaturas(biblioteca.miniaturas, self)
        self.miniaturas.lista.connect(self._miniatura_lista)
        self._items = {}

        v = QVBoxLayout(self)
        v.setSpacing(10)
        f = _fecha_desde_nombre(self.actual.name)
        v.addWidget(etiqueta("Elegí la foto para comparar con la del %s"
                             % (f.strftime("%d/%m/%Y %H:%M") if f else self.actual.name), "titulo"))

        fila = QHBoxLayout()
        fila.addWidget(etiqueta("Carpeta", "suave"))
        self.combo = QComboBox()
        carpetas = biblioteca.todas_las_carpetas()
        for rel in carpetas:
            self.combo.addItem(nombre_visible(rel), rel)
        try:
            inicial = biblioteca.rel(self.actual.parent)
        except ValueError:  # foto abierta desde fuera de la biblioteca
            inicial = CARPETA_IMPORTADAS
        self.combo.setCurrentIndex(max(self.combo.findData(inicial), 0))
        self.combo.currentIndexChanged.connect(self._cargar)
        fila.addWidget(self.combo, 1)
        v.addLayout(fila)

        self.galeria = Galeria()
        self.galeria.setSelectionMode(QAbstractItemView.SingleSelection)
        self.galeria.setDragEnabled(False)
        self.galeria.itemDoubleClicked.connect(lambda *_: self._aceptar())
        self.galeria.itemSelectionChanged.connect(self._actualizar_boton)
        v.addWidget(self.galeria, 1)
        self.vacia = etiqueta("No hay otras fotos en esta carpeta.", "suave")
        v.addWidget(self.vacia)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.btn_ok = botones.button(QDialogButtonBox.Ok)
        self.btn_ok.setText("Comparar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        v.addWidget(botones)
        self._cargar()

    def _cargar(self):
        self.miniaturas.cancelar_pendientes()
        self.galeria.clear()
        self._items = {}
        try:
            fotos = [p for p in self.bib.fotos(self.combo.currentData() or "")
                     if p.resolve() != self.actual.resolve()]
        except (ErrorBiblioteca, OSError):
            fotos = []
        vacio = QPixmap(TAMANO, int(TAMANO * 0.8))
        vacio.fill(QColor(theme.color("superficie")))
        for p in fotos:
            f = _fecha_desde_nombre(p.name)
            it = QListWidgetItem(QIcon(vacio), f.strftime("%d/%m/%Y %H:%M") if f else p.stem)
            it.setData(Qt.UserRole, str(p))
            it.setToolTip(p.name)
            self.galeria.addItem(it)
            self._items[str(p)] = it
            self.miniaturas.pedir(p)
        self.vacia.setVisible(not fotos)
        self._actualizar_boton()

    def _miniatura_lista(self, ruta, img):
        it = self._items.get(ruta)
        if it is not None:
            it.setIcon(QIcon(QPixmap.fromImage(img)))

    def _actualizar_boton(self):
        self.btn_ok.setEnabled(bool(self.galeria.selectedItems()))

    def _aceptar(self):
        items = self.galeria.selectedItems()
        if items:
            self.elegida = Path(items[0].data(Qt.UserRole))
            self.accept()

    def done(self, r):
        self.miniaturas.cancelar_pendientes()
        super().done(r)
