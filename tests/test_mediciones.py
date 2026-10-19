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


def test_delta_t_sin_valor_si_la_camara_no_mide(temps):
    ms = Mediciones()
    caliente = ms.agregar(PUNTO, [30.5, 10.5])     # 45
    ms.referencia = ms.agregar(AREA, [49, 29, 61, 36]).nombre   # 35
    assert ms.delta_t(caliente, temps, (-20.0, 125.0)) == pytest.approx(10.0)
    assert ms.delta_t(caliente, temps, (-20.0, 40.0)) is None   # 45 es «>40»
    assert ms.delta_t(caliente, temps, (36.0, 125.0)) is None   # la referencia es «<36»


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


def test_notas_se_guardan_aunque_no_haya_mediciones(tmp_path):
    bib = Library(tmp_path)
    ms = Mediciones(notas="Borne R flojo, ajustar")
    bib.guardar_mediciones("IMG1.jpg", ms)
    assert bib.leer_mediciones("IMG1.jpg").notas == "Borne R flojo, ajustar"
    bib.guardar_mediciones("IMG1.jpg", Mediciones(notas="   "))
    assert not list(bib.carpeta_mediciones.glob("*.json"))


def test_csv_de_mediciones_para_excel_en_castellano(tmp_path, temps):
    from thermal_studio.core.exportar import csv_mediciones
    from thermal_studio.core.thermal_image import ThermalImage
    img = ThermalImage(temps, type("M", (), {"fecha": None, "emisividad": 0.95})())
    ms = Mediciones(notas="Revisar")
    ms.agregar(PUNTO, [30.5, 10.5])
    ms.agregar(AREA, [49, 29, 61, 36])
    ms.referencia = "A1"
    destino = tmp_path / "m.csv"
    csv_mediciones(destino, img, ms)
    texto = destino.read_text(encoding="utf-8-sig")
    assert "P1;Punto;45,0;45,0;45,0;10,0;" in texto
    assert "A1;Área;35,0;" in texto and texto.count(";sí") == 1
    assert "Notas;Revisar" in texto


def test_render_ecualizado_usa_las_posiciones():
    from thermal_studio.core.thermal_image import ThermalImage, tabla_colores
    t = np.linspace(0, 10, 100).reshape(10, 10)
    img = ThermalImage(t, None)
    lineal = img.render("white_hot", rango=(0, 10))
    assert np.array_equal(tabla_colores("white_hot"), tabla_colores("white_hot", posiciones=None))
    # Todo el contraste en la mitad baja: un pixel a 2,5 C queda mucho mas claro
    pos = np.concatenate([np.linspace(0, 0.5, 200), np.linspace(0.5, 1, 57)[1:]])
    eq = img.render("white_hot", rango=(0, 10), posiciones=pos)
    f, c = np.unravel_index(np.argmin(np.abs(t - 2.5)), t.shape)
    assert int(eq[f, c, 0]) > int(lineal[f, c, 0]) + 25
