"""Imagen anotada (PNG) e informe PDF.

Todo se dibuja con QPainter, sin dependencias nuevas: la misma funcion que
arma la imagen con las mediciones sirve para exportar PNG y para el PDF.
"""
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from PySide6.QtCore import QBuffer, QIODevice, QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen,
    QPolygonF,
)

from ..core.library import fecha_visible
from ..core.mediciones import AREA, LINEA, NOMBRES_TIPO, PUNTO, estadistica, resultados
from ..core.thermal_image import posiciones_ecualizadas, tabla_colores
from ..core.uti760x import TempConverter
from ..i18n import fecha, fecha_hora, num, temp, tr

COLOR_TRAZO = QColor("#ffffff")
COLOR_SOMBRA = QColor(0, 0, 0, 190)
COLOR_MAX = QColor("#ff5b4f")
ACENTO = QColor("#e86a10")
GRIS = QColor("#5b6270")
GRIS_CLARO = QColor("#e4e7ec")
AVISO = QColor("#b26b00")


@dataclass
class Ajustes:
    """Como se ve la imagen: lo mismo que eligio el usuario en la barra."""
    paleta: str
    invertir: bool = False
    ecualizar: bool = True
    rango: tuple | None = None  # None = automatico de cada foto


@dataclass
class DatosInforme:
    titulo: str = tr("Informe termográfico")
    instalacion: str = ""
    inspector: str = ""
    fecha: date = field(default_factory=date.today)
    incluir_visible: bool = True
    observaciones: str = ""  # conclusiones y recomendaciones generales


# -- imagen anotada --------------------------------------------------------
def _qimage_rgb(rgb):
    rgb = np.ascontiguousarray(rgb)
    alto, ancho, _ = rgb.shape
    return QImage(rgb.data, ancho, alto, 3 * ancho, QImage.Format_RGB888).copy()


def _rango_y_posiciones(img, ajustes):
    lo, hi = ajustes.rango or img.rango_auto()
    pos = posiciones_ecualizadas(img.temps, lo, hi) if ajustes.ecualizar else None
    return lo, hi, pos


def _etiqueta(p, x, y, texto, color=COLOR_TRAZO, limite=None):
    """Texto con fondo oscuro, con la esquina de abajo a la izquierda en (x, y).
    `limite` (ancho, alto) la mantiene dentro de la imagen."""
    fm = QFontMetricsF(p.font())
    r = fm.boundingRect(texto)
    pad = fm.height() * 0.18
    ancho, alto = r.width() + 2 * pad, r.height() + 2 * pad
    if limite is not None:
        x = min(max(x, 0), limite[0] - ancho)
        y = min(max(y, alto), limite[1])
    caja = QRectF(x, y - alto, ancho, alto)
    p.fillRect(caja, COLOR_SOMBRA)
    p.setPen(color)
    p.drawText(caja, Qt.AlignCenter, texto)


def _triangulo(p, x, y, lado, color):
    t = QPolygonF([QPointF(x, y - lado * 0.6), QPointF(x - lado / 2, y + lado * 0.4),
                   QPointF(x + lado / 2, y + lado * 0.4)])
    p.setPen(QPen(Qt.black, max(lado / 10, 1)))
    p.setBrush(color)
    p.drawPolygon(t)
    p.setBrush(Qt.NoBrush)


def imagen_anotada(img, mediciones, ajustes, escala=2, con_barra=True):
    """QImage de la termica con la paleta, las mediciones y la barra de color."""
    lo, hi, pos = _rango_y_posiciones(img, ajustes)
    base = _qimage_rgb(img.render(ajustes.paleta, (lo, hi), ajustes.invertir, pos))
    base = base.scaled(img.ancho * escala, img.alto * escala, Qt.IgnoreAspectRatio,
                       Qt.SmoothTransformation)
    ancho_barra = int(70 * escala) if con_barra else 0
    out = QImage(base.width() + ancho_barra, base.height(), QImage.Format_RGB888)
    out.fill(QColor("#15181e"))
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.drawImage(0, 0, base)
    f = QFont()
    f.setPixelSize(int(11 * escala))
    p.setFont(f)
    grosor = max(1.5 * escala, 1)
    limite = (base.width(), base.height())

    # Maxima de toda la imagen
    mx = img.maximo()
    _triangulo(p, (mx.col + 0.5) * escala, (mx.fila + 0.5) * escala, 9 * escala, COLOR_MAX)
    _etiqueta(p, (mx.col + 0.5) * escala + 6 * escala, (mx.fila + 0.5) * escala,
              temp(mx.temp), COLOR_MAX, limite)

    for m in mediciones.lista:
        e = estadistica(m, img.temps)
        p.setPen(QPen(COLOR_TRAZO, grosor))
        g = [v * escala for v in m.geom]
        if m.tipo == PUNTO:
            x, y = g
            r = 7 * escala
            p.drawLine(QPointF(x - r, y), QPointF(x + r, y))
            p.drawLine(QPointF(x, y - r), QPointF(x, y + r))
            p.drawEllipse(QPointF(x, y), r * 0.55, r * 0.55)
            _etiqueta(p, x + r, y - r * 0.3, "%s  %s" % (m.nombre, temp(e.maxima)), limite=limite)
            continue
        if m.tipo == LINEA:
            p.drawLine(QPointF(g[0], g[1]), QPointF(g[2], g[3]))
            ex, ey = g[2] + 4 * escala, g[3] - 4 * escala
        else:
            x0, x1 = sorted((g[0], g[2]))
            y0, y1 = sorted((g[1], g[3]))
            p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
            ex, ey = x0, y0 - 2 * escala
        _triangulo(p, (e.col_max + 0.5) * escala, (e.fila_max + 0.5) * escala, 7 * escala,
                   COLOR_TRAZO)
        _etiqueta(p, ex, ey, tr("%s  máx %s") % (m.nombre, temp(e.maxima)), limite=limite)

    if con_barra:
        _barra(p, QRectF(base.width() + 12 * escala, 10 * escala, 18 * escala,
                         base.height() - 20 * escala), lo, hi, ajustes, pos, escala)
    p.end()
    return out


def _barra(p, rect, lo, hi, ajustes, pos, escala):
    tabla = tabla_colores(ajustes.paleta, ajustes.invertir, pos)
    alto = int(rect.height())
    franja = QImage(1, alto, QImage.Format_RGB888)
    for y in range(alto):
        c = tabla[int((1 - y / max(alto - 1, 1)) * (len(tabla) - 1))]
        franja.setPixelColor(0, y, QColor(int(c[0]), int(c[1]), int(c[2])))
    p.drawImage(rect, franja)
    p.setPen(QPen(QColor("#2a303b"), 1))
    p.drawRect(rect)
    p.setPen(QColor("#c9ced8"))
    for k in range(6):
        t = lo + (hi - lo) * k / 5
        y = rect.bottom() - rect.height() * k / 5
        p.drawLine(QPointF(rect.right(), y), QPointF(rect.right() + 4 * escala, y))
        p.drawText(QRectF(rect.right() + 6 * escala, y - 8 * escala, 40 * escala, 16 * escala),
                   Qt.AlignLeft | Qt.AlignVCenter, "%.0f" % t)


# -- PDF -------------------------------------------------------------------
class _Pagina:
    """Ayuda para dibujar en mm sobre el PDF, con paginado y pie."""

    MARGEN_PIE = 14  # mm reservados abajo para el pie

    def __init__(self, writer, painter, datos, total=None):
        self.w, self.p = writer, painter
        self.datos, self.total = datos, total
        self.n = 1
        self.dpi = writer.resolution()
        r = writer.pageLayout().paintRectPixels(self.dpi)
        self.ancho_mm = r.width() / self.dpi * 25.4
        self.alto_mm = r.height() / self.dpi * 25.4

    def cabe(self, y, alto):
        return y + alto <= self.alto_mm - self.MARGEN_PIE

    def nueva_pagina(self):
        self.pie()
        self.w.newPage()
        self.n += 1

    def pie(self):
        y = self.alto_mm - 6
        self.linea(0, y - 1.5, self.ancho_mm)
        self.fuente(7.5, color=GRIS)
        d = self.datos
        self.texto(0, y, self.ancho_mm / 2,
                   d.titulo + (" — " + d.instalacion if d.instalacion else ""))
        self.texto(self.ancho_mm / 2, y, self.ancho_mm / 2,
                   tr("Página %d de %d") % (self.n, self.total) if self.total else "",
                   alinear=Qt.AlignRight | Qt.AlignTop)

    def alto_texto(self, ancho, texto):
        """Alto en mm que ocupa el texto envuelto en ese ancho, sin dibujarlo."""
        caja = QRectF(0, 0, self.mm(ancho), self.mm(1000))
        r = self.p.boundingRect(caja, int(Qt.AlignLeft | Qt.AlignTop) | int(Qt.TextWordWrap), texto)
        return r.height() / self.dpi * 25.4

    def mm(self, v):
        return v * self.dpi / 25.4

    def fuente(self, puntos, negrita=False, color=Qt.black):
        f = QFont()
        f.setPointSizeF(puntos)
        f.setBold(negrita)
        self.p.setFont(f)
        self.p.setPen(color)

    def texto(self, x, y, ancho, texto, alto=None, alinear=Qt.AlignLeft | Qt.AlignTop,
              envolver=False):
        """Dibuja texto en (x, y) mm; devuelve el alto usado en mm."""
        flags = int(alinear) | (int(Qt.TextWordWrap) if envolver else 0)
        caja = QRectF(self.mm(x), self.mm(y), self.mm(ancho), self.mm(alto or 1000))
        usado = self.p.boundingRect(caja, flags, texto)
        self.p.drawText(caja, flags, texto)
        return usado.height() / self.dpi * 25.4

    def linea(self, x0, y, x1, color=GRIS_CLARO, grosor=0.3):
        self.p.setPen(QPen(color, self.mm(grosor)))
        self.p.drawLine(QPointF(self.mm(x0), self.mm(y)), QPointF(self.mm(x1), self.mm(y)))

    def imagen(self, x, y, ancho, qimg):
        """Dibuja la imagen con ese ancho; devuelve el alto en mm."""
        alto = ancho * qimg.height() / qimg.width()
        self.p.drawImage(QRectF(self.mm(x), self.mm(y), self.mm(ancho), self.mm(alto)), qimg)
        return alto


def _fmt(v):
    return temp(v)


def _fmt_delta(v):
    return "" if v is None else temp(v, signo=True)


def _escritor(destino, titulo):
    writer = QPdfWriter(destino)
    writer.setResolution(200)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter))
    writer.setTitle(titulo)
    writer.setCreator("Thermal Studio")
    return writer


def generar_pdf(path, fotos, datos, ajustes, nombre_lugar=None):
    """fotos: lista de (ThermalImage, Mediciones). Caratula (una o mas paginas,
    con las observaciones y el resumen) y una pagina por foto.
    `nombre_lugar(path)` da el nombre visible de la carpeta."""
    lugar = nombre_lugar or (lambda ruta: fecha_visible(ruta.parent.name))

    # Borrador de la caratula, solo para saber cuantas paginas ocupa y poder
    # poner "Pagina n de N" en todas
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    borrador = _escritor(buffer, datos.titulo)
    p = QPainter(borrador)
    pg = _Pagina(borrador, p, datos)
    _caratula(pg, fotos, datos, lugar)
    paginas_caratula = pg.n
    p.end()

    writer = _escritor(str(path), datos.titulo)
    p = QPainter(writer)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    pg = _Pagina(writer, p, datos, total=paginas_caratula + len(fotos))
    _caratula(pg, fotos, datos, lugar)
    for img, ms in fotos:
        pg.nueva_pagina()
        _pagina_foto(pg, img, ms, datos, ajustes, lugar)
    pg.pie()
    p.end()


def _caratula(pg, fotos, datos, lugar):
    y = 20
    pg.fuente(9, True, ACENTO)
    pg.texto(0, y, pg.ancho_mm, tr("INFORME TERMOGRÁFICO"))
    y += 7
    pg.fuente(22, True)
    y += pg.texto(0, y, pg.ancho_mm, datos.titulo, envolver=True) + 4
    pg.fuente(11)
    for etiqueta_, valor in ((tr("Instalación"), datos.instalacion),
                             (tr("Inspector"), datos.inspector),
                             (tr("Fecha del informe"), fecha(datos.fecha)),
                             (tr("Fotos"), str(len(fotos)))):
        if not valor:
            continue
        pg.fuente(10, color=GRIS)
        pg.texto(0, y, 45, etiqueta_)
        pg.fuente(11)
        y += max(pg.texto(45, y, pg.ancho_mm - 45, valor, envolver=True), 6) + 1.5
    y += 8

    # Observaciones generales del inspector, por parrafos (pueden seguir en
    # la pagina siguiente)
    obs = [par.strip() for par in datos.observaciones.strip().split("\n") if par.strip()]
    if obs:
        pg.fuente(9, True, ACENTO)
        pg.texto(0, y, pg.ancho_mm, tr("OBSERVACIONES"))
        y += 7
        pg.fuente(10.5)
        for par in obs:
            alto = pg.alto_texto(pg.ancho_mm, par)
            if not pg.cabe(y, alto):
                pg.nueva_pagina()
                y = 0
                pg.fuente(10.5)
            y += pg.texto(0, y, pg.ancho_mm, par, envolver=True) + 2.5
        y += 6

    # Resumen: una fila por foto (puede seguir en la pagina siguiente)
    cols = [(0, tr("Fecha")), (32, tr("Lugar")), (100, tr("Máxima")), (125, tr("Mayor ΔT")), (152, tr("Mediciones"))]

    def encabezado(y, sigue=False):
        pg.fuente(9, True, ACENTO)
        pg.texto(0, y, pg.ancho_mm, tr("RESUMEN (continuación)") if sigue else tr("RESUMEN"))
        y += 7
        pg.fuente(8.5, True, GRIS)
        for x, t in cols:
            pg.texto(x, y, 40, t)
        y += 5.5
        pg.linea(0, y - 1, pg.ancho_mm, GRIS)
        return y

    if not pg.cabe(y, 25):
        pg.nueva_pagina()
        y = 0
    y = encabezado(y)
    for img, ms in fotos:
        if not pg.cabe(y, 6):
            pg.nueva_pagina()
            y = encabezado(0, sigue=True)
        filas = resultados(ms, img.temps)
        deltas = [r.delta_t for r in filas if r.delta_t is not None]
        mayor = max(deltas, key=abs) if deltas else None
        f = img.meta.fecha
        pg.fuente(9.5)
        pg.texto(cols[0][0], y, 32, fecha_hora(f) if f else "—")
        pg.texto(cols[1][0], y, 66, lugar(img.path) if img.path else "—")
        pg.texto(cols[2][0], y, 25, _fmt(img.maximo().temp))
        if mayor is not None and mayor >= 1.0:
            pg.fuente(9.5, True, AVISO)
        pg.texto(cols[3][0], y, 27, _fmt_delta(mayor) or "—")
        pg.fuente(9.5)
        pg.texto(cols[4][0], y, 30, str(len(filas)) if filas else "—")
        y += 6
        pg.linea(0, y - 1.2, pg.ancho_mm)
    y += 6
    nota = (tr("ΔT: máxima de cada medición menos la máxima de la medición de referencia de "
            "la misma foto. Temperaturas calculadas por Thermal Studio a partir de los "
            "datos radiométricos de la cámara: ±%s típico en el rango normal.")
            % temp(TempConverter.ERROR_TIPICO_C))
    pg.fuente(8, color=GRIS)
    if not pg.cabe(y, pg.alto_texto(pg.ancho_mm, nota)):
        pg.nueva_pagina()
        y = 0
        pg.fuente(8, color=GRIS)
    pg.texto(0, y, pg.ancho_mm, nota, envolver=True)


def _pagina_foto(pg, img, ms, datos, ajustes, lugar):
    y = 0
    f = img.meta.fecha
    pg.fuente(18, True)
    pg.texto(0, y, 120, fecha(f) if f else tr("Sin fecha"))
    pg.fuente(12, color=GRIS)
    pg.texto(48, y + 2.2, 40, f.strftime("%H:%M") if f else "")
    pg.fuente(10, color=GRIS)
    pg.texto(0, y + 9, pg.ancho_mm, "%s  ·  %s" % (lugar(img.path) if img.path else "",
                                                   img.path.name if img.path else ""))
    y += 17

    termica = imagen_anotada(img, ms, ajustes, escala=2)
    visible = QImage()
    con_visible = datos.incluir_visible and img.visible_jpeg and visible.loadFromData(
        img.visible_jpeg)
    if con_visible:
        ancho_t = pg.ancho_mm * 0.64
        alto = pg.imagen(0, y, ancho_t, termica)
        ancho_v = pg.ancho_mm - ancho_t - 4
        visible = visible.scaledToWidth(1000, Qt.SmoothTransformation)
        pg.imagen(ancho_t + 4, y, ancho_v, visible)
        pg.fuente(8, color=GRIS)
        pg.texto(ancho_t + 4, y + ancho_v * visible.height() / visible.width() + 1, ancho_v,
                 tr("Foto visible"))
    else:
        alto = pg.imagen(0, y, pg.ancho_mm * 0.8, termica)
    y += alto + 6

    # Datos generales
    mx, mn = img.maximo(), img.minimo()
    pg.fuente(9, True, ACENTO)
    pg.texto(0, y, 80, tr("TEMPERATURAS"))
    pg.texto(95, y, 80, tr("PARÁMETROS DE CAPTURA"))
    y0 = y + 6
    m = img.meta
    filas_izq = ((tr("Máxima"), _fmt(mx.temp)), (tr("Mínima"), _fmt(mn.temp)),
                 (tr("Centro"), _fmt(img.centro().temp)))
    filas_der = ((tr("Emisividad"), num(m.emisividad, 2) if m.emisividad is not None else "—"),
                 (tr("T. reflejada"), _fmt(m.temp_reflejada)), (tr("Distancia"),
                  num(m.distancia_m) + " m" if m.distancia_m is not None else "—"),
                 (tr("Humedad"), "%s %%" % m.humedad if m.humedad is not None else "—"))
    for i, (a, b) in enumerate(filas_izq):
        pg.fuente(9.5, color=GRIS)
        pg.texto(0, y0 + i * 5.2, 30, a)
        pg.fuente(9.5, True)
        pg.texto(30, y0 + i * 5.2, 40, b)
    for i, (a, b) in enumerate(filas_der):
        pg.fuente(9.5, color=GRIS)
        pg.texto(95, y0 + i * 5.2, 30, a)
        pg.fuente(9.5)
        pg.texto(125, y0 + i * 5.2, 50, b)
    y = y0 + 4 * 5.2 + 5

    # Mediciones
    filas = resultados(ms, img.temps)
    if filas:
        pg.fuente(9, True, ACENTO)
        pg.texto(0, y, 80, tr("MEDICIONES"))
        y += 6
        cols = [(0, tr("Medición")), (55, tr("Tipo")), (78, tr("Máxima")), (102, tr("Mínima")),
                (126, tr("Media")), (150, tr("ΔT"))]
        pg.fuente(8.5, True, GRIS)
        for x, t in cols:
            pg.texto(x, y, 40, t)
        y += 5.5
        pg.linea(0, y - 1, pg.ancho_mm, GRIS)
        for r in filas:
            if y > pg.alto_mm - 35:
                break
            pg.fuente(9.5, r.es_referencia)
            pg.texto(0, y, 54, ("★ " if r.es_referencia else "") + r.nombre)
            pg.fuente(9.5)
            pg.texto(55, y, 22, NOMBRES_TIPO[r.tipo])
            pg.texto(78, y, 24, _fmt(r.maxima))
            pg.texto(102, y, 24, _fmt(r.minima))
            pg.texto(126, y, 24, _fmt(r.media))
            if r.es_referencia:
                pg.fuente(9.5, color=GRIS)
                pg.texto(150, y, 30, tr("referencia"))
            else:
                if r.delta_t is not None and r.delta_t >= 1.0:
                    pg.fuente(9.5, True, AVISO)
                pg.texto(150, y, 30, _fmt_delta(r.delta_t) or "—")
            y += 5.5
            pg.linea(0, y - 1.2, pg.ancho_mm)
        y += 4

    if ms.notas.strip():
        pg.fuente(9, True, ACENTO)
        pg.texto(0, y, 80, tr("NOTAS"))
        y += 6
        pg.fuente(10)
        pg.texto(0, y, pg.ancho_mm, ms.notas.strip(), alto=pg.alto_mm - 12 - y, envolver=True)

    if img.rango_alto or img.fuera_de_rango:
        pg.fuente(8, color=AVISO)
        pg.texto(0, pg.alto_mm - 14, pg.ancho_mm,
                 tr("Atención: foto en el rango alto de la cámara, sin calibrar; las temperaturas "
                 "no son confiables.") if img.rango_alto else
                 tr("Hay zonas fuera del rango calibrado (%d a %d °C): sus valores son aproximados.")
                 % TempConverter.RANGO_VALIDADO_C, envolver=True)
