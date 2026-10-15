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
from ..core.library import CARPETA_IMPORTADAS, ErrorBiblioteca, es_foto
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
        it = self.itemAt(ev.position().toPoint())
        return None if it is None else it.data(0, ROL_REL)

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
        it = self.itemAt(ev.position().toPoint())
        self.setCurrentItem(it, 0, self.selectionModel().SelectionFlag.NoUpdate)
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
            self.mensaje.emit(texto + " Están en «%s»." % CARPETA_IMPORTADAS)

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
    def _crear_carpetas(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        h = QHBoxLayout()
        h.addWidget(QLabel("<b>Carpetas</b>"), 1)
        for texto, tip, fn in (("+ Nueva", "Crear una carpeta dentro de la seleccionada", self.nueva_carpeta),
                               ("Renombrar", "", self.renombrar_carpeta),
                               ("Eliminar", "Eliminar la carpeta (solo si no tiene fotos)", self.eliminar_carpeta)):
            b = QPushButton(texto)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            h.addWidget(b)
        v.addLayout(h)

        self.arbol = ArbolCarpetas()
        self.arbol.currentItemChanged.connect(self._carpeta_elegida)
        self.arbol.fotosSoltadas.connect(self._fotos_soltadas)
        self.arbol.carpetaSoltada.connect(self._carpeta_soltada)
        self.arbol.customContextMenuRequested.connect(self._menu_arbol)
        v.addWidget(self.arbol)
        return w

    def set_biblioteca(self, biblioteca):
        self.bib = biblioteca
        self.miniaturas.set_cache(biblioteca.miniaturas)
        self.carpeta_actual = None
        self.refrescar()

    def refrescar(self):
        """Rearma el arbol conservando la carpeta elegida y las expandidas."""
        actual = self.carpeta_actual
        expandidas = {it.data(0, ROL_REL) for it in self._items_arbol() if it.isExpanded()}
        self.arbol.blockSignals(True)
        self.arbol.clear()
        conteos = self._conteos()
        raiz = QTreeWidgetItem([self._etiqueta(self.bib.raiz.name, conteos.get("", 0))])
        raiz.setData(0, ROL_REL, "")
        raiz.setToolTip(0, str(self.bib.raiz))
        self.arbol.addTopLevelItem(raiz)

        def agregar(padre, rel):
            for nombre in self.bib.subcarpetas(rel):
                r = "%s/%s" % (rel, nombre) if rel else nombre
                it = QTreeWidgetItem([self._etiqueta(nombre, conteos.get(r, 0))])
                it.setData(0, ROL_REL, r)
                padre.addChild(it)
                agregar(it, r)
                it.setExpanded(r in expandidas)
        agregar(raiz, "")
        raiz.setExpanded(True)
        self.arbol.blockSignals(False)
        self.seleccionar_carpeta(actual if actual is not None else "", forzar=True)

    def _conteos(self):
        """{carpeta relativa: fotos en ella y sus subcarpetas}."""
        conteos = {}
        for p in self.bib.indice().values():
            partes = Path(self.bib.rel(p.parent)).parts if p.parent != self.bib.raiz else ()
            for k in range(len(partes) + 1):
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
        if rel:
            self.seleccionar_carpeta("", forzar)

    def _carpeta_elegida(self, item, *_):
        if item is None:
            return
        self.carpeta_actual = item.data(0, ROL_REL)
        self._cargar_galeria()

    def _rel_seleccionada(self):
        it = self.arbol.currentItem()
        return it.data(0, ROL_REL) if it else ""

    def _intentar(self, fn, *args):
        try:
            return fn(*args)
        except ErrorBiblioteca as e:
            QMessageBox.warning(self, "Carpetas", str(e))
        except OSError as e:
            QMessageBox.warning(self, "Carpetas", "No se pudo completar la operación:\n%s" % e)
        return None

    def nueva_carpeta(self):
        padre = self._rel_seleccionada()
        nombre, ok = QInputDialog.getText(
            self, "Nueva carpeta",
            "Nombre de la carpeta nueva dentro de «%s»:" % (padre or self.bib.raiz.name))
        if ok and nombre.strip():
            rel = self._intentar(self.bib.crear_carpeta, padre, nombre)
            if rel is not None:
                self.carpeta_actual = rel
                self.refrescar()

    def renombrar_carpeta(self):
        rel = self._rel_seleccionada()
        if not rel:
            QMessageBox.information(self, "Carpetas", "Elegí la carpeta que querés renombrar.")
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
        if not rel:
            QMessageBox.information(self, "Carpetas", "Elegí la carpeta que querés eliminar.")
            return
        r = QMessageBox.question(self, "Eliminar carpeta", "¿Eliminar la carpeta «%s»?" % rel)
        if r == QMessageBox.Yes and self._intentar(self.bib.eliminar_carpeta, rel) is None:
            self.carpeta_actual = rel.rsplit("/", 1)[0] if "/" in rel else ""
            self.refrescar()

    def _fotos_soltadas(self, rutas, destino):
        nuevas = self._intentar(self.bib.traer_fotos, rutas, destino)
        if nuevas is not None:
            self.refrescar()
            self.mensaje.emit("%d foto%s en «%s»." % (len(nuevas), "" if len(nuevas) == 1 else "s",
                                                     destino or self.bib.raiz.name))

    def _carpeta_soltada(self, rel, destino):
        nuevo = self._intentar(self.bib.mover_carpeta, rel, destino)
        if nuevo is not None:
            self.carpeta_actual = nuevo
            self.refrescar()

    def _menu_arbol(self, pos):
        it = self.arbol.itemAt(pos)
        if it:
            self.arbol.setCurrentItem(it)
        m = QMenu(self)
        m.addAction("Nueva carpeta…", self.nueva_carpeta)
        if it and it.data(0, ROL_REL):
            m.addAction("Renombrar…", self.renombrar_carpeta)
            m.addAction("Eliminar", self.eliminar_carpeta)
        m.addSeparator()
        m.addAction("Mostrar en el Explorador",
                    lambda: sistema.mostrar_en_explorador(self.bib.abs(self._rel_seleccionada())))
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
        rel = self.carpeta_actual or ""
        try:
            fotos = self.bib.fotos(rel)
        except (ErrorBiblioteca, OSError):
            fotos = []
        n_sub = len(self.bib.subcarpetas(rel)) if fotos == [] else 0
        if fotos:
            self.lbl_galeria.setText("<b>%s</b> — %d foto%s"
                                     % (rel or self.bib.raiz.name, len(fotos),
                                        "" if len(fotos) == 1 else "s"))
        elif n_sub:
            self.lbl_galeria.setText("<b>%s</b> — sin fotos sueltas; abrí una subcarpeta"
                                     % (rel or self.bib.raiz.name))
        else:
            self.lbl_galeria.setText("<b>%s</b> — vacía" % (rel or self.bib.raiz.name))
        for p in fotos:
            fecha = _fecha_desde_nombre(p.name)
            texto = fecha.strftime("%d/%m/%y %H:%M") if fecha else p.stem
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
        raiz = self.bib.raiz.name
        opciones = [raiz] + self.bib.todas_las_carpetas()
        actual = self.carpeta_actual or ""
        elegida, ok = QInputDialog.getItem(
            self, "Mover fotos", "Mover %d foto%s a:" % (len(rutas), "" if len(rutas) == 1 else "s"),
            opciones, opciones.index(actual) if actual in opciones else 0, False)
        if ok:
            self._fotos_soltadas(rutas, "" if elegida == raiz else elegida)
