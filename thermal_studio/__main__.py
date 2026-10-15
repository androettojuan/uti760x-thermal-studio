"""Arranque: python -m thermal_studio [imagen.jpg]"""
import sys


def main():
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import APP_NOMBRE, MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NOMBRE)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:
        win.abrir(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
