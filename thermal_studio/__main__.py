"""Arranque: python -m thermal_studio [imagen.jpg]"""
import sys


def main():
    from pathlib import Path

    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .ui import theme
    from .ui.main_window import APP_NOMBRE, MainWindow

    if sys.platform == "win32":
        # Para que Windows muestre el icono propio en la barra de tareas
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ThermalStudio.App")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NOMBRE)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "ui" / "assets" / "icono.png")))
    app.setStyle("Fusion")
    # El tema va antes de crear la ventana, para que nazca con los colores correctos
    theme.aplicar(app, QSettings("ThermalStudio", "ThermalStudio").value("tema", theme.OSCURO))
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.abrir(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
