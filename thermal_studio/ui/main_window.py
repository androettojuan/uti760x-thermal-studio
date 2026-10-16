"""Ventana principal: biblioteca | visor | datos, con barra de herramientas arriba."""
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QButtonGroup, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from ..core import camera_ftp, palettes
from ..core.importer import Modo
from ..core.library import Library
from ..core.mediciones import AREA, LINEA, PUNTO
from ..core.thermal_image import ThermalImage
from ..core.uti760x import FormatoInvalido, TempConverter
from . import sistema, theme
from .compare import VistaComparacion
from .mediciones_ui import CapaMediciones, PanelMediciones
from .library_panel import LibraryPanel
from .viewer import CONTRASTE_CAMARA, CONTRASTE_LINEAL, ThermalViewer, fmt_temp
from .widgets import (
    TarjetaDato, boton, boton_icono, etiqueta, marco, pixmap_redondeado, separador,
    swatch_paleta,
)

APP_NOMBRE = "Thermal Studio"
EXTENSIONES = {".jpg", ".jpeg"}


def _fmt(v, sufijo=""):
    return "—" if v is None else "%s%s" % (v, sufijo)


# -- panel derecho -----------------------------------------------------------
class MiniaturaVisible(QLabel):
    """Foto visible en el panel: se ajusta al ancho y se amplia con un clic."""

    clic = Signal()

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Foto visible tomada por la cámara. Clic para verla en grande (V)")
        self.setMinimumWidth(1)  # que no impida achicar el panel
        self._original = None

    def set_foto(self, pix):
        self._original = pix
        self._escalar()

    def _escalar(self):
        if self._original is None or self._original.isNull():
            self.clear()
            return
        ancho = max(self.width(), 120)
        self.setPixmap(pixmap_redondeado(
            self._original.scaledToWidth(ancho, Qt.SmoothTransformation), 10))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._original is not None and (self.pixmap().isNull()
                                           or self.pixmap().width() != max(self.width(), 120)):
            self._escalar()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._original is not None:
            self.clic.emit()
        super().mouseReleaseEvent(ev)


class _FotoAjustada(QLabel):
    """Muestra una foto entera, ajustada al tamano disponible."""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(200, 150)
        self._original = None

    def set_foto(self, pix):
        self._original = pix
        self._escalar()

    def _escalar(self):
        if self._original is not None and not self._original.isNull():
            self.setPixmap(self._original.scaled(self.size(), Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._escalar()


class VentanaVisible(QDialog):
    """Foto visible en grande. No es modal: sigue a la foto abierta mientras
    se navega, asi se puede tener al lado de la termica."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.foto = _FotoAjustada()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self.foto)
        self.resize(1000, 780)

    def mostrar(self, pix, titulo):
        self.setWindowTitle("Foto visible — %s" % titulo)
        self.foto.set_foto(pix)


class PanelInfo(QScrollArea):
    """Panel derecho: temperaturas, parametros de captura y foto visible."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        cont = marco("panel")
        self.setWidget(cont)
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        self.archivo = etiqueta("Sin imagen", "titulo")
        self.archivo.setWordWrap(True)
        self.fecha = etiqueta("Elegí una foto de la biblioteca", "suave")
        lay.addWidget(self.archivo)
        lay.addWidget(self.fecha)

        # Cursor
        cursor = marco("tarjeta")
        cv = QVBoxLayout(cursor)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(0)
        cv.addWidget(etiqueta("BAJO EL CURSOR", "seccion"))
        self.cursor = etiqueta("—", "grande")
        self.coords = etiqueta("Pasá el mouse por la imagen", "suave")
        cv.addWidget(self.cursor)
        cv.addWidget(self.coords)
        lay.addWidget(cursor)

        # Estadisticas
        grid = QGridLayout()
        grid.setSpacing(8)
        self.tmax = TarjetaDato("Máxima", "max")
        self.tmin = TarjetaDato("Mínima", "min")
        self.tcentro = TarjetaDato("Centro")
        self.tmedia = TarjetaDato("Media")
        self.delta = TarjetaDato("Diferencia máx − mín (ΔT)", "acento")
        grid.addWidget(self.tmax, 0, 0)
        grid.addWidget(self.tmin, 0, 1)
        grid.addWidget(self.tcentro, 1, 0)
        grid.addWidget(self.tmedia, 1, 1)
        grid.addWidget(self.delta, 2, 0, 1, 2)
        lay.addLayout(grid)

        # Mediciones
        lay.addSpacing(4)
        self.mediciones = PanelMediciones()
        lay.addWidget(self.mediciones)

        # Parametros
        lay.addSpacing(4)
        lay.addWidget(etiqueta("PARÁMETROS DE CAPTURA", "seccion"))
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)
        lay.addLayout(form)

        def fila(titulo):
            v = QLabel("—")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(etiqueta(titulo, "suave"), v)
            return v
        self.ems = fila("Emisividad")
        self.trefl = fila("T. reflejada")
        self.tamb = fila("T. ambiente")
        self.hum = fila("Humedad")
        self.dist = fila("Distancia")

        self.aviso = etiqueta("", "suave")
        self.aviso.setWordWrap(True)
        lay.addWidget(self.aviso)

        self.titulo_visible = etiqueta("FOTO VISIBLE", "seccion")
        self.visible = MiniaturaVisible()
        lay.addWidget(self.titulo_visible)
        lay.addWidget(self.visible)
        self.titulo_visible.hide()
        lay.addStretch(1)
        self._img = None
        self.foto_visible = None
        theme.al_cambiar(lambda: self._img and self._pintar_aviso(self._img))

    def mostrar(self, img):
        self._img = img
        m = img.meta
        self.archivo.setText(img.path.name if img.path else "—")
        self.fecha.setText(m.fecha.strftime("%d/%m/%Y  %H:%M:%S") if m.fecha else "Sin fecha")
        mx, mn = img.maximo(), img.minimo()
        self.tmax.set(fmt_temp(mx.temp))
        self.tmin.set(fmt_temp(mn.temp))
        self.tcentro.set(fmt_temp(img.centro().temp))
        self.tmedia.set(fmt_temp(img.media()))
        self.delta.set("%.1f °C" % (mx.temp - mn.temp))
        self.ems.setText(_fmt(m.emisividad))
        self.trefl.setText(_fmt(m.temp_reflejada, " °C"))
        self.tamb.setText(_fmt(m.temp_ambiente, " °C"))
        self.hum.setText(_fmt(m.humedad, " %"))
        self.dist.setText(_fmt(m.distancia_m, " m"))
        self._pintar_aviso(img)

        pix = QPixmap()
        if img.visible_jpeg and pix.loadFromData(img.visible_jpeg):
            self.foto_visible = pix
            self.visible.set_foto(pix)
            self.titulo_visible.show()
        else:
            self.foto_visible = None
            self.visible.set_foto(None)
            self.titulo_visible.hide()

    def _pintar_aviso(self, img):
        aviso = "Precisión de la conversión a grados: ±%.1f °C típico." % img.incertidumbre_c
        if img.rango_alto:
            aviso = ("<b style='color:%s'>⚠ Rango alto sin calibrar</b><br>La foto se sacó en el "
                     "rango de temperatura alto de la cámara, que el programa todavía no sabe "
                     "convertir. Las temperaturas que ves no son confiables."
                     % theme.color("aviso"))
        elif img.fuera_de_rango:
            lo, hi = TempConverter.RANGO_VALIDADO_C
            aviso = ("<b style='color:%s'>⚠ Fuera del rango calibrado</b><br>La imagen tiene "
                     "temperaturas fuera de %d a %d °C; los valores extremos son aproximados."
                     "<br><br>%s" % (theme.color("aviso"), lo, hi, aviso))
        self.aviso.setText(aviso)

    def set_cursor(self, fila, col, temp):
        self.cursor.setText(fmt_temp(temp))
        self.coords.setText("Pasá el mouse por la imagen" if temp is None
                            else "x %d · y %d" % (col, fila))


# -- visor con estado vacio --------------------------------------------------
class AreaVisor(QStackedWidget):
    def __init__(self, viewer, comparacion):
        super().__init__()
        vacio = marco("panel")
        v = QVBoxLayout(vacio)
        v.setAlignment(Qt.AlignCenter)
        icono = QLabel()
        icono.setAlignment(Qt.AlignCenter)
        theme.al_cambiar(lambda: icono.setPixmap(
            theme.icono("mdi6.thermometer-lines", "texto_suave").pixmap(QSize(64, 64))))
        v.addWidget(icono)
        t = etiqueta("Elegí una foto de la biblioteca", "titulo")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        s = etiqueta("o traé las nuevas desde la cámara con «Traer faltantes»", "suave")
        s.setAlignment(Qt.AlignCenter)
        v.addWidget(s)
        theme.al_cambiar(lambda: vacio.setStyleSheet(
            "QFrame { background: %s; }" % theme.color("fondo")))
        self.addWidget(vacio)
        self.addWidget(viewer)
        self.addWidget(comparacion)

    def mostrar_visor(self):
        self.setCurrentIndex(1)

    def mostrar_comparacion(self):
        self.setCurrentIndex(2)

    def comparando(self):
        return self.currentIndex() == 2


# -- dialogo de conexion -----------------------------------------------------
class DialogoCamara(QDialog):
    """Datos de conexion al FTP de la camara."""

    def __init__(self, conexion, red_wifi="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conexión con la cámara")
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(10)
        self.host = QLineEdit(conexion["host"])
        self.puerto = QSpinBox()
        self.puerto.setRange(1, 65535)
        self.puerto.setValue(int(conexion["puerto"]))
        self.usuario = QLineEdit(conexion["usuario"])
        self.clave = QLineEdit(conexion["clave"])
        self.clave.setEchoMode(QLineEdit.Password)
        self.red = QLineEdit(red_wifi)
        self.red.setPlaceholderText("Se detecta sola al conectarse la primera vez")
        intro = etiqueta("Conectá la PC al WiFi de la cámara y activá el FTP en la cámara.",
                         "suave")
        intro.setWordWrap(True)
        form.addRow(intro)
        form.addRow("Red WiFi", self.red)
        form.addRow("Dirección", self.host)
        form.addRow("Puerto", self.puerto)
        form.addRow("Usuario", self.usuario)
        form.addRow("Contraseña", self.clave)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                                   | QDialogButtonBox.RestoreDefaults)
        botones.button(QDialogButtonBox.Ok).setText("Guardar")
        botones.button(QDialogButtonBox.Ok).setProperty("variante", "primario")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.button(QDialogButtonBox.RestoreDefaults).setText("Valores de fábrica")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        botones.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        form.addRow(botones)

    def _defaults(self):
        self.host.setText(camera_ftp.HOST)
        self.puerto.setValue(camera_ftp.PUERTO)
        self.usuario.setText(camera_ftp.USUARIO)
        self.clave.setText(camera_ftp.CLAVE)

    def conexion(self):
        return {"host": self.host.text().strip(), "puerto": self.puerto.value(),
                "usuario": self.usuario.text(), "clave": self.clave.text()}

    def red_wifi(self):
        return self.red.text().strip()


# -- ventana -----------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ThermalStudio", "ThermalStudio")
        self.img = None
        self.archivos = []  # .jpg de la carpeta actual, para anterior/siguiente
        self.indice = -1

        self.setWindowTitle(APP_NOMBRE)
        self.resize(1440, 860)
        self.setAcceptDrops(True)

        self.viewer = ThermalViewer()
        self.capa = CapaMediciones(self.viewer)
        self.viewer.cursorMovido.connect(self._cursor_movido)
        self.viewer.rangoCambiado.connect(self._rango_desde_barra)
        self.comparacion = VistaComparacion()
        self.comparacion.rangoCambiado.connect(self._rango_desde_barra)
        self.comparacion.cerrar.connect(self.cerrar_comparacion)
        self.area_visor = AreaVisor(self.viewer, self.comparacion)

        self.panel = PanelInfo()
        self.panel.setMinimumWidth(290)
        self.panel.visible.clic.connect(self.ver_visible)
        self._ventana_visible = None

        raiz = self.settings.value("biblioteca") or str(sistema.biblioteca_por_defecto())
        self.biblioteca = Library(raiz)
        self.panel_bib = LibraryPanel(self.biblioteca, self.conexion_camara)
        self.panel_bib.setMinimumWidth(340)
        self.panel_bib.abrirFoto.connect(self.abrir)
        self.panel_bib.compararFotos.connect(self.comparar)
        self.panel_bib.mensaje.connect(lambda m: self.statusBar().showMessage(m, 10000))

        self.split = QSplitter(Qt.Horizontal)
        self.split.setHandleWidth(7)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.panel_bib)
        self.split.addWidget(self.area_visor)
        self.split.addWidget(self.panel)
        self.split.setStretchFactor(1, 1)
        estado = self.settings.value("divisores")
        if estado is None or not self.split.restoreState(estado):
            self.split.setSizes([380, 760, 300])

        # La barra va a todo el ancho y no dentro de la columna del visor: ahi
        # su ancho minimo (~1090 px) dejaba a los tres paneles en su minimo y
        # los divisores no se podian mover
        raiz_ui = QWidget()
        rv = QVBoxLayout(raiz_ui)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self._crear_barra())
        rv.addWidget(self.split, 1)
        self.setCentralWidget(raiz_ui)

        self._crear_menu()
        self._conectar_mediciones()
        self.statusBar().showMessage("Listo")

    # -- menu --------------------------------------------------------------
    def _crear_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        self.act_abrir = m.addAction("Abrir imagen…", self.dialogo_abrir)
        self.act_abrir.setShortcut(QKeySequence.Open)
        m.addAction("Cambiar carpeta de la biblioteca…", self.cambiar_biblioteca)
        m.addAction("Mostrar biblioteca en el Explorador",
                    lambda: sistema.mostrar_en_explorador(self.biblioteca.raiz))
        m.addSeparator()
        m.addAction("Salir", self.close).setShortcut(QKeySequence.Quit)

        m = mb.addMenu("&Cámara")
        self.act_importar = m.addAction("Traer fotos faltantes",
                                        lambda: self.importar(Modo.FALTANTES))
        self.act_importar.setShortcut("Ctrl+I")
        m.addAction("Traer todas las fotos", lambda: self.importar(Modo.TODO))
        m.addSeparator()
        m.addAction("Configurar conexión…", self.configurar_camara)

        m = mb.addMenu("&Ver")
        for texto, w, atajo in (("Biblioteca", self.panel_bib, "Ctrl+1"),
                                ("Datos", self.panel, "Ctrl+2")):
            a = m.addAction(texto)
            a.setCheckable(True)
            a.setChecked(True)
            a.setShortcut(atajo)
            a.toggled.connect(w.setVisible)
        m.addSeparator()
        self.act_visible = m.addAction("Foto visible en grande", self.ver_visible)
        self.act_visible.setShortcut("V")
        a = m.addAction("Suavizar la imagen térmica")
        a.setCheckable(True)
        a.setToolTip("Interpola al ampliar, como la pantalla de la cámara. No agrega detalle: "
                     "el sensor es de 640×512")
        a.setChecked(self.settings.value("suavizar", True, type=bool))
        a.toggled.connect(self._suavizado_cambiado)
        for v in self._visores():
            v.set_suavizado(a.isChecked())
        m.addSeparator()
        self.act_comparar = m.addAction("Comparar las dos fotos seleccionadas",
                                        self.comparar_seleccionadas)
        self.act_comparar.setShortcut("C")
        a = m.addAction("Soltar herramienta / cerrar comparación", self._escape)
        a.setShortcut(Qt.Key_Escape)
        a = m.addAction("Borrar la medición elegida", self.borrar_medicion)
        a.setShortcut(QKeySequence.Delete)
        m.addSeparator()
        sub = m.addMenu("Tema")
        grupo = QActionGroup(self)
        for nombre, texto in ((theme.OSCURO, "Oscuro"), (theme.CLARO, "Claro")):
            a = sub.addAction(texto)
            a.setCheckable(True)
            a.setChecked(theme.gestor.nombre == nombre)
            a.triggered.connect(lambda _=False, n=nombre: self.set_tema(n))
            grupo.addAction(a)
        self._acciones_tema = {a.text(): a for a in grupo.actions()}

    def _suavizado_cambiado(self, activo):
        self.settings.setValue("suavizar", activo)
        for v in self._visores():
            v.set_suavizado(activo)

    def ver_visible(self):
        if self.panel.foto_visible is None:
            self.statusBar().showMessage("Esta foto no tiene imagen visible.", 5000)
            return
        if self._ventana_visible is None:
            self._ventana_visible = VentanaVisible(self)
        self._actualizar_visible()
        self._ventana_visible.show()
        self._ventana_visible.raise_()
        self._ventana_visible.activateWindow()

    def _actualizar_visible(self):
        v = self._ventana_visible
        if self.panel.foto_visible is None:
            v.hide()
        else:
            v.mostrar(self.panel.foto_visible, self.img.path.name if self.img.path else "")

    def set_tema(self, nombre):
        theme.aplicar(QApplication.instance(), nombre)
        self.settings.setValue("tema", nombre)
        for a in self._acciones_tema.values():
            a.setChecked(a.text() == ("Oscuro" if nombre == theme.OSCURO else "Claro"))

    def conexion_camara(self):
        s = self.settings
        return {"host": s.value("camara/host", camera_ftp.HOST),
                "puerto": int(s.value("camara/puerto", camera_ftp.PUERTO)),
                "usuario": s.value("camara/usuario", camera_ftp.USUARIO),
                "clave": s.value("camara/clave", camera_ftp.CLAVE)}

    def configurar_camara(self):
        d = DialogoCamara(self.conexion_camara(), self.panel_bib.red_camara(), self)
        if d.exec() == QDialog.Accepted:
            for k, v in d.conexion().items():
                self.settings.setValue("camara/" + k, v)
            self.settings.setValue("camara/wifi", d.red_wifi())
            self.panel_bib.monitor.acelerar()

    def importar(self, modo):
        self.panel_bib.show()
        self.panel_bib.importar(modo)

    def cambiar_biblioteca(self):
        if self.panel_bib.importando():
            QMessageBox.information(self, APP_NOMBRE, "Esperá a que termine la importación.")
            return
        d = QFileDialog.getExistingDirectory(self, "Carpeta de la biblioteca",
                                             str(self.biblioteca.raiz))
        if d:
            self.biblioteca = Library(d)
            self.settings.setValue("biblioteca", d)
            self.panel_bib.set_biblioteca(self.biblioteca)

    def closeEvent(self, ev):
        if self.panel_bib.importando():
            r = QMessageBox.question(self, APP_NOMBRE, "Hay una importación en curso. "
                                     "¿Cancelarla y salir? Las fotos ya descargadas se conservan.")
            if r != QMessageBox.Yes:
                ev.ignore()
                return
        self.panel_bib.detener()
        self.settings.setValue("divisores", self.split.saveState())
        super().closeEvent(ev)

    # -- barra de herramientas ---------------------------------------------
    def _crear_barra(self):
        barra = marco("barra")
        h = QHBoxLayout(barra)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(6)

        # Navegacion (las flechas del teclado solo actuan con el foco en el visor;
        # en el arbol y la galeria siguen moviendo la seleccion)
        self.act_ant = QAction(self, shortcut=Qt.Key_Left, triggered=lambda: self._navegar(-1))
        self.act_sig = QAction(self, shortcut=Qt.Key_Right, triggered=lambda: self._navegar(1))
        for a in (self.act_ant, self.act_sig):
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.viewer.addAction(a)
        self.btn_ant = boton_icono("mdi6.chevron-left", "Foto anterior (←)")
        self.btn_sig = boton_icono("mdi6.chevron-right", "Foto siguiente (→)")
        self.btn_ant.clicked.connect(lambda: self._navegar(-1))
        self.btn_sig.clicked.connect(lambda: self._navegar(1))
        h.addWidget(self.btn_ant)
        h.addWidget(self.btn_sig)
        h.addWidget(separador())

        # Paleta
        h.addWidget(etiqueta("Paleta", "suave"))
        self.combo_paleta = QComboBox()
        self.combo_paleta.setIconSize(QSize(56, 14))
        self.combo_paleta.setMinimumWidth(230)
        for pid in palettes.disponibles():
            self.combo_paleta.addItem(swatch_paleta(pid), palettes.NOMBRES[pid], pid)
        guardada = self.settings.value("paleta", palettes.POR_DEFECTO)
        self.combo_paleta.setCurrentIndex(max(self.combo_paleta.findData(guardada), 0))
        self.combo_paleta.currentIndexChanged.connect(self._paleta_cambiada)
        h.addWidget(self.combo_paleta)
        self.btn_invertir = boton_icono("mdi6.swap-horizontal", "Invertir la paleta",
                                        checkable=True)
        self.btn_invertir.toggled.connect(self._paleta_cambiada)
        h.addWidget(self.btn_invertir)
        h.addWidget(separador())

        # Contraste
        h.addWidget(etiqueta("Contraste", "suave"))
        self.combo_contraste = QComboBox()
        self.combo_contraste.addItem("Como la cámara", CONTRASTE_CAMARA)
        self.combo_contraste.addItem("Lineal", CONTRASTE_LINEAL)
        self.combo_contraste.setToolTip(
            "Como la cámara: reparte los colores según cuánto ocupa cada temperatura en la "
            "imagen, para ver detalles aunque haya cielo u objetos muy fríos o calientes.\n"
            "Lineal: escala pareja entre mínima y máxima, para comparar fotos entre sí.\n"
            "Las temperaturas medidas son las mismas en los dos modos.")
        guardado = self.settings.value("contraste", CONTRASTE_CAMARA)
        self.combo_contraste.setCurrentIndex(max(self.combo_contraste.findData(guardado), 0))
        self.combo_contraste.currentIndexChanged.connect(self._contraste_cambiado)
        h.addWidget(self.combo_contraste)
        h.addWidget(separador())

        # Rango
        h.addWidget(etiqueta("Rango", "suave"))
        self.spin_lo = self._spin()
        self.spin_hi = self._spin()
        h.addWidget(self.spin_lo)
        h.addWidget(etiqueta("–", "suave"))
        h.addWidget(self.spin_hi)
        btn_auto = boton("Auto", "mdi6.arrow-expand-vertical",
                         tooltip="Ajustar el rango a la imagen: hasta la máxima, sin el cielo ni el "
                         "5 % más frío (A)")
        btn_auto.setShortcut("A")
        btn_auto.clicked.connect(self.rango_auto)
        h.addWidget(btn_auto)
        self.btn_fijar = boton_icono(
            "mdi6.lock-outline", "Mantener el rango al cambiar de foto, para compararlas "
            "con la misma escala de colores", checkable=True)
        h.addWidget(self.btn_fijar)
        h.addWidget(separador())

        self.btn_marcas = boton_icono("mdi6.crosshairs-gps",
                                      "Mostrar máxima, mínima y centro sobre la imagen",
                                      checkable=True)
        self.btn_marcas.setChecked(True)
        self.btn_marcas.toggled.connect(
            lambda on: [v.set_marcas_visibles(on) for v in self._visores()])
        h.addWidget(self.btn_marcas)
        h.addWidget(separador())

        # Herramientas de medicion
        h.addWidget(etiqueta("Medir", "suave"))
        self.grupo_herr = QButtonGroup(self)
        self.grupo_herr.setExclusive(True)
        self.botones_herr = {}
        for herr, icono, texto, atajo in (
                (None, "mdi6.cursor-default-outline", "Mover y elegir (Esc)", "Esc"),
                (PUNTO, "mdi6.crosshairs", "Punto: clic en la imagen (P)", "P"),
                (LINEA, "mdi6.vector-line", "Línea con perfil: arrastrá en la imagen (L)", "L"),
                (AREA, "mdi6.vector-square", "Área: arrastrá en la imagen (R)", "R")):
            b = boton_icono(icono, texto, checkable=True)
            if atajo != "Esc":
                b.setShortcut(atajo)
            b.clicked.connect(lambda _=False, x=herr: self.set_herramienta(x))
            self.grupo_herr.addButton(b)
            self.botones_herr[herr] = b
            h.addWidget(b)
        self.botones_herr[None].setChecked(True)
        h.addStretch(1)

        # Muestra el tema al que se pasa: sol en oscuro, luna en claro
        self.btn_tema = boton_icono("mdi6.white-balance-sunny", "Cambiar entre tema oscuro y claro")
        theme.al_cambiar(lambda: self.btn_tema.setIcon(theme.icono(
            "mdi6.white-balance-sunny" if theme.gestor.nombre == theme.OSCURO
            else "mdi6.weather-night")))
        self.btn_tema.clicked.connect(lambda: self.set_tema(
            theme.CLARO if theme.gestor.nombre == theme.OSCURO else theme.OSCURO))
        h.addWidget(self.btn_tema)

        for v in self._visores():
            v.set_contraste(self.combo_contraste.currentData())
        self._paleta_cambiada()
        self._actualizar_navegacion()
        return barra

    def _spin(self):
        s = QDoubleSpinBox()
        s.setRange(-100, 2000)
        s.setDecimals(1)
        s.setSingleStep(0.5)
        s.setSuffix(" °C")
        s.setAlignment(Qt.AlignRight)
        s.setMinimumWidth(92)
        s.setKeyboardTracking(False)
        s.setEnabled(False)
        s.valueChanged.connect(self._rango_desde_spins)
        return s

    # -- abrir -------------------------------------------------------------
    def dialogo_abrir(self):
        carpeta = self.settings.value("ultima_carpeta", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir imagen térmica", carpeta, "Imágenes de la cámara (*.jpg *.jpeg *.JPG)")
        if path:
            self.abrir(path)

    def abrir(self, path):
        path = Path(path)
        try:
            img = ThermalImage.abrir(path)
        except (FormatoInvalido, OSError) as e:
            QMessageBox.warning(self, APP_NOMBRE,
                                "No se pudo abrir %s:\n\n%s" % (path.name, e))
            return False

        rango = self.viewer.rango() if (self.btn_fijar.isChecked() and self.img) else None
        self.img = img
        self.area_visor.mostrar_visor()
        self.viewer.mostrar(img, rango)
        self.panel.mostrar(img)
        mediciones = self.biblioteca.leer_mediciones(path.name)
        self.capa.set_mediciones(mediciones)
        self.panel.mediciones.set_datos(mediciones, img.temps)
        if self._ventana_visible is not None and self._ventana_visible.isVisible():
            self._actualizar_visible()
        self._sincronizar_spins()
        for s in (self.spin_lo, self.spin_hi):
            s.setEnabled(True)

        self.settings.setValue("ultima_carpeta", str(path.parent))
        self.archivos = sorted(p for p in path.parent.iterdir()
                               if p.suffix.lower() in EXTENSIONES)
        self.indice = self.archivos.index(path) if path in self.archivos else -1
        self._actualizar_navegacion()
        self.setWindowTitle("%s — %s" % (path.name, APP_NOMBRE))
        self.statusBar().showMessage(str(path))
        self.panel_bib.marcar_abierta(path)
        return True

    def _navegar(self, paso):
        i = self.indice + paso
        while 0 <= i < len(self.archivos):
            if self.abrir(self.archivos[i]):
                return
            i += paso

    def _actualizar_navegacion(self):
        simple = not self.area_visor.comparando()
        self.btn_ant.setEnabled(simple and self.indice > 0)
        self.btn_sig.setEnabled(simple and 0 <= self.indice < len(self.archivos) - 1)

    # -- mediciones --------------------------------------------------------
    def _conectar_mediciones(self):
        capa, panel = self.capa, self.panel.mediciones
        capa.cambiaron.connect(panel.refrescar)
        capa.terminaron.connect(self._guardar_mediciones)
        capa.seleccionada.connect(lambda n: panel.elegir(n))
        panel.seleccionada.connect(capa.elegir)
        panel.renombrar.connect(self._renombrar_medicion)
        panel.borrar.connect(self.borrar_medicion)
        panel.referenciaCambiada.connect(self._referencia_cambiada)

    def set_herramienta(self, herramienta):
        if self.area_visor.comparando() and herramienta is not None:
            self.statusBar().showMessage("Para medir, cerrá la comparación (Esc).", 5000)
            herramienta = None
        elif self.img is None and herramienta is not None:
            self.statusBar().showMessage("Abrí una foto para medir sobre ella.", 5000)
            herramienta = None
        self.capa.set_herramienta(herramienta)
        self.botones_herr[herramienta].setChecked(True)
        if herramienta is not None:
            self.viewer.setFocus()

    def _escape(self):
        if self.capa.herramienta is not None:
            self.set_herramienta(None)
        else:
            self.cerrar_comparacion()

    def borrar_medicion(self, nombre=None):
        nombre = nombre or self.capa.elegida
        if nombre:
            self.capa.borrar(nombre)
            self.panel.mediciones.refrescar()

    def _renombrar_medicion(self, viejo, nuevo):
        if self.capa.mediciones.renombrar(viejo, nuevo):
            self.capa.renombrado(viejo, nuevo.strip())
            self._guardar_mediciones()
        else:
            self.statusBar().showMessage(
                "No se puede usar ese nombre: está vacío o ya lo tiene otra medición.", 6000)
        self.panel.mediciones.refrescar()

    def _referencia_cambiada(self):
        self.panel.mediciones.refrescar()
        self._guardar_mediciones()

    def _guardar_mediciones(self):
        if self.img is None or self.img.path is None:
            return
        try:
            self.biblioteca.guardar_mediciones(self.img.path.name, self.capa.mediciones)
        except OSError as e:
            self.statusBar().showMessage("No se pudieron guardar las mediciones: %s" % e, 10000)

    # -- comparacion -------------------------------------------------------
    def comparar_seleccionadas(self):
        rutas = self.panel_bib.galeria.rutas_seleccionadas()
        if len(rutas) != 2:
            QMessageBox.information(
                self, APP_NOMBRE, "Para comparar, seleccioná dos fotos en la galería "
                "(Ctrl + clic en la segunda) y apretá C.")
            return
        self.comparar(rutas)

    def comparar(self, rutas):
        try:
            a, b = (ThermalImage.abrir(r) for r in rutas)
        except (FormatoInvalido, OSError) as e:
            QMessageBox.warning(self, APP_NOMBRE, "No se pudo abrir una de las fotos:\n\n%s" % e)
            return
        fijo = self.btn_fijar.isChecked() and (self.img or self.area_visor.comparando())
        self.comparacion.mostrar(a, b, self._vista_activa().rango() if fijo else None)
        self.set_herramienta(None)
        self.area_visor.mostrar_comparacion()
        self.comparacion.setFocus()
        self._sincronizar_spins()
        for s in (self.spin_lo, self.spin_hi):
            s.setEnabled(True)
        self._actualizar_navegacion()
        self.setWindowTitle("Comparación — %s" % APP_NOMBRE)

    def cerrar_comparacion(self):
        if not self.area_visor.comparando():
            return
        if self.img:
            self.area_visor.mostrar_visor()
            self._sincronizar_spins()
            self.setWindowTitle("%s — %s" % (self.img.path.name, APP_NOMBRE))
        else:
            self.area_visor.setCurrentIndex(0)
        self._actualizar_navegacion()

    # -- paleta y rango ----------------------------------------------------
    def _paleta_cambiada(self, *_):
        pid = self.combo_paleta.currentData()
        self.settings.setValue("paleta", pid)
        for v in self._visores():
            v.set_paleta(pid, self.btn_invertir.isChecked())

    def _contraste_cambiado(self, *_):
        modo = self.combo_contraste.currentData()
        self.settings.setValue("contraste", modo)
        for v in self._visores():
            v.set_contraste(modo)

    def _visores(self):
        """Todos los visores, para que paleta, contraste, etc. valgan en los dos modos."""
        return [self.viewer] + self.comparacion.viewers

    def _vista_activa(self):
        """El visor simple o la comparacion: los dos tienen set_rango/rango."""
        return self.comparacion if self.area_visor.comparando() else self.viewer

    def rango_auto(self):
        if self.area_visor.comparando():
            self.comparacion.set_rango(*self.comparacion.rango_auto())
        elif self.img:
            self.viewer.set_rango(*self.img.rango_auto())
        self._sincronizar_spins()

    def _rango_desde_spins(self, *_):
        if self.img or self.area_visor.comparando():
            self._vista_activa().set_rango(self.spin_lo.value(), self.spin_hi.value())

    def _rango_desde_barra(self, lo, hi):
        self._sincronizar_spins()

    def _sincronizar_spins(self):
        lo, hi = self._vista_activa().rango()
        for s, v in ((self.spin_lo, lo), (self.spin_hi, hi)):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)

    # -- cursor ------------------------------------------------------------
    def _cursor_movido(self, fila, col, temp):
        self.panel.set_cursor(fila, col, temp)

    # -- arrastrar y soltar ------------------------------------------------
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for url in ev.mimeData().urls():
            if url.isLocalFile():
                self.abrir(url.toLocalFile())
                break
