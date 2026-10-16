"""Lector del formato .jpg de la UNI-T UTi760x.

La 760x guarda un JPEG normal (el render con overlay, tal cual se ve en
pantalla) y le pega despues un bloque JSON con los datos crudos en base64,
cerrado por un footer de 24 bytes:

    [JPEG completo ... FFD9][JSON UTF-8][uint32 len_json][20 bytes "UTi760X"]

Detalle de cada campo y de como se valido el formato en
docs/formato_uti760x.md.
"""
import base64
import json
import struct
from pathlib import Path
from ..i18n import tr

import numpy as np

FOOTER_SIZE = 24
IR_W, IR_H = 640, 512


class FormatoInvalido(ValueError):
    """El archivo no es una imagen radiometrica de la UTi760x."""


class TempConverter:
    """Convierte los uint16 de tempData a grados Celsius.

    tempData no es absoluto: el mismo objeto da valores crudos distintos
    segun la temperatura del sensor (`realFPA`). Se usa la forma de Planck
    (la de las camaras FLIR), con corrimiento y ganancia que dependen de la
    temperatura del sensor:

        f = (fpa - 25) / 10
        raw = R (1 + g1 f + g2 f^2) / (exp(B / T_K) - F) + O0 + O1 f + O2 f^2

    Ajustado (herramientas/calibracion/calibrar.py) sobre 243 lecturas de la
    pantalla de la camara (168 fotos del 11/06/2026 al 16/10/2026, de -19 a
    96 C), las LUT exactas de tres export CSV del software de UNI-T y la tabla
    de calibracion de fabrica que trae cada foto (-10 a 120 C).

        rango cubierto : raw 2444..9519 (-19 a 120 C), FPA 16..40.3 C
        rms            : 0.47 C
        error maximo   : 1.31 C

    Queda una variacion de una sesion a otra (hasta ~1 C) que nada en el
    archivo explica; ver docs/formato_uti760x.md. Solo vale para el rango
    normal (tempMode 0); el rango alto (tempMode 1) no esta calibrado.
    """

    # B, ln R, F, O0, O1, g1, O2, g2
    COEF = (1411.8818236439847, 12.788060064195722, 1.4584608654654863,
            1103.9706359000722, 22.646081658280018, -0.18316988778525192,
            -81.81853020377739, 0.049336755508830724)
    RANGO_VALIDADO = (2444, 9519)
    RANGO_VALIDADO_C = (-19, 120)
    # Lo que mide la camara en el rango normal: fuera de esto la pantalla
    # muestra "<-20,0" o ">125,0"
    RANGO_CAMARA_NORMAL = (-20.0, 125.0)
    FPA_VALIDADO = (16.0, 40.3)
    FPA_POR_DEFECTO = 25.0
    ERROR_TIPICO_C = 0.47
    ERROR_MAX_C = 1.31

    @classmethod
    def to_celsius(cls, raw, fpa=None):
        b, ln_r, f_planck, o0, o1, g1, o2, g2 = cls.COEF
        f = ((cls.FPA_POR_DEFECTO if fpa is None else fpa) - 25) / 10
        corrimiento = o0 + o1 * f + o2 * f * f
        ganancia = 1 + g1 * f + g2 * f * f
        neto = np.maximum(np.asarray(raw, dtype=np.float64) - corrimiento, 1e-3)
        return b / np.log(np.exp(ln_r) * ganancia / neto + f_planck) - 273.15

    @classmethod
    def fuera_de_rango(cls, raw_min, raw_max, fpa=None):
        lo, hi = cls.RANGO_VALIDADO
        flo, fhi = cls.FPA_VALIDADO
        return (raw_min < lo or raw_max > hi
                or (fpa is not None and not flo <= fpa <= fhi))


def es_uti760x(path):
    """True si el archivo termina con el footer de la UTi760x."""
    try:
        with open(path, "rb") as f:
            f.seek(-FOOTER_SIZE, 2)
            foot = f.read(FOOTER_SIZE)
    except OSError:
        return False
    return foot[4:].rstrip(b"\x00").lower().startswith(b"uti")


class Uti760xFile:
    """Acceso a los bloques crudos de un .jpg de la UTi760x."""

    def __init__(self, path):
        self.path = Path(path)
        self.file_bytes = self.path.read_bytes()
        self.meta = self._extract_json()
        self.save_image = self.meta.get("saveImage", {})
        self.params = self.save_image.get("parameterSetting", {})

    def _extract_json(self):
        b = self.file_bytes
        if len(b) < FOOTER_SIZE:
            raise FormatoInvalido(tr("Archivo demasiado corto"))
        foot = b[-FOOTER_SIZE:]
        json_len = struct.unpack("<I", foot[:4])[0]
        self.model = foot[4:].rstrip(b"\x00").decode("latin-1")
        if not self.model.lower().startswith("uti"):
            raise FormatoInvalido(tr("No es una imagen radiometrica de UNI-T"))
        start = len(b) - FOOTER_SIZE - json_len
        if start < 0:
            raise FormatoInvalido(tr("Bloque de datos truncado"))
        try:
            return json.loads(b[start:start + json_len].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise FormatoInvalido(tr("Bloque de datos corrupto: %s") % e) from e

    def _b64(self, key):
        v = self.save_image.get(key)
        return base64.b64decode(v) if v else None

    def temp_raw(self):
        """Array (512, 640) uint16. Fila 0 = arriba."""
        d = self._b64("tempData")
        if d is None:
            raise FormatoInvalido(tr("La imagen no tiene datos de temperatura"))
        if len(d) != IR_W * IR_H * 2:
            raise FormatoInvalido("tempData tiene %d bytes, se esperaban %d"
                                  % (len(d), IR_W * IR_H * 2))
        return np.frombuffer(d, dtype="<u2").reshape(IR_H, IR_W)

    def thermal_gray(self):
        """Array (512, 640) uint8 con la imagen termica sin overlay, o None."""
        d = self._b64("thermalImageData")
        if d is None or len(d) != IR_W * IR_H:
            return None
        return np.frombuffer(d, dtype=np.uint8).reshape(IR_H, IR_W)

    def visible_jpeg(self):
        """Bytes del JPEG de la camara visible, o None."""
        d = self._b64("hdCameraImageData")
        if d and d[:2] == b"\xff\xd8":
            return d
        return None

    def render_jpeg(self):
        """El JPEG de arriba de todo: el render con overlay de la camara."""
        return self.file_bytes[:self.file_bytes.rfind(b"\xff\xd9") + 2]
