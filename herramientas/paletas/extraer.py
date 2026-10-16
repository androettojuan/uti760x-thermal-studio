"""Extrae las paletas de la camara de sus propias fotos.

Cada foto trae thermalImageData (gris 0-255 que la camara colorea) y el render
JPEG final, y en parameterSetting el numero de paleta (chooseColor). Para cada
nivel de gris se toma la mediana del color de esos pixeles en el render.
Uso (desde la raiz del repo):
    PYTHONPATH=. .venv/bin/python herramientas/paletas/extraer.py <carpeta con fotos>
"""
import collections, glob, io, json, os, sys
import numpy as np
from PIL import Image
from thermal_studio.core.uti760x import Uti760xFile

carpeta = sys.argv[1]
fs = sorted(f for f in glob.glob(carpeta + "/**/*.jpg", recursive=True) if ".thermal" not in f)
acum = collections.defaultdict(lambda: [[] for _ in range(256)])
usadas = collections.Counter()
for f in fs:
    try:
        u = Uti760xFile(f)
        gris = u.thermal_gray()
        if gris is None:
            continue
        p = u.params
        clave = (p.get("chooseColor"), p.get("colorReverse"))
        im = Image.open(io.BytesIO(u.render_jpeg())).convert("RGB")
    except Exception as e:
        print("salteo", os.path.basename(f), e); continue
    if im.size != (640, 512):
        im = im.resize((640, 512), Image.BOX)   # promedio 2x2: mismo pixel del sensor
    rgb = np.asarray(im).reshape(-1, 3)
    g = gris.ravel()
    # muestreo para no juntar millones de pixeles por paleta
    idx = np.random.default_rng(0).choice(g.size, 60000, replace=False)
    for i in idx:
        acum[clave][g[i]].append(rgb[i])
    usadas[clave] += 1

salida = {}
for clave, por_nivel in acum.items():
    lut = np.full((256, 3), np.nan)
    cuenta = np.array([len(v) for v in por_nivel])
    for nivel, v in enumerate(por_nivel):
        if len(v) >= 30:
            lut[nivel] = np.median(np.array(v), axis=0)
    ok = ~np.isnan(lut[:, 0])
    x = np.arange(256)
    for c in range(3):
        lut[:, c] = np.interp(x, x[ok], lut[ok, c])
    # dispersion: cuanto varian los pixeles de un mismo nivel (calidad del ajuste)
    disp = [np.median(np.abs(np.array(v) - lut[n]).sum(1)) for n, v in enumerate(por_nivel) if len(v) >= 30]
    print("paleta %s: %d fotos, niveles con datos %d/256, desvio mediano %.1f" % (
        clave, usadas[clave], ok.sum(), np.median(disp)))
    salida["%s_%s" % clave] = {"fotos": usadas[clave], "niveles_medidos": int(ok.sum()),
                               "lut": lut.round().astype(int).tolist()}
json.dump(salida, open(os.path.join(os.path.dirname(__file__), "extraidas.json"), "w"))
