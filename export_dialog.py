# -*- coding: utf-8 -*-
"""export_dialog.py - finestra di esportazione del profilo (immagine o DXF)."""
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit, QPushButton,
    QHBoxLayout, QFileDialog, QDialogButtonBox, QLabel, QSpinBox
)

from .ui_style import apply_stylesheet


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        apply_stylesheet(self)
        self.setWindowTitle(self.tr("Esporta profilo"))
        self.resize(420, 180)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._opzioni = [
            (self.tr("Immagine PNG"), ".png"),
            (self.tr("Immagine JPG"), ".jpg"),
            (self.tr("Immagine SVG"), ".svg"),
            (self.tr("Immagine PDF"), ".pdf"),
            (self.tr("DXF 2D (sezione)"), ".dxf"),
            (self.tr("DXF 3D (coordinate reali)"), ".dxf"),
        ]
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItems([t for t, _ in self._opzioni])
        self.tipo_combo.currentIndexChanged.connect(self._aggiorna_estensione)
        form.addRow(self.tr("Formato:"), self.tipo_combo)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        browse_btn = QPushButton(self.tr("Sfoglia…"))
        browse_btn.setObjectName("browseButton")
        browse_btn.clicked.connect(self._sfoglia)

        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)
        form.addRow(self.tr("File di destinazione:"), path_row)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        form.addRow(self.tr("Risoluzione (DPI, solo immagini):"), self.dpi_spin)

        layout.addLayout(form)
        self.info_label = QLabel(
            self.tr("Nota: il formato DWG nativo richiede software proprietario (AutoCAD / ODA File "
                    "Converter). Il DXF generato è pienamente compatibile e apribile/convertibile in DWG.")
        )
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("dialogInfo")
        layout.addWidget(self.info_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )

        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)

        if ok_button:
            ok_button.setObjectName("exportOkButton")

        if cancel_button:
            cancel_button.setObjectName("exportCancelButton")

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    def _estensione_corrente(self):
        idx = self.tipo_combo.currentIndex()
        return self._opzioni[idx][1] if 0 <= idx < len(self._opzioni) else ".png"

    def _aggiorna_estensione(self):
        if self.path_edit.text():
            base, _ = self._split_ext(self.path_edit.text())
            self.path_edit.setText(base + self._estensione_corrente())

    @staticmethod
    def _split_ext(path):
        import os
        root, ext = os.path.splitext(path)
        return root, ext

    def _sfoglia(self):
        ext = self._estensione_corrente()
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Esporta profilo"), f"profilo{ext}",
                                               f"{self.tr('File')} (*{ext})")
        if path:
            if not path.lower().endswith(ext):
                path += ext
            self.path_edit.setText(path)

    def get_selection(self):
        idx = self.tipo_combo.currentIndex()
        # indice fisso: 0=PNG 1=JPG 2=SVG 3=PDF 4=DXF2D 5=DXF3D — non dipende dal testo tradotto
        is_dxf = idx >= 4
        dxf_mode = None
        if is_dxf:
            dxf_mode = "2D" if idx == 4 else "3D"
        return {
            "path": self.path_edit.text(),
            "is_dxf": is_dxf,
            "dxf_mode": dxf_mode,
            "dpi": self.dpi_spin.value(),
        }
