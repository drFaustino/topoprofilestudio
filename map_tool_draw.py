# -*- coding: utf-8 -*-
"""
map_tool_draw.py
Strumento mappa per disegnare il tracciato del profilo con il mouse
(click per aggiungere vertici, doppio click o Invio per terminare, Esc per annullare)
e gestione del marker/indicatore mobile sulla mappa sincronizzato con il grafico.
"""
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsWkbTypes, QgsPointXY, QgsGeometry
from qgis.gui import QgsMapTool, QgsRubberBand, QgsVertexMarker


class DrawProfileMapTool(QgsMapTool):
    tracciatoCompletato = pyqtSignal(QgsGeometry)
    tracciatoAnnullato = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.points = []
        self.rubber_band = QgsRubberBand(canvas, QgsWkbTypes.LineGeometry)
        self.rubber_band.setColor(QColor(255, 120, 0, 200))
        self.rubber_band.setWidth(3)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def canvasPressEvent(self, event):
        pt = self.toMapCoordinates(event.pos())
        if event.button() == Qt.MouseButton.RightButton:
            self._finish()
            return
        self.points.append(QgsPointXY(pt))
        self._update_band()

    def canvasMoveEvent(self, event):
        if not self.points:
            return
        pt = self.toMapCoordinates(event.pos())
        self._update_band(preview=pt)

    def canvasDoubleClickEvent(self, event):
        self._finish()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish()

    def _update_band(self, preview=None):
        self.rubber_band.reset(QgsWkbTypes.LineGeometry)
        for p in self.points:
            self.rubber_band.addPoint(p, False)
        if preview is not None:
            self.rubber_band.addPoint(QgsPointXY(preview), True)
        else:
            self.rubber_band.show()

    def _finish(self):
        if len(self.points) >= 2:
            geom = QgsGeometry.fromPolylineXY(self.points)
            self.tracciatoCompletato.emit(geom)
        self._reset()

    def _cancel(self):
        self.tracciatoAnnullato.emit()
        self._reset()

    def _reset(self):
        self.points = []
        self.rubber_band.reset(QgsWkbTypes.LineGeometry)

    def deactivate(self):
        self._reset()
        super().deactivate()


class MapIndicator:
    """Marker mobile sulla mappa che segue la posizione sincronizzata dal grafico del profilo."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.marker = QgsVertexMarker(canvas)
        self.marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.marker.setColor(QColor(255, 0, 0))
        self.marker.setFillColor(QColor(255, 0, 0, 120))
        self.marker.setIconSize(14)
        self.marker.setPenWidth(3)
        self.hide()

    def show_at(self, x, y):
        self.marker.setCenter(QgsPointXY(x, y))
        self.marker.show()

    def hide(self):
        self.marker.hide()

    def remove(self):
        try:
            self.canvas.scene().removeItem(self.marker)
        except RuntimeError:
            self.marker = None
