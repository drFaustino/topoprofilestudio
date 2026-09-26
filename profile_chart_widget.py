# -*- coding: utf-8 -*-
"""Grafico del profilo altimetrico e figura condivisa per le esportazioni."""
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout

from .profile_core import smooth_profile_z

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator


class ProfileChartWidget(QWidget):
    posizioneSpostata = pyqtSignal(float, float)
    posizioneUscita = pyqtSignal()
    markerCliccato = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(6, 3), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        self.ax = self.figure.add_subplot(111)
        self.ax_right = None
        self.samples = []
        self.markers = []
        self.label_a = "A"
        self.label_b = "A'"
        self.ref_elevation = 0.0
        self.smoothing_level = 7
        self.same_scale = False
        self.profile_color = "#c0392b"
        self.background_color = "#ffaa7f"
        self._cross_v = None
        self._cross_dot = None

        self.canvas.mpl_connect("motion_notify_event", self._on_move)
        self.canvas.mpl_connect("figure_leave_event", self._on_leave)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        self._style(self.ax)
        self._draw(self.ax, interactive=False)
        self.canvas.draw_idle()

    def _style(self, ax):
        ax.figure.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#ffffff")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.5)

    @staticmethod
    def _automatic_reference(samples):
        if not samples:
            return 0.0
        vals = [float(s.z) for s in samples]
        zmin, zmax = min(vals), max(vals)
        span = max(zmax - zmin, 1.0)
        return zmin - max(span * 0.05, 1.0)

    def set_data(self, samples, markers=None, label_a="A", label_b="A'",
             smoothing=False, smoothing_level=7,
             profile_color="#c0392b", background_color="#ffaa7f"):
        self.samples = samples or []
        self.markers = markers or []
        self.label_a = label_a
        self.label_b = label_b
        self.smoothing_enabled = bool(smoothing)
        self.smoothing_level = int(smoothing_level or 7)
        self.profile_color = profile_color or "#c0392b"
        self.background_color = background_color or "#ffaa7f"
        self.ref_elevation = self._automatic_reference(self.samples)
        self.redraw()

    def redraw(self):
        self.ax.clear()
        if self.ax_right is not None:
            self.ax_right.remove()
            self.ax_right = None
        self._style(self.ax)
        self._draw(self.ax, interactive=True)
        self.canvas.draw_idle()

    def _scaled_x(self, distance):
        return float(distance)

    def _scaled_z(self, elevation):
        return float(elevation) - self.ref_elevation

    @staticmethod
    def _nice_ticks(vmin, vmax, nbins=7):
        if vmax <= vmin:
            return [vmin]
        return list(MaxNLocator(nbins=nbins).tick_values(vmin, vmax))

    def _draw(self, ax, interactive=True):
        # ------------------------------------------------------------
        # Assi sempre visibili, anche quando non è ancora presente
        # un profilo.
        # ------------------------------------------------------------

        ax.set_xlabel(
            self.tr("Distanza progressiva (m)"),
            fontweight="bold",
            labelpad=16
        )

        ax.set_ylabel(
            self.tr("Quota (m s.l.m.)"),
            fontweight="bold",
            labelpad=14
        )

        # Mantiene sempre visibile la griglia.
        ax.grid(
            True,
            linestyle="--",
            linewidth=0.6,
            alpha=0.5
        )

        # ------------------------------------------------------------
        # GRAFICO VUOTO
        # ------------------------------------------------------------

        if not self.samples:
            ax.set_xlim(0, 100)
            ax.set_ylim(0, 100)

            # Scala neutra iniziale.
            # I valori servono solo a rendere leggibili
            # assi e griglia prima del caricamento del profilo.
            ax.set_xticks([0, 20, 40, 60, 80, 100])
            ax.set_yticks([0, 20, 40, 60, 80, 100])

            return

        xs = [self._scaled_x(s.dist_progressiva) for s in self.samples]
        raw_z = [s.z for s in self.samples]
        profile_z = smooth_profile_z(self.samples, self.smoothing_level) if self.smoothing_enabled else raw_z
        zs_plot = [self._scaled_z(z) for z in profile_z]

        ax.plot(xs, zs_plot, color=self.profile_color, linewidth=2, zorder=3)
        ax.fill_between(xs, zs_plot, 0.0, color=self.background_color, alpha=0.65, zorder=1)

        ax.set_xlim(left=0)

        x_ticks = [v for v in self._nice_ticks(self.samples[0].dist_progressiva, self.samples[-1].dist_progressiva, 8)
                   if self.samples[0].dist_progressiva - 1e-6 <= v <= self.samples[-1].dist_progressiva + 1e-6]
        ax.set_xticks([self._scaled_x(v) for v in x_ticks])
        ax.set_xticklabels([f"{v:g}" for v in x_ticks])

        z_min = min(s.z for s in self.samples)
        z_max = max(s.z for s in self.samples)

        # ------------------------------------------------------------
        # Scala Y: deve comprendere sempre almeno un tick
        # superiore alla quota massima del profilo.
        #
        # Esempio:
        # quota max = 594.8 m
        # -> ultimo tick = 600 m
        # ------------------------------------------------------------

        y_ticks = self._nice_ticks(
            z_min,
            z_max,
            6
        )

        y_ticks = [
            v for v in y_ticks
            if v >= z_min - 1e-6
        ]

        if y_ticks:
            if y_ticks[-1] <= z_max + 1e-6:

                if len(y_ticks) >= 2:
                    step = (
                        y_ticks[-1]
                        - y_ticks[-2]
                    )
                else:
                    step = max(
                        abs(z_max - z_min) / 5.0,
                        1.0
                    )

                y_ticks.append(
                    y_ticks[-1] + step
                )

        ymin = min(zs_plot)
        ymax = max(zs_plot)

        span = max(
            ymax - ymin,
            1.0
        )

        pad = max(
            span * 0.08,
            0.05
        )

        lower = -max(
            span * 0.06,
            0.05
        )

        upper = ymax + pad * 2.4

        # Garantisce che l'ultimo tick sia realmente
        # contenuto nell'area del grafico.
        if y_ticks:
            upper = max(
                upper,
                self._scaled_z(y_ticks[-1])
                + pad * 0.35
            )

        ax.set_ylim(
            lower,
            upper
        )

        y_tick_positions = [
            self._scaled_z(v)
            for v in y_ticks
        ]

        ax.set_yticks(
            y_tick_positions
        )

        ax.set_yticklabels(
            [f"{v:g}" for v in y_ticks]
        )

        # Etichette A e A' sopra le estremità. A' è anche il riferimento del secondo asse Y.
        ax.text(xs[0], upper, self.label_a, fontsize=12, fontweight="bold",
                ha="left", va="bottom", color="#2c3e50", clip_on=False)
        self.ax_right = ax.twinx()
        self.ax_right.set_ylim(ax.get_ylim())
        self.ax_right.set_yticks(y_tick_positions)
        self.ax_right.set_yticklabels([])
        self.ax_right.tick_params(axis="y", length=4, width=0.8)
        self.ax_right.spines["top"].set_visible(False)
        self.ax_right.spines["left"].set_visible(False)
        self.ax_right.spines["bottom"].set_visible(False)
        self.ax_right.spines["right"].set_visible(True)
        self.ax_right.text(1.0, 1.015, self.label_b, transform=self.ax_right.transAxes,
                           fontsize=12, fontweight="bold", ha="right", va="bottom",
                           color="#2c3e50", clip_on=False)

        top_label_y = upper - pad * 0.55
        for m in self.markers:
            mx = self._scaled_x(m["distanza"])
            mz = self._scaled_z(m["quota"])
            colore = _colore_categoria(m.get("categoria", "altro"))
            ax.plot([mx, mx], [mz, top_label_y], color=colore, linestyle=":", linewidth=1.2, alpha=0.85, zorder=2)
            ax.plot([mx], [mz], marker="o", color=colore, markersize=6, zorder=4)
            ax.annotate(m["etichetta"], xy=(mx, top_label_y), xytext=(0, 4),
                        textcoords="offset points", xycoords="data", fontsize=8,
                        fontweight="bold", color=colore, ha="center", va="bottom",
                        zorder=5, clip_on=False)

        if interactive:
            self._cross_v = ax.axvline(xs[0], color="#3498db", linewidth=1, alpha=0.0)
            self._cross_dot, = ax.plot([xs[0]], [zs_plot[0]], "o", color="#2980b9", alpha=0.0, zorder=5)

    def build_export_figure(self, width_in=11.0, min_height_in=3.6, max_height_in=7.5, dpi=150):
        if not self.samples:
            return None
        xs = [self._scaled_x(s.dist_progressiva) for s in self.samples]
        raw_z = [s.z for s in self.samples]
        profile_z = smooth_profile_z(self.samples, self.smoothing_level) if self.smoothing_enabled else raw_z
        zs_plot = [self._scaled_z(z) for z in profile_z]
        x_span = (max(xs) - min(xs)) or 1.0
        z_span = (max(zs_plot) - min(zs_plot)) or 1.0

        rapporto = z_span / x_span
        height_in = min(
            max(width_in * rapporto * 1.35 + 1.4, min_height_in),
            max_height_in
        )

        fig = Figure(figsize=(width_in, height_in), dpi=dpi)
        ax = fig.add_subplot(111)
        self._style(ax)
        self._draw(ax, interactive=False)
        fig.subplots_adjust(left=0.105, right=0.94, top=0.84, bottom=0.18)
        return fig

    def _nearest_sample(self, dist_scaled):
        if not self.samples:
            return None
        target = dist_scaled
        return min(self.samples, key=lambda s: abs(s.dist_progressiva - target))

    def _on_move(self, event):
        if event.inaxes not in (self.ax, self.ax_right) or event.xdata is None or not self.samples:
            return
        s = self._nearest_sample(event.xdata)
        if s is None:
            return
        x_plot = self._scaled_x(s.dist_progressiva)
        profile_z = smooth_profile_z(self.samples, self.smoothing_level) if self.smoothing_enabled else None
        z_value = profile_z[self.samples.index(s)] if profile_z else s.z
        z_plot = self._scaled_z(z_value)
        if self._cross_v is not None:
            self._cross_v.set_xdata([x_plot, x_plot])
            self._cross_v.set_alpha(0.8)
        if self._cross_dot is not None:
            self._cross_dot.set_data([x_plot], [z_plot])
            self._cross_dot.set_alpha(1.0)
        self.canvas.draw_idle()
        self.posizioneSpostata.emit(s.x, s.y)

    def _on_leave(self, event):
        if self._cross_v is not None:
            self._cross_v.set_alpha(0.0)
        if self._cross_dot is not None:
            self._cross_dot.set_alpha(0.0)
        self.canvas.draw_idle()
        self.posizioneUscita.emit()

    def _on_click(self, event):
        if event.inaxes not in (self.ax, self.ax_right) or event.xdata is None:
            return
        s = self._nearest_sample(event.xdata)
        if s is not None:
            self.markerCliccato.emit(s.dist_progressiva)


def _colore_categoria(categoria):
    palette = {
        "litologico": "#00b793",      # Cambio litologico: 0, 183, 147
        "faglia": "#ff0000",           # Rosso
        "sovrascorrimento": "#8b4513", # Marrone
        "piega": "#000000",            # Nero
        "limite": "#008000",           # Verde
        "sondaggio": "#0093b7",       # 0, 147, 183
        "prova": "#ff00ff",            # Magenta
        "piezometro": "#0000ff",       # Blu
        "livello": "#87ceeb",          # Celeste
        "altro": "#a3b5ff",            # 163, 181, 255
    }
    return palette.get(categoria, "#a3b5ff")
