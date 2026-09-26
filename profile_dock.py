# -*- coding: utf-8 -*-
"""
profile_dock.py

Pannello principale di TopoProfile Studio.

Gestisce:
- configurazione della sorgente del profilo;
- disegno del tracciato sulla mappa;
- campionamento DTM / curve di livello;
- grafico del profilo;
- marker;
- gestione dei profili salvati;
- persistenza nel progetto QGIS;
- import/export JSON;
- export immagine / DXF;
- stile grafico locale al plugin.

Il pannello è una finestra indipendente e non viene mai agganciato
all'interfaccia principale di QGIS.
"""

import os
import json
from contextlib import contextmanager

from qgis.PyQt.QtCore import Qt, QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QPushButton,
    QDoubleSpinBox,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QCheckBox,
    QAbstractItemView,
    QToolButton,
    QTabWidget,
    QColorDialog,
    QApplication,
)

from qgis.core import (
    QgsProject,
    QgsWkbTypes,
    QgsMapLayerProxyModel,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    Qgis,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
)

from qgis.gui import (
    QgsMapLayerComboBox,
    QgsFieldComboBox,
    QgsRubberBand,
)

from .profile_core import (
    sample_from_dtm,
    sample_from_contours,
    compute_stats,
)

from .profile_chart_widget import ProfileChartWidget
from .map_tool_draw import DrawProfileMapTool, MapIndicator
from .marker_dialog import MarkerDialog
from .export_dialog import ExportDialog
from .export_utils import (
    export_image,
    export_dxf,
    ezdxf_available,
)

from .ui_style import (
    apply_stylesheet,
    show_warning,
    show_information,
    show_critical,
    ask_question,
    ask_text,
    get_save_file_name,
    get_open_file_name,
)


class ProfileDock(QWidget):
    """
    Pannello principale del plugin.

    Per requisito è una finestra indipendente e SEMPRE flottante:
    non deve mai poter essere agganciata all'interno della finestra
    di QGIS e non deve alterare l'interfaccia di QGIS.

    Per questo eredita da QWidget e non da QDockWidget.
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent)

        self.setWindowTitle("TopoProfile Studio")

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        self.iface = iface
        self.canvas = iface.mapCanvas()

        # ------------------------------------------------------------
        # Stato corrente
        # ------------------------------------------------------------

        self.current_samples = []
        self.current_markers = []
        self.current_geom = None
        self.current_crs = QgsProject.instance().crs()
        self.current_profile_name = None

        self.profile_color = "#c0392b"
        self.background_color = "#ffaa7f"

        self._last_source_type = "dtm"
        self._last_source_layer = ""

        self._nome_profilo_auto = True
        self._modo_marker = False
        self._modo_elimina_marker = False

        # ------------------------------------------------------------
        # Strumenti mappa
        # ------------------------------------------------------------

        self.map_tool = DrawProfileMapTool(self.canvas)

        self.map_tool.tracciatoCompletato.connect(
            self._on_tracciato_disegnato
        )

        self.map_tool.tracciatoAnnullato.connect(
            self._on_tracciato_annullato
        )

        self.indicator = MapIndicator(self.canvas)

        # Tracciato temporaneo visualizzato sulla mappa dopo
        # la generazione del profilo.
        self.trace_band = QgsRubberBand(
            self.canvas,
            QgsWkbTypes.LineGeometry
        )

        self.trace_band.setColor(
            QColor(255, 140, 0, 200)
        )

        self.trace_band.setWidth(3)
        self.trace_band.hide()

        # ------------------------------------------------------------
        # Interfaccia
        # ------------------------------------------------------------

        self._build_ui()

        self.resize(800, 800)
        self._centra_finestra()

        self._refresh_saved_list()
        self._restore_project_state()

        QgsProject.instance().cleared.connect(self._on_nuovo_progetto)

    # ==================================================================
    # FINESTRA
    # ==================================================================

    def _centra_finestra(self):
        """Centra il pannello flottante sullo schermo disponibile."""

        screen = self.screen()

        if screen is None and self.windowHandle():
            screen = self.windowHandle().screen()

        if screen is None:
            return

        area = screen.availableGeometry()

        x = area.x() + (
            area.width() - self.width()
        ) // 2

        y = area.y() + (
            area.height() - self.height()
        ) // 2

        self.move(x, y)

    # ==================================================================
    # STATO UI
    # ==================================================================

    @contextmanager
    def _ui_occupata(self, messaggio):
        """
        Segnala visivamente un'elaborazione in corso.

        Il pannello viene temporaneamente disabilitato e viene
        visualizzato il cursore di attesa, mantenendo comunque
        reattiva l'interfaccia Qt.
        """

        precedente = self.status_label.text()

        self.status_label.setText(
            f"● {messaggio}"
        )

        self.setEnabled(False)

        QApplication.setOverrideCursor(
            Qt.CursorShape.WaitCursor
        )

        QCoreApplication.processEvents()

        try:
            yield

        finally:
            QApplication.restoreOverrideCursor()

            self.setEnabled(True)

            self.status_label.setText(precedente)

            QCoreApplication.processEvents()

    # ==================================================================
    # UI
    # ==================================================================

    def _build_ui(self):
        """Costruisce l'interfaccia principale."""

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            10, 10, 10, 10
        )

        main_layout.setSpacing(8)

        # ------------------------------------------------------------
        # HEADER
        # ------------------------------------------------------------

        header = QFrame()
        header.setObjectName("tpHeader")

        hl = QHBoxLayout(header)

        title = QLabel("TopoProfile Studio")
        title.setObjectName("tpTitle")

        subtitle = QLabel(
            self.tr("Profilazione altimetrica")
        )
        subtitle.setObjectName("tpSubtitle")

        hv = QVBoxLayout()
        hv.addWidget(title)
        hv.addWidget(subtitle)

        hl.addLayout(hv)
        hl.addStretch()

        self.status_label = QLabel(
            self.tr("● Pronto")
        )
        self.status_label.setObjectName("tpStatus")

        hl.addWidget(self.status_label)

        main_layout.addWidget(header)

        # ------------------------------------------------------------
        # TAB
        # ------------------------------------------------------------

        tabs = QTabWidget()
        tabs.setObjectName("tpTabs")

        main_layout.addWidget(tabs, 1)

        self.tabs = tabs

        # ============================================================
        # TAB 1 - TRACCIATO
        # ============================================================

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ------------------------------------------------------------
        # SORGENTE TRACCIATO
        # ------------------------------------------------------------

        box = QGroupBox(
            self.tr("Sorgente del tracciato")
        )

        form = QFormLayout(box)

        # ------------------------------------------------------------
        # Pulsanti tracciato sulla stessa riga
        # ------------------------------------------------------------

        tracciato_row = QHBoxLayout()
        tracciato_row.setSpacing(6)

        self.disegna_btn = QPushButton(
            self.tr("✏  Disegna tracciato del profilo")
        )

        self.disegna_btn.setObjectName(
            "btnPrimary"
        )

        self.disegna_btn.setCheckable(True)

        self.disegna_btn.toggled.connect(
            self._toggla_disegno
        )

        tracciato_row.addWidget(
            self.disegna_btn,
            1
        )

        self.annulla_traccia_btn = QPushButton(
            self.tr("✕  Annulla traccia")
        )

        self.annulla_traccia_btn.setObjectName(
            "btnDanger"
        )

        self.annulla_traccia_btn.setToolTip(
            self.tr(
                "Annulla il tracciato appena disegnato, "
                "se presente."
            )
        )

        self.annulla_traccia_btn.clicked.connect(
            self._annulla_traccia
        )

        tracciato_row.addWidget(
            self.annulla_traccia_btn
        )

        form.addRow(tracciato_row)

        layout.addWidget(box)

        # ------------------------------------------------------------
        # INFO DISEGNO
        # ------------------------------------------------------------

        info = QLabel(
            self.tr(
                "Nel disegno: click sinistro = vertice, "
                "click destro = termina e riapre il pannello, "
                "Esc = annulla."
            )
        )

        info.setWordWrap(True)
        info.setObjectName("tpHint")

        layout.addWidget(info)

        # ------------------------------------------------------------
        # QUOTE
        # ------------------------------------------------------------

        quote_box = QGroupBox(
            self.tr("Quote")
        )

        qform = QFormLayout(quote_box)

        self.dtm_radio = QRadioButton(
            self.tr("DTM raster")
        )

        self.contour_radio = QRadioButton(
            self.tr("Curve di livello vettoriali")
        )

        self.dtm_radio.setChecked(True)

        elev_group = QButtonGroup(self)
        elev_group.addButton(self.dtm_radio)
        elev_group.addButton(self.contour_radio)

        qform.addRow(self.dtm_radio)

        self.dtm_combo = QgsMapLayerComboBox()

        self.dtm_combo.setFilters(
            QgsMapLayerProxyModel.RasterLayer
        )

        qform.addRow(
            self.tr("Layer DTM:"),
            self.dtm_combo
        )

        qform.addRow(self.contour_radio)

        self.contour_combo = QgsMapLayerComboBox()

        self.contour_combo.setFilters(
            QgsMapLayerProxyModel.LineLayer
        )

        qform.addRow(
            self.tr("Layer curve:"),
            self.contour_combo
        )

        self.contour_field_combo = QgsFieldComboBox()

        self.contour_field_combo.setLayer(
            self.contour_combo.currentLayer()
        )

        self.contour_combo.layerChanged.connect(
            self.contour_field_combo.setLayer
        )

        qform.addRow(
            self.tr("Campo quota:"),
            self.contour_field_combo
        )

        self.intervallo_spin = QDoubleSpinBox()

        self.intervallo_spin.setRange(
            0.1,
            100000
        )

        self.intervallo_spin.setValue(5.0)
        self.intervallo_spin.setSuffix(" m")

        qform.addRow(
            self.tr("Intervallo campionamento:"),
            self.intervallo_spin
        )

        layout.addWidget(quote_box)

        # ------------------------------------------------------------
        # GENERA PROFILO
        # ------------------------------------------------------------

        genera_row = QHBoxLayout()

        self.genera_btn = QPushButton(
            self.tr("▶  Genera profilo")
        )

        self.genera_btn.setObjectName(
            "btnSuccess"
        )

        self.genera_btn.clicked.connect(
            self._genera_profilo
        )

        genera_row.addWidget(
            self.genera_btn,
            1
        )

        layout.addLayout(genera_row)

        hint = QLabel(
            self.tr(
                "Dopo la generazione viene mostrata "
                "automaticamente la scheda Profilo con "
                "grafico, statistiche e dislivello."
            )
        )

        hint.setObjectName("tpHint")
        hint.setWordWrap(True)

        layout.addWidget(hint)

        layout.addStretch()

        tabs.addTab(
            tab,
            self.tr("①  Tracciato")
        )

        # ============================================================
        # TAB 2 - PROFILO
        # ============================================================

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ------------------------------------------------------------
        # PARAMETRI
        # ------------------------------------------------------------

        settings = QGroupBox(
            self.tr("Parametri del profilo")
        )

        form = QFormLayout(settings)

        # Etichette direzione
        label_row = QHBoxLayout()

        self.label_a_edit = QLineEdit("A")
        self.label_b_edit = QLineEdit("A'")

        swap_btn = QToolButton()
        swap_btn.setText("⇄")

        swap_btn.setToolTip(
            self.tr("Scambia le etichette")
        )

        swap_btn.clicked.connect(
            self._swap_labels
        )

        label_row.addWidget(
            self.label_a_edit
        )

        label_row.addWidget(
            self.label_b_edit
        )

        label_row.addWidget(
            swap_btn
        )

        form.addRow(
            self.tr("Etichette direzione:"),
            label_row
        )

        self.label_a_edit.textChanged.connect(
            self._aggiorna_nome_profilo_automatico
        )

        self.label_b_edit.textChanged.connect(
            self._aggiorna_nome_profilo_automatico
        )

        # ------------------------------------------------------------
        # SMUSSATURA
        # ------------------------------------------------------------

        smooth_row = QHBoxLayout()

        self.smoothing_check = QCheckBox(
            self.tr("Smussa linea del profilo")
        )

        self.smoothing_check.setToolTip(
            self.tr(
                "Riduce la seghettatura della linea del "
                "profilo nel grafico, nelle immagini e nel DXF."
            )
        )

        smooth_row.addWidget(
            self.smoothing_check
        )

        smooth_row.addWidget(
            QLabel(self.tr("Livello:"))
        )

        self.smoothing_level_combo = QComboBox()

        self.smoothing_level_combo.addItem(
            self.tr("Leggero"),
            3
        )

        self.smoothing_level_combo.addItem(
            self.tr("Medio"),
            7
        )

        self.smoothing_level_combo.addItem(
            self.tr("Forte"),
            11
        )

        self.smoothing_level_combo.setCurrentIndex(1)

        smooth_row.addWidget(
            self.smoothing_level_combo
        )

        smooth_row.addStretch()

        form.addRow(
            smooth_row
        )

        # ------------------------------------------------------------
        # AGGIORNA + COLORI
        # ------------------------------------------------------------

        update_row = QHBoxLayout()

        aggiorna_btn = QPushButton(
            self.tr("⟳  Aggiorna il profilo")
        )

        aggiorna_btn.setObjectName(
            "btnPrimary"
        )

        aggiorna_btn.clicked.connect(
            self._aggiorna_grafico
        )

        update_row.addWidget(
            aggiorna_btn
        )

        self.profile_color_btn = QPushButton(
            self.tr("Colore linea")
        )

        self.profile_color_btn.setObjectName(
            "btnSecondary"
        )

        self.profile_color_btn.clicked.connect(
            self._choose_profile_color
        )

        update_row.addWidget(
            self.profile_color_btn
        )

        self.background_color_btn = QPushButton(
            self.tr("Colore area sotto profilo")
        )

        self.background_color_btn.setObjectName(
            "btnSecondary"
        )

        self.background_color_btn.clicked.connect(
            self._choose_background_color
        )

        update_row.addWidget(
            self.background_color_btn
        )

        update_row.addStretch()

        form.addRow(
            update_row
        )

        layout.addWidget(settings)

        self.smoothing_check.toggled.connect(
            self._aggiorna_grafico
        )

        self.smoothing_level_combo.currentIndexChanged.connect(
            self._aggiorna_grafico
        )

        # ------------------------------------------------------------
        # GRAFICO
        # ------------------------------------------------------------

        chart_box = QGroupBox(
            self.tr("Anteprima profilo altimetrico")
        )

        chart_layout = QVBoxLayout(chart_box)

        self.chart = ProfileChartWidget()

        self.chart.posizioneSpostata.connect(
            self._on_hover_mappa
        )

        self.chart.posizioneUscita.connect(
            self.indicator.hide
        )

        self.chart.markerCliccato.connect(
            self._on_click_grafico
        )

        chart_layout.addWidget(
            self.chart,
            1
        )

        self.stats_label = QLabel(
            self.tr(
                "Lunghezza: —  |  "
                "Quota min: —  |  "
                "Quota max: —  |  "
                "Dislivello: —"
            )
        )

        self.stats_label.setObjectName(
            "tpStats"
        )

        chart_layout.addWidget(
            self.stats_label
        )

        # ------------------------------------------------------------
        # MARKER
        # ------------------------------------------------------------

        marker_row = QHBoxLayout()

        self._modo_marker = False
        self._modo_elimina_marker = False

        self.add_marker_btn = QPushButton(
            self.tr("📍  Aggiungi marker")
        )

        self.add_marker_btn.setObjectName(
            "btnWarning"
        )

        self.add_marker_btn.setCheckable(True)

        self.add_marker_btn.toggled.connect(
            self._toggle_modo_marker
        )

        marker_row.addWidget(
            self.add_marker_btn
        )

        self.delete_marker_btn = QPushButton(
            self.tr("✕  Elimina marker")
        )

        self.delete_marker_btn.setObjectName(
            "btnDanger"
        )

        self.delete_marker_btn.setCheckable(True)

        self.delete_marker_btn.toggled.connect(
            self._toggle_modo_elimina_marker
        )

        marker_row.addWidget(
            self.delete_marker_btn
        )

        marker_row.addStretch()

        chart_layout.addLayout(
            marker_row
        )

        layout.addWidget(
            chart_box,
            1
        )

        self.profile_tab = tab

        tabs.addTab(
            tab,
            self.tr("②  Profilo")
        )

        # ============================================================
        # TAB 3 - SALVATAGGI / EXPORT
        # ============================================================

        tab = QWidget()
        layout = QVBoxLayout(tab)

        box = QGroupBox(
            self.tr("Gestione profili")
        )

        sl = QVBoxLayout(box)

        # ------------------------------------------------------------
        # SALVATAGGIO PROFILO
        # ------------------------------------------------------------

        save_row = QHBoxLayout()

        self.nome_profilo_edit = QLineEdit()

        self.nome_profilo_edit.setPlaceholderText(
            self.tr(
                "Nome profilo (es. Sezione A-A')"
            )
        )

        self._nome_profilo_auto = True

        self.nome_profilo_edit.textEdited.connect(
            self._on_nome_profilo_modificato_manualmente
        )

        save_btn = QPushButton(
            self.tr("💾  Salva")
        )

        save_btn.setObjectName(
            "btnSuccess"
        )

        save_btn.clicked.connect(
            self._salva_profilo
        )

        save_row.addWidget(
            self.nome_profilo_edit,
            1
        )

        save_row.addWidget(
            save_btn
        )

        sl.addLayout(
            save_row
        )

        # ------------------------------------------------------------
        # SALVA COME LAYER
        # ------------------------------------------------------------

        save_layer_btn = QPushButton(
            self.tr("▣  Salva come layer nel progetto")
        )

        save_layer_btn.setObjectName(
            "btnAccent"
        )

        save_layer_btn.clicked.connect(
            self._salva_come_layer
        )

        sl.addWidget(
            save_layer_btn
        )

        # ------------------------------------------------------------
        # LISTA PROFILI
        # ------------------------------------------------------------

        list_area = QHBoxLayout()

        self.lista_profili = QListWidget()

        self.lista_profili.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.lista_profili.itemDoubleClicked.connect(
            self._carica_profilo_selezionato
        )

        list_area.addWidget(
            self.lista_profili,
            1
        )

        # ------------------------------------------------------------
        # AZIONI
        # ------------------------------------------------------------

        action_col = QVBoxLayout()
        action_col.setSpacing(6)

        def add_action(
            text,
            slot,
            obj="btnSecondary"
        ):
            button = QPushButton(text)

            button.setObjectName(obj)

            button.setMinimumWidth(175)

            button.clicked.connect(slot)

            action_col.addWidget(button)

            return button

        add_action(
            self.tr("Carica"),
            self._carica_profilo_selezionato,
            "btnPrimary"
        )

        add_action(
            self.tr("Rinomina"),
            self._rinomina_profilo
        )

        add_action(
            self.tr("Elimina"),
            self._elimina_profilo,
            "btnDanger"
        )

        sep1 = QFrame()
        sep1.setFrameShape(
            QFrame.Shape.HLine
        )
        sep1.setFrameShadow(
            QFrame.Shadow.Sunken
        )

        action_col.addWidget(sep1)

        add_action(
            self.tr("Salva nel progetto"),
            self._salva_nel_progetto
        )

        add_action(
            self.tr("Carica dal progetto"),
            self._carica_dal_progetto
        )

        add_action(
            self.tr("Elimina dal progetto"),
            self._elimina_dal_progetto,
            "btnDanger"
        )

        sep2 = QFrame()
        sep2.setFrameShape(
            QFrame.Shape.HLine
        )
        sep2.setFrameShadow(
            QFrame.Shadow.Sunken
        )

        action_col.addWidget(sep2)

        add_action(
            self.tr("Salva su file…"),
            self._salva_su_file
        )

        add_action(
            self.tr("Carica da file…"),
            self._carica_da_file
        )

        sep3 = QFrame()
        sep3.setFrameShape(
            QFrame.Shape.HLine
        )
        sep3.setFrameShadow(
            QFrame.Shadow.Sunken
        )

        action_col.addWidget(sep3)

        add_action(
            self.tr("⬇  Esporta profilo…"),
            self._esporta,
            "btnPrimary"
        )

        action_col.addStretch()

        list_area.addLayout(
            action_col
        )

        sl.addLayout(
            list_area,
            1
        )

        layout.addWidget(
            box,
            1
        )

        tabs.addTab(
            tab,
            self.tr("③  Salvataggi & export")
        )

        tabs.currentChanged.connect(
            self._aggiorna_pulsanti_nav
        )

        # ============================================================
        # NAVIGAZIONE
        # ============================================================

        nav_row = QHBoxLayout()

        self.nav_indietro_btn = QPushButton(
            self.tr("◀  Indietro")
        )

        self.nav_indietro_btn.setObjectName(
            "btnSecondary"
        )

        self.nav_indietro_btn.clicked.connect(
            self._scheda_indietro
        )

        self.nav_avanti_btn = QPushButton(
            self.tr("Avanti  ▶")
        )

        self.nav_avanti_btn.setObjectName(
            "btnPrimary"
        )

        self.nav_avanti_btn.clicked.connect(
            self._scheda_avanti
        )

        nav_chiudi_btn = QPushButton(
            self.tr("✕  Chiudi")
        )

        nav_chiudi_btn.setObjectName(
            "btnDanger"
        )

        nav_chiudi_btn.clicked.connect(
            self.close
        )

        nav_row.addWidget(
            self.nav_indietro_btn
        )

        nav_row.addWidget(
            self.nav_avanti_btn
        )

        nav_row.addStretch()

        nav_row.addWidget(
            nav_chiudi_btn
        )

        main_layout.addLayout(
            nav_row
        )

        self._aggiorna_pulsanti_nav()

        # ============================================================
        # STILE GLOBALE DEL PLUGIN
        # ============================================================

        self.setObjectName("tpRoot")

        apply_stylesheet(self)

        self._update_color_buttons()

    # ==================================================================
    # NAVIGAZIONE SCHEDE
    # ==================================================================

    def _scheda_indietro(self):
        """Passa alla scheda precedente."""

        i = self.tabs.currentIndex()

        if i > 0:
            self.tabs.setCurrentIndex(i - 1)

    def _scheda_avanti(self):
        """Passa alla scheda successiva."""

        i = self.tabs.currentIndex()

        if i < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(i + 1)

    def _aggiorna_pulsanti_nav(self, idx=None):
        """Aggiorna lo stato dei pulsanti di navigazione."""

        idx = (
            self.tabs.currentIndex()
            if idx is None
            else idx
        )

        self.nav_indietro_btn.setEnabled(
            idx > 0
        )

        self.nav_avanti_btn.setEnabled(
            idx < self.tabs.count() - 1
        )

    # ==================================================================
    # TRACCIATO
    # ==================================================================

    def _toggla_disegno(self, checked):
        """Attiva/disattiva la modalità di disegno."""

        if checked:
            self._hide_trace_band()

            self.canvas.setMapTool(
                self.map_tool
            )

            self.disegna_btn.setText(
                self.tr(
                    "Disegno attivo — "
                    "click destro per terminare"
                )
            )

            # Nasconde temporaneamente il pannello
            # per lasciare libera la mappa.
            self.hide()

        else:
            self.canvas.unsetMapTool(
                self.map_tool
            )

            self.disegna_btn.setText(
                self.tr(
                    "✏  Disegna tracciato del profilo"
                )
            )

    def _on_tracciato_annullato(self):
        """Gestisce l'annullamento del disegno."""

        self.disegna_btn.setChecked(False)

        self.show()
        self.raise_()
        self.activateWindow()

        self.status_label.setText(
            self.tr("● Disegno annullato")
        )

    def _on_tracciato_disegnato(self, geom):
        """Gestisce il tracciato completato."""

        self.current_geom = geom
        self.current_crs = QgsProject.instance().crs()

        self.disegna_btn.setChecked(False)

        self.show()
        self.raise_()
        self.activateWindow()

        self.tabs.setCurrentIndex(0)

        self.iface.messageBar().pushMessage(
            "TopoProfile Studio",
            self.tr(
                "Tracciato completato. Ora puoi scegliere "
                "le quote e generare il profilo."
            ),
            level=Qgis.Success,
            duration=4
        )

    def _annulla_traccia(self):
        """
        Annulla il tracciato appena disegnato.

        Rimuove la linea temporanea dalla mappa senza
        toccare un eventuale profilo già salvato/caricato.
        """

        ha_traccia = (
            self.current_geom is not None
        )

        self.current_geom = None

        self._hide_trace_band()

        if ha_traccia:
            self.status_label.setText(
                self.tr("● Tracciato annullato")
            )

            self.iface.messageBar().pushMessage(
                "TopoProfile Studio",
                self.tr("Tracciato annullato."),
                level=Qgis.Info,
                duration=3
            )

        else:
            self.iface.messageBar().pushMessage(
                "TopoProfile Studio",
                self.tr(
                    "Non c'è nessun tracciato da annullare."
                ),
                level=Qgis.Warning,
                duration=3
            )

    # ==================================================================
    # GENERAZIONE PROFILO
    # ==================================================================

    def _get_tracciato_geom(self):
        """Restituisce geometria e CRS del tracciato corrente."""

        if not self.current_geom:
            raise ValueError(
                self.tr(
                    "Disegna prima un tracciato sulla mappa."
                )
            )

        return (
            self.current_geom,
            QgsProject.instance().crs()
        )

    def _genera_profilo(self):
        """Genera il profilo dal DTM o dalle curve di livello."""

        try:
            geom, crs = self._get_tracciato_geom()

            interval = (
                self.intervallo_spin.value()
            )

            # --------------------------------------------------------
            # DTM
            # --------------------------------------------------------

            if self.dtm_radio.isChecked():

                dtm = self.dtm_combo.currentLayer()

                if not dtm:
                    raise ValueError(
                        self.tr(
                            "Seleziona un layer DTM."
                        )
                    )

                with self._ui_occupata(
                    self.tr(
                        "Generazione del profilo "
                        "dal DTM in corso…"
                    )
                ):
                    samples = sample_from_dtm(
                        geom,
                        crs,
                        dtm,
                        interval
                    )

                source_type = "dtm"
                source_layer = dtm.name()

            # --------------------------------------------------------
            # CURVE DI LIVELLO
            # --------------------------------------------------------

            else:

                contour = (
                    self.contour_combo.currentLayer()
                )

                field = (
                    self.contour_field_combo.currentField()
                )

                if not contour or not field:
                    raise ValueError(
                        self.tr(
                            "Seleziona il layer delle curve "
                            "di livello e il campo quota."
                        )
                    )

                with self._ui_occupata(
                    self.tr(
                        "Generazione del profilo dalle "
                        "curve di livello in corso…"
                    )
                ):
                    samples = sample_from_contours(
                        geom,
                        crs,
                        contour,
                        field,
                        interval
                    )

                source_type = "contours"
                source_layer = contour.name()

        except Exception as e:
            show_warning(
                self,
                "TopoProfile Studio",
                str(e)
            )
            return

        if not samples:
            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Impossibile generare il profilo "
                    "(nessun campione valido)."
                )
            )
            return

        self.current_samples = samples
        self.current_geom = geom
        self.current_crs = crs

        self._last_source_type = source_type
        self._last_source_layer = source_layer

        self.current_markers = []

        self._aggiorna_grafico()
        self._aggiorna_stats()
        self._aggiorna_nome_profilo_automatico()

        self._show_trace_band(
            geom,
            crs
        )

        self.tabs.setCurrentWidget(
            self.profile_tab
        )

        self.status_label.setText(
            self.tr("● Profilo generato")
        )

    # ==================================================================
    # SMUSSATURA
    # ==================================================================

    def _smoothing_level(self):
        """Restituisce il livello di smoothing corrente."""

        return int(
            self.smoothing_level_combo.currentData()
            or 7
        )

    def _set_smoothing_level(self, value):
        """Imposta il livello di smoothing."""

        idx = (
            self.smoothing_level_combo.findData(
                int(value or 7)
            )
        )

        self.smoothing_level_combo.setCurrentIndex(
            idx if idx >= 0 else 1
        )

    # ==================================================================
    # COLORI
    # ==================================================================

    def _choose_profile_color(self):
        """Apre il selettore colore della linea del profilo."""

        dialog = QColorDialog(
            QColor(self.profile_color),
            self
        )

        dialog.setWindowTitle(
            self.tr("Colore linea del profilo")
        )

        apply_stylesheet(dialog)

        if dialog.exec() == dialog.DialogCode.Accepted:
            color = dialog.currentColor()

            if color.isValid():
                self.profile_color = color.name()

                self._update_color_buttons()
                self._aggiorna_grafico()

    def _choose_background_color(self):
        """Apre il selettore colore dell'area sotto il profilo."""

        dialog = QColorDialog(
            QColor(self.background_color),
            self
        )

        dialog.setWindowTitle(
            self.tr("Colore area sotto profilo")
        )

        apply_stylesheet(dialog)

        if dialog.exec() == dialog.DialogCode.Accepted:
            color = dialog.currentColor()

            if color.isValid():
                self.background_color = color.name()

                self._update_color_buttons()
                self._aggiorna_grafico()

    def _update_color_buttons(self):
        """
        Aggiorna il colore visualizzato sui pulsanti colore.

        Lo stile viene applicato localmente ai due pulsanti,
        mantenendo dimensioni, bordi e font del tema principale.
        """

        if hasattr(self, "profile_color_btn"):
            self.profile_color_btn.setStyleSheet(
                f"""
                QPushButton#btnSecondary {{
                    background: {self.profile_color};
                    color: white;
                    border: 0;
                    border-radius: 7px;
                    padding: 7px 12px;
                    font-weight: 600;
                    min-height: 24px;
                }}

                QPushButton#btnSecondary:hover {{
                    background: {self.profile_color};
                }}
                """
            )

        if hasattr(self, "background_color_btn"):
            self.background_color_btn.setStyleSheet(
                f"""
                QPushButton#btnSecondary {{
                    background: {self.background_color};
                    color: white;
                    border: 0;
                    border-radius: 7px;
                    padding: 7px 12px;
                    font-weight: 600;
                    min-height: 24px;
                }}

                QPushButton#btnSecondary:hover {{
                    background: {self.background_color};
                }}
                """
            )

    def _swap_labels(self):
        """Scambia le etichette A e B."""

        a = self.label_a_edit.text()
        b = self.label_b_edit.text()

        self.label_a_edit.setText(b)
        self.label_b_edit.setText(a)

        self._aggiorna_grafico()

    # ==================================================================
    # NOME PROFILO
    # ==================================================================

    def _on_nome_profilo_modificato_manualmente(
        self,
        _testo
    ):
        """
        Disattiva l'aggiornamento automatico del nome
        dopo una modifica manuale.
        """

        self._nome_profilo_auto = False

    def _aggiorna_nome_profilo_automatico(self):
        """Aggiorna automaticamente il nome del profilo."""

        if not getattr(
            self,
            "_nome_profilo_auto",
            True
        ):
            return

        a = (
            self.label_a_edit.text().strip()
            or "A"
        )

        b = (
            self.label_b_edit.text().strip()
            or "A'"
        )

        self.nome_profilo_edit.blockSignals(
            True
        )

        self.nome_profilo_edit.setText(
            f"{a} - {b}"
        )

        self.nome_profilo_edit.blockSignals(
            False
        )

    # ==================================================================
    # GRAFICO
    # ==================================================================

    def _aggiorna_grafico(self):
        """Aggiorna il grafico del profilo."""

        self.chart.set_data(
            self.current_samples,
            self.current_markers,
            label_a=(
                self.label_a_edit.text()
                or "A"
            ),
            label_b=(
                self.label_b_edit.text()
                or "A'"
            ),
            smoothing=(
                self.smoothing_check.isChecked()
            ),
            smoothing_level=(
                self._smoothing_level()
            ),
            profile_color=self.profile_color,
            background_color=self.background_color,
        )

        self._aggiorna_stats()

        if self.current_samples:
            QgsProject.instance().writeEntry(
                "TopoProfileStudio",
                "current_profile",
                json.dumps(
                    self._profile_state_dict(),
                    ensure_ascii=False
                )
            )

    def _aggiorna_stats(self):
        """Aggiorna le statistiche del profilo."""

        if not self.current_samples:

            self.stats_label.setText(
                self.tr(
                    "Lunghezza: —  |  "
                    "Quota min: —  |  "
                    "Quota max: —  |  "
                    "Dislivello: —"
                )
            )

            return

        st = compute_stats(
            self.current_samples
        )

        self.stats_label.setText(
            self.tr(
                "Lunghezza: {0:.1f} m  |  "
                "Quota min: {1:.1f} m  |  "
                "Quota max: {2:.1f} m  |  "
                "Dislivello: {3:.1f} m"
            ).format(
                st["length"],
                st["min_z"],
                st["max_z"],
                st["relief"]
            )
        )

    # ==================================================================
    # INDICATORE MAPPA
    # ==================================================================

    def _on_hover_mappa(self, x, y):
        """Mostra l'indicatore sulla mappa."""

        self.indicator.show_at(
            x,
            y
        )

    # ==================================================================
    # TRACCIATO TEMPORANEO
    # ==================================================================

    def _show_trace_band(self, geom, crs):
        """Mostra il tracciato temporaneo sulla mappa."""

        try:
            g = QgsGeometry(geom)

            project_crs = (
                QgsProject.instance().crs()
            )

            if crs != project_crs:

                xform = QgsCoordinateTransform(
                    crs,
                    project_crs,
                    QgsProject.instance()
                )

                g.transform(xform)

            self.trace_band.reset(
                QgsWkbTypes.LineGeometry
            )

            self.trace_band.addGeometry(
                g,
                None
            )

            self.trace_band.show()

        except Exception as e:

            self.iface.messageBar().pushMessage(
                "TopoProfile Studio",
                self.tr(
                    "Impossibile aggiornare il tracciato "
                    "temporaneo: {0}"
                ).format(e),
                level=Qgis.Warning,
                duration=3
            )

    def _hide_trace_band(self):
        """Nasconde il tracciato temporaneo."""

        self.trace_band.reset(
            QgsWkbTypes.LineGeometry
        )

        self.trace_band.hide()

    # ==================================================================
    # MARKER
    # ==================================================================

    def _toggle_modo_marker(self, checked):
        """Attiva/disattiva la modalità aggiunta marker."""

        self._modo_marker = checked

        self.add_marker_btn.setText(
            self.tr(
                "Clicca sul grafico per posizionare il marker…"
            )
            if checked
            else self.tr("📍  Aggiungi marker")
        )

        if (
            checked
            and self.delete_marker_btn.isChecked()
        ):
            self.delete_marker_btn.setChecked(
                False
            )

    def _toggle_modo_elimina_marker(self, checked):
        """Attiva/disattiva la modalità eliminazione marker."""

        self._modo_elimina_marker = checked

        self.delete_marker_btn.setText(
            self.tr(
                "Clicca sul marker da eliminare…"
            )
            if checked
            else self.tr("✕  Elimina marker")
        )

        if (
            checked
            and self.add_marker_btn.isChecked()
        ):
            self.add_marker_btn.setChecked(
                False
            )

    def _on_click_grafico(
        self,
        distanza_progressiva
    ):
        """Gestisce il click sul grafico."""

        if not self.current_samples:
            return

        # ============================================================
        # ELIMINA MARKER
        # ============================================================

        if self._modo_elimina_marker:

            if not self.current_markers:

                self.iface.messageBar().pushMessage(
                    "TopoProfile Studio",
                    self.tr(
                        "Non ci sono marker da eliminare."
                    ),
                    level=Qgis.Warning,
                    duration=3
                )

                self.delete_marker_btn.setChecked(
                    False
                )

                return

            marker = min(
                self.current_markers,
                key=lambda m: abs(
                    m["distanza"]
                    - distanza_progressiva
                )
            )

            tolleranza = max(
                (
                    self.current_samples[-1]
                    .dist_progressiva
                    -
                    self.current_samples[0]
                    .dist_progressiva
                ) * 0.02,
                5.0
            )

            if (
                abs(
                    marker["distanza"]
                    - distanza_progressiva
                )
                > tolleranza
            ):

                self.iface.messageBar().pushMessage(
                    "TopoProfile Studio",
                    self.tr(
                        "Clicca più vicino al marker "
                        "che vuoi eliminare."
                    ),
                    level=Qgis.Warning,
                    duration=3
                )

                return

            risposta = ask_question(
                self,
                self.tr("Elimina marker"),
                self.tr(
                    "Vuoi eliminare il marker '{0}'?"
                ).format(
                    marker.get(
                        "etichetta",
                        ""
                    )
                )
            )

            if (
                risposta
                == QMessageBox.StandardButton.Yes
            ):
                self.current_markers.remove(
                    marker
                )

                self._aggiorna_grafico()

                self.iface.messageBar().pushMessage(
                    "TopoProfile Studio",
                    self.tr("Marker eliminato."),
                    level=Qgis.Success,
                    duration=3
                )

            self.delete_marker_btn.setChecked(
                False
            )

            return

        # ============================================================
        # AGGIUNGI MARKER
        # ============================================================

        if not self._modo_marker:
            return

        s = min(
            self.current_samples,
            key=lambda sample: abs(
                sample.dist_progressiva
                - distanza_progressiva
            )
        )

        dlg = MarkerDialog(
            s.dist_progressiva,
            s.z,
            self
        )

        if dlg.exec():
            self.current_markers.append(
                dlg.get_marker()
            )

            self.current_markers.sort(
                key=lambda m: m["distanza"]
            )

            self._aggiorna_grafico()

        self.add_marker_btn.setChecked(
            False
        )

    # ==================================================================
    # PERSISTENZA STATO CORRENTE
    # ==================================================================

    def _automatic_reference(self):
        """Calcola la quota di riferimento automatica per il DXF."""

        if not self.current_samples:
            return 0.0

        vals = [
            float(s.z)
            for s in self.current_samples
        ]

        zmin = min(vals)
        zmax = max(vals)

        return (
            zmin
            - max(
                (zmax - zmin) * 0.05,
                1.0
            )
        )

    def _profile_state_dict(self):
        """Costruisce il dizionario di stato del profilo."""

        return {
            "version": 1,

            "name": (
                self.nome_profilo_edit.text().strip()
                if hasattr(
                    self,
                    "nome_profilo_edit"
                )
                else (
                    self.current_profile_name
                    or ""
                )
            ),

            "label_a": (
                self.label_a_edit.text()
                or "A"
            ),

            "label_b": (
                self.label_b_edit.text()
                or "A'"
            ),

            "smoothing": (
                self.smoothing_check.isChecked()
            ),

            "smoothing_level": (
                self._smoothing_level()
            ),

            "profile_color": (
                self.profile_color
            ),

            "background_color": (
                self.background_color
            ),

            "crs": (
                self.current_crs.authid()
                if self.current_crs
                else QgsProject.instance()
                .crs()
                .authid()
            ),

            "geometry_wkt": (
                self.current_geom.asWkt()
                if (
                    self.current_geom
                    and not self.current_geom.isNull()
                )
                else ""
            ),

            "source_type": (
                getattr(
                    self,
                    "_last_source_type",
                    "dtm"
                )
            ),

            "source_layer": (
                getattr(
                    self,
                    "_last_source_layer",
                    ""
                )
            ),

            "samples": [
                {
                    "x": s.x,
                    "y": s.y,
                    "z": s.z,
                    "dist_progressiva": (
                        s.dist_progressiva
                    ),
                    "dist_parziale": (
                        s.dist_parziale
                    ),
                }
                for s in self.current_samples
            ],

            "markers": list(
                self.current_markers
            ),
        }

    def _apply_profile_state(self, state):
        """Applica uno stato di profilo alla UI."""

        if (
            not state
            or not state.get("samples")
        ):
            return False

        from .profile_core import ProfileSample

        self.current_samples = [
            ProfileSample(
                float(d["x"]),
                float(d["y"]),
                float(d["z"]),
                float(d["dist_progressiva"]),
                float(
                    d.get(
                        "dist_parziale",
                        0.0
                    )
                )
            )
            for d in state["samples"]
        ]

        self.current_markers = list(
            state.get(
                "markers",
                []
            )
        )

        self.current_profile_name = (
            state.get("name")
            or None
        )

        self._nome_profilo_auto = False

        self.nome_profilo_edit.setText(
            state.get(
                "name",
                ""
            )
        )

        self.label_a_edit.setText(
            state.get(
                "label_a"
            )
            or "A"
        )

        self.label_b_edit.setText(
            state.get(
                "label_b"
            )
            or "A'"
        )

        self.smoothing_check.setChecked(
            bool(
                state.get(
                    "smoothing",
                    False
                )
            )
        )

        self._set_smoothing_level(
            state.get(
                "smoothing_level",
                7
            )
        )

        self.profile_color = state.get(
            "profile_color",
            "#c0392b"
        )

        self.background_color = state.get(
            "background_color",
            "#ffaa7f"
        )

        self._update_color_buttons()

        crs_authid = (
            state.get("crs")
            or QgsProject.instance()
            .crs()
            .authid()
        )

        crs = QgsCoordinateReferenceSystem(
            crs_authid
        )

        geometry_wkt = (
            state.get(
                "geometry_wkt"
            )
            or ""
        )

        if geometry_wkt:

            try:
                self.current_geom = (
                    QgsGeometry.fromWkt(
                        geometry_wkt
                    )
                )

            except (
                TypeError,
                ValueError
            ):
                self.current_geom = None

        else:
            self.current_geom = None

        if crs.isValid():
            self.current_crs = crs

        self._last_source_type = (
            state.get(
                "source_type",
                "dtm"
            )
        )

        self._last_source_layer = (
            state.get(
                "source_layer",
                ""
            )
        )

        self._aggiorna_grafico()

        if self.current_geom:

            self._show_trace_band(
                self.current_geom,
                self.current_crs
            )

        else:
            self._hide_trace_band()

        self.tabs.setCurrentWidget(
            self.profile_tab
        )

        return True

    # ==================================================================
    # PROGETTO QGIS
    # ==================================================================
    def _on_nuovo_progetto(self):
        """
        Pulisce completamente l'interfaccia quando viene creato
        un nuovo progetto QGIS.

        Il plugin viene riportato allo stato iniziale:
        nessun profilo, nessun marker, nessun tracciato,
        nessuna sorgente selezionata.
        """

        # ------------------------------------------------------------
        # Stato del profilo
        # ------------------------------------------------------------

        self.current_samples = []
        self.current_markers = []
        self.current_geom = None
        self.current_profile_name = None
        self.current_crs = QgsProject.instance().crs()

        # ------------------------------------------------------------
        # Stato sorgente
        # ------------------------------------------------------------

        self._last_source_type = "dtm"
        self._last_source_layer = ""

        # ------------------------------------------------------------
        # Nome profilo
        # ------------------------------------------------------------

        self._nome_profilo_auto = True

        self.nome_profilo_edit.blockSignals(True)
        self.nome_profilo_edit.clear()
        self.nome_profilo_edit.blockSignals(False)

        # ------------------------------------------------------------
        # Etichette direzione
        # ------------------------------------------------------------

        self.label_a_edit.blockSignals(True)
        self.label_b_edit.blockSignals(True)

        self.label_a_edit.setText("A")
        self.label_b_edit.setText("A'")

        self.label_a_edit.blockSignals(False)
        self.label_b_edit.blockSignals(False)

        # ------------------------------------------------------------
        # Marker
        # ------------------------------------------------------------

        self._modo_marker = False
        self._modo_elimina_marker = False

        self.add_marker_btn.setChecked(False)
        self.delete_marker_btn.setChecked(False)

        # ------------------------------------------------------------
        # Smoothing
        # ------------------------------------------------------------

        self.smoothing_check.blockSignals(True)
        self.smoothing_check.setChecked(False)
        self.smoothing_check.blockSignals(False)

        self._set_smoothing_level(7)

        # ------------------------------------------------------------
        # Colori predefiniti
        # ------------------------------------------------------------

        self.profile_color = "#c0392b"
        self.background_color = "#ffaa7f"

        self._update_color_buttons()

        # ------------------------------------------------------------
        # Sorgente quote
        # ------------------------------------------------------------

        self.dtm_radio.setChecked(True)

        self.dtm_combo.setCurrentIndex(-1)
        self.contour_combo.setCurrentIndex(-1)

        self.intervallo_spin.setValue(5.0)

        # ------------------------------------------------------------
        # Grafico
        # ------------------------------------------------------------

        self.chart.set_data(
            [],
            [],
            label_a="A",
            label_b="A'",
            smoothing=False,
            smoothing_level=7,
            profile_color=self.profile_color,
            background_color=self.background_color,
        )

        # ------------------------------------------------------------
        # Statistiche
        # ------------------------------------------------------------

        self._aggiorna_stats()

        # ------------------------------------------------------------
        # Tracciato temporaneo / indicatore
        # ------------------------------------------------------------

        self._hide_trace_band()
        self.indicator.hide()

        # ------------------------------------------------------------
        # Lista profili
        # ------------------------------------------------------------

        self._refresh_saved_list()

        # ------------------------------------------------------------
        # Prima scheda
        # ------------------------------------------------------------

        self.tabs.setCurrentIndex(0)

        # ------------------------------------------------------------
        # Stato interfaccia
        # ------------------------------------------------------------

        self.status_label.setText(
            self.tr("● Nuovo progetto")
        )

    @staticmethod
    def _project_entry_value(
        group,
        key,
        default=""
    ):
        """
        Restituisce il valore di una voce di progetto.

        Compatibile con QGIS 4.x, dove readEntry()
        restituisce una coppia (valore, trovato).
        """

        result = QgsProject.instance().readEntry(
            group,
            key,
            default
        )

        if isinstance(result, tuple):
            return (
                result[0]
                if result
                else default
            )

        return result

    def _salva_nel_progetto(self):
        """Salva il profilo corrente nel progetto."""

        self._hide_trace_band()

        if not self.current_samples:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Genera prima un profilo."
                )
            )

            return

        state = self._profile_state_dict()

        QgsProject.instance().writeEntry(
            "TopoProfileStudio",
            "current_profile",
            json.dumps(
                state,
                ensure_ascii=False
            )
        )

        profiles = self._project_profiles()

        nome = (
            state.get("name")
            or self.current_profile_name
        )

        if nome:

            profiles[nome] = state

            self._write_project_profiles(
                profiles
            )

            self._refresh_saved_list()

        self.iface.messageBar().pushMessage(
            "TopoProfile Studio",
            self.tr(
                "Profilo corrente memorizzato nel progetto. "
                "Salva il progetto QGIS per conservarlo."
            ),
            level=Qgis.Success,
            duration=4
        )

    def _carica_dal_progetto(self):
        """Carica un profilo memorizzato nel progetto."""

        profiles = self._project_profiles()

        self._refresh_saved_list()

        if profiles:

            raw = self._project_entry_value(
                "TopoProfileStudio",
                "current_profile",
                ""
            )

            state = None

            if raw:

                try:
                    candidate = json.loads(
                        str(raw)
                    )

                    if (
                        isinstance(candidate, dict)
                        and candidate.get("samples")
                    ):
                        state = candidate

                except (
                    TypeError,
                    ValueError,
                    json.JSONDecodeError
                ):
                    state = None

            if state is None:

                first_name = sorted(
                    profiles.keys(),
                    key=str.casefold
                )[0]

                state = profiles[
                    first_name
                ]

            if self._apply_profile_state(
                state
            ):

                name = (
                    state.get("name")
                    or self.current_profile_name
                )

                if name:

                    items = (
                        self.lista_profili.findItems(
                            name,
                            Qt.MatchFlag.MatchExactly
                        )
                    )

                    if items:
                        self.lista_profili.setCurrentItem(
                            items[0]
                        )

                return

        show_information(
            self,
            "TopoProfile Studio",
            self.tr(
                "Nel progetto non sono presenti "
                "profili salvati."
            )
        )

    def _restore_project_state(self):
        """Ripristina silenziosamente il profilo corrente."""

        raw = self._project_entry_value(
            "TopoProfileStudio",
            "current_profile",
            ""
        )

        if not raw:
            return

        try:

            state = json.loads(
                str(raw)
            )

            if (
                not isinstance(state, dict)
                or not state.get("samples")
            ):
                return

            self._apply_profile_state(
                state
            )

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError
        ):
            return

        except Exception:
            return

    # ==================================================================
    # FILE JSON
    # ==================================================================

    def _salva_su_file(self):
        """Salva il profilo corrente in un file JSON."""

        self._hide_trace_band()

        if not self.current_samples:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Genera prima un profilo."
                )
            )

            return

        path, _ = get_save_file_name(
            self,
            self.tr(
                "Salva profilo TopoProfile Studio"
            ),
            "profilo_topoprofile.json",
            self.tr(
                "Profilo TopoProfile Studio (*.json)"
            )
        )

        if not path:
            return

        try:

            with open(
                path,
                "w",
                encoding="utf-8"
            ) as fh:

                json.dump(
                    self._profile_state_dict(),
                    fh,
                    ensure_ascii=False,
                    indent=2
                )

            self.iface.messageBar().pushMessage(
                "TopoProfile Studio",
                self.tr(
                    "Profilo salvato in {0}"
                ).format(path),
                level=Qgis.Success,
                duration=4
            )

        except Exception as e:

            show_critical(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Impossibile salvare il file:\n{0}"
                ).format(e)
            )

    def _carica_da_file(self):
        """Carica un profilo da file JSON."""

        path, _ = get_open_file_name(
            self,
            self.tr(
                "Carica profilo TopoProfile Studio"
            ),
            "",
            self.tr(
                "Profilo TopoProfile Studio (*.json)"
            )
        )

        if not path:
            return

        try:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as fh:

                state = json.load(fh)

            if (
                not isinstance(state, dict)
                or not state.get("samples")
            ):
                raise ValueError(
                    "profilo vuoto o non valido"
                )

            if not self._apply_profile_state(
                state
            ):
                raise ValueError(
                    "profilo vuoto o non valido"
                )

            # --------------------------------------------------------
            # Inserimento nel progetto
            # --------------------------------------------------------

            profiles = self._project_profiles()

            nome = (
                state.get("name")
                or os.path.splitext(
                    os.path.basename(path)
                )[0]
            ).strip()

            base = (
                nome
                or self.tr("Profilo importato")
            )

            nome = base
            n = 2

            while nome in profiles:
                nome = f"{base} ({n})"
                n += 1

            state["name"] = nome

            profiles[nome] = state

            self._write_project_profiles(
                profiles
            )

            self.current_profile_name = nome

            self.nome_profilo_edit.setText(
                nome
            )

            self._refresh_saved_list()

            items = (
                self.lista_profili.findItems(
                    nome,
                    Qt.MatchFlag.MatchExactly
                )
            )

            if items:
                self.lista_profili.setCurrentItem(
                    items[0]
                )

            self.iface.messageBar().pushMessage(
                "TopoProfile Studio",
                self.tr(
                    "Profilo caricato da {0} e "
                    "aggiunto alla lista del progetto."
                ).format(path),
                level=Qgis.Success,
                duration=4
            )

        except Exception as e:

            show_critical(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Impossibile caricare il file:\n{0}"
                ).format(e)
            )

    # ==================================================================
    # PROFILI SALVATI
    # ==================================================================

    def _project_profiles(self):
        """Restituisce i profili salvati nel progetto."""

        raw = self._project_entry_value(
            "TopoProfileStudio",
            "profiles",
            ""
        )

        if not raw:
            return {}

        try:

            data = json.loads(
                str(raw)
            )

            return (
                data
                if isinstance(data, dict)
                else {}
            )

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError
        ):
            return {}

    def _write_project_profiles(
        self,
        profiles
    ):
        """Scrive i profili nel progetto QGIS."""

        QgsProject.instance().writeEntry(
            "TopoProfileStudio",
            "profiles",
            json.dumps(
                profiles,
                ensure_ascii=False
            )
        )

    def _salva_profilo(self):
        """Salva il profilo nella lista del progetto."""

        self._hide_trace_band()

        if not self.current_samples:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Genera prima un profilo."
                )
            )

            return

        nome = (
            self.nome_profilo_edit.text().strip()
        )

        if not nome:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Assegna un nome al profilo."
                )
            )

            return

        profiles = self._project_profiles()

        if nome in profiles:

            risposta = ask_question(
                self,
                self.tr("Profilo esistente"),
                self.tr(
                    "Esiste già un profilo con il nome "
                    "'{0}'. Sovrascriverlo?"
                ).format(nome)
            )

            if (
                risposta
                != QMessageBox.StandardButton.Yes
            ):
                return

        state = self._profile_state_dict()

        state["name"] = nome

        profiles[nome] = state

        self._write_project_profiles(
            profiles
        )

        self.current_profile_name = nome

        self._refresh_saved_list()

        self.iface.messageBar().pushMessage(
            "TopoProfile Studio",
            self.tr(
                "Profilo '{0}' salvato nel progetto."
            ).format(nome),
            level=Qgis.Success,
            duration=3
        )

    def _refresh_saved_list(self):
        """Aggiorna la lista dei profili salvati."""

        self.lista_profili.clear()

        for name in sorted(
            self._project_profiles().keys(),
            key=str.casefold
        ):
            self.lista_profili.addItem(
                QListWidgetItem(name)
            )

    def _carica_profilo_selezionato(self):
        """Carica il profilo selezionato nella lista."""

        item = (
            self.lista_profili.currentItem()
        )

        if not item:
            return

        state = (
            self._project_profiles().get(
                item.text()
            )
        )

        if not state:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Impossibile caricare il profilo."
                )
            )

            return

        self._apply_profile_state(
            state
        )

    def _rinomina_profilo(self):
        """Rinomina il profilo selezionato."""

        item = (
            self.lista_profili.currentItem()
        )

        if not item:
            return

        nuovo, ok = ask_text(
            self,
            self.tr("Rinomina profilo"),
            self.tr("Nuovo nome:"),
            item.text()
        )

        nuovo = nuovo.strip()

        if (
            not ok
            or not nuovo
            or nuovo == item.text()
        ):
            return

        profiles = self._project_profiles()

        if nuovo in profiles:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Esiste già un profilo con il nome "
                    "'{0}'."
                ).format(nuovo)
            )

            return

        state = profiles.pop(
            item.text(),
            None
        )

        if state is not None:

            state["name"] = nuovo

            profiles[nuovo] = state

            self._write_project_profiles(
                profiles
            )

            if (
                self.current_profile_name
                == item.text()
            ):

                self.current_profile_name = nuovo

                self.nome_profilo_edit.setText(
                    nuovo
                )

            self._refresh_saved_list()

    def _elimina_profilo(self):
        """Elimina il profilo selezionato dal progetto."""

        self._elimina_dal_progetto()

    def _elimina_dal_progetto(self):
        """Elimina un profilo dal progetto."""

        self._hide_trace_band()

        item = (
            self.lista_profili.currentItem()
        )

        nome = (
            item.text()
            if item
            else (
                self.current_profile_name
                or self.nome_profilo_edit.text().strip()
            )
        )

        if not nome:
            return

        risposta = ask_question(
            self,
            self.tr("Elimina dal progetto"),
            self.tr(
                "Eliminare dal progetto il profilo "
                "'{0}'? Questa operazione non elimina "
                "eventuali file JSON esterni."
            ).format(nome)
        )

        if (
            risposta
            != QMessageBox.StandardButton.Yes
        ):
            return

        profiles = self._project_profiles()

        profiles.pop(
            nome,
            None
        )

        self._write_project_profiles(
            profiles
        )

        self._refresh_saved_list()

        if (
            self.current_profile_name
            == nome
        ):
            self._reset_profilo_corrente()

    def _reset_profilo_corrente(self):
        """Resetta completamente il profilo corrente."""

        self.current_samples = []
        self.current_markers = []
        self.current_geom = None
        self.current_profile_name = None

        self._nome_profilo_auto = True

        self.nome_profilo_edit.clear()

        self.chart.set_data(
            [],
            []
        )

        self._aggiorna_stats()

        self._hide_trace_band()

        self.indicator.hide()

    # ==================================================================
    # SALVA COME LAYER
    # ==================================================================

    def _salva_come_layer(self):
        """Salva il profilo come layer vettoriale temporaneo."""

        self._hide_trace_band()

        if not self.current_samples:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Genera prima un profilo."
                )
            )

            return

        nome = (
            self.nome_profilo_edit.text().strip()
            or self.tr("Profilo altimetrico")
        )

        uri = (
            f"LineStringZM?"
            f"crs={self.current_crs.authid()}"
        )

        layer = QgsVectorLayer(
            uri,
            nome,
            "memory"
        )

        st = compute_stats(
            self.current_samples
        )

        layer.dataProvider().addAttributes(
            [
                QgsField(
                    "nome",
                    QVariant.String
                ),
                QgsField(
                    "label_a",
                    QVariant.String
                ),
                QgsField(
                    "label_b",
                    QVariant.String
                ),
                QgsField(
                    "lunghezza",
                    QVariant.Double
                ),
                QgsField(
                    "quota_min",
                    QVariant.Double
                ),
                QgsField(
                    "quota_max",
                    QVariant.Double
                ),
                QgsField(
                    "dislivello",
                    QVariant.Double
                ),
            ]
        )

        layer.updateFields()

        feat = QgsFeature(
            layer.fields()
        )

        pts = [
            QgsPoint(
                s.x,
                s.y,
                s.z,
                s.dist_progressiva
            )
            for s in self.current_samples
        ]

        feat.setGeometry(
            QgsGeometry.fromPolyline(pts)
        )

        feat["nome"] = nome

        feat["label_a"] = (
            self.label_a_edit.text()
            or "A"
        )

        feat["label_b"] = (
            self.label_b_edit.text()
            or "A'"
        )

        feat["lunghezza"] = (
            st["length"]
        )

        feat["quota_min"] = (
            st["min_z"]
        )

        feat["quota_max"] = (
            st["max_z"]
        )

        feat["dislivello"] = (
            st["relief"]
        )

        layer.dataProvider().addFeature(
            feat
        )

        layer.updateExtents()

        QgsProject.instance().addMapLayer(
            layer
        )

        self.iface.messageBar().pushMessage(
            "TopoProfile Studio",
            self.tr(
                "Layer '{0}' aggiunto al progetto."
            ).format(nome),
            level=Qgis.Success,
            duration=3
        )

    # ==================================================================
    # ESPORTAZIONE
    # ==================================================================

    def _esporta(self):
        """Gestisce l'esportazione del profilo."""

        if not self.current_samples:

            show_warning(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Genera prima un profilo."
                )
            )

            return

        dlg = ExportDialog(self)

        if not dlg.exec():
            return

        sel = dlg.get_selection()

        if not sel["path"]:
            return

        try:

            with self._ui_occupata(
                self.tr(
                    "Esportazione in corso…"
                )
            ):

                # ----------------------------------------------------
                # DXF
                # ----------------------------------------------------

                if sel["is_dxf"]:

                    if not ezdxf_available():

                        show_warning(
                            self,
                            "TopoProfile Studio",
                            self.tr(
                                "La libreria 'ezdxf' non è "
                                "disponibile nell'ambiente Python "
                                "di QGIS.\n"
                                "Installala con: pip install ezdxf "
                                "(nella console OSGeo4W/QGIS) "
                                "per abilitare l'export DXF."
                            )
                        )

                        return

                    export_dxf(
                        self.current_samples,
                        sel["path"],
                        mode=sel["dxf_mode"],
                        label_a=(
                            self.label_a_edit.text()
                            or "A"
                        ),
                        label_b=(
                            self.label_b_edit.text()
                            or "A'"
                        ),
                        markers=self.current_markers,
                        ref_elevation=(
                            self._automatic_reference()
                        ),
                        smoothing=(
                            self.smoothing_check.isChecked()
                        ),
                        smoothing_level=(
                            self._smoothing_level()
                        ),
                    )

                # ----------------------------------------------------
                # IMMAGINE
                # ----------------------------------------------------

                else:

                    export_fig = (
                        self.chart.build_export_figure()
                    )

                    if export_fig is None:

                        show_warning(
                            self,
                            "TopoProfile Studio",
                            self.tr(
                                "Genera prima un profilo."
                            )
                        )

                        return

                    export_image(
                        export_fig,
                        sel["path"],
                        dpi=sel["dpi"]
                    )

            self.iface.messageBar().pushMessage(
                "TopoProfile Studio",
                self.tr(
                    "Esportato in {0}"
                ).format(
                    sel["path"]
                ),
                level=Qgis.Success,
                duration=4
            )

        except Exception as e:

            show_critical(
                self,
                "TopoProfile Studio",
                self.tr(
                    "Errore durante l'esportazione:\n{0}"
                ).format(e)
            )

    # ==================================================================
    # CHIUSURA / CLEANUP
    # ==================================================================

    def closeEvent(self, event):
        """
        Chiude la finestra senza distruggere il pannello.

        Il plugin può quindi riaprirla successivamente.
        """

        self.canvas.unsetMapTool(
            self.map_tool
        )

        super().closeEvent(event)

    def cleanup(self):
        """
        Rilascia definitivamente le risorse sulla mappa.

        Viene chiamato dallo scaricamento del plugin.
        """

        try:
            QgsProject.instance().cleared.disconnect(
                self._on_nuovo_progetto
            )
        except (TypeError, RuntimeError):
            pass

        self.canvas.unsetMapTool(
            self.map_tool
        )

        self.indicator.remove()

        try:
            self.canvas.scene().removeItem(
                self.trace_band
            )

        except RuntimeError:

            self.trace_band = None