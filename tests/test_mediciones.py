"""Tests de mediciones (puntos, lineas, areas, Delta T y guardado)."""
import numpy as np
import pytest

from thermal_studio.core.library import Library
from thermal_studio.core.mediciones import (
    AREA, LINEA, PUNTO, Medicion, Mediciones, estadistica, perfil,
)


@pytest.fixture
def temps():
    t = np.full((50, 80), 20.0)
    t[10, 30] = 45.0           # punto caliente
    t[30:35, 50:60] = 35.0     # zona tibia
    return t


def test_punto_lee_el_pixel_que_contiene(temps):
    e = estadistica(Medicion(PUNTO, "P1", [30.7, 10.2]), temps)
    assert e.maxima == e.minima == 45.0
    assert (e.fila_max, e.col_max) == (10, 30)


def test_area_encuentra_maxima_y_media(temps):
    e = estadistica(Medicion(AREA, "A1", [49, 29, 61, 36]), temps)
    assert e.maxima == 35.0
    assert e.minima == 20.0          # el borde del rectangulo toca pixeles a 20
    assert 20.0 < e.media < 35.0
    assert 30 <= e.fila_max < 35 and 50 <= e.col_max < 60


def test_area_dibujada_al_reves_da_lo_mismo(temps):
    a = estadistica(Medicion(AREA, "A1", [49, 29, 61, 36]), temps)
    b = estadistica(Medicion(AREA, "A2", [61, 36, 49, 29]), temps)
    assert a == b


def test_area_fuera_de_la_imagen_se_recorta(temps):
    e = estadistica(Medicion(AREA, "A1", [-10, -10, 200, 200]), temps)
    assert e.pixeles == temps.size
    assert e.maxima == 45.0


def test_linea_pasa_por_el_punto_caliente_y_su_perfil(temps):
    m = Medicion(LINEA, "L1", [20.5, 10.5, 40.5, 10.5])
    e = estadistica(m, temps)
    assert e.maxima == 45.0 and (e.fila_max, e.col_max) == (10, 30)
    dist, valores = perfil(m, temps)
    assert len(dist) == len(valores) == 21
    assert dist[0] == pytest.approx(0) and dist[-1] == pytest.approx(20)
    assert valores[np.argmax(valores)] == 45.0 and dist[np.argmax(valores)] == pytest.approx(10)


def test_delta_t_contra_la_referencia(temps):
    ms = Mediciones()
    caliente = ms.agregar(PUNTO, [30.5, 10.5])
    normal = ms.agregar(AREA, [49, 29, 61, 36])
    assert ms.delta_t(caliente, temps) is None      # sin referencia
    ms.referencia = normal.nombre
    assert ms.delta_t(caliente, temps) == pytest.approx(10.0)
    assert ms.delta_t(normal, temps) is None        # la referencia contra si misma


def test_nombres_automaticos_y_renombrar():
    ms = Mediciones()
    assert [ms.agregar(PUNTO, [0, 0]).nombre for _ in range(2)] == ["P1", "P2"]
    assert ms.agregar(LINEA, [0, 0, 1, 1]).nombre == "L1"
    assert ms.agregar(AREA, [0, 0, 1, 1]).nombre == "A1"
    ms.referencia = "P1"
    assert ms.renombrar("P1", "Fase S")
    assert ms.referencia == "Fase S"
    assert not ms.renombrar("P2", "Fase S")    # ya existe
    assert not ms.renombrar("P2", "  ")        # vacio
    ms.quitar("Fase S")
    assert ms.referencia is None
    assert ms.agregar(PUNTO, [0, 0]).nombre == "P1"   # reusa el numero libre


def test_guardar_y_leer_en_la_biblioteca(tmp_path):
    bib = Library(tmp_path)
    ms = Mediciones()
    ms.agregar(PUNTO, [1, 2])
    ms.agregar(AREA, [3, 4, 10, 12])
    ms.renombrar("A1", "Borne R")
    ms.referencia = "P1"
    bib.guardar_mediciones("IMG20261015225351HD.jpg", ms)

    leidas = bib.leer_mediciones("IMG20261015225351HD.jpg")
    assert leidas.a_dict() == ms.a_dict()
    # La clave es el nombre: da igual en que carpeta este la foto
    assert bib.leer_mediciones(tmp_path / "otra" / "IMG20261015225351HD.jpg").a_dict() == ms.a_dict()

    bib.guardar_mediciones("IMG20261015225351HD.jpg", Mediciones())
    assert not list(bib.carpeta_mediciones.glob("*.json"))


def test_archivo_con_basura_no_impide_leer(tmp_path):
    d = {"referencia": "X", "mediciones": [
        {"tipo": "punto", "nombre": "P1", "geom": [1, 2]},
        {"tipo": "triangulo", "nombre": "T1", "geom": [1, 2]},
        {"tipo": "area", "nombre": "A1", "geom": [1]},
        {"nombre": "sin tipo"},
    ]}
    ms = Mediciones.desde_dict(d)
    assert [m.nombre for m in ms.lista] == ["P1"]
    assert ms.referencia is None
