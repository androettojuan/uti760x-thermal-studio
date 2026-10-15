"""Integracion con el sistema operativo: carpeta Documentos y Explorador.

Contempla correr en Windows directo o en WSL (desarrollo), donde las rutas de
Windows se ven como /mnt/c/... y el Explorador es explorer.exe.
"""
import platform
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
