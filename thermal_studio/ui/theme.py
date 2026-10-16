"""Tema visual: colores (oscuro y claro), hoja de estilos e iconos.

Los colores se definen una sola vez como tokens; la hoja de estilos (QSS), la
paleta de Qt, los iconos y el visor (pyqtgraph) salen de ellos. Al cambiar de
tema se emite `gestor.cambiado` y cada widget que lo necesite se actualiza.

Variantes de estilo por propiedad dinamica:
    QPushButton[variante="primario" | "secundario" | "icono" | "peligro"]
    QLabel[rol="titulo" | "seccion" | "suave" | "valor" | "grande"]
    QFrame[rol="tarjeta" | "panel" | "barra"]
"""
import tempfile
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import QObject, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPalette

OSCURO = "oscuro"
CLARO = "claro"

TOKENS = {
    OSCURO: {
        "fondo": "#0e1014",        # detras de todo / visor
        "panel": "#15181e",        # paneles laterales y barra
        "superficie": "#1d2129",   # tarjetas, campos
        "superficie_hover": "#262b35",
        "borde": "#2a303b",
        "texto": "#e7e9ee",
        "texto_suave": "#8c94a6",
        "acento": "#ff7a1a",       # naranja "termico"
        "acento_hover": "#ff9142",
        "acento_texto": "#14100c",
        "seleccion": "#3a2a1c",
        "max": "#ff5b4f",
        "min": "#3d9bff",
        "aviso": "#ffb020",
        "peligro": "#ff5b4f",
        "ok": "#34c759",
    },
    CLARO: {
        "fondo": "#e9ecf1",
        "panel": "#f7f8fa",
        "superficie": "#ffffff",
        "superficie_hover": "#eef1f5",
        "borde": "#d9dee6",
        "texto": "#1a1f29",
        "texto_suave": "#626b7d",
        "acento": "#ec6a00",
        "acento_hover": "#ff7f16",
        "acento_texto": "#ffffff",
        "seleccion": "#ffe3cc",
        "max": "#e0362b",
        "min": "#1f78e0",
        "aviso": "#b26b00",
        "peligro": "#d93025",
        "ok": "#1f9d45",
    },
}

FUENTES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Ubuntu Sans", "Noto Sans",
           "DejaVu Sans"]


class _Gestor(QObject):
    cambiado = Signal(str)

    def __init__(self):
        super().__init__()
        self.nombre = OSCURO

    @property
    def t(self):
        return TOKENS[self.nombre]


gestor = _Gestor()


def color(token):
    return gestor.t[token]


def icono(nombre, token="texto", **kw):
    """Icono vectorial (qtawesome, set mdi6) con el color del tema actual."""
    t = gestor.t
    return qta.icon(nombre, color=t[token], color_disabled=t["borde"],
                    color_active=t[token], **kw)


def icono_vivo(setter, nombre, token="texto", **kw):
    """Aplica el icono ahora y de nuevo cada vez que cambia el tema."""
    setter(icono(nombre, token, **kw))
    gestor.cambiado.connect(lambda *_: setter(icono(nombre, token, **kw)))


def al_cambiar(fn):
    """Llama a fn() ahora y en cada cambio de tema."""
    fn()
    gestor.cambiado.connect(lambda *_: fn())


def aplicar(app, nombre):
    gestor.nombre = nombre if nombre in TOKENS else OSCURO
    t = gestor.t

    f = QFont()
    f.setFamilies(FUENTES)
    f.setPointSizeF(10)
    app.setFont(f)

    pal = QPalette()
    for rol, tok in ((QPalette.Window, "panel"), (QPalette.WindowText, "texto"),
                     (QPalette.Base, "superficie"), (QPalette.AlternateBase, "panel"),
                     (QPalette.Text, "texto"), (QPalette.Button, "superficie"),
                     (QPalette.ButtonText, "texto"), (QPalette.Highlight, "acento"),
                     (QPalette.HighlightedText, "acento_texto"),
                     (QPalette.ToolTipBase, "superficie"), (QPalette.ToolTipText, "texto"),
                     (QPalette.PlaceholderText, "texto_suave")):
        pal.setColor(rol, QColor(t[tok]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(t["texto_suave"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t["texto_suave"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(t["texto_suave"]))
    app.setPalette(pal)
    app.setStyleSheet(_qss(dict(t, **_flechas_arbol(t))))
    gestor.cambiado.emit(gestor.nombre)


def _flechas_arbol(t):
    """El QSS solo acepta imagenes de archivo para las flechas del arbol: se
    generan desde los iconos, con el color del tema, en una carpeta temporal."""
    carpeta = Path(tempfile.gettempdir()) / "thermal_studio_tema"
    carpeta.mkdir(exist_ok=True)
    rutas = {}
    for clave, nombre in (("flecha_cerrada", "mdi6.chevron-right"),
                          ("flecha_abierta", "mdi6.chevron-down")):
        ruta = carpeta / ("%s_%s.png" % (clave, t["texto_suave"].lstrip("#")))
        if not ruta.exists():
            qta.icon(nombre, color=t["texto_suave"]).pixmap(QSize(16, 16)).save(str(ruta))
        rutas[clave] = ruta.as_posix()
    return rutas


def _qss(t):
    return """
* { outline: none; }
QMainWindow, QDialog { background: %(panel)s; }
QWidget { color: %(texto)s; }
QToolTip { background: %(superficie)s; color: %(texto)s; border: 1px solid %(borde)s;
           padding: 5px 8px; border-radius: 6px; }

/* --- contenedores --- */
QFrame[rol="panel"] { background: %(panel)s; border: none; }
QFrame[rol="barra"] { background: %(panel)s; border-bottom: 1px solid %(borde)s; }
QFrame[rol="tarjeta"] { background: %(superficie)s; border: 1px solid %(borde)s;
                        border-radius: 10px; }
QFrame[rol="separador"] { background: %(borde)s; border: none; margin: 4px 6px; }
/* Zona de agarre de 7 px con una linea de 1 px al medio: con el handle de
   1 px no habia forma de agarrarlo con el mouse */
QSplitter::handle:horizontal { width: 7px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 transparent, stop:0.43 transparent, stop:0.431 %(borde)s, stop:0.569 %(borde)s,
    stop:0.57 transparent, stop:1 transparent); }
QSplitter::handle:vertical { height: 7px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
    stop:0 transparent, stop:0.43 transparent, stop:0.431 %(borde)s, stop:0.569 %(borde)s,
    stop:0.57 transparent, stop:1 transparent); }
QSplitter::handle:horizontal:hover, QSplitter::handle:horizontal:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent,
    stop:0.28 transparent, stop:0.285 %(acento)s, stop:0.715 %(acento)s,
    stop:0.72 transparent, stop:1 transparent); }
QSplitter::handle:vertical:hover, QSplitter::handle:vertical:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 transparent,
    stop:0.28 transparent, stop:0.285 %(acento)s, stop:0.715 %(acento)s,
    stop:0.72 transparent, stop:1 transparent); }

/* --- textos --- */
QLabel[rol="titulo"] { font-size: 15px; font-weight: 600; }
QLabel[rol="seccion"] { color: %(texto_suave)s; font-size: 11px; font-weight: 600;
                        letter-spacing: 0.8px; }
QLabel[rol="suave"] { color: %(texto_suave)s; font-size: 12px; }
QLabel[rol="etiqueta"] { color: %(texto_suave)s; font-size: 11px; }
QLabel[rol="valor"] { font-size: 17px; font-weight: 600; }
QLabel[rol="grande"] { font-size: 26px; font-weight: 600; }

/* --- botones --- */
QPushButton, QToolButton {
    background: %(superficie)s; border: 1px solid %(borde)s; border-radius: 8px;
    padding: 6px 12px; }
QPushButton:hover, QToolButton:hover { background: %(superficie_hover)s; }
QPushButton:pressed, QToolButton:pressed { background: %(borde)s; }
QPushButton:disabled, QToolButton:disabled { color: %(texto_suave)s; border-color: %(borde)s; }
QPushButton[variante="primario"] { background: %(acento)s; color: %(acento_texto)s;
                                   border: 1px solid %(acento)s; font-weight: 600; }
QPushButton[variante="primario"]:hover { background: %(acento_hover)s; }
QPushButton[variante="primario"]:disabled { background: %(superficie)s; color: %(texto_suave)s;
                                            border-color: %(borde)s; }
QPushButton[variante="icono"], QToolButton[variante="icono"] {
    background: transparent; border: 1px solid transparent; padding: 5px; }
QPushButton[variante="icono"]:hover, QToolButton[variante="icono"]:hover {
    background: %(superficie_hover)s; }
QToolButton[variante="icono"]:checked, QPushButton[variante="icono"]:checked {
    background: %(seleccion)s; border-color: %(acento)s; }
QPushButton[variante="peligro"]:hover { border-color: %(peligro)s; color: %(peligro)s; }
/* Botones de texto que funcionan como selector (p. ej. Máximas / ΔT) */
QPushButton[variante="secundario"]:checked {
    background: %(seleccion)s; border-color: %(acento)s; color: %(texto)s; }

/* --- campos --- */
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {
    background: %(superficie)s; border: 1px solid %(borde)s; border-radius: 8px;
    padding: 5px 8px; min-height: 18px; selection-background-color: %(acento)s;
    selection-color: %(acento_texto)s; }
QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover, QLineEdit:hover { border-color: %(texto_suave)s; }
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus { border-color: %(acento)s; }
QComboBox:disabled, QDoubleSpinBox:disabled { color: %(texto_suave)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: %(superficie)s; border: 1px solid %(borde)s;
    border-radius: 8px; padding: 4px; selection-background-color: %(seleccion)s;
    selection-color: %(texto)s; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QCheckBox { spacing: 8px; }

/* --- listas y arboles --- */
QTreeView, QListView { background: transparent; border: none; }
QTreeView { show-decoration-selected: 1; }
QTreeView::branch { background: transparent; }
QTreeView::branch:selected { background: %(seleccion)s; }
QTreeView::branch:closed:has-children { image: url(%(flecha_cerrada)s); }
QTreeView::branch:open:has-children { image: url(%(flecha_abierta)s); }
QTreeView::item { padding: 4px 2px; }
QTreeView::item:hover, QListView::item:hover { background: %(superficie_hover)s; }
QTreeView::item:selected, QListView::item:selected { background: %(seleccion)s; color: %(texto)s; }
QListView::item { border-radius: 8px; padding: 4px; }

/* --- barras de desplazamiento finas --- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle { background: %(borde)s; border-radius: 3px; min-height: 30px; min-width: 30px; }
QScrollBar::handle:hover { background: %(texto_suave)s; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    background: none; border: none; width: 0; height: 0; }

/* --- progreso --- */
QProgressBar { background: %(superficie)s; border: 1px solid %(borde)s; border-radius: 6px;
               height: 14px; text-align: center; font-size: 11px; }
QProgressBar::chunk { background: %(acento)s; border-radius: 5px; }

/* --- menus y barra de estado --- */
QMenuBar { background: %(panel)s; border-bottom: 1px solid %(borde)s; padding: 2px 6px; }
QMenuBar::item { padding: 5px 10px; border-radius: 6px; background: transparent; }
QMenuBar::item:selected { background: %(superficie_hover)s; }
QMenu { background: %(superficie)s; border: 1px solid %(borde)s; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: %(seleccion)s; }
QMenu::separator { height: 1px; background: %(borde)s; margin: 4px 8px; }
QStatusBar { background: %(panel)s; border-top: 1px solid %(borde)s; color: %(texto_suave)s; }
QStatusBar::item { border: none; }
""" % t
