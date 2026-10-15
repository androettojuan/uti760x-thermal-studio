"""Miniaturas de la galeria, generadas en segundo plano y cacheadas en disco.

Se usa el JPEG que la camara guarda al principio del archivo (el render con
paleta y overlay, tal cual se vio en pantalla), que es mucho mas rapido que
decodificar los datos radiometricos.
"""
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage

TAMANO = 160


def _ruta_cache(carpeta_cache, foto):
    st = foto.stat()
    return Path(carpeta_cache) / ("%s_%d.jpg" % (foto.stem, st.st_size))


def _generar(foto, destino):
    datos = foto.read_bytes()
    fin = datos.rfind(b"\xff\xd9")
    img = QImage()
    if fin < 0 or not img.loadFromData(datos[:fin + 2]):
        return None
    img = img.scaled(TAMANO, TAMANO, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    img.save(str(destino), "JPG", 85)
    return img


class _Senales(QObject):
    lista = Signal(str, QImage)  # ruta de la foto, miniatura


class _Tarea(QRunnable):
    def __init__(self, foto, cache, senales):
        super().__init__()
        self.foto, self.cache, self.senales = foto, cache, senales

    def run(self):
        try:
            destino = _ruta_cache(self.cache, self.foto)
            img = QImage(str(destino)) if destino.exists() else QImage()
            if img.isNull():
                img = _generar(self.foto, destino)
        except OSError:
            img = None
        if img is not None and not img.isNull():
            self.senales.lista.emit(str(self.foto), img)


class CargadorMiniaturas(QObject):
    """pedir(foto) -> emite `lista(ruta, QImage)` cuando la miniatura esta."""

    lista = Signal(str, QImage)

    def __init__(self, carpeta_cache, parent=None):
        super().__init__(parent)
        self.cache = Path(carpeta_cache)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self._senales = _Senales()
        self._senales.lista.connect(self.lista)

    def set_cache(self, carpeta_cache):
        self.cache = Path(carpeta_cache)

    def cancelar_pendientes(self):
        self.pool.clear()

    def pedir(self, foto):
        self.pool.start(_Tarea(Path(foto), self.cache, self._senales))
