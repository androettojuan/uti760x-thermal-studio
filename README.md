# UTi760x Thermal Studio

App de escritorio para analizar y organizar las imágenes de la cámara termográfica
**UNI-T UTi760x**. Lee los datos radiométricos reales que la cámara guarda dentro
de cada `.jpg` (640×512 temperaturas), no solo la imagen que se ve en pantalla.

**Qué hace hoy:**
- **Visor:** temperatura bajo el cursor, máxima / mínima / centro marcadas, las
  paletas de la cámara, rango de colores ajustable y fijo entre fotos para comparar.
- **Importación por WiFi:** se conecta al FTP de la cámara y trae solo las fotos
  nuevas (o todas), con progreso y cancelación, sin duplicar nunca.
- **Biblioteca:** carpetas propias (por ejemplo `Subestación Norte\Tablero A`),
  galería con miniaturas y arrastrar y soltar para organizar.

Precisión: la conversión a grados coincide con el export del software de UNI-T
con un error típico de ±0,4 °C (máximo 0,93 °C) en el rango −13 a 52 °C. Fuera de
ese rango la app avisa que los valores son aproximados.

### Uso

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-app.txt     # en Windows: .venv\Scripts\pip
.venv/bin/python -m thermal_studio                # opcional: ruta a una foto .jpg
.venv/bin/python -m pytest tests                  # tests
```

Para importar desde la cámara: conectá la PC al WiFi de la cámara y activá el FTP
en la cámara. Por defecto la app usa `192.168.32.1:2121` con usuario y contraseña
`admin` / `admin` (se cambia en *Cámara → Configurar conexión…*). Las fotos se
guardan en `Documentos\Termografías`.

El código está en `thermal_studio/`: `core/` (lectura del formato, biblioteca,
importación; sin dependencias de Qt) y `ui/` (PySide6 + pyqtgraph).

## Licencia

MIT © 2026 Juan Manuel Androetto. Ver [LICENSE](LICENSE).
