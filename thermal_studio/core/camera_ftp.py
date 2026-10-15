"""Descarga de fotos desde la camara por WiFi (servidor FTP de la UTi760x).

La camara crea un punto de acceso WiFi y sirve un FTP en 192.168.32.1:2121,
usuario/clave de fabrica admin/admin. Carpetas:

    /pic            IMG<AAAAMMDDhhmmss>HD.jpg  fotos radiometricas (~4 MB)
    /pic_thumbnail  IMG + mismo nombre          miniaturas
    /video          VIDEO<fecha>.mp4
"""
import ftplib
import socket
from dataclasses import dataclass
from pathlib import Path

HOST = "192.168.32.1"
PUERTO = 2121
USUARIO = "admin"
CLAVE = "admin"
CARPETA_FOTOS = "/pic"


class ErrorCamara(Exception):
    """Fallo de conexion o de transferencia; el mensaje es para el usuario."""


class Cancelado(Exception):
    pass


@dataclass(frozen=True)
class ArchivoCamara:
    nombre: str
    tamano: int


def _parsear_list(linea):
    """'-rw------- 1 user group 4236075 Jun 11 22:13 IMG....jpg' -> ArchivoCamara."""
    partes = linea.split(None, 8)
    if len(partes) < 9 or not partes[0].startswith("-"):
        return None
    try:
        return ArchivoCamara(partes[8], int(partes[4]))
    except ValueError:
        return None


class CameraFTP:
    def __init__(self, host=HOST, puerto=PUERTO, usuario=USUARIO, clave=CLAVE, timeout=10):
        self.host, self.puerto = host, int(puerto)
        self.usuario, self.clave = usuario, clave
        self.timeout = timeout
        self.ftp = None

    def __enter__(self):
        self.conectar()
        return self

    def __exit__(self, *exc):
        self.cerrar()

    def conectar(self):
        ftp = ftplib.FTP(timeout=self.timeout)
        try:
            ftp.connect(self.host, self.puerto)
        except (OSError, socket.timeout) as e:
            raise ErrorCamara(
                "No se encontró la cámara en %s:%d.\n\nRevisá que la PC esté conectada al "
                "WiFi de la cámara y que el FTP esté activado en la cámara." % (self.host, self.puerto)
            ) from e
        try:
            ftp.login(self.usuario, self.clave)
        except ftplib.error_perm as e:
            ftp.close()
            raise ErrorCamara("La cámara rechazó el usuario o la contraseña del FTP.") from e
        ftp.voidcmd("TYPE I")
        self.ftp = ftp

    def cerrar(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except (OSError, ftplib.Error):
                self.ftp.close()
            self.ftp = None

    def listar_fotos(self):
        """Fotos .jpg de la camara, ordenadas por nombre (= por fecha de toma)."""
        lineas = []
        try:
            self.ftp.retrlines("LIST %s" % CARPETA_FOTOS, lineas.append)
        except (OSError, ftplib.Error) as e:
            raise ErrorCamara("No se pudo leer la lista de fotos de la cámara: %s" % e) from e
        archivos = (_parsear_list(l) for l in lineas)
        return sorted((a for a in archivos if a and a.nombre.lower().endswith(".jpg")),
                      key=lambda a: a.nombre)

    def descargar(self, archivo, destino, progreso=None, cancelado=None):
        """Descarga `archivo` a la ruta `destino`.

        Escribe en un .parcial y renombra al terminar, para que un corte a
        mitad de camino nunca deje una foto rota en la biblioteca.
        progreso(bytes_recibidos) se llama por cada bloque; si cancelado()
        devuelve True se aborta con Cancelado.
        """
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        parcial = destino.with_name(destino.name + ".parcial")
        recibido = 0
        try:
            with open(parcial, "wb") as f:
                def bloque(data):
                    nonlocal recibido
                    if cancelado and cancelado():
                        raise Cancelado()
                    f.write(data)
                    recibido += len(data)
                    if progreso:
                        progreso(recibido)
                self.ftp.retrbinary("RETR %s/%s" % (CARPETA_FOTOS, archivo.nombre),
                                    bloque, blocksize=64 * 1024)
            if recibido != archivo.tamano:
                raise ErrorCamara("La descarga de %s quedó incompleta (%d de %d bytes)."
                                  % (archivo.nombre, recibido, archivo.tamano))
            parcial.replace(destino)
        except Cancelado:
            parcial.unlink(missing_ok=True)
            # La transferencia quedo a medias: la conexion ya no sirve
            self.ftp.close()
            self.ftp = None
            raise
        except (OSError, ftplib.Error) as e:
            parcial.unlink(missing_ok=True)
            raise ErrorCamara("Falló la descarga de %s: %s" % (archivo.nombre, e)) from e
        except BaseException:
            parcial.unlink(missing_ok=True)
            raise
