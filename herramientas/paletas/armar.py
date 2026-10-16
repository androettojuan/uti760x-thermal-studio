"""Arma thermal_studio/core/palettes.json con las paletas de la UTi760x.

Fuentes (sacadas de fotos de la camara del usuario, ver extraer.py/barra.py):
  barras.json             mediana de la barra de color de muchas fotos
                          radiometricas, por numero de paleta (chooseColor)
  nuevas_sin_datos.json   barra de las fotos del 16/10/2026 22:24, una por
                          paleta (JPEG sin datos, identificadas a ojo)
    PYTHONPATH=. .venv/bin/python herramientas/paletas/armar.py
"""
import json, os
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
barras = json.load(open(os.path.join(AQUI, "barras.json")))
nuevas = json.load(open(os.path.join(AQUI, "nuevas_sin_datos.json")))

FUENTES = {  # id -> lut (de frio a caliente)
    "iron": barras["0_127"]["lut"],
    "rainbow": barras["2_127"]["lut"],
    "rainbow_hc": barras["3_127"]["lut"],
    "lava": nuevas["222415"],
    "white_hot": nuevas["222423"],
    "black_hot": nuevas["222427"],
    "highlight": nuevas["222430"],
    "red": nuevas["222433"],
    "green": nuevas["222437"],
    "blue": nuevas["222439"],
}


def limpiar_puntas(p, n=8, factor=6):
    """Los extremos de la barra arrastran a veces el borde o una caja de texto:
    un salto mucho mayor que los normales se reemplaza por el color vecino."""
    p = np.array(p, float)
    salto = np.abs(np.diff(p, axis=0)).sum(1)
    tope = factor * (np.median(salto) + 2)
    for i in range(n, -1, -1):
        if np.abs(p[i] - p[i + 1]).sum() > tope:
            p[i] = p[i + 1]
    for i in range(len(p) - n - 1, len(p) - 1):
        if np.abs(p[i + 1] - p[i]).sum() > tope:
            p[i + 1] = p[i]
    return np.clip(p.round(), 0, 255).astype(int)


salida = {k: limpiar_puntas(v).tolist() for k, v in FUENTES.items()}
# rainbow_hc: en las 6 fotos con esa paleta la barra tocaba la caja del valor
# maximo y los ultimos tonos salen celestes; el extremo real es rosado casi blanco
salida["rainbow_hc"][-6:] = [salida["rainbow_hc"][-7]] * 6
for k, v in salida.items():
    s = np.abs(np.diff(np.array(v), axis=0)).sum(1)
    print("%-11s primero %-16s ultimo %-16s salto max %3d en %d" % (k, v[0], v[-1], s.max(), s.argmax()))
destino = os.path.join(AQUI, "..", "..", "thermal_studio", "core", "palettes.json")
with open(destino, "w") as f:
    json.dump(salida, f, separators=(",", ":"))
print("escrito", os.path.normpath(destino))
