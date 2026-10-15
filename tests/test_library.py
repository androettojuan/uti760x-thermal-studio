"""Tests de la biblioteca y la importacion, con una camara falsa."""
import pytest

from thermal_studio.core import importer
from thermal_studio.core.camera_ftp import ArchivoCamara, Cancelado, _parsear_list
from thermal_studio.core.importer import Modo
from thermal_studio.core.library import ErrorBiblioteca, Library, fecha_de_nombre

A = ArchivoCamara("IMG20260611212820HD.jpg", 10)
B = ArchivoCamara("IMG20260618195947HD.jpg", 20)
C = ArchivoCamara("IMG20260618200007HD.jpg", 30)


class CamaraFalsa:
    def __init__(self, archivos):
        self.archivos = archivos
        self.descargadas = []

    def listar_fotos(self):
        return list(self.archivos)

    def descargar(self, archivo, destino, progreso=None, cancelado=None):
        if cancelado and cancelado():
            raise Cancelado()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"x" * archivo.tamano)
        if progreso:
            progreso(archivo.tamano)
        self.descargadas.append(archivo.nombre)


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "Termografias")


def test_parsear_list_de_la_camara():
    a = _parsear_list("-rw-------   1 user group      4236075 Jun 11 22:13 IMG20260611212732HD.jpg")
    assert a == ArchivoCamara("IMG20260611212732HD.jpg", 4236075)
    assert _parsear_list("drwx------   3 user group  0 Aug 31 19:31 pic") is None


def test_fecha_de_nombre():
    assert fecha_de_nombre("IMG20260611212820HD.jpg") == "2026-06-11"
    assert fecha_de_nombre("foto.jpg") is None


def test_carpetas(lib):
    lib.crear_carpeta("", "Subestación Norte")
    lib.crear_carpeta("Subestación Norte", "Tablero A")
    assert lib.todas_las_carpetas() == ["Subestación Norte", "Subestación Norte/Tablero A"]
    assert lib.renombrar_carpeta("Subestación Norte/Tablero A", "Tablero B") == \
        "Subestación Norte/Tablero B"
    with pytest.raises(ErrorBiblioteca):
        lib.crear_carpeta("", "Subestación Norte")
    with pytest.raises(ErrorBiblioteca):
        lib.crear_carpeta("", "mal:nombre")
    with pytest.raises(ErrorBiblioteca):
        lib.crear_carpeta("", "CON")
    with pytest.raises(ErrorBiblioteca):
        lib.abs("../afuera")
    # la carpeta interna no aparece
    assert ".thermal_studio" not in lib.subcarpetas()


def test_no_elimina_carpetas_con_fotos(lib):
    lib.crear_carpeta("", "Tablero")
    (lib.abs("Tablero") / "IMG1.jpg").write_bytes(b"x")
    with pytest.raises(ErrorBiblioteca, match="1 foto"):
        lib.eliminar_carpeta("Tablero")
    (lib.abs("Tablero") / "IMG1.jpg").unlink()
    lib.eliminar_carpeta("Tablero")
    assert lib.subcarpetas() == []


def test_mover_carpeta_dentro_de_si_misma_falla(lib):
    lib.crear_carpeta("", "A")
    lib.crear_carpeta("A", "B")
    with pytest.raises(ErrorBiblioteca):
        lib.mover_carpeta("A", "A/B")
    lib.crear_carpeta("", "C")
    assert lib.mover_carpeta("A", "C") == "C/A"


def test_mover_fotos_no_pisa(lib):
    lib.crear_carpeta("", "X")
    lib.crear_carpeta("", "Y")
    (lib.abs("X") / "f.jpg").write_bytes(b"1")
    (lib.abs("Y") / "f.jpg").write_bytes(b"2")
    [nueva] = lib.mover_fotos([lib.abs("X") / "f.jpg"], "Y")
    assert nueva.name == "f (2).jpg"
    assert (lib.abs("Y") / "f.jpg").read_bytes() == b"2"


def test_importar_todo_y_faltantes(lib):
    cam = CamaraFalsa([A, B])
    plan = importer.planificar(cam.listar_fotos(), lib, Modo.FALTANTES)
    importer.ejecutar(plan, cam, lib)
    assert (lib.abs("Importadas/2026-06-11") / A.nombre).exists()
    assert (lib.abs("Importadas/2026-06-18") / B.nombre).exists()

    # La camara saca una foto nueva; el usuario organiza A y borra B
    cam.archivos.append(C)
    lib.crear_carpeta("", "Tablero A")
    lib.mover_fotos([lib.abs("Importadas/2026-06-11") / A.nombre], "Tablero A")
    (lib.abs("Importadas/2026-06-18") / B.nombre).unlink()

    plan = importer.planificar(cam.listar_fotos(), lib, Modo.FALTANTES)
    assert [a.nombre for a, _ in plan.a_descargar] == [C.nombre]
    assert plan.ya_en_biblioteca == 1 and plan.importadas_antes == 1

    plan = importer.planificar(cam.listar_fotos(), lib, Modo.TODO)
    assert [a.nombre for a, _ in plan.a_descargar] == [B.nombre, C.nombre]
    assert plan.ya_en_biblioteca == 1  # A no se duplica aunque se haya movido


def test_cancelar_deja_registrado_lo_ya_bajado(lib):
    cam = CamaraFalsa([A, B, C])
    plan = importer.planificar(cam.listar_fotos(), lib, Modo.TODO)
    n = []
    with pytest.raises(Cancelado):
        importer.ejecutar(plan, cam, lib, progreso=lambda *a: n.append(1),
                          cancelado=lambda: len(n) >= 1)
    assert set(lib.registro()) == {A.nombre}
