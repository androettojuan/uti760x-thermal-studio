"""Lector del formato .jpg de la UNI-T UTi760x.

La 760x guarda un JPEG normal (el render con overlay, tal cual se ve en
pantalla) y le pega despues un bloque JSON con los datos crudos en base64,
cerrado por un footer de 24 bytes:

    [JPEG completo ... FFD9][JSON UTF-8][uint32 len_json][20 bytes "UTi760X"]

Version numpy de other/fase0/unit760x.py; ver ahi el detalle de cada campo y
de como se valido el formato.
"""
import base64
import json
import struct
from pathlib import Path

import numpy as np

FOOTER_SIZE = 24
IR_W, IR_H = 640, 512


class FormatoInvalido(ValueError):
    """El archivo no es una imagen radiometrica de la UTi760x."""


class TempConverter:
    """Convierte los uint16 de tempData a grados Celsius.

    Cubica global ajustada sobre tres LUT exactas (export CSV del software de
    UNI-T). No hay una curva unica exacta para todas las imagenes: entre fotos
    hay hasta 1.35 C de variacion que nada en el archivo explica. Ver
    other/fase0/unit760x.py para el analisis completo.

        rango cubierto : raw 2786..6157  (-13.5 a 51.6 C)
        rms            : 0.43 C
        error maximo   : 0.93 C
    """

    COEF = (-75.21962706155418, 0.01763571385387947,
            2.6184492414457977e-06, -3.466733210211375e-10)
    RANGO_VALIDADO = (2786, 6157)
    ERROR_TIPICO_C = 0.43
    ERROR_MAX_C = 0.93

    @classmethod
    def to_celsius(cls, raw):
        c0, c1, c2, c3 = cls.COEF
        r = np.asarray(raw, dtype=np.float64)
        return c0 + r * (c1 + r * (c2 + r * c3))

    @classmethod
    def fuera_de_rango(cls, raw_min, raw_max):
        lo, hi = cls.RANGO_VALIDADO
        return raw_min < lo or raw_max > hi


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
            raise FormatoInvalido("Archivo demasiado corto")
        foot = b[-FOOTER_SIZE:]
        json_len = struct.unpack("<I", foot[:4])[0]
        self.model = foot[4:].rstrip(b"\x00").decode("latin-1")
        if not self.model.lower().startswith("uti"):
            raise FormatoInvalido("No es una imagen radiometrica de UNI-T")
        start = len(b) - FOOTER_SIZE - json_len
        if start < 0:
            raise FormatoInvalido("Bloque de datos truncado")
        try:
            return json.loads(b[start:start + json_len].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise FormatoInvalido("Bloque de datos corrupto: %s" % e) from e

    def _b64(self, key):
        v = self.save_image.get(key)
        return base64.b64decode(v) if v else None

    def temp_raw(self):
        """Array (512, 640) uint16. Fila 0 = arriba."""
        d = self._b64("tempData")
        if d is None:
            raise FormatoInvalido("La imagen no tiene datos de temperatura")
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
