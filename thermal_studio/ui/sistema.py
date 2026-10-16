"""Integracion con el sistema operativo: carpeta Documentos, Explorador y WiFi.

Contempla correr en Windows directo o en WSL (desarrollo), donde las rutas de
Windows se ven como /mnt/c/... y el Explorador es explorer.exe.
"""
import os
import platform
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices

NOMBRE_BIBLIOTECA = "Termografías"


@lru_cache(maxsize=None)
def es_wsl():
    return sys.platform.startswith("linux") and "microsoft" in platform.uname().release.lower()


def _wslpath(arg, ruta):
    return subprocess.run(["wslpath", arg, str(ruta)], capture_output=True, text=True,
                          check=True, timeout=10).stdout.strip()


@lru_cache(maxsize=None)
def documentos():
    if es_wsl():
        try:
            win = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 "[Environment]::GetFolderPath('MyDocuments')"],
                capture_output=True, text=True, check=True, timeout=20).stdout.strip()
            if win:
                return Path(_wslpath("-u", win))
        except (OSError, subprocess.SubprocessError):
            pass
    loc = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return Path(loc) if loc else Path.home() / "Documents"


def biblioteca_por_defecto():
    return documentos() / NOMBRE_BIBLIOTECA


def mostrar_en_explorador(ruta):
    """Abre el Explorador en la carpeta (o con el archivo seleccionado)."""
    ruta = Path(ruta)
    if es_wsl() or sys.platform == "win32":
        win = _wslpath("-w", ruta) if es_wsl() else str(ruta)
        args = ["explorer.exe", "/select,", win] if ruta.is_file() else ["explorer.exe", win]
        subprocess.Popen(args)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta if ruta.is_dir() else ruta.parent)))


def abrir_archivo(ruta):
    """Abre el archivo con el programa predeterminado (por ejemplo, un PDF)."""
    ruta = Path(ruta)
    try:
        if es_wsl():
            subprocess.Popen(["explorer.exe", _wslpath("-w", ruta)])
            return
    except (OSError, subprocess.SubprocessError):
        pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))


# -- WiFi --------------------------------------------------------------------
# En Windows (y desde WSL) se usa netsh; en Linux, NetworkManager (nmcli).
_RE_SSID = re.compile(r"^\s*SSID\s*:\s*(.+?)\s*$", re.MULTILINE)


def _usa_netsh():
    return sys.platform == "win32" or es_wsl()


def _correr(args, timeout=15):
    """Ejecuta un comando sin abrir ventana de consola. Devuelve (codigo, salida)."""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    if args[0].startswith("netsh") and es_wsl():
        args = ["netsh.exe"] + args[1:]
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)
    crudo = r.stdout + r.stderr
    # netsh responde en la codificacion de la consola de Windows (cp850 en espanol)
    for cod in (("oem",) if sys.platform == "win32" else ()) + ("utf-8", "cp850"):
        try:
            return r.returncode, crudo.decode(cod)
        except (UnicodeDecodeError, LookupError):
            continue
    return r.returncode, crudo.decode("latin-1")


def wifi_actual():
    """SSID de la red WiFi a la que esta conectada la PC, o None."""
    if _usa_netsh():
        codigo, salida = _correr(["netsh", "wlan", "show", "interfaces"])
        m = _RE_SSID.search(salida) if codigo == 0 else None
        return m.group(1) if m else None
    codigo, salida = _correr(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"])
    if codigo == 0:
        for linea in salida.splitlines():
            activo, _, ssid = linea.partition(":")
            if activo in ("yes", "sí", "si") and ssid:
                return ssid
    return None


def conectar_wifi(ssid):
    """Conecta a una red WiFi ya guardada en el sistema. Devuelve (ok, mensaje)."""
    if _usa_netsh():
        codigo, salida = _correr(["netsh", "wlan", "connect", "name=%s" % ssid])
    else:
        codigo, salida = _correr(["nmcli", "connection", "up", "id", ssid], timeout=40)
    return codigo == 0, salida.strip()


def abrir_redes_wifi():
    """Abre la lista de redes WiFi del sistema para elegir una a mano."""
    if es_wsl():
        subprocess.Popen(["explorer.exe", "ms-availablenetworks:"])
    elif sys.platform == "win32":
        os.startfile("ms-availablenetworks:")
    else:
        for cmd in (["nm-connection-editor"], ["gnome-control-center", "wifi"]):
            try:
                subprocess.Popen(cmd)
                return True
            except OSError:
                continue
        return False
    return True
