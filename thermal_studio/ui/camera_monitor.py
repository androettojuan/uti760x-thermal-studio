"""Vigila si la camara esta al alcance y cuantas fotos nuevas tiene.

Cada pocos segundos, en un hilo aparte: prueba si el FTP de la camara acepta
conexiones y averigua a que red WiFi esta conectada la PC. Cuando la camara
aparece, lista sus fotos para contar las que faltan importar.
"""
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from ..core import importer
from ..core.camera_ftp import CameraFTP, ErrorCamara, camara_disponible
from ..core.importer import Modo
from . import sistema

INTERVALO_MS = 4000
INTERVALO_RAPIDO_MS = 1500  # mientras se esta conectando


@dataclass
class Estado:
    conectada: bool
    wifi: str | None            # red a la que esta conectada la PC
    nuevas: int | None = None   # fotos sin importar; None = todavia no se sabe
    en_camara: int | None = None


def _emitir(senal, *args):
    """Emite ignorando el caso de que la app ya se haya cerrado."""
    try:
        senal.emit(*args)
    except RuntimeError:
        pass


class _Relay(QObject):
    sondeo = Signal(bool, object)   # conectada, wifi
    conteo = Signal(int, int)       # nuevas, en camara
    conexion = Signal(bool, str)    # resultado de pedir conectar el WiFi


class _ConectarWifi(QRunnable):
    def __init__(self, ssid, relay):
        super().__init__()
        self.ssid, self.relay = ssid, relay

    def run(self):
        _emitir(self.relay.conexion, *sistema.conectar_wifi(self.ssid))


class _Sondeo(QRunnable):
    def __init__(self, conexion, relay):
        super().__init__()
        self.conexion, self.relay = conexion, relay

    def run(self):
        ok = camara_disponible(self.conexion["host"], self.conexion["puerto"])
        _emitir(self.relay.sondeo, ok, sistema.wifi_actual())


class _Conteo(QRunnable):
    def __init__(self, conexion, biblioteca, relay):
        super().__init__()
        self.conexion, self.biblioteca, self.relay = conexion, biblioteca, relay

    def run(self):
        try:
            with CameraFTP(**self.conexion) as cam:
                archivos = cam.listar_fotos()
        except (ErrorCamara, OSError):
            return
        plan = importer.planificar(archivos, self.biblioteca, Modo.FALTANTES)
        _emitir(self.relay.conteo, len(plan.a_descargar), len(archivos))


class MonitorCamara(QObject):
    cambiado = Signal(object)           # Estado
    conexionPedida = Signal(bool, str)  # ok, mensaje del sistema

    def __init__(self, conexion, biblioteca, parent=None):
        super().__init__(parent)
        self.conexion = conexion      # callable -> dict
        self.biblioteca = biblioteca  # callable -> Library
        self.estado = Estado(False, None)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._relay = _Relay()
        self._relay.sondeo.connect(self._sondeado)
        self._relay.conteo.connect(self._contado)
        self._relay.conexion.connect(self.conexionPedida)
        self._ocupado = False
        self._pausado = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.sondear)

    def iniciar(self):
        self.sondear()
        self._timer.start(INTERVALO_MS)

    def detener(self):
        """Al cerrar la app: no lanzar mas sondeos y esperar los que estan en curso."""
        self._timer.stop()
        self._pausado = True
        self._pool.clear()
        self._pool.waitForDone(5000)

    def pausar(self, pausado):
        """Se pausa durante la importacion, para no competir por la conexion."""
        self._pausado = pausado

    def acelerar(self):
        """Sondear mas seguido un rato (despues de pedir conectar el WiFi)."""
        self._timer.start(INTERVALO_RAPIDO_MS)
        QTimer.singleShot(30000, lambda: self._timer.start(INTERVALO_MS))
        self.sondear()

    def conectar_wifi(self, ssid):
        """Pide al sistema conectarse a la red de la camara (ya guardada)."""
        self._pool.start(_ConectarWifi(ssid, self._relay))
        self.acelerar()

    def sondear(self):
        if self._ocupado or self._pausado:
            return
        self._ocupado = True
        self._pool.start(_Sondeo(self.conexion(), self._relay))

    def recontar(self):
        """Vuelve a contar las fotos nuevas (por ejemplo, despues de importar)."""
        if self.estado.conectada:
            self._pool.start(_Conteo(self.conexion(), self.biblioteca(), self._relay))

    def _sondeado(self, conectada, wifi):
        self._ocupado = False
        antes = self.estado
        if conectada and not antes.conectada:
            self._timer.start(INTERVALO_MS)
            self.estado = Estado(True, wifi)
            self.recontar()
        elif conectada:
            self.estado = Estado(True, wifi, antes.nuevas, antes.en_camara)
        else:
            self.estado = Estado(False, wifi)
        if self.estado != antes:
            self.cambiado.emit(self.estado)

    def _contado(self, nuevas, en_camara):
        if self.estado.conectada:
            self.estado = Estado(True, self.estado.wifi, nuevas, en_camara)
            self.cambiado.emit(self.estado)
