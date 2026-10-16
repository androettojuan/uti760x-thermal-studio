"""Tests del nucleo (sin Qt). Usan las fotos reales de fotos/, si estan."""
from pathlib import Path

import numpy as np
import pytest

from thermal_studio.core import palettes
from thermal_studio.core.thermal_image import ThermalImage
from thermal_studio.core.uti760x import FormatoInvalido, TempConverter, es_uti760x

FOTOS = Path(__file__).resolve().parent.parent / "fotos"
IMG = FOTOS / "IMG20260611212820HD.jpg"
CSV = FOTOS / "ver.CSV"  # export del software de UNI-T para IMG

requiere_fotos = pytest.mark.skipif(not IMG.exists(), reason="faltan las fotos de muestra")


def _leer_csv(path):
    filas = []
    for ln in path.read_text().splitlines():
        p = [x for x in ln.strip().split(",") if x != ""]
        if p:
            filas.append([float(x) for x in p])
    return np.array(filas)


@requiere_fotos
def test_abre_y_lee_metadatos():
    img = ThermalImage.abrir(IMG)
    assert img.temps.shape == (512, 640)
    assert img.meta.modelo.startswith("UTi760")
    assert img.meta.fecha.isoformat() == "2026-06-11T21:28:20"
    assert img.meta.emisividad == 0.95
    assert not img.fuera_de_rango


@requiere_fotos
def test_temperaturas_coinciden_con_export_de_uni_t():
    img = ThermalImage.abrir(IMG)
    ref = _leer_csv(CSV)
    assert ref.shape == img.temps.shape
    assert np.abs(img.temps - ref).max() <= TempConverter.ERROR_MAX_C
    assert img.maximo().temp == pytest.approx(ref.max(), abs=TempConverter.ERROR_MAX_C)
    assert img.minimo().temp == pytest.approx(ref.min(), abs=TempConverter.ERROR_MAX_C)


@requiere_fotos
def test_max_min_y_centro_apuntan_al_pixel_correcto():
    img = ThermalImage.abrir(IMG)
    for p in (img.maximo(), img.minimo(), img.centro()):
        assert img.temp_en(p.fila, p.col) == pytest.approx(p.temp)
    assert img.temp_en(-1, 0) is None
    assert img.temp_en(0, 640) is None


@requiere_fotos
def test_render_satura_fuera_del_rango():
    img = ThermalImage.abrir(IMG)
    lo, hi = img.rango_auto()
    rgb = img.render("white_hot", rango=(lo, hi))
    assert rgb.shape == (512, 640, 3) and rgb.dtype == np.uint8
    lut = palettes.get("white_hot")
    m = img.maximo()
    assert tuple(rgb[m.fila, m.col]) == tuple(lut[-1])
    # Con un rango por debajo de toda la imagen, todo queda en el color mas caliente
    todo_caliente = img.render("white_hot", rango=(lo - 20, lo - 10))
    assert (todo_caliente == lut[-1]).all()


def test_paletas():
    for nombre in palettes.disponibles():
        lut = palettes.get(nombre)
        assert lut.shape == (256, 3) and lut.dtype == np.uint8
    # Sacadas por separado de la camara: tienen que ser casi una la inversa de la otra
    dif = np.abs(palettes.get("black_hot").astype(int) - palettes.get("white_hot")[::-1])
    assert dif.mean() < 6
    assert (palettes.get("iron", invertir=True) == palettes.get("iron")[::-1]).all()


def test_rechaza_archivos_que_no_son_de_la_camara(tmp_path):
    falso = tmp_path / "otra.jpg"
    falso.write_bytes(b"\xff\xd8" + b"x" * 100 + b"\xff\xd9")
    assert not es_uti760x(falso)
    with pytest.raises(FormatoInvalido):
        ThermalImage.abrir(falso)


def test_conversion_es_monotona_en_todo_el_rango():
    raw = np.arange(1400, 16000, 5)
    for fpa in (10, 16, 25, 38, 45):
        assert np.all(np.diff(TempConverter.to_celsius(raw, fpa)) > 0)


def test_conversion_corrige_por_temperatura_del_sensor():
    # Lecturas de la pantalla de la camara: el mismo crudo vale distinto
    # segun realFPA (sin la correccion, la primera daba 15 C)
    casos = [  # raw, realFPA, C en pantalla
        (3998, 37.31, 31.5),  # IMG20261015225351, max
        (6818, 37.90, 81.1),  # IMG20261015230357, max
        (6157, 21.03, 51.6),  # IMG20260611213042, max
        (9519, 22.71, 95.9),  # IMG20261016102003, max (la cubica daba 104,7)
        (8020, 22.71, 77.5),  # IMG20261016102003, centro
    ]
    for raw, fpa, esperado in casos:
        assert TempConverter.to_celsius(raw, fpa) == pytest.approx(
            esperado, abs=TempConverter.ERROR_MAX_C)


def test_rango_auto_ignora_cielo_y_conserva_el_punto_caliente():
    temps = np.full((100, 100), 25.0)
    temps[:30] = -35.0          # cielo, debajo del piso de medicion
    temps[30, :3] = -28.0       # borde frio suelto
    temps[50, 50] = 80.0        # punto caliente de un solo pixel
    lo, hi = ThermalImage(temps, None).rango_auto()
    assert hi == 80.0
    assert lo == 25.0


def test_ecualizado_da_mas_colores_a_lo_que_ocupa_mas_imagen():
    temps = np.full((100, 100), 30.0)
    temps[:, :10] = np.linspace(0, 20, 100)[:, None]  # 10 % de la imagen, 0 a 20 C
    temps[:, 10:] = 30 + np.linspace(0, 2, 90)[None, :]  # 90 %, entre 30 y 32 C
    img = ThermalImage(temps, None)
    pos = img.posiciones_ecualizadas(0.0, 32.0, 256)
    assert pos[0] == 0.0 and pos[-1] == 1.0
    assert np.all(np.diff(pos) > 0)
    # Lineal, 30-32 C tendria 1/16 de los colores; ecualizado, la mayoria
    en_tramo = np.mean(pos >= 30 / 32)
    assert en_tramo > 0.6


def test_rango_auto_conjunto_abarca_las_dos_fotos():
    from thermal_studio.core.thermal_image import rango_auto_conjunto
    fria = ThermalImage(np.linspace(0, 20, 10000).reshape(100, 100), None)
    caliente = ThermalImage(np.linspace(10, 60, 10000).reshape(100, 100), None)
    lo, hi = rango_auto_conjunto([fria, caliente])
    assert hi == 60.0
    assert lo == pytest.approx(fria.rango_auto()[0])
