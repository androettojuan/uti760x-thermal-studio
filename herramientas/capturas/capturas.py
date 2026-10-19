"""Capturas del programa para el README (docs/capturas/).

Arma una biblioteca de demostracion en una carpeta temporal (con nombres
genericos, no los de la biblioteca real), le carga mediciones y saca las
capturas sin mostrar ninguna ventana. Correr desde la raiz del repo:

    PYTHONPATH=. .venv/bin/python herramientas/capturas/capturas.py [carpeta con las fotos]

Por defecto busca las fotos en Documentos/Termografías. Si el programa cambia
algo que se ve, volver a correrlo y actualizar el README.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "docs" / "capturas"
TAMANO = (1600, 940)

# Fotos de la demo (todas del 15/10/2026, sin GPS en la imagen)
PRINCIPAL = "IMG20261015230357HD.jpg"           # empalme a 81 C
COMPARAR = ("IMG20261015231005HD.jpg", "IMG20261015231010HD.jpg")
RELLENO = ["IMG20261015225351HD.jpg", "IMG20261015225601HD.jpg", "IMG20261015225641HD.jpg",
           "IMG20261015225713HD.jpg", "IMG20261015230302HD.jpg", "IMG20261015230651HD.jpg",
           "IMG20261015230704HD.jpg", "IMG20261015230727HD.jpg", "IMG20261015231214HD.jpg"]
# Textos de la demo en cada idioma (no son del programa: no van en los catalogos)
TEXTOS = {
    "es": dict(linea="Línea Norte", poste="Poste 231", sur="Subestación Sur",
               trafo="Transformador T1", empalme="Empalme", cable="Cable",
               notas="Empalme recalentado: revisar el ajuste y reemplazar el conector.",
               obs="Empalme recalentado en el poste de la derivación: programar el "
                   "cambio del conector.",
               seccionador="Seccionador", cruceta="Cruceta", poste_ref="Poste"),
    "en": dict(linea="North Line", poste="Pole 231", sur="South Substation",
               trafo="Transformer T1", empalme="Splice", cable="Cable",
               notas="Overheated splice: check the tightening and replace the connector.",
               obs="Overheated splice on the branch pole: schedule the connector "
                   "replacement.",
               seccionador="Disconnector", cruceta="Crossarm", poste_ref="Pole"),
}
T = TEXTOS["es"]


def _lugar():
    return "%s/%s" % (T["linea"], T["poste"])


def _buscar(origen, nombre):
    for p in Path(origen).rglob(nombre):
        if ".thermal_studio" not in p.parts:
            return p
    raise SystemExit("No encuentro %s en %s" % (nombre, origen))


def _biblioteca(origen, destino):
    imp = destino / "Importadas" / "2026-10-15"
    imp.mkdir(parents=True)
    for n in [PRINCIPAL] + RELLENO:
        shutil.copy2(_buscar(origen, n), imp)
    lugar = destino / _lugar()
    lugar.mkdir(parents=True)
    for n in COMPARAR:
        shutil.copy2(_buscar(origen, n), lugar)
    (destino / T["sur"] / T["trafo"]).mkdir(parents=True)


def _mediciones(bib):
    from thermal_studio.core.mediciones import AREA, LINEA, PUNTO, Mediciones

    ms = Mediciones()
    empalme = ms.agregar(AREA, [376, 228, 406, 256])
    ms.renombrar(empalme.nombre, T["empalme"])
    cable = ms.agregar(AREA, [250, 300, 330, 330])
    ms.renombrar(cable.nombre, T["cable"])
    ms.agregar(LINEA, [215, 120, 215, 400])  # a lo largo del poste
    ms.agregar(PUNTO, [120, 300])
    ms.referencia = T["cable"]
    ms.notas = T["notas"]
    bib.guardar_mediciones(PRINCIPAL, ms)

    # Las mismas mediciones (mismo nombre) en las dos fotos del poste, para cruzarlas
    nombres = (T["seccionador"], T["cruceta"], T["poste_ref"])
    for foto, cajas in ((COMPARAR[0], ([170, 180, 260, 250], [200, 335, 280, 370],
                                       [300, 420, 370, 480])),
                        (COMPARAR[1], ([185, 185, 270, 255], [200, 360, 280, 392],
                                       [300, 430, 380, 490]))):
        ms = Mediciones()
        for nombre, caja in zip(nombres, cajas):
            m = ms.agregar(AREA, caja)
            ms.renombrar(m.nombre, nombre)
        ms.referencia = T["poste_ref"]
        bib.guardar_mediciones(foto, ms)


def _esperar(app, segundos):
    from PySide6.QtCore import QDeadlineTimer, QEventLoop
    fin = QDeadlineTimer(int(segundos * 1000))
    while not fin.hasExpired():
        app.processEvents(QEventLoop.AllEvents, 50)


def _pdf_a_png(pdf, salida, paginas):
    """Paginas del PDF lado a lado, como una sola imagen."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    doc.load(str(pdf))
    imgs = []
    for i in paginas:
        tam = doc.pagePointSize(i)
        escala = 820 / tam.height()
        imgs.append(doc.render(i, QSize(int(tam.width() * escala), int(tam.height() * escala))))
    margen = 24
    total = QImage(sum(i.width() for i in imgs) + margen * (len(imgs) + 1),
                   max(i.height() for i in imgs) + 2 * margen, QImage.Format_RGB32)
    total.fill(QColor("#2b2f36"))
    p = QPainter(total)
    x = margen
    for im in imgs:
        # El PDF no tiene fondo: la hoja es blanca
        p.fillRect(x, margen, im.width(), im.height(), QColor("white"))
        p.drawImage(x, margen, im)
        x += im.width() + margen
    p.end()
    total.save(str(salida))


def capturar(origen, idioma):
    tmp = Path(tempfile.mkdtemp(prefix="capturas-"))
    # Configuracion propia: no tocar la del programa instalado
    os.environ["XDG_CONFIG_HOME"] = str(tmp / "config")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QLocale, QSettings
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from thermal_studio import i18n
    i18n.set_idioma(idioma)
    T.update(TEXTOS[idioma])
    QLocale.setDefault(QLocale({"es": "es_AR", "en": "en_US", "pt": "pt_BR"}[idioma]))
    from thermal_studio.core.library import Library

    bib_dir = tmp / "Termografias"
    _biblioteca(origen, bib_dir)
    _mediciones(Library(bib_dir))
    QSettings("ThermalStudio", "ThermalStudio").setValue("biblioteca", str(bib_dir))

    app = QApplication([])
    # La fuente de Windows, para que se vea como en Windows
    for f in Path("/mnt/c/Windows/Fonts").glob("segoeui*.ttf"):
        QFontDatabase.addApplicationFont(str(f))
    from thermal_studio.__main__ import _traducir_qt
    from thermal_studio.ui import theme
    from thermal_studio.ui.informe import DatosInforme, generar_pdf
    from thermal_studio.ui.main_window import MainWindow
    _traducir_qt(app, idioma)
    app.setStyle("Fusion")
    theme.aplicar(app, theme.OSCURO)

    sufijo = "" if idioma == "es" else "-" + idioma
    SALIDA.mkdir(parents=True, exist_ok=True)
    w = MainWindow()
    w.resize(*TAMANO)
    w.show()
    w.split.setSizes([360, 920, 320])
    w.panel_bib.seleccionar_carpeta("Importadas/2026-10-15", forzar=True)
    principal = bib_dir / "Importadas" / "2026-10-15" / PRINCIPAL
    w.abrir(principal)
    w.panel.mediciones.elegir(T["empalme"])
    w.capa.elegir(T["empalme"])
    _esperar(app, 3)  # miniaturas
    w.statusBar().clearMessage()  # mostraria la ruta temporal
    w.grab().save(str(SALIDA / ("principal%s.png" % sufijo)))
    if idioma != "es":
        return

    lugar = bib_dir / _lugar()
    w.panel_bib.seleccionar_carpeta(_lugar(), forzar=True)
    w.comparar([lugar / n for n in COMPARAR])
    _esperar(app, 2)
    w.statusBar().clearMessage()
    w.grab().save(str(SALIDA / "comparacion.png"))

    from thermal_studio.core.thermal_image import ThermalImage
    lib = Library(bib_dir)
    datos = DatosInforme(instalacion=T["linea"], inspector="Juan Manuel Androetto",
                         observaciones=T["obs"])
    pdf = tmp / "informe.pdf"
    fotos = [(ThermalImage.abrir(principal), lib.leer_mediciones(PRINCIPAL))]
    generar_pdf(pdf, fotos, datos, w._ajustes_imagen(), w._nombre_lugar)
    _pdf_a_png(pdf, SALIDA / "informe.png", [0, 1])
    w.close()


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] in ("es", "en", "pt"):
        capturar(sys.argv[1], sys.argv[2])
    else:
        origen = sys.argv[1] if len(sys.argv) > 1 else "/mnt/c/Users/Usuario/Documents/Termografías"
        # Un proceso por idioma: los textos se arman al importar la interfaz
        for idioma in ("es", "en"):
            subprocess.run([sys.executable, __file__, origen, idioma], check=True,
                           env=dict(os.environ, PYTHONPATH=str(RAIZ)))
        print("Capturas en", SALIDA)
