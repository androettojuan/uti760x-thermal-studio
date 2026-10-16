"""Mediciones en la interfaz: dibujo sobre el visor y panel con la tabla.

CapaMediciones vive sobre un ThermalViewer: crea, dibuja y deja mover las
mediciones. PanelMediciones muestra la tabla (nombre, max, min, media,
Delta T contra la referencia) y el perfil de la linea elegida. Los dos
trabajan sobre el mismo objeto Mediciones y se avisan por senales.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QGraphicsRectItem, QHBoxLayout, QHeaderView, QMenu, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core.mediciones import AREA, LINEA, PUNTO, Mediciones, estadistica, perfil
from . import theme
from .viewer import MarcasSinClic
from .widgets import boton, etiqueta

COLOR_MEDICION = "#ffffff"
COLOR_SOMBRA = (0, 0, 0, 170)
TAM_MINIMO = 2.0  # en pixeles de imagen: menos que esto es un clic, no un arrastre


def _fmt(t):
    return "—" if t is None else "%.1f" % t


def _fmt_delta(d):
    return "" if d is None else "%+.1f" % d


class _Punto(pg.TargetItem):
    """TargetItem que avisa cuando se le hace clic, para seleccionarlo."""

    def __init__(self, al_clic, **kw):
        super().__init__(**kw)
        self._al_clic = al_clic

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            ev.accept()
            self._al_clic()
        else:
            super().mouseClickEvent(ev)


class CapaMediciones(QObject):
    """Dibuja y edita las mediciones de la imagen de un visor.

    Senales:
      cambiaron()         cambio la geometria (en vivo, mientras se arrastra)
      terminaron()        termino un cambio: momento de guardar
      seleccionada(str)   se eligio una medicion en la imagen ("" = ninguna)
    """

    cambiaron = Signal()
    terminaron = Signal()
    seleccionada = Signal(str)

    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.vb = viewer.vb
        self.mediciones = Mediciones()
        self.herramienta = None   # None (mover) | PUNTO | LINEA | AREA
        self.elegida = ""
        self._items = {}          # nombre -> (item grafico, etiqueta)
        self._borrador = None     # item mientras se dibuja una linea o un area
        self._inicio = None
        self.maximos = MarcasSinClic(pxMode=True, size=11, symbol="t1",
                                          brush=pg.mkBrush(COLOR_MEDICION),
                                          pen=pg.mkPen("k", width=1))
        self.maximos.setZValue(15)
        self.vb.addItem(self.maximos)
        self.vb.manejador_arrastre = self._arrastre
        self.vb.manejador_clic = self._clic

    # -- API ---------------------------------------------------------------
    def set_mediciones(self, mediciones):
        self._limpiar()
        self.mediciones = mediciones
        self.elegida = ""
        for m in mediciones.lista:
            self._crear_item(m)
        self.actualizar()

    def set_herramienta(self, herramienta):
        self.herramienta = herramienta

    def elegir(self, nombre):
        self.elegida = nombre
        self._pintar()

    def borrar(self, nombre):
        if not nombre or self.mediciones.buscar(nombre) is None:
            return
        self.mediciones.quitar(nombre)
        item, texto = self._items.pop(nombre)
        self.vb.removeItem(item)
        self.vb.removeItem(texto)
        if self.elegida == nombre:
            self.elegida = ""
        self.actualizar()
        self.terminaron.emit()

    def renombrado(self, viejo, nuevo):
        if viejo in self._items:
            self._items[nuevo] = self._items.pop(viejo)
        if self.elegida == viejo:
            self.elegida = nuevo
        self.actualizar()

    def actualizar(self):
        """Recalcula etiquetas y marcas de maxima con la imagen actual."""
        img = self.viewer.img
        puntos = []
        for m in self.mediciones.lista:
            _, texto = self._items[m.nombre]
            if img is None:
                continue
            e = estadistica(m, img.temps)
            if m.tipo == PUNTO:
                texto.setText("%s  %.1f °C" % (m.nombre, e.maxima))
                texto.setPos(m.geom[0] + 6, m.geom[1] - 6)
            else:
                texto.setText("%s  máx %.1f °C" % (m.nombre, e.maxima))
                puntos.append({"pos": (e.col_max + 0.5, e.fila_max + 0.5)})
                if m.tipo == LINEA:
                    texto.setPos(m.geom[2] + 6, m.geom[3] - 6)
                else:
                    texto.setPos(min(m.geom[0], m.geom[2]), min(m.geom[1], m.geom[3]) - 2)
        self.maximos.setData(puntos)
        self._pintar()

    # -- dibujo ------------------------------------------------------------
    def _limpiar(self):
        for item, texto in self._items.values():
            self.vb.removeItem(item)
            self.vb.removeItem(texto)
        self._items = {}

    def _pen(self, nombre):
        color = theme.color("acento") if nombre == self.elegida else COLOR_MEDICION
        return pg.mkPen(color, width=2)

    def _pintar(self):
        for nombre, (item, texto) in self._items.items():
            pen = self._pen(nombre)
            if isinstance(item, pg.TargetItem):
                item.setPen(pen)
            else:
                item.setPen(pen)
            texto.setColor(pen.color())

    def _crear_item(self, m):
        nombre = m.nombre
        if m.tipo == PUNTO:
            item = _Punto(lambda: self._elegida_en_imagen(item), pos=(m.geom[0], m.geom[1]),
                          size=16, symbol="crosshair", pen=self._pen(nombre))
            item.sigPositionChanged.connect(lambda *_: self._movido(item))
            item.sigPositionChangeFinished.connect(lambda *_: self.terminaron.emit())
        elif m.tipo == LINEA:
            item = pg.LineSegmentROI([(m.geom[0], m.geom[1]), (m.geom[2], m.geom[3])],
                                     pen=self._pen(nombre))
        else:
            x0, y0, x1, y1 = m.geom
            item = pg.RectROI((min(x0, x1), min(y0, y1)), (abs(x1 - x0), abs(y1 - y0)),
                              pen=self._pen(nombre), sideScalers=True)
        if m.tipo != PUNTO:
            item.setAcceptedMouseButtons(Qt.LeftButton)
            item.sigClicked.connect(lambda *_: self._elegida_en_imagen(item))
            item.sigRegionChanged.connect(lambda *_: self._movido(item))
            item.sigRegionChangeFinished.connect(lambda *_: self.terminaron.emit())
        item.setZValue(12)
        texto = pg.TextItem(color=COLOR_MEDICION, fill=pg.mkBrush(*COLOR_SOMBRA), anchor=(0, 1))
        texto.setZValue(13)
        self.vb.addItem(item)
        self.vb.addItem(texto)
        item.nombre_medicion = nombre
        self._items[nombre] = (item, texto)

    def _nombre_de(self, item):
        return next((n for n, (it, _) in self._items.items() if it is item), None)

    def _elegida_en_imagen(self, item):
        nombre = self._nombre_de(item)
        if nombre:
            self.elegir(nombre)
            self.seleccionada.emit(nombre)

    def _movido(self, item):
        nombre = self._nombre_de(item)
        m = self.mediciones.buscar(nombre) if nombre else None
        if m is None:
            return
        if m.tipo == PUNTO:
            p = item.pos()
            m.geom = [float(p.x()), float(p.y())]
        elif m.tipo == LINEA:
            a, b = (item.pos() + h.pos() for h in item.getHandles())
            m.geom = [float(a.x()), float(a.y()), float(b.x()), float(b.y())]
        else:
            p, s = item.pos(), item.size()
            m.geom = [float(p.x()), float(p.y()), float(p.x() + s.x()), float(p.y() + s.y())]
        self.actualizar()
        self.cambiaron.emit()

    # -- creacion con el mouse ---------------------------------------------
    def _dentro(self, p):
        img = self.viewer.img
        return img is not None and 0 <= p.x() < img.ancho and 0 <= p.y() < img.alto

    def _agregar(self, tipo, geom):
        m = self.mediciones.agregar(tipo, geom)
        self._crear_item(m)
        self.elegir(m.nombre)
        self.actualizar()
        self.seleccionada.emit(m.nombre)
        self.cambiaron.emit()
        self.terminaron.emit()

    def _clic(self, ev):
        """Clic en la imagen: con la herramienta de punto, agrega uno.
        Devuelve True si lo uso."""
        if self.herramienta != PUNTO or ev.button() != Qt.LeftButton:
            if ev.button() == Qt.LeftButton and self.elegida:
                self.elegir("")
                self.seleccionada.emit("")
            return False
        p = self.vb.mapSceneToView(ev.scenePos())
        if not self._dentro(p):
            return False
        # Al centro del pixel, que es lo que se mide
        self._agregar(PUNTO, [np.floor(p.x()) + 0.5, np.floor(p.y()) + 0.5])
        return True

    def _arrastre(self, ev):
        """Arrastre en la imagen: con linea o area, la dibuja. True si lo uso."""
        if self.herramienta not in (LINEA, AREA) or ev.button() != Qt.LeftButton:
            return False
        p = self.vb.mapSceneToView(ev.scenePos())
        if ev.isStart():
            inicio = self.vb.mapSceneToView(ev.buttonDownScenePos())
            if not self._dentro(inicio):
                return False
            self._inicio = inicio
            pen = pg.mkPen(theme.color("acento"), width=2, style=Qt.DashLine)
            if self.herramienta == LINEA:
                self._borrador = pg.PlotCurveItem(pen=pen)
            else:
                self._borrador = QGraphicsRectItem()
                self._borrador.setPen(pen)
            self.vb.addItem(self._borrador)
        if self._borrador is None:
            return True
        a = self._inicio
        if self.herramienta == LINEA:
            self._borrador.setData([a.x(), p.x()], [a.y(), p.y()])
        else:
            self._borrador.setRect(min(a.x(), p.x()), min(a.y(), p.y()),
                                   abs(p.x() - a.x()), abs(p.y() - a.y()))
        if ev.isFinish():
            self.vb.removeItem(self._borrador)
            self._borrador = None
            img = self.viewer.img
            x = float(np.clip(p.x(), 0, img.ancho))
            y = float(np.clip(p.y(), 0, img.alto))
            if max(abs(x - a.x()), abs(y - a.y())) >= TAM_MINIMO:
                self._agregar(self.herramienta, [a.x(), a.y(), x, y])
        return True


class PanelMediciones(QWidget):
    """Tabla de mediciones con Delta T contra la referencia, y perfil de linea.

    Senales:
      seleccionada(str)       se eligio una fila
      renombrar(str, str)     se edito un nombre (viejo, nuevo)
      borrar(str)
      referenciaCambiada()
    """

    seleccionada = Signal(str)
    renombrar = Signal(str, str)
    borrar = Signal(str)
    referenciaCambiada = Signal()

    COLUMNAS = ("Nombre", "Máx", "Mín", "Media", "ΔT")

    def __init__(self):
        super().__init__()
        self.mediciones = Mediciones()
        self.temps = None
        self._llenando = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        cab = QHBoxLayout()
        cab.addWidget(etiqueta("MEDICIONES", "seccion"))
        cab.addStretch(1)
        self.btn_ref = boton("Referencia", "mdi6.star-outline",
                             tooltip="Usar la medición elegida como referencia del ΔT")
        self.btn_ref.clicked.connect(self._alternar_referencia)
        self.btn_borrar = boton("", "mdi6.delete-outline", tooltip="Borrar la medición (Supr)")
        self.btn_borrar.clicked.connect(lambda: self.borrar.emit(self._nombre_elegido()))
        cab.addWidget(self.btn_ref)
        cab.addWidget(self.btn_borrar)
        v.addLayout(cab)

        self.ayuda = etiqueta("Usá las herramientas de la barra para medir: punto (P), "
                              "línea (L) o área (R). ΔT es la máxima de cada medición "
                              "menos la de la referencia (★).", "suave")
        self.ayuda.setWordWrap(True)
        v.addWidget(self.ayuda)

        self.tabla = QTableWidget(0, len(self.COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self.COLUMNAS)
        self.tabla.verticalHeader().hide()
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        enc = self.tabla.horizontalHeader()
        enc.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.COLUMNAS)):
            enc.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tabla.itemSelectionChanged.connect(self._fila_elegida)
        self.tabla.itemChanged.connect(self._editada)
        self.tabla.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu)
        v.addWidget(self.tabla)

        self.titulo_perfil = etiqueta("", "suave")
        v.addWidget(self.titulo_perfil)
        self.grafico = pg.PlotWidget()
        self.grafico.setMinimumHeight(150)
        self.grafico.setMenuEnabled(False)
        self.grafico.setMouseEnabled(False, False)
        self.grafico.setLabel("left", "°C")
        self.grafico.setLabel("bottom", "píxeles")
        self.curva = self.grafico.plot([], [])
        v.addWidget(self.grafico)
        theme.al_cambiar(self._aplicar_tema)
        self._actualizar_visibilidad()
        self._actualizar_perfil()

    # -- API ---------------------------------------------------------------
    def set_datos(self, mediciones, temps):
        self.mediciones, self.temps = mediciones, temps
        self.refrescar()

    def refrescar(self):
        """Recalcula la tabla. Conserva la fila elegida."""
        elegida = self._nombre_elegido()
        self._llenando = True
        self.tabla.setRowCount(len(self.mediciones.lista))
        for fila, m in enumerate(self.mediciones.lista):
            e = estadistica(m, self.temps) if self.temps is not None else None
            d = self.mediciones.delta_t(m, self.temps) if self.temps is not None else None
            es_ref = m.nombre == self.mediciones.referencia
            nombre = QTableWidgetItem(m.nombre)
            nombre.setData(Qt.UserRole, m.nombre)
            nombre.setToolTip("Doble clic para cambiar el nombre")
            if es_ref:
                nombre.setText("★ " + m.nombre)
            valores = (_fmt(e and e.maxima), _fmt(e and e.minima), _fmt(e and e.media),
                       "ref." if es_ref else _fmt_delta(d))
            self.tabla.setItem(fila, 0, nombre)
            for col, texto in enumerate(valores, start=1):
                it = QTableWidgetItem(texto)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 4 and d is not None and d >= 1.0:
                    it.setForeground(pg.mkColor(theme.color("aviso")))
                self.tabla.setItem(fila, col, it)
        self._llenando = False
        if elegida:
            self.elegir(elegida, emitir=False)
        self._actualizar_visibilidad()
        self._actualizar_perfil()

    def elegir(self, nombre, emitir=False):
        self.tabla.blockSignals(not emitir)
        self.tabla.clearSelection()
        for fila in range(self.tabla.rowCount()):
            if self.tabla.item(fila, 0).data(Qt.UserRole) == nombre:
                self.tabla.selectRow(fila)
                break
        self.tabla.blockSignals(False)
        self._actualizar_botones()
        self._actualizar_perfil()

    # -- interno -----------------------------------------------------------
    def _nombre_elegido(self):
        filas = self.tabla.selectionModel().selectedRows() if self.tabla.selectionModel() else []
        if not filas:
            return ""
        it = self.tabla.item(filas[0].row(), 0)
        return it.data(Qt.UserRole) if it else ""

    def _fila_elegida(self):
        self._actualizar_botones()
        self._actualizar_perfil()
        self.seleccionada.emit(self._nombre_elegido())

    def _editada(self, item):
        if self._llenando or item.column() != 0:
            return
        viejo = item.data(Qt.UserRole)
        nuevo = item.text().lstrip("★").strip()
        if nuevo != viejo:
            self.renombrar.emit(viejo, nuevo)

    def _alternar_referencia(self):
        nombre = self._nombre_elegido()
        if not nombre:
            return
        es = self.mediciones.referencia == nombre
        self.mediciones.referencia = None if es else nombre
        self.referenciaCambiada.emit()

    def _menu(self, pos):
        nombre = self._nombre_elegido()
        if not nombre:
            return
        m = QMenu(self)
        es_ref = self.mediciones.referencia == nombre
        m.addAction("Quitar como referencia" if es_ref else "Usar como referencia del ΔT",
                    self._alternar_referencia)
        m.addAction("Cambiar nombre", lambda: self.tabla.editItem(
            self.tabla.item(self.tabla.currentRow(), 0)))
        m.addSeparator()
        m.addAction("Borrar", lambda: self.borrar.emit(nombre))
        m.exec(self.tabla.viewport().mapToGlobal(pos))

    def _actualizar_botones(self):
        nombre = self._nombre_elegido()
        self.btn_ref.setEnabled(bool(nombre))
        self.btn_borrar.setEnabled(bool(nombre))

    def _actualizar_visibilidad(self):
        hay = bool(self.mediciones.lista)
        self.tabla.setVisible(hay)
        self.btn_ref.setVisible(hay)
        self.btn_borrar.setVisible(hay)
        # Alto justo para las filas, sin scroll propio dentro del panel
        alto = self.tabla.horizontalHeader().height() + 4 + sum(
            self.tabla.rowHeight(f) for f in range(self.tabla.rowCount()))
        self.tabla.setFixedHeight(max(alto, 30))
        self._actualizar_botones()

    def _actualizar_perfil(self):
        m = self.mediciones.buscar(self._nombre_elegido())
        if m is None or m.tipo != LINEA or self.temps is None:
            self.grafico.hide()
            self.titulo_perfil.hide()
            return
        dist, valores = perfil(m, self.temps)
        self.curva.setData(dist, valores)
        self.titulo_perfil.setText("Perfil de %s" % m.nombre)
        self.titulo_perfil.show()
        self.grafico.show()

    def _aplicar_tema(self):
        self.grafico.setBackground(theme.color("superficie"))
        self.curva.setPen(pg.mkPen(theme.color("acento"), width=2))
        for eje in ("left", "bottom"):
            a = self.grafico.getAxis(eje)
            a.setPen(pg.mkPen(theme.color("borde")))
            a.setTextPen(pg.mkPen(theme.color("texto_suave")))
