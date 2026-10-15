"""Ventana principal: biblioteca | visor | datos, con barra de herramientas arriba."""
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QScrollArea, QSpinBox, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from ..core import camera_ftp, palettes
from ..core.importer import Modo
from ..core.library import Library
from ..core.thermal_image import ThermalImage
from ..core.uti760x import FormatoInvalido, TempConverter
from . import sistema, theme
from .library_panel import LibraryPanel
from .viewer import ThermalViewer, fmt_temp
from .widgets import (
    boton, boton_icono, etiqueta, marco, pixmap_redondeado, separador, swatch_paleta,
)

APP_NOMBRE = "Thermal Studio"
EXTENSIONES = {".jpg", ".jpeg"}


def _fmt(v, sufijo=""):
    return "—" if v is None else "%s%s" % (v, sufijo)


# -- panel derecho -----------------------------------------------------------
class TarjetaDato(QWidget):
    """Tarjeta chica: punto de color + etiqueta arriba, valor grande abajo."""

    def __init__(self, titulo, token_color=None):
        super().__init__()
        caja = marco("tarjeta", self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(caja)
        v = QVBoxLayout(caja)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(2)
        self.titulo = etiqueta(titulo, "etiqueta")
        self.valor = etiqueta("—", "valor")
        self.valor.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.titulo)
        v.addWidget(self.valor)
        if token_color:
            def pintar():
                c = theme.color(token_color)
                self.titulo.setText("<span style='color:%s'>●</span>&nbsp; %s" % (c, titulo))
            theme.al_cambiar(pintar)

    def set(self, texto):
        self.valor.setText(texto)


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
        self.visible = QLabel()
        self.visible.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.titulo_visible)
        lay.addWidget(self.visible)
        self.titulo_visible.hide()
        lay.addStretch(1)
        self._img = None
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
            ancho = max(self.viewport().width() - 34, 200)
            pix = pix.scaledToWidth(ancho, Qt.SmoothTransformation)
            self.visible.setPixmap(pixmap_redondeado(pix, 10))
            self.visible.setToolTip("Foto visible tomada por la cámara")
            self.titulo_visible.show()
        else:
            self.visible.clear()
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
    def __init__(self, viewer):
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

    def mostrar_visor(self):
        self.setCurrentIndex(1)


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
        self.viewer.cursorMovido.connect(self._cursor_movido)
        self.viewer.rangoCambiado.connect(self._rango_desde_barra)
        self.area_visor = AreaVisor(self.viewer)

        self.panel = PanelInfo()
        self.panel.setMinimumWidth(290)

        raiz = self.settings.value("biblioteca") or str(sistema.biblioteca_por_defecto())
        self.biblioteca = Library(raiz)
        self.panel_bib = LibraryPanel(self.biblioteca, self.conexion_camara)
        self.panel_bib.setMinimumWidth(340)
        self.panel_bib.abrirFoto.connect(self.abrir)
        self.panel_bib.mensaje.connect(lambda m: self.statusBar().showMessage(m, 10000))

        centro = QWidget()
        cv = QVBoxLayout(centro)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self._crear_barra())
        cv.addWidget(self.area_visor, 1)

        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(self.panel_bib)
        self.split.addWidget(centro)
        self.split.addWidget(self.panel)
        self.split.setStretchFactor(1, 1)
        estado = self.settings.value("divisores")
        if estado is None or not self.split.restoreState(estado):
            self.split.setSizes([380, 760, 300])
        self.setCentralWidget(self.split)

        self._crear_menu()
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
        sub = m.addMenu("Tema")
        grupo = QActionGroup(self)
        for nombre, texto in ((theme.OSCURO, "Oscuro"), (theme.CLARO, "Claro")):
            a = sub.addAction(texto)
            a.setCheckable(True)
            a.setChecked(theme.gestor.nombre == nombre)
            a.triggered.connect(lambda _=False, n=nombre: self.set_tema(n))
            grupo.addAction(a)
        self._acciones_tema = {a.text(): a for a in grupo.actions()}

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

        # Rango
        h.addWidget(etiqueta("Rango", "suave"))
        self.spin_lo = self._spin()
        self.spin_hi = self._spin()
        h.addWidget(self.spin_lo)
        h.addWidget(etiqueta("–", "suave"))
        h.addWidget(self.spin_hi)
        btn_auto = boton("Auto", "mdi6.arrow-expand-vertical",
                         tooltip="Ajustar el rango a la mínima y máxima de la imagen (A)")
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
        self.btn_marcas.toggled.connect(self.viewer.set_marcas_visibles)
        h.addWidget(self.btn_marcas)
        h.addStretch(1)

        # Muestra el tema al que se pasa: sol en oscuro, luna en claro
        self.btn_tema = boton_icono("mdi6.white-balance-sunny", "Cambiar entre tema oscuro y claro")
        theme.al_cambiar(lambda: self.btn_tema.setIcon(theme.icono(
            "mdi6.white-balance-sunny" if theme.gestor.nombre == theme.OSCURO
            else "mdi6.weather-night")))
        self.btn_tema.clicked.connect(lambda: self.set_tema(
            theme.CLARO if theme.gestor.nombre == theme.OSCURO else theme.OSCURO))
        h.addWidget(self.btn_tema)

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
        self.btn_ant.setEnabled(self.indice > 0)
        self.btn_sig.setEnabled(0 <= self.indice < len(self.archivos) - 1)

    # -- paleta y rango ----------------------------------------------------
    def _paleta_cambiada(self, *_):
        pid = self.combo_paleta.currentData()
        self.settings.setValue("paleta", pid)
        self.viewer.set_paleta(pid, self.btn_invertir.isChecked())

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
