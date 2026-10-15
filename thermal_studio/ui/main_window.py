"""Ventana principal."""
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QDoubleSpinBox,
    QFileDialog, QFormLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QToolBar, QVBoxLayout, QWidget,
)

from ..core import camera_ftp, palettes
from ..core.importer import Modo
from ..core.library import Library
from ..core.thermal_image import ThermalImage
from ..core.uti760x import FormatoInvalido
from . import sistema
from .library_panel import LibraryPanel
from .viewer import COLOR_MAX, COLOR_MIN, ThermalViewer, fmt_temp

APP_NOMBRE = "Thermal Studio"
EXTENSIONES = {".jpg", ".jpeg"}


def _fmt(v, sufijo=""):
    return "—" if v is None else "%s%s" % (v, sufijo)


class PanelInfo(QWidget):
    """Panel derecho: temperaturas, parametros de captura y foto visible."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)

        def fila(titulo, estilo=""):
            lbl = QLabel("—")
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if estilo:
                lbl.setStyleSheet(estilo)
            form.addRow(titulo, lbl)
            return lbl

        self.archivo = fila("Archivo:")
        self.fecha = fila("Fecha:")
        form.addRow(QLabel(""))
        self.cursor = fila("Cursor:", "font-weight: bold; font-size: 14px;")
        self.tmax = fila("Máxima:", "color: %s; font-weight: bold;" % COLOR_MAX)
        self.tmin = fila("Mínima:", "color: %s; font-weight: bold;" % COLOR_MIN)
        self.tcentro = fila("Centro:")
        self.tmedia = fila("Media:")
        self.delta = fila("Máx − mín:")
        form.addRow(QLabel(""))
        self.ems = fila("Emisividad:")
        self.trefl = fila("T. reflejada:")
        self.tamb = fila("T. ambiente:")
        self.hum = fila("Humedad:")
        self.dist = fila("Distancia:")

        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color: #888; font-size: 11px;")
        lay.addWidget(self.aviso)

        self.visible = QLabel()
        self.visible.setAlignment(Qt.AlignCenter)
        self.visible.setMinimumHeight(120)
        lay.addWidget(self.visible)
        lay.addStretch(1)

    def mostrar(self, img):
        m = img.meta
        self.archivo.setText(img.path.name if img.path else "—")
        self.fecha.setText(m.fecha.strftime("%d/%m/%Y %H:%M:%S") if m.fecha else "—")
        mx, mn = img.maximo(), img.minimo()
        self.tmax.setText(fmt_temp(mx.temp))
        self.tmin.setText(fmt_temp(mn.temp))
        self.tcentro.setText(fmt_temp(img.centro().temp))
        self.tmedia.setText(fmt_temp(img.media()))
        self.delta.setText("%.1f °C" % (mx.temp - mn.temp))
        self.ems.setText(_fmt(m.emisividad))
        self.trefl.setText(_fmt(m.temp_reflejada, " °C"))
        self.tamb.setText(_fmt(m.temp_ambiente, " °C"))
        self.hum.setText(_fmt(m.humedad, " %"))
        self.dist.setText(_fmt(m.distancia_m, " m"))

        aviso = "Precisión de la conversión a grados: ±%.1f °C típico." % img.incertidumbre_c
        if img.fuera_de_rango:
            aviso = ("<b style='color:#ff9f0a'>Atención:</b> la imagen tiene temperaturas "
                     "fuera del rango calibrado (−13 a 52 °C). Los valores extremos "
                     "son aproximados y pueden tener más error.<br>" + aviso)
        self.aviso.setText(aviso)

        pix = QPixmap()
        if img.visible_jpeg and pix.loadFromData(img.visible_jpeg):
            self.visible.setPixmap(pix.scaledToWidth(260, Qt.SmoothTransformation))
            self.visible.setToolTip("Foto visible tomada por la cámara")
        else:
            self.visible.clear()

    def set_cursor(self, temp):
        self.cursor.setText(fmt_temp(temp))


class DialogoCamara(QDialog):
    """Datos de conexion al FTP de la camara."""

    def __init__(self, conexion, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conexión con la cámara")
        form = QFormLayout(self)
        self.host = QLineEdit(conexion["host"])
        self.puerto = QSpinBox()
        self.puerto.setRange(1, 65535)
        self.puerto.setValue(int(conexion["puerto"]))
        self.usuario = QLineEdit(conexion["usuario"])
        self.clave = QLineEdit(conexion["clave"])
        self.clave.setEchoMode(QLineEdit.Password)
        form.addRow(QLabel("Conectá la PC al WiFi de la cámara y activá el FTP en la cámara."))
        form.addRow("Dirección:", self.host)
        form.addRow("Puerto:", self.puerto)
        form.addRow("Usuario:", self.usuario)
        form.addRow("Contraseña:", self.clave)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                                   | QDialogButtonBox.RestoreDefaults)
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ThermalStudio", "ThermalStudio")
        self.img = None
        self.archivos = []  # .jpg de la carpeta actual, para anterior/siguiente
        self.indice = -1

        self.setWindowTitle(APP_NOMBRE)
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        self.viewer = ThermalViewer()
        self.setCentralWidget(self.viewer)
        self.viewer.cursorMovido.connect(self._cursor_movido)
        self.viewer.rangoCambiado.connect(self._rango_desde_barra)

        self.panel = PanelInfo()
        dock = QDockWidget("Datos", self)
        dock.setWidget(self.panel)
        dock.setMinimumWidth(280)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        raiz = self.settings.value("biblioteca") or str(sistema.biblioteca_por_defecto())
        self.biblioteca = Library(raiz)
        self.panel_bib = LibraryPanel(self.biblioteca, self.conexion_camara)
        self.panel_bib.abrirFoto.connect(self.abrir)
        self.panel_bib.mensaje.connect(lambda m: self.statusBar().showMessage(m, 10000))
        self.dock_bib = QDockWidget("Biblioteca", self)
        self.dock_bib.setWidget(self.panel_bib)
        self.dock_bib.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
                                  | QDockWidget.DockWidgetClosable)
        self.dock_bib.setMinimumWidth(380)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_bib)

        self._crear_menu()
        self._crear_barra()
        self.statusBar().showMessage("Elegí una foto de la biblioteca, importá desde la cámara (Ctrl+I) o abrí una imagen (Ctrl+O).")

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
        m.addAction(self.dock_bib.toggleViewAction())

    def conexion_camara(self):
        s = self.settings
        return {"host": s.value("camara/host", camera_ftp.HOST),
                "puerto": int(s.value("camara/puerto", camera_ftp.PUERTO)),
                "usuario": s.value("camara/usuario", camera_ftp.USUARIO),
                "clave": s.value("camara/clave", camera_ftp.CLAVE)}

    def configurar_camara(self):
        d = DialogoCamara(self.conexion_camara(), self)
        if d.exec() == QDialog.Accepted:
            for k, v in d.conexion().items():
                self.settings.setValue("camara/" + k, v)

    def importar(self, modo):
        self.dock_bib.show()
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
        super().closeEvent(ev)

    # -- barra de herramientas ---------------------------------------------
    def _crear_barra(self):
        tb = QToolBar("Principal")
        tb.setMovable(False)
        self.addToolBar(tb)

        importar = QAction("⬇ Importar de la cámara", self,
                           triggered=lambda: self.importar(Modo.FALTANTES))
        importar.setToolTip("Traer las fotos nuevas de la cámara por WiFi (Ctrl+I)")
        tb.addAction(importar)
        tb.addSeparator()
        abrir = QAction("Abrir…", self, triggered=self.dialogo_abrir)
        self.act_ant = QAction("◀ Anterior", self, shortcut=Qt.Key_Left,
                               triggered=lambda: self._navegar(-1))
        self.act_sig = QAction("Siguiente ▶", self, shortcut=Qt.Key_Right,
                               triggered=lambda: self._navegar(1))
        for a in (abrir, self.act_ant, self.act_sig):
            tb.addAction(a)
        # Las flechas solo navegan con el foco en el visor; en el arbol y la
        # galeria siguen moviendo la seleccion
        for a in (self.act_ant, self.act_sig):
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.viewer.addAction(a)
        tb.addSeparator()

        tb.addWidget(QLabel(" Paleta: "))
        self.combo_paleta = QComboBox()
        for pid in palettes.disponibles():
            self.combo_paleta.addItem(palettes.NOMBRES[pid], pid)
        guardada = self.settings.value("paleta", palettes.POR_DEFECTO)
        i = self.combo_paleta.findData(guardada)
        self.combo_paleta.setCurrentIndex(max(i, 0))
        self.combo_paleta.currentIndexChanged.connect(self._paleta_cambiada)
        tb.addWidget(self.combo_paleta)

        self.chk_invertir = QCheckBox("Invertir")
        self.chk_invertir.toggled.connect(self._paleta_cambiada)
        tb.addWidget(self.chk_invertir)
        tb.addSeparator()

        tb.addWidget(QLabel(" Rango: "))
        self.spin_lo = self._spin()
        self.spin_hi = self._spin()
        tb.addWidget(self.spin_lo)
        tb.addWidget(QLabel(" a "))
        tb.addWidget(self.spin_hi)
        btn_auto = QPushButton("Auto")
        btn_auto.setToolTip("Ajustar el rango a la mínima y máxima de la imagen (A)")
        btn_auto.setShortcut("A")
        btn_auto.clicked.connect(self.rango_auto)
        tb.addWidget(btn_auto)
        self.chk_fijar = QCheckBox("Mantener al cambiar de imagen")
        self.chk_fijar.setToolTip("Usar el mismo rango para todas las imágenes, para compararlas")
        tb.addWidget(self.chk_fijar)
        tb.addSeparator()

        self.chk_marcas = QCheckBox("Máx/mín/centro")
        self.chk_marcas.setChecked(True)
        self.chk_marcas.toggled.connect(self.viewer.set_marcas_visibles)
        tb.addWidget(self.chk_marcas)

        self._paleta_cambiada()
        self._actualizar_navegacion()

    def _spin(self):
        s = QDoubleSpinBox()
        s.setRange(-100, 2000)
        s.setDecimals(1)
        s.setSingleStep(0.5)
        s.setSuffix(" °C")
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

        rango = self.viewer.rango() if (self.chk_fijar.isChecked() and self.img) else None
        self.img = img
        self.viewer.mostrar(img, rango)
        self.panel.mostrar(img)
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
        self.act_ant.setEnabled(self.indice > 0)
        self.act_sig.setEnabled(0 <= self.indice < len(self.archivos) - 1)

    # -- paleta y rango ----------------------------------------------------
    def _paleta_cambiada(self, *_):
        pid = self.combo_paleta.currentData()
        self.settings.setValue("paleta", pid)
        self.viewer.set_paleta(pid, self.chk_invertir.isChecked())

    def rango_auto(self):
        if self.img:
            self.viewer.set_rango(*self.img.rango_auto())
            self._sincronizar_spins()

    def _rango_desde_spins(self, *_):
        if self.img:
            self.viewer.set_rango(self.spin_lo.value(), self.spin_hi.value())

    def _rango_desde_barra(self, lo, hi):
        self._sincronizar_spins()

    def _sincronizar_spins(self):
        lo, hi = self.viewer.rango()
        for s, v in ((self.spin_lo, lo), (self.spin_hi, hi)):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)

    # -- cursor ------------------------------------------------------------
    def _cursor_movido(self, fila, col, temp):
        self.panel.set_cursor(temp)
        if temp is not None:
            self.statusBar().showMessage("x=%d  y=%d   %s" % (col, fila, fmt_temp(temp)))

    # -- arrastrar y soltar ------------------------------------------------
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for url in ev.mimeData().urls():
            if url.isLocalFile():
                self.abrir(url.toLocalFile())
                break
