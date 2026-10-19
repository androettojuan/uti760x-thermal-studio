# Formato de archivo de la UNI-T UTi760x

Ingenieria inversa hecha el 2026-09-18 sobre 5 fotos de la camara (SN
ATI3B25450008, capturas del 2026-06-11) y un CSV exportado del software de UNI-T.

Parser: `thermal_studio/core/uti760x.py`

## Estructura del archivo

    [JPEG completo, hasta FFD9]   <- el render con overlay, como se ve en pantalla
    [JSON UTF-8]                  <- todos los datos crudos, en base64
    [uint32 little-endian]        <- longitud del JSON
    [20 bytes]                    <- nombre del modelo, "UTi760X" + padding \x00

El footer son 24 bytes al final del archivo. Para ubicar el JSON: leer los
ultimos 24 bytes, sacar la longitud, y el JSON arranca en
`len(archivo) - 24 - longitud`. Verificado exacto en los 5 archivos.

Que un visor de imagenes abra el .jpg sin quejarse es justamente el riesgo: el
JPEG esta completo y bien formado, asi que cualquier programa que lo reguarde
tira el bloque JSON a la basura sin avisar.

## Campos de `JSON["saveImage"]`

| Campo | Tamano | Que es |
|---|---|---|
| `tempData` | 655360 B | **640x512 uint16 LE. Radiometrico.** Fila-mayor, fila 0 arriba. |
| `thermalImageData` | 327680 B | 640x512 uint8, imagen termica en gris sin overlay |
| `hdCameraImageData` | ~300-560 kB | JPEG con EXIF de la camara visible |
| `cameraImageData` | 1133568 B | sin identificar |
| `analyzeData` | str JSON | anotaciones hechas en camara (vacio en las muestras) |
| `smartMeterData` | str JSON | vacio en las muestras |
| `parameterSetting` | dict 41 claves | parametros de captura |
| `parameterSetting.lensInfo` | dict 144 claves | calibracion de fabrica |

### `parameterSetting`

`ems` (emisividad), `reflexTemp` (temp reflejada), `tempAir`, `tempEnv`, `hum`
(humedad %), `distance` (m), `airTrans` (transmisividad), `chooseColor` (indice
de paleta), `colorReverse`, `customColorData`, `imageMode`, `isothermalType`,
`pipOffsetX/Y`, `pipScale`, `pipTrans`, `mixTrans` (opacidad de fusion),
`realFPA` (temperatura del sensor), `unit`, `irEdgeOn`, `laserOn`, `lensType`.

### `lensInfo`

Tablas de calibracion radiometrica de fabrica: `diffTable_N_0/1` (24 pares
temperatura -> valor de gris, de -50 a 180 C), `setTempN` / `recTempN` (puntos de
calibracion: setpoint contra lectura), `envCompensationN`, `bDiffTableN`,
`bGaryCompensationN`, `lenGrayN`, `baseTemp`, y las condiciones de calibracion
(`calemis`, `calReftemper`, `calFPA`, `calHum`, `caliDistance`).

Los `diffTable` estan en otra escala que los valores de `tempData` (van de 0 a
1330, contra 2786..6157 observados), asi que no se pueden usar directo.

## Conversion raw -> grados

Dentro de una imagen, el mapeo `tempData` -> temperatura es una **funcion
exacta**. Comprobado en tres imagenes cruzando los 327680 pixeles contra su CSV
exportado: 1067 / 466 / 949 valores raw distintos, **cero colisiones** en las
tres.

Pero **no existe una curva unica que valga para todas las imagenes**. Cruzando
las LUT exactas entre si, un mismo raw da temperaturas distintas segun la foto:

| par | raw en comun | identicos | dif max |
|---|---|---|---|
| 12820 vs 12954 | 466 | 0 | 0.89 C |
| 12820 vs 13134 | 712 | 0 | 1.35 C |
| 12954 vs 13134 | 466 | 0 | 1.09 C |

Hay una variacion real de imagen a imagen, de hasta ~1.3 C. Se intento explicar
y no se logro:

- **Offset lineal en `realFPA`** (temperatura del sensor): ajusta 12954 y 13134
  a +-0.12 C, y el corrimiento medido (1.05 C) casi iguala la diferencia de FPA
  (1.01 C), lo que parecia prometedor. Pero falla en 12820 por 2.5 C, y ahi el
  error ni siquiera es constante: va de -2.5 a -0.8.
- **Corrimiento en el dominio raw**: ajusta las tres a +-0.51 C, pero los
  corrimientos (0 / -16 / +32) no siguen a `realFPA` (19.32 / 20.47 / 21.48) ni
  a ningun otro campo. No se puede predecir para una imagen nueva.
- Las tres fotos tienen **`lensInfo` identico** y los mismos parametros de
  captura (ems 0.95, reflejada 25, distancia 0.6, humedad 55). Lo unico que
  difiere en todo el archivo es `realFPA`. **Nada en el archivo explica la
  diferencia.**

Descartado: que `ver.CSV` fuera un export defectuoso. Sus valores coinciden con
lo que mostraba la pantalla de la camara (-13.5 / 11.0 / -9.0), asi que es fiel.

### Lo que se usa

Una sola cubica global, ajustada sobre las tres LUT completas mas tres anclas
leidas del overlay de la foto caliente (raw 6157 = 51.6 C). Las anclas importan:
sin ellas el extremo alto queda sin datos y la extrapolacion se dispara. Un
ajuste anterior hecho solo con el rango frio erraba **14 C** en ese punto.

    T = -75.2196 + 0.0176357*r + 2.61845e-6*r^2 - 3.46673e-10*r^3

    rango    : raw 2786..6157  (-13.5 a 51.6 C)
    rms      : 0.43 C
    err max  : 0.93 C

Validacion fuera de muestra con `IMG20260611213109HD.jpg`, que no tiene CSV:
error -0.27 C en el maximo y +0.77 C en el minimo contra la pantalla. Las cinco
fotos dan max/min/centro dentro de +-0.9 C de lo que muestra la camara.

### Para mejorarlo

Hacen falta CSVs de escenas **calientes** (50-150 C). Arriba de 25 C hay tres
anclas leidas a ojo de un overlay y nada mas.

### Emisividad

`tempData` viene **sin** corregir por emisividad: la camara la aplica al
mostrar. Con la misma escena a 0.95 y a 0.80 (`IMG20261019191426HD.jpg` y
`IMG20261019191449HD.jpg`), los crudos casi no cambian y la pantalla si (max
29.7 -> 34.6, min 12.4 -> 10.2). La tabla de fabrica dice `calemis` 0.95 y
`calReftemper` 25, igual que todas las lecturas de la calibracion, asi que el
modelo da la temperatura a 0.95 / 25 C y la app la lleva a la de la foto con

    medida = e * S(T_objeto) + (1 - e) * S(T_reflejada)

usando la parte de Planck del modelo como S. Contra la pantalla a 0.80: max
+0.2, min -0.7, centro -0.4 C (sin corregir: -1.3, +2.0, +0.1). Esto deja
recalcular con otra emisividad despues de sacar la foto.

## Cosas verificadas contra la pantalla de la camara

`IMG20260611212820HD.jpg`: la pantalla decia max 11.0, min -13.5, centro -9.0.
El parser da max 10.96 en (fila 405, col 158), min -13.51 en (fila 4, col 394),
centro -9.07 en (256, 320). Las posiciones caen exactamente sobre los marcadores
rojo y verde que dibuja la camara. Confirma orden fila-mayor y fila 0 = arriba.

## Variantes de esquema

`IMG20260611213042HD.jpg` tiene otro esquema: claves raiz `QR_Code`,
`mergeImage`, `seconds` en vez de `ifChoose`/`saveImageID`/`saveMediaID`, y un
`parameterSetting` de 43 claves con `brightNess`, `contrast`, `sharpness`,
`isShowMaxTemp`, `tempDew`, `pipRect`, sin `lensInfo`. Es 640x512 en vez de
1280x1024 y parece regenerado por el software de PC / la app del telefono, no
sacado directo de la camara. **El parser tiene que tolerar las dos variantes.**

## 2026-10-15 — La conversion depende de realFPA (resuelto)

Con fotos sacadas con el sensor a ~37.5 C (antes 16-28 C) la cubica global
erraba ~15 C (IMG20261015225351: pantalla max 31.5 / centro 26.8, la app daba
15.0 / ~11). El crudo de tempData NO es absoluto: depende de la temperatura del
sensor. Se reajusto con 222 lecturas de max/min del overlay de 164 fotos
(FPA 16.1-38.4 C, -19 a 81 C) + las LUT de los CSV (peso 0.02):

    r = (raw-4000)/1000, f = (fpa-25)/10
    T = c0 + c1 r + c2 r^2 + c3 r^3 + c4 f + c5 f r
    rms 0.49 C, max 1.32 C; octubre: rms 0.30, max 0.52

Agregar f^2 o f*r^2 no mejora y extrapola peor (validacion dejando un dia
afuera). La variacion residual de ~0.5 C por foto sigue sin explicar.
tempMode 1 (rango alto, lenGray0=3879) es otra curva: 2 fotos (175.1 y 180.3 C
en pantalla), sin calibrar. Pantalla muestra "<-20,0" por debajo de -20 C.
Lecturas transcriptas: indice de foto (orden de ruta en la biblioteca) + max/min.

## 2026-10-16 — Forma de Planck + tabla de fabrica (resuelto el extremo alto)

La cubica extrapolaba mal arriba de 81 C: IMG20261016102003 (raw max 9519,
FPA 22.7) daba 104.7 C con la camara en 95.9. Cambios:

- Modelo de Planck con corrimiento y ganancia segun FPA (7 parametros):
  raw = R(1+g f)/(exp(B/T_K)-F) + O0 + O1 f + O2 f^2, f=(fpa-25)/10.
- **La tabla de fabrica sirve**: lensInfo.lenGray0..4 = raw a setTemp0..4
  (-10, 0, 20, 75, 120 C) con el sensor a calFPA (40.27). Los modelos
  ajustados SIN ella ya la reproducian (contra setTemp, no recTemp), asi
  que se usa como dato con peso 1. Ancla el extremo alto hasta 120 C.
- Resultado: rms 0.54, max 2.25 (una lectura de julio), LODO max 2.5;
  95.9 -> 94.6, 77.5 -> 77.7. Monotona de raw 1400 a 16000 para FPA 10-45.
- Datos persistentes: herramientas/calibracion/lecturas_overlay.csv (por nombre de foto,
  ya no por indice) y herramientas/calibracion/calibrar.py para reajustar.
- Pendiente: lenGray12..16 (2318, 2636, 3349, 6239, 9516) parece otra tabla
  (otra FPA u otro rango); sin identificar.

## 2026-10-16 — Congelador y ganancia segun FPA

Cuatro fotos de un congelador (-11 a +10 C) con el sensor a 30,4 C, una zona de
FPA sin datos hasta entonces. El modelo de 7 parametros daba ~0,7 C menos que
la pantalla, parejo en todo el rango de la foto. Se agrego un termino de
ganancia cuadratico en FPA (8 parametros): rms 0,55 -> 0,47 C, maximo 2,25 ->
1,31 C, validacion dejando un dia afuera 2,40 -> 1,66 C.

El sesgo por FPA no tiene tendencia (-0,4 / +0,3 / -0,3 / -0,7 / +0,1 C en
tramos de 16 a 39 C) y las 12 lecturas nuevas son de una sola sesion de 20 s:
es la variacion entre sesiones ya conocida (hasta ~1 C), probablemente la
autocalibracion del obturador. Para separarla de un efecto real de FPA hacen
falta mas sesiones con el sensor entre 29 y 36 C.

### 19/10/2026: 100-123 C y otra sesion de freezer

Dos fotos de 100 y 123 C en rango normal (raw hasta 11716): el modelo daba
~1 C de mas arriba de 90 C. Reajustado: arriba de 50 C rms 0,62 -> 0,37 C,
maximo 1,10 -> 0,70 C. Rango validado ahora -19 a 123 C.

Cinco fotos de freezer con el sensor a 22 C: el modelo da +0,6 a +1,2 C sobre
la pantalla, parejo. Sesiones viejas con el sensor a 18-21 C daban -1,5 C en
el mismo rango, y entre los metadatos de las sesiones no cambia nada salvo
realFPA, IDs y fecha. Reajustar con estas lecturas no mejora nada (rms 0,49
igual), asi que se dejaron los coeficientes: es la variacion de la camara
entre sesiones, no un error del modelo, y no se puede corregir desde el
archivo. Queda dentro de la exactitud que declara la camara (+-2 C).
