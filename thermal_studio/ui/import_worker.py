"""Importacion desde la camara en un hilo aparte, en dos pasos.

1. HiloPlan: conecta, lista las fotos y arma el plan (rapido).
2. HiloDescarga: descarga lo planificado, informando el progreso.

Entre uno y otro la ventana puede pedir confirmacion al usuario.
"""
import time

from PySide6.QtCore import QThread, Signal

from ..core import importer
from ..core.camera_ftp import CameraFTP, Cancelado, ErrorCamara


class HiloPlan(QThread):
    listo = Signal(object, int)  # Plan, fotos en la camara
    error = Signal(str)

    def __init__(self, conexion, biblioteca, modo, parent=None):
        super().__init__(parent)
        self.conexion, self.biblioteca, self.modo = conexion, biblioteca, modo

    def run(self):
        try:
            with CameraFTP(**self.conexion) as cam:
                archivos = cam.listar_fotos()
            self.listo.emit(importer.planificar(archivos, self.biblioteca, self.modo),
                            len(archivos))
        except ErrorCamara as e:
            self.error.emit(str(e))
        except OSError as e:
            self.error.emit("Error al preparar la importación: %s" % e)


class HiloDescarga(QThread):
    # indice, total, nombre, bytes acumulados, bytes totales, bytes/segundo
    progreso = Signal(int, int, str, int, int, float)
    terminado = Signal(list, bool, str)  # rutas bajadas, cancelado, error ("" si ok)

    def __init__(self, conexion, biblioteca, plan, parent=None):
        super().__init__(parent)
        self.conexion, self.biblioteca, self.plan = conexion, biblioteca, plan
        self._cancelar = False
        self._hechas = []

    def cancelar(self):
        self._cancelar = True

    def run(self):
        inicio = time.monotonic()
        total_bytes = self.plan.bytes_totales
        ultimo = 0.0

        def progreso(i, total, archivo, _bytes_archivo, acumulado):
            nonlocal ultimo
            ahora = time.monotonic()
            if ahora - ultimo < 0.1 and acumulado < total_bytes:
                return  # no saturar la interfaz
            ultimo = ahora
            vel = acumulado / max(ahora - inicio, 1e-3)
            self.progreso.emit(i, total, archivo.nombre, acumulado, total_bytes, vel)

        cancelado, error = False, ""
        try:
            with CameraFTP(**self.conexion) as cam:
                importer.ejecutar(self.plan, cam, self.biblioteca, progreso=progreso,
                                  cancelado=lambda: self._cancelar, hechas=self._hechas)
        except Cancelado:
            cancelado = True
        except ErrorCamara as e:
            error = str(e)
        except OSError as e:
            error = "Error al guardar las fotos: %s" % e
        self.terminado.emit(self._hechas, cancelado, error)
