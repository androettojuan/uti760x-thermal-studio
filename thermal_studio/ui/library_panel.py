"""Panel lateral: importacion desde la camara, arbol de carpetas y galeria."""
import json
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QProgressBar, QSplitter, QStackedWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core.importer import Modo
from ..core.library import CARPETA_IMPORTADAS, ErrorBiblioteca, es_foto, fecha_visible
from ..core.thermal_image import _fecha_desde_nombre
from . import sistema, theme
from .camera_monitor import MonitorCamara
from .import_worker import HiloDescarga, HiloPlan
from .thumbnails import TAMANO, CargadorMiniaturas
from .widgets import boton, boton_icono, etiqueta, marco

MIME_CARPETA = "application/x-thermal-studio-carpeta"
ROL_REL = Qt.UserRole
ROL_RUTA = Qt.UserRole


def _fmt_bytes(n):
    return "%.0f MB" % (n / 1e6) if n >= 1e6 else "%.0f KB" % (n / 1e3)


def _fmt_duracion(seg):
    seg = int(seg)
    return "%d min %02d s" % divmod(seg, 60) if seg >= 60 else "%d s" % seg


# -- arbol de carpetas -----------------------------------------------------
class ArbolCarpetas(QTreeWidget):
    """Arbol de la biblioteca. Acepta fotos (de la galeria o de afuera) y
    carpetas arrastradas desde el mismo arbol."""

    fotosSoltadas = Signal(list, str)          # rutas, carpeta destino
    carpetaSoltada = Signal(str, str)          # carpeta origen, carpeta destino

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mimeData(self, items):
        md = QMimeData()
        rels = [it.data(0, ROL_REL) for it in items if it.data(0, ROL_REL)]
        md.setData(MIME_CARPETA, json.dumps(rels).encode())
        return md

    def mimeTypes(self):
        return [MIME_CARPETA, "text/uri-list"]

    def _destino(self, ev):
        """Carpeta donde se suelta; "" (nivel principal) si es una carpeta
        soltada en el espacio vacio; None si no se puede soltar ahi."""
        it = self.itemAt(ev.position().toPoint())
        if it is not None:
            return it.data(0, ROL_REL)
        return "" if ev.mimeData().hasFormat(MIME_CARPETA) else None

    def dragEnterEvent(self, ev):
        md = ev.mimeData()
        if md.hasFormat(MIME_CARPETA) or md.hasUrls():
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):
        destino = self._destino(ev)
        if destino is None:
            ev.ignore()
            return
        ev.acceptProposedAction()

    def dropEvent(self, ev):
        destino = self._destino(ev)
        md = ev.mimeData()
        if destino is None:
            ev.ignore()
            return
        if md.hasFormat(MIME_CARPETA):
            for rel in json.loads(bytes(md.data(MIME_CARPETA)).decode()):
                self.carpetaSoltada.emit(rel, destino)
        elif md.hasUrls():
            rutas = [Path(u.toLocalFile()) for u in md.urls() if u.isLocalFile()]
            rutas = [r for r in rutas if es_foto(r)]
            if rutas:
                self.fotosSoltadas.emit(rutas, destino)
        ev.setDropAction(Qt.MoveAction)
        ev.accept()


# -- galeria ---------------------------------------------------------------
class Galeria(QListWidget):
    MIN_COLUMNAS = 2
    MARGEN_CELDA = 18   # padding del item + separacion entre celdas
    ALTO_TEXTO = 38     # renglon con la fecha debajo de la miniatura

    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.IconMode)
        self._ajustar_celdas()
        self.setSpacing(4)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def _ajustar_celdas(self):
        """Reparte el ancho en columnas iguales, con al menos dos.

        Las miniaturas no pasan de TAMANO (el tamano al que se generan),
        para que no se vean borrosas en paneles anchos.
        """
        # Margen de seguridad: si la suma justa no entra por un pixel, Qt
        # pasa la segunda foto al renglon de abajo
        ancho = max(self.viewport().width() - 8, 1)
        cols = max(self.MIN_COLUMNAS, ancho // (TAMANO + self.MARGEN_CELDA + self.spacing()))
        # Qt suma el espaciado alrededor de cada celda de la grilla
        celda = (ancho - self.spacing() * (cols + 1)) // cols
        icono = max(min(celda - self.MARGEN_CELDA, TAMANO), 40)
        grilla = QSize(celda, int(icono * 0.8) + self.ALTO_TEXTO)
        if grilla != self.gridSize():
            self.setIconSize(QSize(icono, int(icono * 0.8)))
            self.setGridSize(grilla)
            self.doItemsLayout()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._ajustar_celdas()

    def viewportEvent(self, ev):
        # El area visible tambien cambia sola (aparece o se va la barra de
        # desplazamiento) sin que cambie el tamano del widget
        if ev.type() == QEvent.Resize:
            self._ajustar_celdas()
        return super().viewportEvent(ev)

    def mimeData(self, items):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(it.data(ROL_RUTA)) for it in items])
        return md

    def rutas_seleccionadas(self):
        return [Path(it.data(ROL_RUTA)) for it in self.selectedItems()]


def _icono_vacio():
    pix = QPixmap(TAMANO, int(TAMANO * 0.8))
    pix.fill(QColor(theme.color("superficie")))
    return QIcon(pix)


# -- panel -----------------------------------------------------------------
class LibraryPanel(QFrame):
    abrirFoto = Signal(Path)
    compararFotos = Signal(list)  # dos rutas
    mensaje = Signal(str)

    def __init__(self, biblioteca, conexion_camara, parent=None):
        super().__init__(parent)
        self.setProperty("rol", "panel")
        self.bib = biblioteca
        self.conexion_camara = conexion_camara  # callable -> dict para CameraFTP
        self.carpeta_actual = None
        self._items_galeria = {}
        self._hilo = None
        self._icono_vacio = _icono_vacio()

        self.miniaturas = CargadorMiniaturas(self.bib.miniaturas, self)
        self.miniaturas.lista.connect(self._miniatura_lista)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 14, 12, 8)
        lay.setSpacing(12)
        lay.addWidget(self._crear_camara())

        split = QSplitter(Qt.Vertical)
        split.setHandleWidth(14)
        split.setStyleSheet("QSplitter::handle { background: transparent; }")
        split.addWidget(self._crear_carpetas())
        split.addWidget(self._crear_galeria())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

        self.refrescar()
        theme.gestor.cambiado.connect(self._tema_cambiado)

        self.settings = QSettings("ThermalStudio", "ThermalStudio")
        self._conectando = None  # QTimer de espera mientras se conecta el WiFi
        self.monitor = MonitorCamara(self.conexion_camara, lambda: self.bib, self)
        self.monitor.cambiado.connect(self._estado_camara)
        self.monitor.conexionPedida.connect(self._conexion_pedida)
        self._estado_camara(self.monitor.estado, inicial=True)
        self.monitor.iniciar()

    def _tema_cambiado(self, *_):
        self._icono_vacio = _icono_vacio()
        self.refrescar()
        if hasattr(self, "monitor"):
            self._estado_camara(self.monitor.estado)

    # == camara ==============================================================
    def _crear_camara(self):
        caja = marco("tarjeta")
        v = QVBoxLayout(caja)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)
        cab = QHBoxLayout()
        cab.setSpacing(10)
        self.ico_camara = etiqueta()
        cab.addWidget(self.ico_camara)
        tit = QVBoxLayout()
        tit.setSpacing(0)
        tit.addWidget(etiqueta("Cámara", "titulo"))
        self.lbl_estado = etiqueta("Buscando la cámara…", "suave")
        self.lbl_estado.setWordWrap(True)
        tit.addWidget(self.lbl_estado)
        cab.addLayout(tit, 1)
        v.addLayout(cab)

        # Dos juegos de botones: importar (conectada) o conectar (sin conexion)
        self.pila_botones = QStackedWidget()
        importar = QWidget()
        h = QHBoxLayout(importar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.btn_faltantes = boton("Traer faltantes", "mdi6.download", "primario",
                                   "Descargar solo las fotos que todavía no se importaron")
        self.btn_todo = boton("Traer todas", "mdi6.download-multiple", "secundario",
                              "Descargar todas las fotos de la cámara que no estén en la "
                              "biblioteca, incluidas las que hayas borrado antes")
        self.btn_faltantes.clicked.connect(lambda: self.importar(Modo.FALTANTES))
        self.btn_todo.clicked.connect(lambda: self.importar(Modo.TODO))
        h.addWidget(self.btn_faltantes)
        h.addWidget(self.btn_todo)

        conectar = QWidget()
        h = QHBoxLayout(conectar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.btn_conectar = boton("Conectar", "mdi6.wifi", "primario")
        self.btn_conectar.clicked.connect(self.conectar)
        self.btn_redes = boton("Redes WiFi", "mdi6.format-list-bulleted", "secundario",
                               "Abrir la lista de redes WiFi para elegir la de la cámara")
        self.btn_redes.clicked.connect(self._abrir_redes)
        h.addWidget(self.btn_conectar)
        h.addWidget(self.btn_redes)
        self.pila_botones.addWidget(importar)
        self.pila_botones.addWidget(conectar)
        v.addWidget(self.pila_botones)

        self.barra = QProgressBar()
        self.barra.setTextVisible(True)
        self.lbl_progreso = etiqueta("", "suave")
        self.lbl_progreso.setWordWrap(True)
        self.btn_cancelar = boton("Cancelar", "mdi6.close", "peligro")
        self.btn_cancelar.clicked.connect(self._cancelar)
        for w in (self.barra, self.lbl_progreso, self.btn_cancelar):
            v.addWidget(w)
            w.hide()
        return caja

    # -- estado de la conexion ---------------------------------------------
    def red_camara(self):
        """Nombre (SSID) de la red WiFi de la camara, si se conoce."""
        return self.settings.value("camara/wifi", "") or ""

    def _estado_camara(self, estado, inicial=False):
        # La primera vez que se encuentra la camara, se aprende el nombre de su red
        if estado.conectada and estado.wifi and not self.red_camara():
            self.settings.setValue("camara/wifi", estado.wifi)
        if estado.conectada and self._conectando:
            self._conectando.stop()
            self._conectando = None

        def punto(token, texto):
            return "<span style='color:%s'>●</span>&nbsp; %s" % (theme.color(token), texto)

        red = self.red_camara()
        if inicial:
            texto, tok, conectada = "Buscando la cámara…", "texto_suave", False
        elif estado.conectada:
            conectada, tok = True, "ok"
            if estado.nuevas is None:
                texto = "Conectada · buscando fotos nuevas…"
            elif estado.nuevas == 0:
                texto = "Conectada · no hay fotos nuevas (%d en la cámara)" % estado.en_camara
            else:
                texto = "Conectada · <b>%d foto%s nueva%s</b>" % (
                    estado.nuevas, "" if estado.nuevas == 1 else "s",
                    "" if estado.nuevas == 1 else "s")
        elif self._conectando:
            texto, tok, conectada = "Conectando a «%s»…" % red, "aviso", False
        else:
            conectada, tok = False, "texto_suave"
            texto = "Sin conexión"
            if estado.wifi and estado.wifi != red:
                texto += " · estás en la red «%s»" % estado.wifi
            elif estado.wifi == red and red:
                texto += " · conectado a «%s» pero la cámara no responde. ¿Tiene el FTP " \
                         "activado?" % red
            elif not estado.wifi:
                texto += " · el WiFi está desconectado"
        self.lbl_estado.setText(punto(tok, texto))
        self.ico_camara.setPixmap(theme.icono(
            "mdi6.wifi" if conectada else "mdi6.wifi-off",
            "acento" if conectada else "texto_suave").pixmap(QSize(22, 22)))

        if not self.importando():
            self.pila_botones.setCurrentIndex(0 if conectada else 1)
        self._reintentar = bool(red) and estado.wifi == red and not conectada
        if self._reintentar:
            self.btn_conectar.setText("Reintentar")
            self.btn_conectar.setToolTip("Volver a buscar la cámara en la red «%s»" % red)
        elif red:
            self.btn_conectar.setText("Conectar a «%s»" % red)
            self.btn_conectar.setToolTip(
                "Conectar la PC al WiFi de la cámara. Mientras estés conectado a la "
                "cámara, la PC puede quedarse sin internet por WiFi.")
        else:
            self.btn_conectar.setText("Elegir red de la cámara")
            self.btn_conectar.setToolTip("Abrir la lista de redes WiFi para conectarte a la "
                                         "de la cámara. La app la recuerda para la próxima vez.")
        self.btn_conectar.setEnabled(not self._conectando)
        self.btn_redes.setVisible(bool(red))

    def conectar(self):
        red = self.red_camara()
        if getattr(self, "_reintentar", False):
            self.monitor.acelerar()
            return
        if not red:
            self._abrir_redes()
            return
        self.monitor.conectar_wifi(red)
        self._conectando = QTimer(self)
        self._conectando.setSingleShot(True)
        self._conectando.timeout.connect(self._conexion_vencida)
        self._conectando.start(30000)
        self._estado_camara(self.monitor.estado)

    def _conexion_pedida(self, ok, mensaje):
        if ok or not self._conectando:
            return  # sigue esperando que la camara responda
        self._conectando.stop()
        self._conectando = None
        self._estado_camara(self.monitor.estado)
        r = QMessageBox.question(
            self, "Conectar",
            "Windows no pudo conectarse a la red «%s».\n\n%s\n\n¿Abrir la lista de redes "
            "WiFi para elegirla a mano?" % (self.red_camara(), mensaje or ""))
        if r == QMessageBox.Yes:
            self._abrir_redes()

    def _conexion_vencida(self):
        self._conectando = None
        self._estado_camara(self.monitor.estado)
        QMessageBox.information(
            self, "Conectar",
            "No se encontró la cámara en la red «%s».\n\nRevisá que la cámara esté encendida, "
            "con el punto de acceso WiFi y el FTP activados." % self.red_camara())

    def _abrir_redes(self):
        if not sistema.abrir_redes_wifi():
            QMessageBox.information(self, "Conectar",
                                    "Abrí la configuración de WiFi del sistema y conectate a la "
                                    "red de la cámara.")
        self.monitor.acelerar()

    def importando(self):
        return self._hilo is not None

    def importar(self, modo):
        if self.importando():
            return
        self._modo = modo
        self.monitor.pausar(True)
        self._set_ocupado(True, "Conectando con la cámara…")
        self._hilo = HiloPlan(self.conexion_camara(), self.bib, modo, self)
        self._hilo.listo.connect(self._plan_listo)
        self._hilo.error.connect(self._error_camara)
        self._hilo.start()

    def _plan_listo(self, plan, en_camara):
        self._hilo = None
        n = len(plan.a_descargar)
        if n == 0:
            self._set_ocupado(False)
            detalle = "Las %d fotos de la cámara ya están en la biblioteca." % en_camara
            if plan.importadas_antes:
                detalle = ("No hay fotos nuevas en la cámara.\n\n%d ya están en la biblioteca y "
                           "%d se importaron antes y después se borraron (usá «Traer todas» "
                           "para volver a bajarlas)." % (plan.ya_en_biblioteca, plan.importadas_antes))
            QMessageBox.information(self, "Importar", detalle)
            return
        if n > 20:  # descarga larga: avisar cuanto va a tardar
            r = QMessageBox.question(
                self, "Importar",
                "Se van a descargar %d foto%s (%s), unos %s.\n\n¿Continuar?"
                % (n, "" if n == 1 else "s", _fmt_bytes(plan.bytes_totales),
                   _fmt_duracion(plan.bytes_totales / 2.5e6)))
            if r != QMessageBox.Yes:
                self._set_ocupado(False)
                return
        self._set_ocupado(True, "Descargando %d fotos…" % n, descargando=True)
        self._hilo = HiloDescarga(self.conexion_camara(), self.bib, plan, self)
        self._hilo.progreso.connect(self._progreso)
        self._hilo.terminado.connect(self._descarga_terminada)
        self._hilo.start()

    def _progreso(self, i, total, nombre, acumulado, total_bytes, vel):
        self.barra.setValue(int(1000 * acumulado / max(total_bytes, 1)))
        self.barra.setFormat("%d de %d" % (i + 1, total))
        restante = (total_bytes - acumulado) / max(vel, 1)
        self.lbl_progreso.setText("%s / %s — %.1f MB/s — faltan %s"
                                  % (_fmt_bytes(acumulado), _fmt_bytes(total_bytes),
                                     vel / 1e6, _fmt_duracion(restante)))

    def _descarga_terminada(self, hechas, cancelado, error):
        self._hilo = None
        self._set_ocupado(False)
        n = len(hechas)
        self.refrescar()
        if hechas:
            carpeta = self.bib.rel(Path(hechas[-1]).parent)
            self.seleccionar_carpeta(carpeta)
        texto = "Se importaron %d foto%s." % (n, "" if n == 1 else "s")
        if error:
            QMessageBox.warning(self, "Importar", "%s\n\n%s" % (error, texto))
        elif cancelado:
            self.mensaje.emit("Importación cancelada. " + texto)
        else:
            self.mensaje.emit(texto + " Están en «%s»." % self.NOMBRE_IMPORTADAS)

    def _error_camara(self, msg):
        self._hilo = None
        self._set_ocupado(False)
        QMessageBox.warning(self, "Cámara", msg)

    def _cancelar(self):
        if isinstance(self._hilo, HiloDescarga):
            self._hilo.cancelar()
            self.lbl_progreso.setText("Cancelando…")

    def _set_ocupado(self, ocupado, texto="", descargando=False):
        if not ocupado:
            self.monitor.pausar(False)
            self.monitor.recontar()
        self.btn_faltantes.setEnabled(not ocupado)
        self.btn_todo.setEnabled(not ocupado)
        self.lbl_progreso.setVisible(ocupado)
        self.lbl_progreso.setText(texto)
        self.barra.setVisible(ocupado)
        if descargando:
            self.barra.setRange(0, 1000)
            self.barra.setValue(0)
        else:
            self.barra.setRange(0, 0)  # indeterminada mientras conecta
            self.barra.setFormat("")
        self.btn_cancelar.setVisible(descargando)

    def detener(self):
        """Al cerrar la app: cancela y espera la descarga en curso."""
        self.monitor.detener()
        if isinstance(self._hilo, HiloDescarga):
            self._hilo.cancelar()
        if self._hilo:
            self._hilo.wait(15000)

    # == carpetas ============================================================
    # El arbol no muestra la raiz de la biblioteca: arriba de todo va
    # "Termografias" (la carpeta donde cae lo importado) y despues, al mismo
    # nivel, las carpetas del usuario con todas las subcarpetas que quiera.
    NOMBRE_IMPORTADAS = "Termografías"

    def _crear_carpetas(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        h = QHBoxLayout()
        h.setSpacing(4)
        h.addWidget(etiqueta("CARPETAS", "seccion"), 1)
        self.btn_renombrar = boton_icono("mdi6.pencil-outline", "Renombrar la carpeta")
        self.btn_renombrar.clicked.connect(self.renombrar_carpeta)
        self.btn_eliminar = boton_icono("mdi6.trash-can-outline",
                                        "Eliminar la carpeta (solo si no tiene fotos)")
        self.btn_eliminar.clicked.connect(self.eliminar_carpeta)
        h.addWidget(self.btn_renombrar)
        h.addWidget(self.btn_eliminar)
        v.addLayout(h)
        h = QHBoxLayout()
        h.setSpacing(8)
        self.btn_carpeta = boton("Carpeta", "mdi6.folder-plus-outline",
                                 tooltip="Crear una carpeta principal, por ejemplo «Subestaciones»")
        self.btn_carpeta.clicked.connect(self.nueva_carpeta)
        self.btn_subcarpeta = boton("Subcarpeta", "mdi6.file-tree-outline",
                                    tooltip="Crear una carpeta dentro de la seleccionada")
        self.btn_subcarpeta.clicked.connect(self.nueva_subcarpeta)
        h.addWidget(self.btn_carpeta)
        h.addWidget(self.btn_subcarpeta)
        v.addLayout(h)

        self.arbol = ArbolCarpetas()
        self.arbol.setIconSize(QSize(18, 18))
        self.arbol.setIndentation(16)
        self.arbol.currentItemChanged.connect(self._carpeta_elegida)
        self.arbol.fotosSoltadas.connect(self._fotos_soltadas)
        self.arbol.carpetaSoltada.connect(self._carpeta_soltada)
        self.arbol.customContextMenuRequested.connect(self._menu_arbol)
        self.arbol.itemCollapsed.connect(lambda it: self._colapsadas.add(it.data(0, ROL_REL)))
        self.arbol.itemExpanded.connect(lambda it: self._colapsadas.discard(it.data(0, ROL_REL)))
        self._colapsadas = set()  # todo arranca abierto; se recuerda lo que el usuario cierra
        v.addWidget(self.arbol)
        return w

    def nombre_visible(self, rel):
        """Ruta relativa como se muestra: «Importadas/2026-08-28» se ve como
        «Termografías/28/08/2026»."""
        partes = rel.split("/")
        if partes[0] == CARPETA_IMPORTADAS:
            partes = [self.NOMBRE_IMPORTADAS] + [fecha_visible(p) for p in partes[1:]]
        return " › ".join(partes)

    def set_biblioteca(self, biblioteca):
        self.bib = biblioteca
        self.miniaturas.set_cache(biblioteca.miniaturas)
        self.carpeta_actual = None
        self._colapsadas = set()
        self.refrescar()

    def refrescar(self):
        """Rearma el arbol conservando la carpeta elegida y lo que estaba cerrado."""
        actual = self.carpeta_actual
        self.arbol.blockSignals(True)
        self.arbol.clear()
        conteos = self._conteos()
        ico_carpeta = theme.icono("mdi6.folder-outline", "texto_suave")
        ico_fecha = theme.icono("mdi6.calendar-blank-outline", "texto_suave")
        ico_importadas = theme.icono("mdi6.camera-outline", "acento")

        def agregar(padre, rel, nombre, icono, protegida=False):
            it = QTreeWidgetItem([self._etiqueta(nombre, conteos.get(rel, 0))])
            it.setData(0, ROL_REL, rel)
            it.setIcon(0, icono)
            if protegida:
                it.setFlags(it.flags() & ~Qt.ItemIsDragEnabled)
                it.setToolTip(0, "Acá llegan las fotos importadas de la cámara, por fecha")
            if padre is None:
                self.arbol.addTopLevelItem(it)
            else:
                padre.addChild(it)
            subs = self.bib.subcarpetas(rel)
            if rel == CARPETA_IMPORTADAS:
                subs = sorted(subs, reverse=True)  # fechas AAAA-MM-DD: la mas nueva arriba
            for sub in subs:
                visible = fecha_visible(sub) if rel == CARPETA_IMPORTADAS else sub
                agregar(it, "%s/%s" % (rel, sub), visible,
                        ico_fecha if rel == CARPETA_IMPORTADAS else ico_carpeta)
            it.setExpanded(rel not in self._colapsadas)
            return it

        agregar(None, CARPETA_IMPORTADAS, self.NOMBRE_IMPORTADAS, ico_importadas, protegida=True)
        for nombre in self.bib.subcarpetas(""):
            if nombre != CARPETA_IMPORTADAS:
                agregar(None, nombre, nombre, ico_carpeta)
        self.arbol.blockSignals(False)
        self.seleccionar_carpeta(actual or CARPETA_IMPORTADAS, forzar=True)

    def _conteos(self):
        """{carpeta relativa: fotos en ella y sus subcarpetas}."""
        conteos = {}
        for p in self.bib.indice().values():
            partes = Path(self.bib.rel(p.parent)).parts if p.parent != self.bib.raiz else ()
            for k in range(1, len(partes) + 1):
                key = "/".join(partes[:k])
                conteos[key] = conteos.get(key, 0) + 1
        return conteos

    @staticmethod
    def _etiqueta(nombre, n):
        return "%s  (%d)" % (nombre, n) if n else nombre

    def _items_arbol(self):
        out = []

        def rec(it):
            out.append(it)
            for i in range(it.childCount()):
                rec(it.child(i))
        for i in range(self.arbol.topLevelItemCount()):
            rec(self.arbol.topLevelItem(i))
        return out

    def seleccionar_carpeta(self, rel, forzar=False):
        for it in self._items_arbol():
            if it.data(0, ROL_REL) == rel:
                p = it.parent()
                while p:
                    p.setExpanded(True)
                    p = p.parent()
                if forzar or self.arbol.currentItem() is not it:
                    self.arbol.setCurrentItem(it)
                    self._carpeta_elegida(it)
                return
        if rel != CARPETA_IMPORTADAS:
            self.seleccionar_carpeta(CARPETA_IMPORTADAS, forzar)

    def _carpeta_elegida(self, item, *_):
        if item is None:
            return
        self.carpeta_actual = item.data(0, ROL_REL)
        protegida = self.bib.es_protegida(self.carpeta_actual)
        self.btn_renombrar.setEnabled(not protegida)
        self.btn_eliminar.setEnabled(not protegida)
        self._cargar_galeria()

    def _rel_seleccionada(self):
        it = self.arbol.currentItem()
        return it.data(0, ROL_REL) if it else None

    def _intentar(self, fn, *args):
        try:
            return fn(*args)
        except ErrorBiblioteca as e:
            QMessageBox.warning(self, "Carpetas", str(e))
        except OSError as e:
            QMessageBox.warning(self, "Carpetas", "No se pudo completar la operación:\n%s" % e)
        return None

    def _crear(self, padre, pregunta):
        nombre, ok = QInputDialog.getText(self, "Nueva carpeta", pregunta)
        if ok and nombre.strip():
            rel = self._intentar(self.bib.crear_carpeta, padre, nombre)
            if rel is not None:
                self._colapsadas.discard(padre)
                self.carpeta_actual = rel
                self.refrescar()

    def nueva_carpeta(self):
        self._crear("", "Nombre de la carpeta nueva (por ejemplo «Subestaciones»):")

    def nueva_subcarpeta(self):
        padre = self._rel_seleccionada()
        if padre is None:
            QMessageBox.information(self, "Carpetas",
                                    "Elegí primero la carpeta donde va la subcarpeta.")
            return
        self._crear(padre, "Nombre de la carpeta nueva dentro de «%s»:" % self.nombre_visible(padre))

    def renombrar_carpeta(self):
        rel = self._rel_seleccionada()
        if rel is None or self.bib.es_protegida(rel):
            return
        nombre, ok = QInputDialog.getText(self, "Renombrar carpeta", "Nombre nuevo:",
                                          text=Path(rel).name)
        if ok and nombre.strip() and nombre.strip() != Path(rel).name:
            nuevo = self._intentar(self.bib.renombrar_carpeta, rel, nombre)
            if nuevo is not None:
                self.carpeta_actual = nuevo
                self.refrescar()

    def eliminar_carpeta(self):
        rel = self._rel_seleccionada()
        if rel is None or self.bib.es_protegida(rel):
            return
        r = QMessageBox.question(self, "Eliminar carpeta",
                                 "¿Eliminar la carpeta «%s»?" % self.nombre_visible(rel))
        if r == QMessageBox.Yes and self._intentar(self.bib.eliminar_carpeta, rel) is None:
            self.carpeta_actual = rel.rsplit("/", 1)[0] if "/" in rel else None
            self.refrescar()

    def _fotos_soltadas(self, rutas, destino):
        if not destino:
            return  # las fotos van siempre dentro de alguna carpeta
        nuevas = self._intentar(self.bib.traer_fotos, rutas, destino)
        if nuevas is not None:
            self.refrescar()
            self.mensaje.emit("%d foto%s en «%s»." % (len(nuevas), "" if len(nuevas) == 1 else "s",
                                                     self.nombre_visible(destino)))

    def _carpeta_soltada(self, rel, destino):
        nuevo = self._intentar(self.bib.mover_carpeta, rel, destino)
        if nuevo is not None:
            self.carpeta_actual = nuevo
            self.refrescar()

    def _menu_arbol(self, pos):
        it = self.arbol.itemAt(pos)
        m = QMenu(self)
        m.addAction("Nueva carpeta principal…", self.nueva_carpeta)
        if it:
            self.arbol.setCurrentItem(it)
            m.addAction("Nueva subcarpeta…", self.nueva_subcarpeta)
            if not self.bib.es_protegida(it.data(0, ROL_REL)):
                m.addAction("Renombrar…", self.renombrar_carpeta)
                m.addAction("Eliminar", self.eliminar_carpeta)
            m.addSeparator()
            m.addAction("Mostrar en el Explorador",
                        lambda: sistema.mostrar_en_explorador(self.bib.abs(it.data(0, ROL_REL))))
        m.exec(self.arbol.viewport().mapToGlobal(pos))

    # == galeria =============================================================
    def _crear_galeria(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.lbl_galeria = etiqueta("")
        self.lbl_galeria.setWordWrap(True)
        v.addWidget(self.lbl_galeria)
        self.galeria = Galeria()
        self.galeria.currentItemChanged.connect(self._foto_elegida)
        self.galeria.customContextMenuRequested.connect(self._menu_galeria)
        v.addWidget(self.galeria)
        v.addWidget(etiqueta("Arrastrá las fotos a una carpeta para organizarlas.", "suave"))
        return w

    def _cargar_galeria(self):
        self.miniaturas.cancelar_pendientes()
        self.galeria.clear()
        self._items_galeria = {}
        rel = self.carpeta_actual or CARPETA_IMPORTADAS
        try:
            fotos = self.bib.fotos(rel)
            n_sub = len(self.bib.subcarpetas(rel))
        except (ErrorBiblioteca, OSError):
            fotos, n_sub = [], 0
        titulo = self.nombre_visible(rel)
        if fotos:
            self.lbl_galeria.setText("<b>%s</b> &nbsp;<span style='color:%s'>%d foto%s</span>"
                                     % (titulo, theme.color("texto_suave"), len(fotos),
                                        "" if len(fotos) == 1 else "s"))
        elif n_sub:
            self.lbl_galeria.setText("<b>%s</b> — elegí una subcarpeta para ver sus fotos" % titulo)
        else:
            self.lbl_galeria.setText("<b>%s</b> — vacía" % titulo)
        for p in fotos:
            fecha = _fecha_desde_nombre(p.name)
            texto = fecha.strftime("%d/%m/%Y %H:%M") if fecha else p.stem
            it = QListWidgetItem(self._icono_vacio, texto)
            it.setData(ROL_RUTA, str(p))
            it.setToolTip(p.name)
            self.galeria.addItem(it)
            self._items_galeria[str(p)] = it
            self.miniaturas.pedir(p)

    def _miniatura_lista(self, ruta, img: QImage):
        it = self._items_galeria.get(ruta)
        if it is not None:
            it.setIcon(QIcon(QPixmap.fromImage(img)))

    def _foto_elegida(self, item, *_):
        if item is not None:
            self.abrirFoto.emit(Path(item.data(ROL_RUTA)))

    def marcar_abierta(self, ruta):
        """Selecciona en la galeria la foto que se esta viendo, si esta ahi."""
        it = self._items_galeria.get(str(ruta))
        if it is not None and self.galeria.currentItem() is not it:
            self.galeria.blockSignals(True)
            self.galeria.setCurrentItem(it)
            self.galeria.blockSignals(False)
            self.galeria.scrollToItem(it)

    def _menu_galeria(self, pos):
        rutas = self.galeria.rutas_seleccionadas()
        if not rutas:
            return
        m = QMenu(self)
        if len(rutas) == 1:
            m.addAction("Abrir", lambda: self.abrirFoto.emit(rutas[0]))
        elif len(rutas) == 2:
            m.addAction("Comparar (C)", lambda: self.compararFotos.emit(rutas))
        m.addAction("Mover a carpeta…", lambda: self.mover_a_carpeta(rutas))
        m.addSeparator()
        m.addAction("Mostrar en el Explorador", lambda: sistema.mostrar_en_explorador(rutas[0]))
        m.exec(self.galeria.viewport().mapToGlobal(pos))

    def mover_a_carpeta(self, rutas):
        carpetas = self.bib.todas_las_carpetas()
        visibles = [self.nombre_visible(c) for c in carpetas]
        actual = carpetas.index(self.carpeta_actual) if self.carpeta_actual in carpetas else 0
        elegida, ok = QInputDialog.getItem(
            self, "Mover fotos", "Mover %d foto%s a:" % (len(rutas), "" if len(rutas) == 1 else "s"),
            visibles, actual, False)
        if ok:
            self._fotos_soltadas(rutas, carpetas[visibles.index(elegida)])
