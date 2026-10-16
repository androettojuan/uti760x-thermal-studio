"""Visor de imagen termica: imagen con paleta, barra de color y marcadores."""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter

from ..core import palettes
from ..core.thermal_image import posiciones_ecualizadas
from . import theme

pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)

# Sobre la imagen los colores no dependen del tema: el fondo es la imagen misma
COLOR_MAX = "#ff5b4f"
COLOR_MIN = "#3d9bff"
COLOR_CENTRO = "#ffffff"


CONTRASTE_CAMARA = "camara"   # colores repartidos segun el histograma
CONTRASTE_LINEAL = "lineal"   # escala pareja entre minima y maxima


def _colormap(paleta, invertir, posiciones=None):
    lut = palettes.get(paleta, invertir)
    if posiciones is None:
        posiciones = np.linspace(0, 1, len(lut))
    return pg.ColorMap(posiciones, lut)


class MarcasSinClic(pg.ScatterPlotItem):
    """Marcas que no se quedan con los clics: si no, un clic justo sobre la
    marca del centro no llegaba a la herramienta de medir."""

    def mouseClickEvent(self, ev):
        ev.ignore()


class VistaImagen(pg.ViewBox):
    """ViewBox que deja a otro (la capa de mediciones) quedarse con los clics
    y arrastres. Si el manejador devuelve False, se comporta como siempre:
    arrastrar mueve la imagen."""

    def __init__(self):
        super().__init__()
        self.manejador_clic = None
        self.manejador_arrastre = None

    def mouseClickEvent(self, ev):
        if self.manejador_clic and self.manejador_clic(ev):
            ev.accept()
            return
        super().mouseClickEvent(ev)

    def mouseDragEvent(self, ev, axis=None):
        if self.manejador_arrastre and self.manejador_arrastre(ev):
            ev.accept()
            return
        super().mouseDragEvent(ev, axis)


def fmt_temp(t):
    return "—" if t is None else "%.1f °C" % t


class ThermalViewer(pg.GraphicsLayoutWidget):
    """Muestra una ThermalImage.

    Senales:
      cursorMovido(fila, col, temp)  temp = None fuera de la imagen
      rangoCambiado(lo, hi)          al soltar la barra de color
    """

    cursorMovido = Signal(object, object, object)
    rangoCambiado = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.img = None
        self.paleta = palettes.POR_DEFECTO
        self.invertir = False
        self.contraste = CONTRASTE_CAMARA
        self.temps_reparto = None  # si no es None, ecualiza con esto y no con la imagen

        self.vb = VistaImagen()
        self.addItem(self.vb, row=0, col=0)
        self.vb.setAspectLocked(True)
        self.vb.invertY(True)
        self.vb.setMenuEnabled(False)

        self.item = pg.ImageItem()
        self.vb.addItem(self.item)

        self.cbar = pg.ColorBarItem(values=(0, 1), colorMap=_colormap(self.paleta, False),
                                    interactive=True, rounding=0.1, width=22)
        self.cbar.setImageItem(self.item)
        self.cbar.sigLevelsChangeFinished.connect(self._barra_soltada)
        self.addItem(self.cbar, row=0, col=1)

        # Marcadores de max / min / centro
        self.marcas = MarcasSinClic(pxMode=True, size=14)
        self.vb.addItem(self.marcas)
        self.etiquetas = []
        for color in (COLOR_MAX, COLOR_MIN, COLOR_CENTRO):
            t = pg.TextItem(color=color, fill=pg.mkBrush(14, 16, 20, 200), anchor=(0, 1))
            t.setZValue(10)
            self.vb.addItem(t)
            self.etiquetas.append(t)

        # Lectura bajo el cursor
        self.lectura = pg.TextItem(color="w", fill=pg.mkBrush(14, 16, 20, 215))
        self.lectura.setZValue(20)
        self.lectura.hide()
        self.vb.addItem(self.lectura)

        self.set_suavizado(True)
        theme.al_cambiar(self._aplicar_tema)
        self.scene().sigMouseMoved.connect(self._mouse_movido)
        self.setCursor(Qt.CrossCursor)

    # -- API ---------------------------------------------------------------
    def mostrar(self, img, rango=None):
        self.img = img
        self.item.setImage(img.temps, autoLevels=False)
        self.set_rango(*(rango or img.rango_auto()))
        self._actualizar_marcas()
        self.vb.autoRange(padding=0.01)

    def set_paleta(self, paleta, invertir=False):
        self.paleta, self.invertir = paleta, invertir
        self._aplicar_colormap()

    def set_contraste(self, modo):
        self.contraste = modo
        self._aplicar_colormap()

    def set_suavizado(self, activo):
        """Interpola los colores al ampliar, como la pantalla de la camara.

        Es solo como se dibuja: no agrega detalle, y la lectura bajo el
        cursor sigue siendo la del pixel real del sensor (640x512).
        """
        self.setRenderHint(QPainter.SmoothPixmapTransform, activo)
        self.viewport().update()

    def set_reparto(self, temps):
        """Temperaturas con las que repartir los colores en modo camara, o None
        para usar las de la imagen. Al comparar se le pasan las de todas."""
        self.temps_reparto = temps
        self._aplicar_colormap()

    def set_rango(self, lo, hi):
        if hi <= lo:
            hi = lo + 0.1
        self.cbar.setLevels((lo, hi))
        self._aplicar_colormap()

    def rango(self):
        return tuple(float(v) for v in self.cbar.levels())

    def set_marcas_visibles(self, visible):
        self.marcas.setVisible(visible)
        for t in self.etiquetas:
            t.setVisible(visible)

    # -- interno -----------------------------------------------------------
    def _aplicar_colormap(self):
        """En modo camara el reparto de colores depende de la imagen y del
        rango, asi que se rearma cada vez que cambia alguno de los dos."""
        posiciones = None
        if self.contraste == CONTRASTE_CAMARA and self.img is not None:
            lo, hi = self.rango()
            n = len(palettes.get(self.paleta, self.invertir))
            temps = self.img.temps if self.temps_reparto is None else self.temps_reparto
            posiciones = posiciones_ecualizadas(temps, lo, hi, n)
        self.cbar.setColorMap(_colormap(self.paleta, self.invertir, posiciones))

    def _aplicar_tema(self):
        self.setBackground(theme.color("fondo"))
        eje = self.cbar.axis
        eje.setPen(pg.mkPen(theme.color("borde")))
        eje.setTextPen(pg.mkPen(theme.color("texto_suave")))

    def _actualizar_marcas(self):
        img = self.img
        puntos = [img.maximo(), img.minimo(), img.centro()]
        simbolos = ["t1", "t", "+"]  # triangulo arriba, abajo, cruz
        colores = [COLOR_MAX, COLOR_MIN, COLOR_CENTRO]
        self.marcas.setData(
            [{"pos": (p.col + 0.5, p.fila + 0.5), "symbol": s,
              "brush": pg.mkBrush(c), "pen": pg.mkPen("k", width=1)}
             for p, s, c in zip(puntos, simbolos, colores)])
        for t, p in zip(self.etiquetas, puntos):
            t.setText(fmt_temp(p.temp))
            self._ubicar(t, p.col + 0.5, p.fila + 0.5)

    def _mouse_movido(self, pos_escena):
        if self.img is None or not self.vb.sceneBoundingRect().contains(pos_escena):
            self.lectura.hide()
            self.cursorMovido.emit(None, None, None)
            return
        p = self.vb.mapSceneToView(pos_escena)
        col, fila = int(np.floor(p.x())), int(np.floor(p.y()))
        temp = self.img.temp_en(fila, col)
        if temp is None:
            self.lectura.hide()
        else:
            self.lectura.setText(fmt_temp(temp))
            self._ubicar(self.lectura, p.x(), p.y())
            self.lectura.show()
        self.cursorMovido.emit(fila, col, temp)

    def _ubicar(self, texto, x, y, margen=8):
        """Pone la etiqueta junto a (x, y), del lado que no se sale de la imagen."""
        a_izquierda = x > self.img.ancho * 0.85
        abajo = y < self.img.alto * 0.08
        texto.setAnchor((1, 0) if a_izquierda and abajo else
                        (1, 1) if a_izquierda else
                        (0, 0) if abajo else (0, 1))
        texto.setPos(x + (-margen if a_izquierda else margen),
                     y + (margen if abajo else -margen))

    def _barra_soltada(self, *_):
        self._aplicar_colormap()
        lo, hi = self.rango()
        self.rangoCambiado.emit(lo, hi)

    def leaveEvent(self, ev):
        self.lectura.hide()
        self.cursorMovido.emit(None, None, None)
        super().leaveEvent(ev)
