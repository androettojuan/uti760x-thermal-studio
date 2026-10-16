"""Dialogo para armar el informe PDF: datos de la caratula y que fotos van."""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QRadioButton,
    QVBoxLayout,
)

from .informe import DatosInforme
from .widgets import etiqueta

ABIERTA, ELEGIDAS, CARPETA = "abierta", "elegidas", "carpeta"


class DialogoInforme(QDialog):
    """`opciones`: lista de (clave, texto, cantidad de fotos); las de 0 fotos
    se muestran deshabilitadas."""

    def __init__(self, opciones, instalacion_sugerida="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crear informe PDF")
        self.setMinimumWidth(480)
        self.settings = QSettings("ThermalStudio", "ThermalStudio")
        v = QVBoxLayout(self)
        v.setSpacing(12)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.titulo = QLineEdit(self.settings.value("informe/titulo", "Informe termográfico"))
        self.instalacion = QLineEdit(instalacion_sugerida)
        self.instalacion.setPlaceholderText("Ej.: Subestación Norte, cliente, tablero…")
        self.inspector = QLineEdit(self.settings.value("informe/inspector", ""))
        self.inspector.setPlaceholderText("Quién hizo la inspección")
        form.addRow("Título", self.titulo)
        form.addRow("Instalación", self.instalacion)
        form.addRow("Inspector", self.inspector)
        v.addLayout(form)

        v.addWidget(etiqueta("FOTOS", "seccion"))
        self.grupo = QButtonGroup(self)
        elegida = None
        for clave, texto, n in opciones:
            rb = QRadioButton("%s (%d foto%s)" % (texto, n, "" if n == 1 else "s") if n
                              else texto)
            rb.setEnabled(n > 0)
            rb.clave = clave
            self.grupo.addButton(rb)
            v.addWidget(rb)
            if n > 0 and elegida is None:
                elegida = rb
        if elegida:
            elegida.setChecked(True)

        self.visible = QCheckBox("Incluir la foto visible al lado de la térmica")
        self.visible.setChecked(self.settings.value("informe/visible", True, type=bool))
        v.addWidget(self.visible)
        v.addWidget(etiqueta("Las fotos salen con la paleta y el contraste que estás usando, "
                             "con sus mediciones y notas.", "suave"))

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Crear PDF…")
        botones.button(QDialogButtonBox.Ok).setEnabled(elegida is not None)
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        v.addWidget(botones)

    def fuente(self):
        b = self.grupo.checkedButton()
        return b.clave if b else None

    def datos(self):
        d = DatosInforme(titulo=self.titulo.text().strip() or "Informe termográfico",
                         instalacion=self.instalacion.text().strip(),
                         inspector=self.inspector.text().strip(),
                         incluir_visible=self.visible.isChecked())
        self.settings.setValue("informe/titulo", d.titulo)
        self.settings.setValue("informe/inspector", d.inspector)
        self.settings.setValue("informe/visible", d.incluir_visible)
        return d
