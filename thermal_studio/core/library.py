"""Biblioteca de imagenes: una carpeta raiz con subcarpetas que organiza el usuario.

    Termografias/
    ├── Importadas/2026-06-11/IMG20260611212820HD.jpg   <- destino de la importacion
    ├── Subestacion Norte/Tablero A/...                  <- carpetas del usuario
    └── .thermal_studio/                                 <- datos internos (oculta)
        ├── importadas.json   registro de lo que ya se importo de la camara
        ├── mediciones/       <nombre de la foto>.json, uno por foto medida
        └── miniaturas/       cache de miniaturas

Las rutas de carpeta se manejan relativas a la raiz, con "/" como separador
("" es la raiz misma).
"""
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .mediciones import Mediciones

CARPETA_INTERNA = ".thermal_studio"
CARPETA_IMPORTADAS = "Importadas"
EXTENSIONES = {".jpg", ".jpeg"}

# Windows no acepta estos caracteres ni estos nombres
_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *("COM%d" % i for i in range(1, 10)),
               *("LPT%d" % i for i in range(1, 10))}
_RE_FECHA = re.compile(r"(\d{8})\d{6}")


class ErrorBiblioteca(Exception):
    """Operacion invalida; el mensaje se puede mostrar tal cual al usuario."""


def validar_nombre(nombre):
    nombre = nombre.strip()
    if not nombre:
        raise ErrorBiblioteca("El nombre no puede estar vacío.")
    if _PROHIBIDOS.search(nombre):
        raise ErrorBiblioteca('El nombre no puede contener < > : " / \\ | ? *')
    if nombre.startswith(".") or nombre.endswith("."):
        raise ErrorBiblioteca("El nombre no puede empezar ni terminar con un punto.")
    if nombre.split(".")[0].upper() in _RESERVADOS:
        raise ErrorBiblioteca("«%s» es un nombre reservado de Windows." % nombre)
    return nombre


def es_foto(path):
    return path.is_file() and path.suffix.lower() in EXTENSIONES


_RE_CARPETA_FECHA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def fecha_visible(nombre_carpeta):
    """'2026-08-28' -> '28/08/2026'; cualquier otro nombre queda igual.

    En disco las carpetas de fecha van como AAAA-MM-DD (Windows no acepta "/"
    y asi se ordenan solas); en pantalla se muestran dd/mm/aaaa.
    """
    m = _RE_CARPETA_FECHA.match(nombre_carpeta)
    return "%s/%s/%s" % (m.group(3), m.group(2), m.group(1)) if m else nombre_carpeta


def fecha_de_nombre(nombre):
    """'IMG20260611212820HD.jpg' -> '2026-06-11', o None."""
    m = _RE_FECHA.search(nombre)
    if not m:
        return None
    d = m.group(1)
    return "%s-%s-%s" % (d[:4], d[4:6], d[6:])


class Library:
    def __init__(self, raiz):
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.interna = self.raiz / CARPETA_INTERNA
        self.interna.mkdir(exist_ok=True)
        self.miniaturas = self.interna / "miniaturas"
        self.miniaturas.mkdir(exist_ok=True)
        (self.raiz / CARPETA_IMPORTADAS).mkdir(exist_ok=True)
        self._registro_path = self.interna / "importadas.json"
        self.carpeta_mediciones = self.interna / "mediciones"

    # -- rutas -------------------------------------------------------------
    def abs(self, rel):
        """Ruta absoluta de una carpeta relativa, sin dejar salir de la raiz."""
        p = (self.raiz / rel).resolve() if rel else self.raiz.resolve()
        raiz = self.raiz.resolve()
        if p != raiz and raiz not in p.parents:
            raise ErrorBiblioteca("Ruta fuera de la biblioteca: %s" % rel)
        return p

    def rel(self, path):
        r = Path(path).resolve().relative_to(self.raiz.resolve())
        return "" if str(r) == "." else r.as_posix()

    # -- carpetas ----------------------------------------------------------
    def subcarpetas(self, rel=""):
        """Nombres de las subcarpetas directas, ordenadas, sin las ocultas."""
        base = self.abs(rel)
        return sorted((p.name for p in base.iterdir()
                       if p.is_dir() and not p.name.startswith(".")),
                      key=str.lower)

    def todas_las_carpetas(self):
        """Todas las carpetas relativas (sin la raiz), en orden de arbol."""
        out = []

        def rec(rel):
            for n in self.subcarpetas(rel):
                r = "%s/%s" % (rel, n) if rel else n
                out.append(r)
                rec(r)
        rec("")
        return out

    def crear_carpeta(self, padre_rel, nombre):
        nombre = validar_nombre(nombre)
        p = self.abs(padre_rel) / nombre
        if p.exists():
            raise ErrorBiblioteca("Ya existe una carpeta «%s» ahí." % nombre)
        p.mkdir(parents=True)
        return self.rel(p)

    def es_protegida(self, rel):
        """La raiz y la carpeta de importacion no se renombran, borran ni mueven."""
        return rel in ("", CARPETA_IMPORTADAS)

    def renombrar_carpeta(self, rel, nombre):
        if self.es_protegida(rel):
            raise ErrorBiblioteca("Esta carpeta no se puede renombrar.")
        nombre = validar_nombre(nombre)
        p = self.abs(rel)
        nuevo = p.with_name(nombre)
        if nuevo.exists() and nuevo != p:
            raise ErrorBiblioteca("Ya existe una carpeta «%s» ahí." % nombre)
        p.rename(nuevo)
        return self.rel(nuevo)

    def eliminar_carpeta(self, rel):
        """Solo borra carpetas sin fotos (puede tener subcarpetas vacias)."""
        if self.es_protegida(rel):
            raise ErrorBiblioteca("Esta carpeta no se puede eliminar.")
        p = self.abs(rel)
        n = sum(1 for f in p.rglob("*") if es_foto(f))
        if n:
            raise ErrorBiblioteca("La carpeta tiene %d foto%s. Movelas a otra carpeta antes "
                                  "de eliminarla." % (n, "" if n == 1 else "s"))
        shutil.rmtree(p)

    def mover_carpeta(self, rel, destino_rel):
        if self.es_protegida(rel):
            raise ErrorBiblioteca("Esta carpeta no se puede mover.")
        p, dest = self.abs(rel), self.abs(destino_rel)
        if dest == p or p in dest.parents:
            raise ErrorBiblioteca("No se puede mover una carpeta dentro de sí misma.")
        nuevo = dest / p.name
        if nuevo.exists():
            raise ErrorBiblioteca("Ya existe una carpeta «%s» en el destino." % p.name)
        shutil.move(str(p), str(nuevo))
        return self.rel(nuevo)

    # -- fotos -------------------------------------------------------------
    def fotos(self, rel=""):
        """Fotos directas de la carpeta (no recursivo), ordenadas por nombre."""
        return sorted((p for p in self.abs(rel).iterdir() if es_foto(p)),
                      key=lambda p: p.name)

    def contar_fotos(self, rel=""):
        return sum(1 for p in self.abs(rel).rglob("*")
                   if es_foto(p) and CARPETA_INTERNA not in p.parts)

    def indice(self):
        """{nombre de archivo: ruta} de todas las fotos de la biblioteca."""
        out = {}
        for p in self.raiz.rglob("*"):
            if es_foto(p) and CARPETA_INTERNA not in p.relative_to(self.raiz).parts:
                out.setdefault(p.name, p)
        return out

    def mover_fotos(self, paths, destino_rel):
        """Mueve fotos a otra carpeta. Devuelve la lista de rutas nuevas.

        Si en el destino ya hay un archivo con el mismo nombre, se le agrega
        un sufijo " (2)", " (3)"...
        """
        dest = self.abs(destino_rel)
        nuevas = []
        for src in map(Path, paths):
            if src.parent.resolve() == dest:
                nuevas.append(src)
                continue
            final = self._nombre_libre(dest / src.name)
            shutil.move(str(src), str(final))
            nuevas.append(final)
            self._limpiar_fecha_vacia(src.parent)
        return nuevas

    def _limpiar_fecha_vacia(self, carpeta):
        """Borra una carpeta de fecha de Importadas que quedo vacia."""
        importadas = (self.raiz / CARPETA_IMPORTADAS).resolve()
        carpeta = carpeta.resolve()
        if carpeta.parent == importadas and not any(carpeta.iterdir()):
            carpeta.rmdir()

    def traer_fotos(self, paths, destino_rel):
        """Como mover_fotos, pero las que vienen de fuera de la biblioteca se copian."""
        raiz = self.raiz.resolve()
        adentro = [p for p in map(Path, paths) if raiz in p.resolve().parents]
        afuera = [p for p in map(Path, paths) if raiz not in p.resolve().parents]
        nuevas = self.mover_fotos(adentro, destino_rel)
        dest = self.abs(destino_rel)
        for src in afuera:
            final = self._nombre_libre(dest / src.name)
            shutil.copy2(src, final)
            nuevas.append(final)
        return nuevas

    @staticmethod
    def _nombre_libre(p):
        if not p.exists():
            return p
        i = 2
        while True:
            c = p.with_name("%s (%d)%s" % (p.stem, i, p.suffix))
            if not c.exists():
                return c
            i += 1

    # -- importacion -------------------------------------------------------
    def registro(self):
        """{nombre: {"tamano": int, "importada": iso}} de lo ya importado."""
        try:
            return json.loads(self._registro_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def registrar_importadas(self, archivos):
        """archivos: iterable de (nombre, tamano)."""
        reg = self.registro()
        ahora = datetime.now().isoformat(timespec="seconds")
        for nombre, tamano in archivos:
            reg[nombre] = {"tamano": tamano, "importada": ahora}
        tmp = self._registro_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self._registro_path)

    def carpeta_importacion(self, nombre_foto):
        """Carpeta relativa donde cae una foto importada: Importadas/AAAA-MM-DD."""
        fecha = fecha_de_nombre(nombre_foto) or "sin fecha"
        return "%s/%s" % (CARPETA_IMPORTADAS, fecha)

    # -- mediciones --------------------------------------------------------
    # Se guardan por nombre de archivo y no por ruta: los nombres de la camara
    # llevan fecha y hora, asi que son unicos, y al mover una foto de carpeta
    # sus mediciones la siguen sin hacer nada.
    def _ruta_mediciones(self, nombre_foto):
        return self.carpeta_mediciones / (Path(nombre_foto).name + ".json")

    def leer_mediciones(self, nombre_foto):
        """Mediciones guardadas de una foto (vacias si no tiene)."""
        try:
            d = json.loads(self._ruta_mediciones(nombre_foto).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return Mediciones()
        return Mediciones.desde_dict(d)

    def guardar_mediciones(self, nombre_foto, mediciones):
        """Guarda (o borra, si quedo vacia) la lista de mediciones de una foto."""
        destino = self._ruta_mediciones(nombre_foto)
        if not mediciones.lista:
            destino.unlink(missing_ok=True)
            return
        destino.parent.mkdir(exist_ok=True)
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(mediciones.a_dict(), indent=1, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(destino)
