"""Paletas a partir de la barra de colores que la camara dibuja en cada foto.

La barra va de abajo (frio) a arriba (caliente). Se ubica por renglones casi
uniformes a lo ancho, y se toma la mediana de todas las fotos de una misma
paleta (asi los textos superpuestos en alguna foto no cuentan).
    PYTHONPATH=. .venv/bin/python herramientas/paletas/barra.py <carpeta>
"""
import collections, glob, io, json, os, sys
import numpy as np
from PIL import Image
from thermal_studio.core.uti760x import Uti760xFile

X0, X1 = 1192, 1220      # columnas interiores de la barra en un render de 1280x1024
Y0, Y1 = 60, 960         # zona donde buscarla

def perfil(im):
    """256 colores de abajo hacia arriba, o None si no se encuentra la barra."""
    if im.size != (1280, 1024):
        im = im.resize((1280, 1024), Image.BICUBIC)
    a = np.asarray(im, float)[Y0:Y1, X0:X1]
    uniforme = a.std(axis=1).sum(1) < 18
    # tramo uniforme mas largo = la barra
    mejor, ini = (0, 0), None
    for y, ok in enumerate(list(uniforme) + [False]):
        if ok and ini is None:
            ini = y
        elif not ok and ini is not None:
            if y - ini > mejor[1] - mejor[0]:
                mejor = (ini, y)
            ini = None
    y0, y1 = mejor
    if y1 - y0 < 600:
        return None
    y0, y1 = y0 + 10, y1 - 10        # sacar las puntas redondeadas y su borde
    filas = np.median(a[y0:y1], axis=1)[::-1]   # de abajo (frio) a arriba
    # Puntas: si el tramo arrastro algo pegado a la barra (borde, caja de texto),
    # aparece como un salto brusco de color; se corta ahi
    salto = np.abs(np.diff(filas, axis=0)).sum(1)
    tipico = np.median(salto) + 1
    ini, fin = 0, len(filas)
    while ini < 15 and salto[ini] > 12 * tipico:
        ini += 1
    while fin > len(filas) - 15 and salto[fin - 2] > 12 * tipico:
        fin -= 1
    filas = filas[ini + 1 if ini else 0:fin - 1 if fin < len(filas) else fin]
    x = np.linspace(0, len(filas) - 1, 256)
    return np.stack([np.interp(x, np.arange(len(filas)), filas[:, c]) for c in range(3)], 1)

carpeta = sys.argv[1]
fs = sorted(f for f in glob.glob(carpeta + "/**/*.jpg", recursive=True) if ".thermal" not in f)
por_paleta = collections.defaultdict(list)
for f in fs:
    try:
        u = Uti760xFile(f)
        clave = "%s_%s" % (u.params.get("chooseColor"), u.params.get("colorReverse"))
        pr = perfil(Image.open(io.BytesIO(u.render_jpeg())).convert("RGB"))
    except Exception as e:
        print("salteo", os.path.basename(f), e); continue
    if pr is not None:
        por_paleta[clave].append(pr)
out = {}
for clave, perfiles in por_paleta.items():
    p = np.median(np.array(perfiles), axis=0)
    # Ultima limpieza de puntas sobre la paleta final: un salto mucho mayor que
    # los normales en los extremos se reemplaza por el color vecino
    salto = np.abs(np.diff(p, axis=0)).sum(1)
    tope = 8 * (np.median(salto) + 1)
    for i in range(6, -1, -1):
        if salto[i] > tope:
            p[i] = p[i + 1]
    for i in range(len(p) - 7, len(p) - 1):
        if np.abs(p[i + 1] - p[i]).sum() > tope:
            p[i + 1] = p[i]
    disp = np.median(np.abs(np.array(perfiles) - p).sum(2))
    print("paleta %s: barra en %d fotos, diferencia mediana entre fotos %.1f" % (clave, len(perfiles), disp))
    out[clave] = {"fotos": len(perfiles), "lut": p.round().astype(int).tolist()}
json.dump(out, open(os.path.join(os.path.dirname(__file__), "barras.json"), "w"))
