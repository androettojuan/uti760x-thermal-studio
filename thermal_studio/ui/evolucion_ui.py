"""Vista de evolucion de un lugar (una carpeta) en el tiempo.

Grafico con la maxima de cada foto y la de cada medicion seguida por nombre
(o su Delta T contra la referencia), y una tabla con una fila por foto.
Las fotos se leen en un hilo aparte: una carpeta puede tener muchas.
"""
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QHBoxLayout, QHeaderView, QProgressBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core import evolucion
from ..core.thermal_image import ThermalImage
from ..core.uti760x import FormatoInvalido
from . import theme
from .widgets import boton, etiqueta, marco
from ..i18n import a_unidad, fecha, fecha_hora, formato_fecha, plural, simbolo, temp, tr

# Colores de las series de mediciones (la maxima de la foto va en gris)
COLORES = ["#ff7a1a", "#3d9bff", "#34c759", "#c86bfa", "#ffb020", "#ff5b4f", "#2ec4b6",
           "#e84393", "#a3e635", "#f472b6"]
VER_MAXIMAS, VER_DELTAS = "maximas", "deltas"


class _EjeFechas(pg.DateAxisItem):
    """Fechas como dd/mm/aaaa (o dd/mm hh:mm si las marcas estan a menos de un dia)."""

    def tickStrings(self, values, scale, spacing):
        formato = "%H:%M" if spacing < 86400 else formato_fecha()
        out = []
        for v in values:
            try:
                out.append(datetime.fromtimestamp(v).strftime(formato))
            except (OverflowError, OSError, ValueError):
                out.append("")
        return out


class _Lector(QThread):
    """Lee las fotos de la carpeta y arma una FilaEvolucion por cada una."""

    progreso = Signal(int, int)
    listo = Signal(list)

    def __init__(self, rutas, biblioteca, cache, parent=None):
        super().__init__(parent)
        self.rutas, self.biblioteca, self.cache = rutas, biblioteca, cache
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def _clave(self, ruta):
        """Cambia si cambia la foto o sus mediciones: entonces se vuelve a leer."""
        med = self.biblioteca.carpeta_mediciones / (ruta.name + ".json")
        try:
            return (str(ruta), ruta.stat().st_mtime_ns,
                    med.stat().st_mtime_ns if med.exists() else 0)
        except OSError:
            return None

    def run(self):
        filas = []
        for i, ruta in enumerate(self.rutas):
            if self._cancelar:
                return
            self.progreso.emit(i, len(self.rutas))
            clave = self._clave(ruta)
            if clave is not None and clave in self.cache:
                filas.append(self.cache[clave])
                continue
            try:
                f = evolucion.fila(ruta, ThermalImage.abrir(ruta),
                                   self.biblioteca.leer_mediciones(ruta.name))
            except (FormatoInvalido, OSError):
                continue
            if clave is not None:
                self.cache[clave] = f
            filas.append(f)
        self.listo.emit(evolucion.ordenar(filas))


class VistaEvolucion(QWidget):
    """Senales: abrirFoto(Path), cerrar()."""

    abrirFoto = Signal(Path)
    cerrar = Signal()
    COLUMNAS = (tr("Fecha"), tr("Máxima"), tr("Mayor ΔT"), tr("Mediciones"), tr("Notas"))

    def __init__(self):
        super().__init__()
        self.filas = []
        self.modo = VER_MAXIMAS
        self._cache = {}
        self._lector = None

        fondo = marco("panel", self)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(fondo)
        v = QVBoxLayout(fondo)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)

        barra = QHBoxLayout()
        self.titulo = etiqueta(tr("Evolución"), "titulo")
        self.subtitulo = etiqueta("", "suave")
        barra.addWidget(self.titulo)
        barra.addSpacing(12)
        barra.addWidget(self.subtitulo)
        barra.addStretch(1)
        self.grupo = QButtonGroup(self)
        for clave, texto, ayuda in (
                (VER_MAXIMAS, tr("Máximas"), tr("Máxima de cada foto y de cada medición")),
                (VER_DELTAS, tr("ΔT"), tr("ΔT de cada medición contra la referencia de su foto"))):
            b = boton(texto, tooltip=ayuda)
            b.setCheckable(True)
            b.setChecked(clave == self.modo)
            b.clicked.connect(lambda _=False, c=clave: self._set_modo(c))
            self.grupo.addButton(b)
            barra.addWidget(b)
        barra.addSpacing(8)
        b = boton(tr("Cerrar"), "mdi6.close", tooltip=tr("Volver a ver una sola foto (Esc)"))
        b.clicked.connect(self.cerrar)
        barra.addWidget(b)
        v.addLayout(barra)

        self.progreso = QProgressBar()
        self.progreso.setTextVisible(True)
        self.progreso.hide()
        v.addWidget(self.progreso)

        self.grafico = pg.PlotWidget(axisItems={"bottom": _EjeFechas(orientation="bottom")})
        self.grafico.setMenuEnabled(False)
        self.grafico.showGrid(x=False, y=True, alpha=0.15)
        self.leyenda = self.grafico.addLegend(offset=(10, 10))
        v.addWidget(self.grafico, 3)

        self.vacio = etiqueta("", "suave")
        self.vacio.setWordWrap(True)
        self.vacio.hide()
        v.addWidget(self.vacio)

        self.tabla = QTableWidget(0, len(self.COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(self.COLUMNAS)
        self.tabla.verticalHeader().hide()
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setToolTip(tr("Doble clic para abrir la foto"))
        enc = self.tabla.horizontalHeader()
        for i in range(4):
            enc.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        enc.setSectionResizeMode(4, QHeaderView.Stretch)
        self.tabla.cellDoubleClicked.connect(lambda f, _c: self._abrir_fila(f))
        v.addWidget(self.tabla, 2)
        theme.al_cambiar(self._aplicar_tema)

    # -- API ---------------------------------------------------------------
    def mostrar(self, rutas, biblioteca, nombre_lugar):
        """Empieza a leer las fotos; el grafico aparece cuando terminan."""
        self.detener()
        self.titulo.setText(tr("Evolución — %s") % nombre_lugar)
        self.subtitulo.setText(plural(len(rutas), "Leyendo %d foto…", "Leyendo %d fotos…")
                               % len(rutas))
        self.filas = []
        self._dibujar()
        self.progreso.setRange(0, max(len(rutas), 1))
        self.progreso.setValue(0)
        self.progreso.show()
        self._lector = _Lector([Path(r) for r in rutas], biblioteca, self._cache, self)
        self._lector.progreso.connect(lambda i, n: self.progreso.setValue(i))
        self._lector.listo.connect(self._leidas)
        self._lector.start()

    def detener(self):
        if self._lector is not None:
            self._lector.cancelar()
            self._lector.wait(5000)
            self._lector = None

    # -- interno -----------------------------------------------------------
    def _leidas(self, filas):
        self._lector = None
        self.progreso.hide()
        self.filas = filas
        con_fecha = [f.fecha for f in filas if f.fecha]
        if con_fecha:
            self.subtitulo.setText(tr("%s · del %s al %s") % (
                plural(len(filas), "%d foto", "%d fotos") % len(filas),
                fecha(min(con_fecha)), fecha(max(con_fecha))))
        else:
            self.subtitulo.setText(plural(len(filas), "%d foto", "%d fotos") % len(filas))
        self._llenar_tabla()
        self._dibujar()

    def _set_modo(self, modo):
        self.modo = modo
        self._dibujar()

    def _dibujar(self):
        g = self.grafico
        g.clear()
        self.leyenda.clear()
        con_fecha = [f for f in self.filas if f.fecha]
        series = evolucion.series(self.filas)
        hay_deltas = any(d is not None for s in series.values() for _, _, d in s)
        mensaje = ""
        if not self.filas:
            mensaje = ""
        elif len(con_fecha) < 2:
            mensaje = tr("Hace falta al menos dos fotos con fecha en esta carpeta para ver la evolución.")
        elif self.modo == VER_DELTAS and not hay_deltas:
            mensaje = (tr("Todavía no hay ΔT: en las fotos, marcá una medición como referencia (★) "
                       "y poné a las mediciones del mismo equipo el mismo nombre en cada ronda "
                       "(por ejemplo «Fase R»)."))
        self.vacio.setText(mensaje)
        self.vacio.setVisible(bool(mensaje))

        def ts(fecha):
            return fecha.timestamp()

        if self.modo == VER_MAXIMAS and con_fecha:
            g.setLabel("left", "%s (%s)" % (tr("Máxima"), simbolo()))
            pen = pg.mkPen(theme.color("texto_suave"), width=1.5, style=Qt.DashLine)
            curva = g.plot([ts(f.fecha) for f in con_fecha], [a_unidad(f.maxima) for f in con_fecha],
                           pen=pen, symbol="o", symbolSize=7,
                           symbolBrush=theme.color("texto_suave"), name=tr("Máxima de la foto"))
            self._clic_en_puntos(curva, con_fecha)
        elif self.modo == VER_DELTAS:
            g.setLabel("left", "%s (%s)" % (tr("ΔT contra la referencia"), simbolo()))
            g.addLine(y=0, pen=pg.mkPen(theme.color("borde"), width=1))

        for i, (nombre, puntos) in enumerate(sorted(series.items())):
            if self.modo == VER_DELTAS:
                puntos = [p for p in puntos if p[2] is not None]
            if not puntos:
                continue
            color = COLORES[i % len(COLORES)]
            ys = [a_unidad(p[1]) if self.modo == VER_MAXIMAS else a_unidad(p[2], diferencia=True)
                  for p in puntos]
            g.plot([ts(p[0]) for p in puntos], ys, pen=pg.mkPen(color, width=2), symbol="o",
                   symbolSize=8, symbolBrush=color, name=nombre)
        g.enableAutoRange()

    def _clic_en_puntos(self, curva, filas):
        def clic(_item, puntos, *_):
            if len(puntos):
                i = int(puntos[0].index())
                if 0 <= i < len(filas):
                    self.abrirFoto.emit(Path(filas[i].ruta))
        curva.scatter.sigClicked.connect(clic)

    def _llenar_tabla(self):
        self.tabla.setRowCount(len(self.filas))
        for r, f in enumerate(self.filas):
            d = f.mayor_delta
            valores = (fecha_hora(f.fecha) if f.fecha else tr("Sin fecha"),
                       temp(f.maxima, limites=f.limites), temp(d, signo=True),
                       str(len(f.mediciones)) if f.mediciones else "—",
                       f.notas.replace("\n", " "))
            for c, texto in enumerate(valores):
                it = QTableWidgetItem(texto)
                if c in (1, 2, 3):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 2 and d is not None and d >= 1.0:
                    it.setForeground(pg.mkColor(theme.color("aviso")))
                self.tabla.setItem(r, c, it)

    def _abrir_fila(self, fila):
        if 0 <= fila < len(self.filas):
            self.abrirFoto.emit(Path(self.filas[fila].ruta))

    def _aplicar_tema(self):
        self.grafico.setBackground(theme.color("fondo"))
        for eje in ("left", "bottom"):
            a = self.grafico.getAxis(eje)
            a.setPen(pg.mkPen(theme.color("borde")))
            a.setTextPen(pg.mkPen(theme.color("texto_suave")))
        self._dibujar()
