# -*- coding: utf-8 -*-

"""
Gestione dello stile locale di TopoProfile Studio.

Lo stylesheet viene applicato esclusivamente ai widget del plugin.
"""

import os

from qgis.PyQt.QtWidgets import (
    QDialog,
    QMessageBox,
    QInputDialog,
    QFileDialog,
)

from qgis.core import Qgis, QgsMessageLog


PLUGIN_NAME = "TopoProfile Studio"


def load_stylesheet():
    """Carica lo stylesheet locale del plugin."""

    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "style.qss"
    )

    if not os.path.isfile(path):
        QgsMessageLog.logMessage(
            f"style.qss NON TROVATO: {path}",
            PLUGIN_NAME,
            Qgis.Warning,
        )
        return ""

    try:
        with open(
            path,
            "r",
            encoding="utf-8-sig"
        ) as fh:
            stylesheet = fh.read()

        QgsMessageLog.logMessage(
            f"style.qss caricato: {path} ({len(stylesheet)} caratteri)",
            PLUGIN_NAME,
            Qgis.Info,
        )

        return stylesheet

    except Exception as exc:
        QgsMessageLog.logMessage(
            f"Errore caricando style.qss: {exc}",
            PLUGIN_NAME,
            Qgis.Critical,
        )
        return ""


def apply_stylesheet(widget):
    """
    Applica lo stylesheet esclusivamente al widget passato.
    Non modifica QApplication, QGIS o la finestra principale.
    """

    stylesheet = load_stylesheet()

    if not stylesheet:
        QgsMessageLog.logMessage(
            f"Stylesheet vuoto per {widget.__class__.__name__}",
            PLUGIN_NAME,
            Qgis.Warning,
        )
        return

    widget.setStyleSheet(stylesheet)

    QgsMessageLog.logMessage(
        f"Stylesheet applicato a "
        f"{widget.__class__.__name__} "
        f"(objectName='{widget.objectName()}')",
        PLUGIN_NAME,
        Qgis.Info,
    )


def show_warning(parent, title, text):
    box = QMessageBox(
        QMessageBox.Icon.Warning,
        title,
        text,
        QMessageBox.StandardButton.Ok,
        parent
    )

    apply_stylesheet(box)

    return box.exec()


def show_information(parent, title, text):
    box = QMessageBox(
        QMessageBox.Icon.Information,
        title,
        text,
        QMessageBox.StandardButton.Ok,
        parent
    )

    apply_stylesheet(box)

    return box.exec()


def show_critical(parent, title, text):
    box = QMessageBox(
        QMessageBox.Icon.Critical,
        title,
        text,
        QMessageBox.StandardButton.Ok,
        parent
    )

    apply_stylesheet(box)

    return box.exec()


def ask_question(parent, title, text):
    box = QMessageBox(
        QMessageBox.Icon.Question,
        title,
        text,
        QMessageBox.StandardButton.Yes |
        QMessageBox.StandardButton.No,
        parent
    )

    apply_stylesheet(box)

    return box.exec()


def ask_text(parent, title, label, text=""):
    dialog = QInputDialog(parent)

    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setTextValue(text)

    apply_stylesheet(dialog)

    accepted = (
        dialog.exec() == QDialog.DialogCode.Accepted
    )

    return dialog.textValue(), accepted


def get_save_file_name(
    parent,
    title,
    filename="",
    filter_text=""
):
    dialog = QFileDialog(parent)

    dialog.setWindowTitle(title)
    dialog.setAcceptMode(
        QFileDialog.AcceptMode.AcceptSave
    )

    if filename:
        dialog.selectFile(filename)

    if filter_text:
        dialog.setNameFilter(filter_text)

    apply_stylesheet(dialog)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        files = dialog.selectedFiles()

        return (
            files[0] if files else "",
            dialog.selectedNameFilter()
        )

    return "", ""


def get_open_file_name(
    parent,
    title,
    directory="",
    filter_text=""
):
    dialog = QFileDialog(parent)

    dialog.setWindowTitle(title)
    dialog.setAcceptMode(
        QFileDialog.AcceptMode.AcceptOpen
    )

    if directory:
        dialog.setDirectory(directory)

    if filter_text:
        dialog.setNameFilter(filter_text)

    apply_stylesheet(dialog)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        files = dialog.selectedFiles()

        return (
            files[0] if files else "",
            dialog.selectedNameFilter()
        )

    return "", ""
