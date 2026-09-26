# -*- coding: utf-8 -*-
"""
topoprofilestudio.py
Classe principale del plugin: registra menu, pulsante toolbar, il pannello (dock) del
profilo e carica la traduzione dell'interfaccia in base alla lingua di QGIS.
"""
import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QLocale
from qgis.core import QgsApplication


class TopoProfileStudio:
    def __init__(self, iface):
        self.iface = iface
        self.dock = None
        self.action = None
        self.plugin_dir = os.path.dirname(__file__)
        self.translator = None
        self._load_translation()

    def _load_translation(self):
        """Carica il file di traduzione compilato (.qm) corrispondente alla lingua
        dell'interfaccia di QGIS, se presente in i18n/. Le stringhe sorgente del
        plugin sono in italiano: se non viene trovata alcuna traduzione (es. lingua
        italiana o .qm non compilato) l'interfaccia resta in italiano."""
        try:
            locale = QSettings().value("locale/userLocale", QLocale().name())
            locale_code = str(locale)[:2] if locale else "it"
        except Exception:
            locale_code = "it"

        qm_path = os.path.join(self.plugin_dir, "i18n", f"topoprofilestudio_{locale_code}.qm")
        if os.path.exists(qm_path):
            self.translator = QTranslator()
            if self.translator.load(qm_path):
                QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        # QGIS 4.x: addToolBarIcon() accetta una QAction, non un QIcon.
        from qgis.PyQt.QtGui import QIcon

        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QgsApplication.getThemeIcon(
            "/mActionShowAllLayers.svg"
        )

        self.action = QAction(icon, self.tr("TopoProfile Studio"), self.iface.mainWindow())
        self.action.setToolTip(
            self.tr("Apri TopoProfile Studio - profili altimetrici professionali")
        )
        self.action.setStatusTip(self.tr("Apri TopoProfile Studio"))
        self.action.triggered.connect(self.toggle_dock)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.tr("&TopoProfile Studio"), self.action)

    def tr(self, message):
        return QCoreApplication.translate("TopoProfileStudio", message)

    def unload(self):
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu(self.tr("&TopoProfile Studio"), self.action)
            self.action.deleteLater()
            self.action = None

        if self.dock is not None:
            self.dock.cleanup()
            self.dock.close()
            self.dock.deleteLater()
            self.dock = None

        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def toggle_dock(self):
        if self.dock is None:
            from .profile_dock import ProfileDock

            # Finestra indipendente, mai ancorata alla finestra di QGIS.
            self.dock = ProfileDock(
                self.iface,
                self.iface.mainWindow()
            )

            self.dock.destroyed.connect(self._on_dock_distrutto)
            self.dock.show()
            self.dock.raise_()
            self.dock.activateWindow()

        else:
            if self.dock.isVisible():
                self.dock.hide()
            else:
                self.dock.show()
                self.dock.raise_()
                self.dock.activateWindow()

    def _on_dock_distrutto(self):
        self.dock = None
