# -*- coding: utf-8 -*-
"""marker_dialog.py - finestra per aggiungere/modificare un marker identificativo sul profilo."""
from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox,
    QDialogButtonBox, QVBoxLayout
)

from .ui_style import apply_stylesheet


class MarkerDialog(QDialog):

    def __init__(self, distanza, quota, parent=None, etichetta="", categoria="litologico"):
        super().__init__(parent)
        apply_stylesheet(self)
        # Elenco categorie costruito qui (e non come attributo di classe) in modo che
        # self.tr(...) sia disponibile e le stringhe visualizzate siano traducibili.
        self.CATEGORIE = [
            (self.tr("Cambio litologico"), "litologico"),
            (self.tr("Faglia"), "faglia"),
            (self.tr("Sovrascorrimento"), "sovrascorrimento"),
            (self.tr("Piega"), "piega"),
            (self.tr("Limite"), "limite"),
            (self.tr("Sondaggio"), "sondaggio"),
            (self.tr("Prova"), "prova"),
            (self.tr("Piezometro"), "piezometro"),
            (self.tr("Livello"), "livello"),
            (self.tr("Altro"), "altro"),
        ]

        self.setWindowTitle(self.tr("Marker identificativo"))
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.dist_spin = QDoubleSpinBox()
        self.dist_spin.setRange(0, 10_000_000)
        self.dist_spin.setDecimals(2)
        self.dist_spin.setValue(distanza)
        form.addRow(self.tr("Distanza progressiva (m):"), self.dist_spin)

        self.quota_spin = QDoubleSpinBox()
        self.quota_spin.setRange(-10_000, 10_000)
        self.quota_spin.setDecimals(2)
        self.quota_spin.setValue(quota)
        form.addRow(self.tr("Quota (m):"), self.quota_spin)

        self.label_edit = QLineEdit(etichetta)
        self.label_edit.setPlaceholderText(self.tr("es. Faglia F1, contatto calcari/marne..."))
        form.addRow(self.tr("Etichetta:"), self.label_edit)

        self.cat_combo = QComboBox()
        for testo, val in self.CATEGORIE:
            self.cat_combo.addItem(testo, val)
        valori = [v for _, v in self.CATEGORIE]
        idx = valori.index(categoria) if categoria in valori else 0
        self.cat_combo.setCurrentIndex(idx)
        form.addRow(self.tr("Categoria:"), self.cat_combo)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )

        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)

        if ok_button:
            ok_button.setObjectName("markerOkButton")

        if cancel_button:
            cancel_button.setObjectName("markerCancelButton")

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_marker(self):
        return {
            "distanza": self.dist_spin.value(),
            "quota": self.quota_spin.value(),
            "etichetta": self.label_edit.text().strip() or self.tr("Marker"),
            "categoria": self.cat_combo.currentData(),
        }
