"""Panel lateral: importacion desde la camara, arbol de carpetas y galeria."""
import json
from pathlib import Path

from PySide6.QtCore import QMimeData, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton, QSplitter, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core.importer import Modo
from ..core.library import CARPETA_IMPORTADAS, ErrorBiblioteca, es_foto, fecha_visible
from ..core.thermal_image import _fecha_desde_nombre
from . import sistema
from .import_worker import HiloDescarga, HiloPlan
from .thumbnails import TAMANO, CargadorMiniaturas

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
    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(TAMANO, int(TAMANO * 0.8)))
        self.setGridSize(QSize(TAMANO + 16, int(TAMANO * 0.8) + 34))
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mimeData(self, items):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(it.data(ROL_RUTA)) for it in items])
        return md

    def rutas_seleccionadas(self):
        return [Path(it.data(ROL_RUTA)) for it in self.selectedItems()]


def _icono_vacio():
    pix = QPixmap(TAMANO, int(TAMANO * 0.8))
    pix.fill(QColor("#2a2a2a"))
    return QIcon(pix)


# -- panel -----------------------------------------------------------------
class LibraryPanel(QWidget):
    abrirFoto = Signal(Path)
    mensaje = Signal(str)

    def __init__(self, biblioteca, conexion_camara, parent=None):
        super().__init__(parent)
        self.bib = biblioteca
        self.conexion_camara = conexion_camara  # callable -> dict para CameraFTP
        self.carpeta_actual = None
        self._items_galeria = {}
        self._hilo = None
        self._icono_vacio = _icono_vacio()

        self.miniaturas = CargadorMiniaturas(self.bib.miniaturas, self)
        self.miniaturas.lista.connect(self._miniatura_lista)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self._crear_camara())

        split = QSplitter(Qt.Vertical)
        split.addWidget(self._crear_carpetas())
        split.addWidget(self._crear_galeria())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

        self.refrescar()

    # == camara ==============================================================
    def _crear_camara(self):
        caja = QGroupBox("Cámara (WiFi)")
        v = QVBoxLayout(caja)
        h = QHBoxLayout()
        self.btn_faltantes = QPushButton("Traer faltantes")
        self.btn_faltantes.setToolTip("Descargar solo las fotos que todavía no se importaron")
        self.btn_faltantes.setDefault(True)
        self.btn_todo = QPushButton("Traer todas")
        self.btn_todo.setToolTip("Descargar todas las fotos de la cámara que no estén en la "
                                 "biblioteca, incluidas las que hayas borrado antes")
        self.btn_faltantes.clicked.connect(lambda: self.importar(Modo.FALTANTES))
        self.btn_todo.clicked.connect(lambda: self.importar(Modo.TODO))
        h.addWidget(self.btn_faltantes)
        h.addWidget(self.btn_todo)
        v.addLayout(h)

        self.barra = QProgressBar()
        self.barra.setTextVisible(True)
        self.lbl_progreso = QLabel()
        self.lbl_progreso.setWordWrap(True)
        self.lbl_progreso.setStyleSheet("font-size: 11px;")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self._cancelar)
        for w in (self.barra, self.lbl_progreso, self.btn_cancelar):
            v.addWidget(w)
            w.hide()
        return caja

    def importando(self):
        return self._hilo is not None

    def importar(self, modo):
        if self.importando():
            return
        self._modo = modo
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
        v.addWidget(QLabel("<b>Carpetas</b>"))
        h = QHBoxLayout()
        self.btn_carpeta = QPushButton("+ Carpeta")
        self.btn_carpeta.setToolTip("Crear una carpeta principal, por ejemplo «Subestaciones»")
        self.btn_carpeta.clicked.connect(self.nueva_carpeta)
        self.btn_subcarpeta = QPushButton("+ Subcarpeta")
        self.btn_subcarpeta.setToolTip("Crear una carpeta dentro de la seleccionada")
        self.btn_subcarpeta.clicked.connect(self.nueva_subcarpeta)
        self.btn_renombrar = QPushButton("Renombrar")
        self.btn_renombrar.clicked.connect(self.renombrar_carpeta)
        self.btn_eliminar = QPushButton("Eliminar")
        self.btn_eliminar.setToolTip("Eliminar la carpeta (solo si no tiene fotos)")
        self.btn_eliminar.clicked.connect(self.eliminar_carpeta)
        for b in (self.btn_carpeta, self.btn_subcarpeta, self.btn_renombrar, self.btn_eliminar):
            h.addWidget(b)
        v.addLayout(h)

        self.arbol = ArbolCarpetas()
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
        estilo = self.style()
        ico_carpeta = estilo.standardIcon(estilo.StandardPixmap.SP_DirIcon)
        ico_importadas = estilo.standardIcon(estilo.StandardPixmap.SP_DriveHDIcon)

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
                agregar(it, "%s/%s" % (rel, sub), visible, ico_carpeta)
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
        self.lbl_galeria = QLabel()
        v.addWidget(self.lbl_galeria)
        self.galeria = Galeria()
        self.galeria.currentItemChanged.connect(self._foto_elegida)
        self.galeria.customContextMenuRequested.connect(self._menu_galeria)
        v.addWidget(self.galeria)
        ayuda = QLabel("Arrastrá las fotos a una carpeta para organizarlas.")
        ayuda.setStyleSheet("color: #888; font-size: 11px;")
        v.addWidget(ayuda)
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
            self.lbl_galeria.setText("<b>%s</b> — %d foto%s"
                                     % (titulo, len(fotos), "" if len(fotos) == 1 else "s"))
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
