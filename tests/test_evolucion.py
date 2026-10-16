"""Tests de la evolucion de un lugar en el tiempo."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from thermal_studio.core.evolucion import fila, ordenar, series
from thermal_studio.core.mediciones import AREA, Mediciones
from thermal_studio.core.thermal_image import ThermalImage


def _foto(fecha, fase_r, fase_s, con_ref=True):
    t = np.full((40, 40), 20.0)
    t[5:10, 5:10] = fase_r
    t[20:25, 20:25] = fase_s
    img = ThermalImage(t, SimpleNamespace(fecha=fecha))
    ms = Mediciones()
    ms.agregar(AREA, [4, 4, 11, 11])
    ms.renombrar("A1", "Fase R")
    ms.agregar(AREA, [19, 19, 26, 26])
    ms.renombrar("A1", "Fase S")
    if con_ref:
        ms.referencia = "Fase S"
    return fila(Path("x%s.jpg" % fecha), img, ms)


def test_sigue_cada_medicion_por_nombre_en_orden_de_fecha():
    filas = [_foto(datetime(2026, 10, 15), 45, 30), _foto(datetime(2026, 6, 11), 35, 31),
             _foto(datetime(2026, 8, 28), 40, 30)]
    s = series(filas)
    assert set(s) == {"Fase R", "Fase S"}
    assert [p[0].month for p in s["Fase R"]] == [6, 8, 10]
    assert [p[1] for p in s["Fase R"]] == [35, 40, 45]
    assert [p[2] for p in s["Fase R"]] == [4, 10, 15]          # se viene calentando
    assert all(p[2] is None for p in s["Fase S"])              # la referencia no tiene ΔT


def test_mayor_delta_y_fotos_sin_fecha_al_final():
    a = _foto(None, 50, 30)
    b = _foto(datetime(2026, 6, 11), 35, 31)
    assert [f.fecha for f in ordenar([a, b])] == [b.fecha, None]
    assert a.mayor_delta == 20 and a.maxima == 50
    assert "Fase R" not in series([a])                         # sin fecha no entra al grafico
    assert _foto(datetime(2026, 1, 1), 40, 30, con_ref=False).mayor_delta is None
