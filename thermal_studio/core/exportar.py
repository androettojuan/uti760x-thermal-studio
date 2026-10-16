"""Exportacion a CSV de mediciones y temperaturas.

Los CSV van con punto y coma y coma decimal, en UTF-8 con BOM: es lo que
Excel en castellano abre directo, con los numeros como numeros.
"""
import csv

import numpy as np

from .mediciones import NOMBRES_TIPO, resultados


def _num(v, decimales=1):
    return "" if v is None else ("%.*f" % (decimales, v)).replace(".", ",")


def csv_mediciones(path, img, mediciones):
    filas = resultados(mediciones, img.temps)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Foto", img.path.name if img.path else ""])
        w.writerow(["Fecha", img.meta.fecha.strftime("%d/%m/%Y %H:%M:%S") if img.meta.fecha else ""])
        w.writerow(["Emisividad", _num(img.meta.emisividad, 2)])
        w.writerow([])
        w.writerow(["Medición", "Tipo", "Máxima (°C)", "Mínima (°C)", "Media (°C)",
                    "ΔT contra referencia (°C)", "Referencia"])
        for r in filas:
            w.writerow([r.nombre, NOMBRES_TIPO[r.tipo], _num(r.maxima), _num(r.minima),
                        _num(r.media), _num(r.delta_t), "sí" if r.es_referencia else ""])
        if mediciones.notas.strip():
            w.writerow([])
            w.writerow(["Notas", mediciones.notas.strip()])


def csv_temperaturas(path, temps):
    """Matriz completa (filas x columnas de la imagen), en °C con 2 decimales."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        for fila in np.asarray(temps):
            w.writerow([_num(float(v), 2) for v in fila])
