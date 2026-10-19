"""Exportacion a CSV de mediciones y temperaturas.

Separador de columnas y decimal segun el idioma (punto y coma y coma decimal
en castellano y portugues; coma y punto en ingles), en UTF-8 con BOM: es lo
que el Excel de cada idioma abre directo, con los numeros como numeros.
"""
import csv

import numpy as np

from .mediciones import NOMBRES_TIPO, resultados
from ..i18n import a_unidad, fecha_hora, num, separador_csv, simbolo, tr


def _num(v, decimales=1):
    return "" if v is None else num(v, decimales)


def csv_mediciones(path, img, mediciones):
    filas = resultados(mediciones, img.temps, img.limites)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=separador_csv())
        w.writerow([tr("Foto"), img.path.name if img.path else ""])
        w.writerow([tr("Fecha"), fecha_hora(img.meta.fecha, segundos=True) if img.meta.fecha else ""])
        w.writerow([tr("Emisividad"), _num(img.meta.emisividad, 2)])
        w.writerow([])
        u = simbolo()
        w.writerow([tr("Medición"), tr("Tipo"), tr("Máxima (%s)") % u, tr("Mínima (%s)") % u,
                    tr("Media (%s)") % u, tr("ΔT contra referencia (%s)") % u, tr("Referencia")])
        for r in filas:
            w.writerow([r.nombre, tr(NOMBRES_TIPO[r.tipo]), _num(a_unidad(r.maxima)),
                        _num(a_unidad(r.minima)), _num(a_unidad(r.media)),
                        _num(a_unidad(r.delta_t, diferencia=True)),
                        tr("sí") if r.es_referencia else ""])
        if mediciones.notas.strip():
            w.writerow([])
            w.writerow([tr("Notas"), mediciones.notas.strip()])


def csv_temperaturas(path, temps):
    """Matriz completa (filas x columnas de la imagen), en la unidad elegida
    (°C o °F) con 2 decimales."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=separador_csv())
        # Mucho mas rapido que formatear celda por celda
        dec = num(0.5, 2)[1]
        for fila in a_unidad(np.asarray(temps, dtype=np.float64)):
            w.writerow([("%.2f" % v).replace(".", dec) for v in fila])
