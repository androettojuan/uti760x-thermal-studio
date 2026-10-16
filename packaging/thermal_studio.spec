# PyInstaller: genera dist/ThermalStudio/ (carpeta con el .exe y sus dependencias).
#   pyinstaller packaging/thermal_studio.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))  # SPECPATH lo define PyInstaller
sys.path.insert(0, RAIZ)  # para que collect_data_files encuentre el paquete

datos = collect_data_files("thermal_studio") + collect_data_files("qtawesome")
# Textos propios de Qt (botones Sí/No, Cancelar, menús de los campos de texto)
datos += collect_data_files("PySide6", includes=["Qt/translations/qtbase_es.qm",
                                                 "Qt/translations/qtbase_pt_BR.qm"])

a = Analysis(
    [os.path.join(SPECPATH, "lanzador.py")],
    pathex=[RAIZ],
    datas=datos,
    # Modulos de Qt que la app no usa: achican bastante el instalador
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia",
              "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
              "PySide6.QtSerialPort", "PySide6.QtWebSockets", "PySide6.QtNetworkAuth",
              "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ThermalStudio",
    icon=os.path.join(SPECPATH, "icono.ico"),
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ThermalStudio")
