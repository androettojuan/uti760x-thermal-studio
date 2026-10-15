"""Piezas de interfaz reutilizables, con el estilo del tema."""
import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QSizePolicy, QToolButton

from ..core import palettes
from . import theme


def _repulir(w):
    w.style().unpolish(w)
    w.style().polish(w)


def etiqueta(texto="", rol=None, parent=None):
    lbl = QLabel(texto, parent)
    if rol:
        lbl.setProperty("rol", rol)
    return lbl


def marco(rol, parent=None):
    f = QFrame(parent)
    f.setProperty("rol", rol)
    return f


def separador():
    s = marco("separador")
    s.setFrameShape(QFrame.NoFrame)
    s.setFixedWidth(1)
    s.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    return s


def boton(texto, icono=None, variante="secundario", tooltip="", token_icono=None):
    b = QPushButton(texto)
    b.setProperty("variante", variante)
    b.setCursor(Qt.PointingHandCursor)
    if tooltip:
        b.setToolTip(tooltip)
    if icono:
        tok = token_icono or ("acento_texto" if variante == "primario" else "texto")
        theme.icono_vivo(b.setIcon, icono, tok)
        b.setIconSize(QSize(17, 17))
    return b


def boton_icono(icono, tooltip, checkable=False, token="texto"):
    """Boton solo con icono (para barras). Si es checkable, al activarse el
    icono toma el color de acento."""
    b = QToolButton()
    b.setProperty("variante", "icono")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setIconSize(QSize(19, 19))
    b.setAutoRaise(True)

    def actualizar(*_):
        tok = "acento" if (checkable and b.isChecked()) else token
        b.setIcon(theme.icono(icono, tok))
    b.toggled.connect(actualizar)
    theme.al_cambiar(actualizar)
    return b


def swatch_paleta(nombre, invertir=False, ancho=56, alto=14, radio=4):
    """Icono con el degrade de una paleta, para el selector."""
    lut = palettes.get(nombre, invertir)
    idx = np.linspace(0, len(lut) - 1, ancho).astype(int)
    fila = np.ascontiguousarray(np.repeat(lut[idx][None, :, :], alto, axis=0))
    img = QImage(fila.data, ancho, alto, ancho * 3, QImage.Format_RGB888).copy()
    pix = QPixmap(ancho, alto)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    camino = QPainterPath()
    camino.addRoundedRect(0, 0, ancho, alto, radio, radio)
    p.setClipPath(camino)
    p.drawImage(0, 0, img)
    p.end()
    return QIcon(pix)


def pixmap_redondeado(pix, radio=10):
    out = QPixmap(pix.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    camino = QPainterPath()
    camino.addRoundedRect(0, 0, pix.width(), pix.height(), radio, radio)
    p.setClipPath(camino)
    p.drawPixmap(0, 0, pix)
    p.end()
    return out


def set_propiedad(w, nombre, valor):
    """Cambia una propiedad de estilo y fuerza a Qt a re-aplicar el QSS."""
    w.setProperty(nombre, valor)
    _repulir(w)
