# UTi760x Thermal Studio

App de escritorio para analizar, organizar y documentar las imágenes de la cámara
termográfica **UNI-T UTi760x**. Lee los datos radiométricos reales que la cámara guarda
dentro de cada `.jpg` (640×512 temperaturas), no solo la imagen que se ve en pantalla.

> **English:** desktop app to analyze, organize and report thermal images from the
> **UNI-T UTi760x** camera, using the real per-pixel temperatures stored in each photo.
> Wi-Fi import, measurements with ΔT vs. a reference, comparison over time, PDF reports.
> Available in English, Spanish and Brazilian Portuguese — the installer asks for your
> language. Download it from [Releases](https://github.com/androettojuan/uti760x-thermal-studio/releases/latest).

## Qué hace

- **Importación por WiFi:** se conecta al FTP de la cámara y trae solo las fotos nuevas,
  con progreso y sin duplicar nunca. Avisa si la cámara no le dio dirección a la PC.
- **Biblioteca:** una carpeta por lugar (por ejemplo `Subestación Norte\Tablero A`),
  galería con miniaturas y arrastrar y soltar para organizar.
- **Visor:** temperatura bajo el cursor, máxima, mínima y centro marcadas, las 10 paletas
  de la cámara, contraste «como la cámara» o lineal, foto visible en grande.
- **Mediciones:** puntos, líneas con perfil de temperatura y áreas, con **ΔT contra una
  referencia** (lo que menos cambia entre verano e invierno). Notas por foto.
- **Seguimiento en el tiempo:** comparación lado a lado de dos fechas con la misma escala
  y gráfico de evolución de cada lugar, siguiendo cada medición por su nombre.
- **Informe PDF** con carátula, observaciones, resumen y una página por foto; exportación
  a PNG y CSV (listo para Excel).
- **Idiomas:** español, inglés y portugués de Brasil. El instalador pregunta el idioma y
  se cambia en *Ver → Idioma*. Números, fechas y CSV siguen el formato de cada idioma.
- **Celsius o Fahrenheit** (*Ver → Unidad de temperatura*); Celsius por defecto.

## Precisión

La conversión de los datos crudos a grados usa la forma física de la radiación (Planck),
corregida por la temperatura del sensor, y está ajustada con 231 lecturas de la pantalla
de la cámara, exports del software de UNI-T y la tabla de calibración de fábrica que trae
cada foto: **±0,5 °C típico entre −19 y 120 °C**. Fuera de ese rango, o en el rango alto
de la cámara, la app avisa que los valores son aproximados. El detalle está en
[`docs/formato_uti760x.md`](docs/formato_uti760x.md).

## Instalación (Windows)

Descargá `ThermalStudio-X.Y.Z-instalador.exe` desde
[Releases](https://github.com/androettojuan/uti760x-thermal-studio/releases/latest) y
ejecutalo. Se instala sin permisos de administrador. Como el instalador no está firmado,
Windows puede mostrar «Windows protegió su PC»: clic en *Más información* → *Ejecutar de
todas formas*.

Para importar desde la cámara: pasá las fotos a la carpeta FTP de la cámara, activá su
WiFi y su FTP y conectá la PC a esa red. Por defecto la app usa `192.168.32.1:2121` con
usuario y contraseña `admin` / `admin` (se cambia en *Cámara → Configurar conexión…*).
Las fotos se guardan en `Documentos\Termografías`. La guía rápida está en *Ayuda* (F1).

## Desde el código

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-app.txt     # en Windows: .venv\Scripts\pip
.venv/bin/python -m thermal_studio                # opcional: ruta a una foto .jpg
.venv/bin/python -m pytest tests                  # tests
```

- `thermal_studio/core/`: formato de la cámara, conversión a grados, biblioteca,
  importación, mediciones y exportación. Sin dependencias de Qt.
- `thermal_studio/ui/`: interfaz (PySide6 + pyqtgraph) e informe PDF.
- `herramientas/`: scripts y datos con los que se sacaron las paletas y la calibración
  a partir de fotos de la cámara.
- `docs/formato_uti760x.md`: cómo está armado el archivo de la UTi760x.

Para publicar una versión: actualizar `__version__` en `thermal_studio/__init__.py` y subir
la etiqueta `vX.Y.Z`. GitHub Actions compila el instalador y crea el Release
(`.github/workflows/instalador-windows.yml`).

## Licencia

MIT © 2026 Juan Manuel Androetto. Ver [LICENSE](LICENSE).
