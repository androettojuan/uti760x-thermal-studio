"""Ajuste de la conversion raw -> C de la UTi760x (rango normal, tempMode 0).

Datos: herramientas/calibracion/lecturas_overlay.csv (lecturas de la pantalla de la camara)
+ las LUT exactas de los CSV de fotos/. Correr desde la raiz del repo:
    PYTHONPATH=. .venv/bin/python herramientas/calibracion/calibrar.py
"""
import glob, os, sys
import numpy as np
from thermal_studio.core.uti760x import Uti760xFile

PESO_FABRICA = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
BIB = "/mnt/c/Users/Usuario/Documents/Termografías"
rutas = {os.path.basename(f): f for f in glob.glob(BIB + "/**/*.jpg", recursive=True)
         if ".thermal" not in f}

def leer_csv(p):
    return np.array([[float(x) for x in l.strip().split(",") if x] for l in open(p) if l.strip()])

cache = {}
def datos_foto(n):
    if n not in cache:
        u = Uti760xFile(rutas[n]); r = u.temp_raw()
        cache[n] = (r, u.params["realFPA"], u.params.get("tempMode"))
    return cache[n]

R, F, T, W, DIA = [], [], [], [], []
for l in open("herramientas/calibracion/lecturas_overlay.csv"):
    if l.startswith("#") or not l.strip(): continue
    n, k, t = l.strip().split(";")
    r, fpa, tm = datos_foto(n)
    if tm: continue
    v = {"max": r.max(), "min": r.min(), "centro": r[256, 320]}[k]
    R.append(float(v)); F.append(fpa); T.append(float(t)); W.append(1.0 if k != "centro" else 0.5); DIA.append(n[3:11])
for c, img in [("ver", "212820"), ("54", "212954"), ("34", "213134")]:
    u = Uti760xFile("fotos/IMG20260611%sHD.jpg" % img); r = u.temp_raw().ravel(); t = leer_csv("fotos/%s.CSV" % c).ravel()
    for v in np.unique(r):
        R.append(float(v)); F.append(u.params["realFPA"]); T.append(float(t[r == v].mean())); W.append(0.02); DIA.append("csv" + img)
# Tabla de calibracion de fabrica (lensInfo, igual en todas las fotos):
# lenGray0..4 a setTemp0..4, medida con el sensor a calFPA
li = Uti760xFile(rutas["IMG20261016102003HD.jpg"]).params["lensInfo"]
for k in range(5):
    R.append(float(li["lenGray%d" % k])); F.append(li["calFPA"]); T.append(float(li["setTemp%d" % k]))
    W.append(PESO_FABRICA); DIA.append("fabrica")
R, F, T, W, DIA = map(np.array, (R, F, T, W, DIA))
lect = (W > 0.1) & (DIA != "fabrica")
fab = DIA == "fabrica"

def cubica(p, r, f):
    rs = (r - 4000) / 1000; fs = (f - 25) / 10
    return p[0] + p[1]*rs + p[2]*rs**2 + p[3]*rs**3 + p[4]*fs + p[5]*fs*rs

def planck(p, r, f):
    # raw = Rg * (1 + g1*fs) / (exp(B/Tk) - Fc) + O0 + O1*fs   ->  despejar T
    B, lnR, Fc, O0, O1, g1 = p
    fs = (f - 25) / 10
    s = np.exp(lnR) * (1 + g1 * fs) / np.maximum(r - (O0 + O1 * fs), 1e-3) + Fc
    return B / np.log(np.maximum(s, 1 + 1e-9)) - 273.15

def lm(fun, p0, r, f, t, w, it=400):
    p = np.array(p0, float); lam = 1e-2
    def res(p): return (fun(p, r, f) - t) * np.sqrt(w)
    e = res(p); c = e @ e
    for _ in range(it):
        J = np.empty((len(e), len(p)))
        for j in range(len(p)):
            d = 1e-6 * max(abs(p[j]), 1e-3); q = p.copy(); q[j] += d
            J[:, j] = (res(q) - e) / d
        A = J.T @ J; g = J.T @ e
        while True:
            try: dp = -np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), g)
            except np.linalg.LinAlgError: lam *= 10; continue
            q = p + dp; e2 = res(q); c2 = e2 @ e2
            if np.isfinite(c2) and c2 < c: p, e, c, lam = q, e2, c2, max(lam / 3, 1e-9); break
            lam *= 4
            if lam > 1e12: return p
        if np.abs(dp).max() < 1e-10: break
    return p

modelos = {
    "cubica": (cubica, [19.2, 20.66, -2.41, 0.289, 9.87, 1.11]),
    "planck": (planck, [1400.0, np.log(4e5), 1.0, 0.0, -300.0, 0.0]),
}
mejor = {}
for nombre, (fun, p0) in modelos.items():
    p = lm(fun, p0, R, F, T, W)
    if nombre == "planck":  # varios arranques de B
        cand = [lm(fun, [B, np.log(4e5 * B / 1400), 1.0, 0.0, -300.0, 0.0], R, F, T, W) for B in (900, 1200, 1400, 1700, 2200)]
        p = min(cand + [p], key=lambda q: np.nansum(W * (fun(q, R, F) - T) ** 2))
    e = fun(p, R, F) - T
    lodo = []
    for d in np.unique(DIA[lect]):
        m = DIA != d; q = lm(fun, p, R[m], F[m], T[m], W[m], it=150)
        mm = (DIA == d) & lect; lodo += list(fun(q, R[mm], F[mm]) - T[mm])
    lodo = np.array(lodo)
    print("        fabrica err", [round(float(x), 1) for x in e[fab]])
    peores = np.argsort(-np.abs(np.where(lect, e, 0)))[:4]
    print("        peores", [(round(float(R[i])), round(float(F[i]), 1), T[i], round(float(e[i]), 2)) for i in peores])
    alto = lect & (T > 50)
    print("%-7s lecturas rms %.2f max %.2f | >50C rms %.2f max %.2f | LODO rms %.2f max %.2f | csv max %.2f"
          % (nombre, np.sqrt((e[lect]**2).mean()), np.abs(e[lect]).max(), np.sqrt((e[alto]**2).mean()), np.abs(e[alto]).max(),
             np.sqrt((lodo**2).mean()), np.abs(lodo).max(), np.abs(e[~lect]).max()))
    print("        95,9 C ->", round(float(fun(p, np.array([9519.]), np.array([22.71]))[0]), 1),
          "| lenGray a FPA 40.27:", [round(float(x), 1) for x in fun(p, np.array([2394., 2703, 3405, 6248, 9481]), np.full(5, 40.27))],
          "(setTemp -10 0 20 75 120 / recTemp -6.95 0.67 16.74 65.58 106.18)")
    mejor[nombre] = p
    print("        params", [repr(float(x)) for x in p])
print("Pegar en TempConverter.COEF (variante con O2) despues de reajustar.")
