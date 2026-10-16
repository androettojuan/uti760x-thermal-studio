"""Menu Ayuda: guia rapida y Acerca de (con la licencia)."""
import sys
from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from .. import __version__
from ..core.uti760x import TempConverter
from . import theme
from ..i18n import temp, tr

REPO = "https://github.com/androettojuan/uti760x-thermal-studio"

GUIA = tr("""
<h2>Guía rápida</h2>

<h3>1. Traer las fotos de la cámara</h3>
<ol>
<li>En la cámara, <b>pasá las fotos a la carpeta FTP</b>: el programa solo ve las que
están ahí.</li>
<li>Activá el WiFi y el FTP de la cámara y conectá la PC a su red (por ejemplo
«termica»). El botón <b>Conectar</b> del panel izquierdo lo hace por vos.</li>
<li>Cuando diga <i>Conectada</i>, tocá <b>Traer faltantes</b>: baja solo las fotos nuevas
a <i>Termografías › Importadas › fecha</i>.</li>
</ol>
<p>Si dice que la cámara no le dio dirección a la PC, tocá <b>Reconectar</b> (o desconectá
y volvé a conectar el WiFi).</p>

<h3>2. Organizar: una carpeta por lugar</h3>
<p>Creá una carpeta por equipo o instalación (por ejemplo <i>Subestación Norte › Tablero
A</i>) y arrastrá ahí las fotos de cada ronda. La comparación y la evolución usan la
carpeta como «lugar».</p>

<h3>3. Ver y medir</h3>
<ul>
<li><b>Paleta</b> y <b>Contraste</b>: «Como la cámara» reparte los colores para ver
detalles; «Lineal», para comparar fotos con la misma escala. Las temperaturas no
cambian.</li>
<li><b>Auto</b> ajusta el rango a la imagen sin el cielo; el candado lo mantiene al
cambiar de foto.</li>
<li>Herramientas de la barra: <b>punto (P)</b>, <b>línea (L)</b> con perfil de
temperatura y <b>área (R)</b>. <b>Esc</b> vuelve a mover y elegir.</li>
<li>En la tabla de mediciones, marcá una como <b>Referencia (★)</b>: el <b>ΔT</b> de las
demás es cuánto más calientes están que ella. Es lo que menos cambia entre verano e
invierno, así que conviene para detectar problemas.</li>
<li>Doble clic en el nombre para cambiarlo. Usá <b>los mismos nombres en cada ronda</b>
(«Fase R», «Fase S»…): así se siguen en el tiempo.</li>
<li>Las <b>notas</b> del panel derecho se guardan solas y salen en el informe.</li>
</ul>

<h3>4. Seguir un lugar en el tiempo</h3>
<ul>
<li><b>Comparar (C)</b>: la foto abierta al lado de otra del mismo lugar, con la misma
escala, la fecha grande y las mediciones de igual nombre cruzadas.</li>
<li><b>Evolución (E)</b>, junto al título de la galería: gráfico de la máxima y del ΔT
de cada medición en todas las fotos de la carpeta.</li>
</ul>

<h3>5. Informe y exportación</h3>
<ul>
<li><b>Informe (Ctrl+P)</b>: PDF con carátula y una página por foto (térmica con
mediciones, foto visible, tabla con ΔT y notas).</li>
<li><b>Archivo › Exportar</b>: imagen con mediciones (PNG), mediciones o todas las
temperaturas (CSV para Excel).</li>
</ul>

<h3>Atajos</h3>
<table cellspacing="4">
<tr><td><b>← →</b></td><td>Foto anterior / siguiente</td></tr>
<tr><td><b>A</b></td><td>Rango automático</td></tr>
<tr><td><b>P · L · R</b></td><td>Medir punto · línea · área</td></tr>
<tr><td><b>Supr</b></td><td>Borrar la medición elegida</td></tr>
<tr><td><b>C · E</b></td><td>Comparar · Evolución de la carpeta</td></tr>
<tr><td><b>V</b></td><td>Foto visible en grande</td></tr>
<tr><td><b>Esc</b></td><td>Soltar la herramienta o volver a la foto</td></tr>
<tr><td><b>Ctrl+1 · Ctrl+2</b></td><td>Mostrar u ocultar la biblioteca · los datos</td></tr>
<tr><td><b>Ctrl+P</b></td><td>Crear informe PDF</td></tr>
</table>

<h3>Precisión</h3>
<p>Las temperaturas se calculan con los datos radiométricos de cada foto: ±%(tipico)s
típico entre %(lo)d y %(hi)d °C, comparado con lo que muestra la cámara. Las fotos sacadas
en el rango alto de la cámara todavía no están calibradas y lo avisan.</p>
""")


def _licencia():
    """Texto de LICENSE: al lado del .exe instalado, o en la raiz del repo."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else \
        Path(__file__).resolve().parents[2]
    for p in (base / "LICENSE", base / "_internal" / "LICENSE"):
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            continue
    return tr("MIT License — Copyright (c) 2026 Juan Manuel Androetto. Ver %s") % REPO


def _dialogo(parent, titulo, html, ancho=640, alto=640):
    d = QDialog(parent)
    d.setWindowTitle(titulo)
    d.resize(ancho, alto)
    v = QVBoxLayout(d)
    t = QTextBrowser()
    t.setOpenExternalLinks(True)
    acento = theme.color("acento")
    t.setHtml("<style>h2{color:%s} h3{margin-top:14px} a{color:%s}</style>%s"
              % (acento, acento, html))
    v.addWidget(t)
    b = QDialogButtonBox(QDialogButtonBox.Close)
    b.button(QDialogButtonBox.Close).setText(tr("Cerrar"))
    b.rejected.connect(d.reject)
    v.addWidget(b)
    return d


def mostrar_guia(parent):
    lo, hi = TempConverter.RANGO_VALIDADO_C
    _dialogo(parent, tr("Guía rápida"), GUIA % {"tipico": temp(TempConverter.ERROR_TIPICO_C),
                                             "lo": lo, "hi": hi}).exec()


def mostrar_acerca_de(parent):
    lic = _licencia().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = tr("""
<h2>Thermal Studio %(v)s</h2>
<p>Análisis de imágenes termográficas de la cámara UNI-T UTi760x: importación por WiFi,
mediciones, comparación en el tiempo e informes.</p>
<p>Juan Manuel Androetto · <a href="%(repo)s">%(repo)s</a></p>
<h3>Licencia</h3>
<pre style="font-size:11px; white-space:pre-wrap">%(lic)s</pre>
""") % {"v": __version__, "repo": REPO, "lic": lic}
    _dialogo(parent, tr("Acerca de Thermal Studio"), html, 600, 560).exec()
