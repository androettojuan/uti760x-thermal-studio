"""Importacion de fotos de la camara a la biblioteca.

Dos modos:
  FALTANTES  solo las fotos que nunca se importaron (segun el registro).
  TODO       todas las que no estan hoy en la biblioteca, incluidas las que
             se importaron y despues se borraron.
En ningun modo se duplica una foto que ya esta en la biblioteca, este en la
carpeta que este.
"""
from dataclasses import dataclass, field
from enum import Enum


class Modo(Enum):
    FALTANTES = "faltantes"
    TODO = "todo"


@dataclass
class Plan:
    a_descargar: list = field(default_factory=list)  # [(ArchivoCamara, destino abs)]
    ya_en_biblioteca: int = 0
    importadas_antes: int = 0  # ya importadas y borradas despues (solo FALTANTES las salta)

    @property
    def bytes_totales(self):
        return sum(a.tamano for a, _ in self.a_descargar)


def planificar(archivos_camara, biblioteca, modo):
    indice = biblioteca.indice()
    registro = biblioteca.registro()
    plan = Plan()
    for a in archivos_camara:
        if a.nombre in indice:
            plan.ya_en_biblioteca += 1
        elif modo is Modo.FALTANTES and a.nombre in registro:
            plan.importadas_antes += 1
        else:
            destino = biblioteca.abs(biblioteca.carpeta_importacion(a.nombre)) / a.nombre
            plan.a_descargar.append((a, destino))
    return plan


def ejecutar(plan, camara, biblioteca, progreso=None, cancelado=None, hechas=None):
    """Descarga lo planificado. Devuelve la lista de rutas descargadas.

    progreso(indice, total, archivo, bytes_archivo, bytes_acumulados)
    Cada foto se registra apenas termina, asi que si se cancela o se corta
    la conexion lo ya bajado queda registrado. Si se pasa `hechas`, cada ruta
    terminada se agrega ahi, para conocerlas aunque se corte con excepcion.
    """
    hechas = [] if hechas is None else hechas
    acumulado = 0
    total = len(plan.a_descargar)
    for i, (archivo, destino) in enumerate(plan.a_descargar):
        def cb(n, i=i, archivo=archivo):
            if progreso:
                progreso(i, total, archivo, n, acumulado + n)
        camara.descargar(archivo, destino, progreso=cb, cancelado=cancelado)
        biblioteca.registrar_importadas([(archivo.nombre, archivo.tamano)])
        acumulado += archivo.tamano
        hechas.append(destino)
    return hechas
