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

    tempData no es absoluto: el mismo objeto da valores crudos distintos
    segun la temperatura del sensor (`realFPA`). Con el sensor a 37 C en vez
    de 20 C, una curva sin esa correccion erraba 15 C. Por eso el modelo es
    una cubica en el crudo mas un termino lineal en FPA y uno cruzado:

        r = (raw - 4000) / 1000      f = (fpa - 25) / 10
        T = c0 + c1 r + c2 r^2 + c3 r^3 + c4 f + c5 f r

    Ajustado sobre 222 lecturas del overlay de la camara (max/min de 164 fotos,
    del 11/06/2026 al 15/10/2026) mas las LUT exactas de tres export CSV del
    software de UNI-T. Queda una variacion de foto a foto que nada en el
    archivo explica (ver other/fase0/HALLAZGOS_760X.md).

        rango cubierto : raw 2444..6818 (-19 a 81 C), FPA 16..38.5 C
        rms            : 0.49 C
        error maximo   : 1.32 C

    Solo vale para el rango normal (tempMode 0); el rango alto (tempMode 1)
    no esta calibrado.
    """

    COEF = (19.20393422468132, 20.662431662218864, -2.4116198956989052,
            0.28904251532211234, 9.870617581758466, 1.1091388133918052)
    RANGO_VALIDADO = (2444, 6818)
    RANGO_VALIDADO_C = (-19, 81)
    FPA_VALIDADO = (16.0, 38.5)
    FPA_POR_DEFECTO = 25.0
    ERROR_TIPICO_C = 0.49
    ERROR_MAX_C = 1.32

    @classmethod
    def to_celsius(cls, raw, fpa=None):
        c0, c1, c2, c3, c4, c5 = cls.COEF
        r = (np.asarray(raw, dtype=np.float64) - 4000) / 1000
        f = ((cls.FPA_POR_DEFECTO if fpa is None else fpa) - 25) / 10
        return c0 + c4 * f + r * (c1 + c5 * f + r * (c2 + r * c3))

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
