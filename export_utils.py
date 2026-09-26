# -*- coding: utf-8 -*-
"""
export_utils.py

Esportazione del profilo come immagine (PNG/SVG/JPG/PDF)
e come DXF 2D/3D.

Il DXF viene generato con ezdxf se disponibile nell'ambiente
Python di QGIS.

Il formato DWG nativo richiede una libreria proprietaria
(es. ODA File Converter): il plugin esporta sempre in DXF,
apribile/convertibile in DWG con AutoCAD o ODA.
"""

import os


def export_image(figure, path: str, dpi: int = 300):
    """
    Salva la figura centrata, ritagliata esattamente al suo contenuto.
    """
    ext = os.path.splitext(path)[1].lower().lstrip(".")

    fmt = {
        "jpg": "jpg",
        "jpeg": "jpg",
        "png": "png",
        "svg": "svg",
        "pdf": "pdf",
    }.get(ext, "png")

    figure.savefig(
        path,
        format=fmt,
        dpi=dpi,
        bbox_inches="tight",
        pad_inches=0.35,
        facecolor=figure.get_facecolor(),
    )


def ezdxf_available():
    try:
        import ezdxf  # noqa
        return True
    except ImportError:
        return False


def _dxf_color_categoria(categoria):
    """
    Colori DXF coerenti con le categorie visualizzate nel grafico.

    I colori sono espressi come True Color RGB e convertiti
    nel formato intero utilizzato da ezdxf.
    """
    palette = {
        "litologico": (0, 183, 147),        # #00b793
        "faglia": (255, 0, 0),              # #ff0000
        "sovrascorrimento": (139, 69, 19),  # #8b4513
        "piega": (0, 0, 0),                 # #000000
        "limite": (0, 128, 0),              # #008000
        "sondaggio": (0, 147, 183),         # #0093b7
        "prova": (255, 0, 255),             # #ff00ff
        "piezometro": (0, 0, 255),          # #0000ff
        "livello": (135, 206, 235),         # #87ceeb
        "altro": (163, 181, 255),           # #a3b5ff
    }

    rgb = palette.get(categoria, palette["altro"])

    return (
        (rgb[0] << 16)
        | (rgb[1] << 8)
        | rgb[2]
    )


def _nice_ticks(vmin, vmax, nbins=7):
    """
    Restituisce valori di graduazione puliti per un asse.
    """
    try:
        from matplotlib.ticker import MaxNLocator

        return list(
            MaxNLocator(nbins=nbins).tick_values(
                vmin,
                vmax,
            )
        )

    except Exception:
        if vmax <= vmin:
            return [vmin]

        step = (vmax - vmin) / max(nbins, 1)

        out = []
        v = vmin

        while v <= vmax + step * 0.01:
            out.append(v)
            v += step

        return out


def export_dxf(
    samples,
    path,
    mode="2D",
    label_a="A",
    label_b="A'",
    markers=None,
    ref_elevation=None,
    smoothing=False,
    smoothing_level=7,
):
    """
    Esporta il profilo in DXF.

    2D:
        - X = distanza progressiva
        - Y = quota relativa alla base grafica
        - asse X sotto il profilo
        - due assi Y
        - A e A' sopra i rispettivi assi
        - marker organizzati in layer per categoria

    3D:
        - X/Y = coordinate reali
        - Z = quota reale
        - marker organizzati in layer per categoria
    """

    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # ==================================================================
    # STILI E LAYER
    # ==================================================================

    if "TP_TEXT" not in doc.styles:
        doc.styles.new(
            "TP_TEXT",
            dxfattribs={
                "font": "Arial.ttf",
                "width": 0.92,
            },
        )

    # Layer principali.
    for name, color in (
        ("PROFILO", 1),
        ("MARKER", 6),
        ("TESTO", 7),
        ("ASSI", 8),
    ):
        if name not in doc.layers:
            doc.layers.add(
                name,
                color=color,
            )

    # ==================================================================
    # LAYER DELLE CATEGORIE DEI MARKER
    # ==================================================================

    categoria_layer = {
        "litologico": "MARK_LITOLOGICO",
        "faglia": "MARK_FAGLIA",
        "sovrascorrimento": "MARK_SOVRASCORRIMENTO",
        "piega": "MARK_PIEGA",
        "limite": "MARK_LIMITE",
        "sondaggio": "MARK_SONDAGGIO",
        "prova": "MARK_PROVA",
        "piezometro": "MARK_PIEZOMETRO",
        "livello": "MARK_LIVELLO",
        "altro": "MARK_ALTRO",
    }

    for categoria, layer_name in categoria_layer.items():

        if layer_name not in doc.layers:
            layer = doc.layers.add(layer_name)

            layer.dxf.true_color = _dxf_color_categoria(
                categoria
            )

    markers = markers or []

    # ==================================================================
    # FUNZIONE PER INSERIRE TESTO
    # ==================================================================

    def add_text(
        text,
        position,
        height,
        align=TextEntityAlignment.MIDDLE_CENTER,
        rotation=0.0,
        color=None,
        layer="TESTO",
    ):
        """
        Inserisce testo DXF con allineamento CAD esplicito.
        """

        attrs = {
            "layer": layer,
            "height": max(float(height), 0.01),
            "style": "TP_TEXT",
        }

        if color is not None:
            attrs["color"] = color

        entity = msp.add_text(
            str(text),
            dxfattribs=attrs,
        )

        entity.set_placement(
            position,
            align=align,
        )

        if rotation:
            entity.dxf.rotation = rotation

        return entity

    # ==================================================================
    # DXF 2D
    # ==================================================================

    if mode == "2D":

        if not samples:
            doc.saveas(path)
            return

        # --------------------------------------------------------------
        # PROFILO
        # --------------------------------------------------------------

        from .profile_core import smooth_profile_z

        profile_z = (
            smooth_profile_z(
                samples,
                smoothing_level,
            )
            if smoothing
            else [
                float(s.z)
                for s in samples
            ]
        )

        dist_values = [
            float(s.dist_progressiva)
            for s in samples
        ]

        x_min = min(dist_values)
        x_max = max(dist_values)

        # Il profilo parte da X=0.
        x_offset = x_min

        # Quota di riferimento.
        if ref_elevation is not None:
            base_z = float(ref_elevation)
        else:
            base_z = min(profile_z)

        # --------------------------------------------------------------
        # PUNTI DEL PROFILO
        # --------------------------------------------------------------

        base_pts = [
            (
                float(s.dist_progressiva) - x_offset,
                float(z) - base_z,
                0.0,
            )
            for s, z in zip(
                samples,
                profile_z,
            )
        ]

        # --------------------------------------------------------------
        # PROFILO SMUSSATO
        # --------------------------------------------------------------

        if smoothing and len(base_pts) > 1:

            pts = []
            subdivisions = 8

            for i in range(len(base_pts) - 1):

                p0 = base_pts[i]
                p1 = base_pts[i + 1]

                for j in range(subdivisions):

                    t = j / float(subdivisions)

                    pts.append(
                        (
                            p0[0]
                            + (p1[0] - p0[0]) * t,

                            p0[1]
                            + (p1[1] - p0[1]) * t,

                            0.0,
                        )
                    )

            pts.append(base_pts[-1])

        else:
            pts = base_pts

        if len(pts) >= 2:

            msp.add_polyline3d(
                pts,
                dxfattribs={
                    "layer": "PROFILO"
                },
            )

        # --------------------------------------------------------------
        # ESTENSIONI DEL DISEGNO
        # --------------------------------------------------------------

        x_profile_min = (
            min(p[0] for p in pts)
            if pts
            else 0.0
        )

        x_profile_max = (
            max(p[0] for p in pts)
            if pts
            else 1.0
        )

        z_profile_min = (
            min(p[1] for p in pts)
            if pts
            else 0.0
        )

        z_profile_max = (
            max(p[1] for p in pts)
            if pts
            else 1.0
        )

        x_span = max(
            x_profile_max - x_profile_min,
            1.0,
        )

        z_span = max(
            z_profile_max - z_profile_min,
            1.0,
        )

        # --------------------------------------------------------------
        # DIMENSIONAMENTO TESTO
        # --------------------------------------------------------------

        txt_h = max(
            z_span * 0.045,
            min(
                x_span * 0.012,
                z_span * 0.085,
            ),
            0.30,
        )

        tick_txt_h = txt_h * 0.72
        axis_label_h = txt_h * 0.95

        # --------------------------------------------------------------
        # SPAZIATURE ASSI Y
        # --------------------------------------------------------------

        tick_len = max(
            min(
                z_span * 0.018,
                x_span * 0.012,
            ),
            txt_h * 0.35,
        )

        left_axis_gap = max(
            x_span * 0.018,
            txt_h * 2.8,
        )

        y_axis_1 = x_profile_min - left_axis_gap

        # Asse Y2 leggermente a destra del profilo,
        # usando lo stesso margine dell'asse Y1.
        y_axis_2 = x_profile_max + left_axis_gap

        numeric_gap = max(
            txt_h * 0.65,
            x_span * 0.005,
        )

        # --------------------------------------------------------------
        # LIMITI VERTICALI
        # --------------------------------------------------------------

        elev_orig_min = min(
            float(s.z)
            for s in samples
        )

        elev_orig_max = max(
            float(s.z)
            for s in samples
        )

        elev_ticks = [
            float(v)
            for v in _nice_ticks(
                elev_orig_min,
                elev_orig_max,
                6,
            )
            if float(v)
            >= elev_orig_min - 1e-6
        ]

        if not elev_ticks:
            elev_ticks = [
                float(elev_orig_min)
            ]

        # Garantisce sempre almeno un tick
        # superiore alla quota massima.
        while elev_ticks[-1] <= elev_orig_max + 1e-6:

            if len(elev_ticks) >= 2:

                tick_step = (
                    elev_ticks[-1]
                    - elev_ticks[-2]
                )

            else:

                tick_step = max(
                    (
                        elev_orig_max
                        - elev_orig_min
                    ) / 5.0,
                    1.0,
                )

            if tick_step <= 0:
                tick_step = 1.0

            elev_ticks.append(
                elev_ticks[-1]
                + tick_step
            )

        y_bottom = 0.0

        y_top = max(
            z_profile_max,
            elev_ticks[-1] - base_z,
        )

        if y_top <= y_bottom:
            y_top = y_bottom + 1.0

        # --------------------------------------------------------------
        # A E A'
        # --------------------------------------------------------------

        aa_gap = max(
            txt_h * 2.2,
            z_span * 0.055,
        )

        aa_y = y_top + aa_gap

        add_text(
            label_a,
            (
                y_axis_1,
                aa_y,
            ),
            axis_label_h,
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

        add_text(
            label_b,
            (
                y_axis_2,
                aa_y,
            ),
            axis_label_h,
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

        # --------------------------------------------------------------
        # ASSE Y PRINCIPALE
        # --------------------------------------------------------------

        msp.add_line(
            (
                y_axis_1,
                y_bottom,
            ),
            (
                y_axis_1,
                y_top,
            ),
            dxfattribs={
                "layer": "ASSI"
            },
        )

        # --------------------------------------------------------------
        # SECONDO ASSE Y
        # --------------------------------------------------------------

        msp.add_line(
            (
                y_axis_2,
                y_bottom,
            ),
            (
                y_axis_2,
                y_top,
            ),
            dxfattribs={
                "layer": "ASSI"
            },
        )

        # --------------------------------------------------------------
        # TICK E QUOTE ASSE Y
        # --------------------------------------------------------------

        for zv in elev_ticks:

            if zv < elev_orig_min - 1e-6:
                continue

            zp = float(zv) - base_z

            if zp < y_bottom - 1e-6:
                continue

            if zp > y_top + 1e-6:
                continue

            # Tick asse Y principale.
            msp.add_line(
                (
                    y_axis_1 - tick_len,
                    zp,
                ),
                (
                    y_axis_1 + tick_len,
                    zp,
                ),
                dxfattribs={
                    "layer": "ASSI"
                },
            )

            # Tick asse Y secondario.
            msp.add_line(
                (
                    y_axis_2 - tick_len,
                    zp,
                ),
                (
                    y_axis_2 + tick_len,
                    zp,
                ),
                dxfattribs={
                    "layer": "ASSI"
                },
            )

            # Numero quota.
            add_text(
                f"{zv:g}",
                (
                    y_axis_1
                    - tick_len
                    - numeric_gap,
                    zp,
                ),
                tick_txt_h,
                align=TextEntityAlignment.MIDDLE_RIGHT,
            )

        # --------------------------------------------------------------
        # TITOLO ASSE Y
        # --------------------------------------------------------------

        y_title_gap = max(
            txt_h * 2.2,
            x_span * 0.015,
        )

        y_title_x = (
            y_axis_1
            - tick_len
            - numeric_gap
            - y_title_gap
        )

        y_title_y = (
            y_bottom + y_top
        ) / 2.0

        add_text(
            "Quota (m s.l.m.)",
            (
                y_title_x,
                y_title_y,
            ),
            axis_label_h,
            align=TextEntityAlignment.MIDDLE_CENTER,
            rotation=90.0,
        )

        # --------------------------------------------------------------
        # ASSE X
        # --------------------------------------------------------------

        x_axis_gap = max(
            z_span * 0.12,
            txt_h * 3.4,
        )

        axis_x = y_bottom - x_axis_gap

        msp.add_line(
            (
                x_profile_min,
                axis_x,
            ),
            (
                x_profile_max,
                axis_x,
            ),
            dxfattribs={
                "layer": "ASSI"
            },
        )

        # --------------------------------------------------------------
        # TICK X
        # --------------------------------------------------------------

        dist_orig_min = min(dist_values)
        dist_orig_max = max(dist_values)

        x_ticks = _nice_ticks(
            dist_orig_min,
            dist_orig_max,
            8,
        )

        for dv in x_ticks:

            if dv < dist_orig_min - 1e-6:
                continue

            if dv > dist_orig_max + 1e-6:
                continue

            xv = float(dv) - x_offset

            msp.add_line(
                (
                    xv,
                    axis_x - tick_len,
                ),
                (
                    xv,
                    axis_x + tick_len,
                ),
                dxfattribs={
                    "layer": "ASSI"
                },
            )

            add_text(
                f"{dv:g}",
                (
                    xv,
                    axis_x
                    - tick_len
                    - tick_txt_h * 0.85,
                ),
                tick_txt_h,
                align=TextEntityAlignment.TOP_CENTER,
            )

        # --------------------------------------------------------------
        # ETICHETTA ASSE X
        # --------------------------------------------------------------

        x_title_y = (
            axis_x
            - tick_len
            - tick_txt_h * 2.7
        )

        add_text(
            "Distanza progressiva (m)",
            (
                (
                    x_profile_min
                    + x_profile_max
                ) / 2.0,
                x_title_y,
            ),
            axis_label_h,
            align=TextEntityAlignment.TOP_CENTER,
        )

        # --------------------------------------------------------------
        # MARKER 2D
        # --------------------------------------------------------------

        marker_h = max(
            txt_h * 0.75,
            0.25,
        )

        marker_top = (
            y_top
            + txt_h * 0.9
        )

        for m in markers:

            categoria = m.get(
                "categoria",
                "altro",
            )

            # Categoria non riconosciuta
            # -> layer "altro".
            if categoria not in categoria_layer:
                categoria = "altro"

            marker_layer = categoria_layer[
                categoria
            ]

            colore = _dxf_color_categoria(
                categoria
            )

            mx = (
                float(m["distanza"])
                - x_offset
            )

            mz = (
                float(m["quota"])
                - base_z
            )

            # ----------------------------------------------------------
            # LINEA VERTICALE MARKER
            # ----------------------------------------------------------

            msp.add_line(
                (
                    mx,
                    mz,
                ),
                (
                    mx,
                    marker_top,
                ),
                dxfattribs={
                    "layer": marker_layer,
                    "color": colore,
                },
            )

            # ----------------------------------------------------------
            # ETICHETTA MARKER
            # ----------------------------------------------------------

            add_text(
                m["etichetta"],
                (
                    mx,
                    marker_top
                    + marker_h * 0.25,
                ),
                marker_h,
                align=TextEntityAlignment.BOTTOM_CENTER,
                color=colore,
                layer=marker_layer,
            )

    # ==================================================================
    # DXF 3D
    # ==================================================================

    else:

        from .profile_core import smooth_profile_z

        if not samples:
            doc.saveas(path)
            return

        z_values = (
            smooth_profile_z(
                samples,
                smoothing_level,
            )
            if smoothing
            else [
                float(s.z)
                for s in samples
            ]
        )

        pts = [
            (
                float(s.x),
                float(s.y),
                float(z),
            )
            for s, z in zip(
                samples,
                z_values,
            )
        ]

        if len(pts) >= 2:

            msp.add_polyline3d(
                pts,
                dxfattribs={
                    "layer": "PROFILO"
                },
            )

        marker_h = 1.0

        # --------------------------------------------------------------
        # MARKER 3D
        # --------------------------------------------------------------

        for m in markers:

            categoria = m.get(
                "categoria",
                "altro",
            )

            if categoria not in categoria_layer:
                categoria = "altro"

            marker_layer = categoria_layer[
                categoria
            ]

            colore = _dxf_color_categoria(
                categoria
            )

            nearest = min(
                samples,
                key=lambda s: abs(
                    float(
                        s.dist_progressiva
                    )
                    - float(
                        m["distanza"]
                    )
                ),
            )

            # Punto 3D del marker.
            msp.add_point(
                (
                    float(nearest.x),
                    float(nearest.y),
                    float(nearest.z),
                ),
                dxfattribs={
                    "layer": marker_layer,
                    "color": colore,
                },
            )

            # Etichetta del marker.
            add_text(
                m["etichetta"],
                (
                    float(nearest.x),
                    float(nearest.y),
                    float(nearest.z),
                ),
                marker_h,
                align=TextEntityAlignment.BOTTOM_CENTER,
                color=colore,
                layer=marker_layer,
            )

    # ==================================================================
    # SALVATAGGIO
    # ==================================================================

    doc.saveas(path)