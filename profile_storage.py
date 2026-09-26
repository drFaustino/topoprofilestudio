# -*- coding: utf-8 -*-
"""Archivio persistente dei profili TopoProfile Studio in GeoPackage."""
import os
import datetime
from qgis.core import (
    QgsVectorLayer, QgsField, QgsFields, QgsFeature, QgsGeometry,
    QgsPoint, QgsWkbTypes, QgsVectorFileWriter, QgsProject,
    QgsCoordinateReferenceSystem, edit, QgsFeatureRequest, QgsExpression
)
from qgis.PyQt.QtCore import QVariant


class ProfileStorage:
    LAYER_PROFILES = "profiles"
    LAYER_MARKERS = "markers"

    def __init__(self, gpkg_path: str):
        self.gpkg_path = gpkg_path
        self._ensure_gpkg()

    def _create_layer(self, layer_name, fields, geometry_type, crs):
        """Crea una singola layer GPKG in modo compatibile con QGIS 4.x."""
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.layerName = layer_name
        opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        result = QgsVectorFileWriter.create(
            self.gpkg_path, fields, geometry_type, crs,
            QgsProject.instance().transformContext(), opts
        )
        # QGIS può restituire un Writer oppure un errore; il layer viene verificato subito dopo.
        if hasattr(result, "hasError") and result.hasError():
            raise RuntimeError(result.errorMessage())
        del result

    def _ensure_gpkg(self):
        os.makedirs(os.path.dirname(self.gpkg_path), exist_ok=True)

        profiles_ok = self._open(self.LAYER_PROFILES) is not None
        markers_ok = self._open(self.LAYER_MARKERS) is not None

        if not profiles_ok:
            fields = QgsFields()
            for name, typ in [
                ("name", QVariant.String), ("label_a", QVariant.String), ("label_b", QVariant.String),
                ("ref_elevation", QVariant.Double), ("ref_auto", QVariant.Int), ("elev_scale", QVariant.Double),
                ("dist_scale", QVariant.Double), ("smoothing", QVariant.Int), ("source_type", QVariant.String),
                ("source_layer", QVariant.String), ("created", QVariant.String), ("crs", QVariant.String)
            ]:
                fields.append(QgsField(name, typ))
            try:
                self._create_layer(self.LAYER_PROFILES, fields, QgsWkbTypes.LineStringZM, QgsProject.instance().crs())
            except Exception:
                # Se il vecchio file non è un GeoPackage valido, lo preserviamo e
                # ricreiamo un archivio pulito invece di bloccare il plugin.
                if os.path.exists(self.gpkg_path):
                    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup = self.gpkg_path + ".bak_" + stamp
                    try:
                        os.replace(self.gpkg_path, backup)
                    except OSError:
                        raise RuntimeError(
                            "L'archivio profili esistente non è valido o non è scrivibile. "
                            f"Chiudi eventuali file '{self.gpkg_path}' aperti da altri programmi."
                        )
                self._create_layer(self.LAYER_PROFILES, fields, QgsWkbTypes.LineStringZM, QgsProject.instance().crs())
        else:
            # archivio pre-esistente: aggiunge eventuali campi introdotti in versioni successive
            self._migrate_profiles_schema()

        if not markers_ok:
            fields = QgsFields()
            for name, typ in [
                ("profile_name", QVariant.String), ("distanza", QVariant.Double),
                ("quota", QVariant.Double), ("etichetta", QVariant.String),
                ("categoria", QVariant.String)
            ]:
                fields.append(QgsField(name, typ))
            self._create_layer(self.LAYER_MARKERS, fields, QgsWkbTypes.Point, QgsProject.instance().crs())

    def _migrate_profiles_schema(self):
        """Aggiunge alla layer 'profiles' i campi introdotti in versioni successive
        del plugin, senza distruggere gli archivi esistenti (es. campo 'ref_auto')."""
        lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            return
        try:
            pr = lyr.dataProvider()
            additions = []
            if lyr.fields().indexOf("ref_auto") < 0:
                additions.append(QgsField("ref_auto", QVariant.Int))
            if lyr.fields().indexOf("smoothing") < 0:
                additions.append(QgsField("smoothing", QVariant.Int))
            if additions:
                pr.addAttributes(additions)
                lyr.updateFields()
        except Exception as e:
            raise RuntimeError(f"Impossibile aggiornare i campi del layer {lyr.name()}: {e}") from e

    def _open(self, layer_name):
        if not os.path.exists(self.gpkg_path):
            return None
        uri = f"{self.gpkg_path}|layername={layer_name}"
        lyr = QgsVectorLayer(uri, layer_name, "ogr")
        return lyr if lyr.isValid() else None

    def list_profiles(self):
        lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            self._ensure_gpkg()
            lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            return []
        out = []
        for f in lyr.getFeatures():
            out.append({
                "fid": f.id(), "name": f["name"],
                "label_a": f["label_a"], "label_b": f["label_b"],
                "ref_elevation": f["ref_elevation"], "ref_auto": _safe_ref_auto(f),
                "elev_scale": f["elev_scale"],
                "dist_scale": f["dist_scale"], "smoothing": bool(f["smoothing"]) if "smoothing" in f.fields().names() and f["smoothing"] is not None else False, "source_type": f["source_type"],
                "source_layer": f["source_layer"], "created": f["created"],
                "crs": f["crs"],
            })
        return out

    def save_profile(self, name, samples, crs, label_a="A", label_b="A'",
                     ref_elevation=0.0, ref_auto=True, elev_scale=1.0, dist_scale=1.0,
                     smoothing=False, source_type="dtm", source_layer="", markers=None, overwrite=True):
        """Salva/sovrascrive un profilo e i relativi marker."""
        self._ensure_gpkg()
        lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            raise RuntimeError(
                "Impossibile aprire l'archivio profili. Il GeoPackage non contiene una layer 'profiles'."
            )

        if overwrite:
            self.delete_profile(name)
            lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            raise RuntimeError("Impossibile riaprire l'archivio profili dopo la preparazione del salvataggio.")

        pts = [QgsPoint(s.x, s.y, s.z, s.dist_progressiva) for s in samples]
        geom = QgsGeometry.fromPolyline(pts)
        with edit(lyr):
            feat = QgsFeature(lyr.fields())
            feat.setGeometry(geom)
            feat["name"] = name
            feat["label_a"] = label_a
            feat["label_b"] = label_b
            feat["ref_elevation"] = float(ref_elevation)
            feat["ref_auto"] = 1 if ref_auto else 0
            feat["elev_scale"] = float(elev_scale)
            feat["dist_scale"] = float(dist_scale)
            if lyr.fields().indexOf("smoothing") >= 0:
                feat["smoothing"] = 1 if smoothing else 0
            feat["source_type"] = source_type
            feat["source_layer"] = source_layer
            feat["created"] = datetime.datetime.now().isoformat(timespec="seconds")
            feat["crs"] = crs.authid()
            if not lyr.addFeature(feat):
                raise RuntimeError("Impossibile scrivere il profilo nel GeoPackage.")

        if markers:
            self.save_markers(name, markers)

    def load_profile(self, name):
        lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            return None
        req = QgsFeatureRequest(QgsExpression(f'"name" = \'{_esc(name)}\''))
        feat = next(lyr.getFeatures(req), None)
        if feat is None:
            return None
        geom = feat.geometry()
        pts = geom.constGet().points() if hasattr(geom.constGet(), "points") else geom.asPolyline()
        from .profile_core import ProfileSample
        samples = []
        prev_prog = 0.0
        for p in pts:
            prog = p.m() if hasattr(p, "m") else 0.0
            samples.append(ProfileSample(p.x(), p.y(), p.z(), prog, prog - prev_prog))
            prev_prog = prog
        info = {
            "name": feat["name"], "label_a": feat["label_a"], "label_b": feat["label_b"],
            "ref_elevation": feat["ref_elevation"], "ref_auto": _safe_ref_auto(feat),
            "elev_scale": feat["elev_scale"],
            "dist_scale": feat["dist_scale"], "smoothing": bool(feat["smoothing"]) if "smoothing" in feat.fields().names() and feat["smoothing"] is not None else False, "source_type": feat["source_type"],
            "source_layer": feat["source_layer"], "crs": feat["crs"],
        }
        return samples, info, self.load_markers(name)

    def delete_profile(self, name):
        lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            return
        req = QgsFeatureRequest(QgsExpression(f'"name" = \'{_esc(name)}\''))
        ids = [f.id() for f in lyr.getFeatures(req)]
        if ids:
            with edit(lyr):
                lyr.deleteFeatures(ids)
        self.delete_markers(name)

    def rename_profile(self, old_name, new_name):
        lyr = self._open(self.LAYER_PROFILES)
        if not lyr:
            return
        req = QgsFeatureRequest(QgsExpression(f'"name" = \'{_esc(old_name)}\''))
        feat = next(lyr.getFeatures(req), None)
        if feat:
            with edit(lyr):
                lyr.changeAttributeValue(feat.id(), lyr.fields().indexOf("name"), new_name)
        mlyr = self._open(self.LAYER_MARKERS)
        if mlyr:
            req2 = QgsFeatureRequest(QgsExpression(f'"profile_name" = \'{_esc(old_name)}\''))
            with edit(mlyr):
                for f in mlyr.getFeatures(req2):
                    mlyr.changeAttributeValue(f.id(), mlyr.fields().indexOf("profile_name"), new_name)

    def save_markers(self, profile_name, markers):
        self.delete_markers(profile_name)
        lyr = self._open(self.LAYER_MARKERS)
        if not lyr:
            return
        from qgis.core import QgsPointXY
        with edit(lyr):
            for m in markers:
                feat = QgsFeature(lyr.fields())
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
                feat["profile_name"] = profile_name
                feat["distanza"] = float(m["distanza"])
                feat["quota"] = float(m["quota"])
                feat["etichetta"] = m["etichetta"]
                feat["categoria"] = m.get("categoria", "altro")
                lyr.addFeature(feat)

    def load_markers(self, profile_name):
        lyr = self._open(self.LAYER_MARKERS)
        if not lyr:
            return []
        req = QgsFeatureRequest(QgsExpression(f'"profile_name" = \'{_esc(profile_name)}\''))
        out = []
        for f in lyr.getFeatures(req):
            out.append({
                "distanza": f["distanza"], "quota": f["quota"],
                "etichetta": f["etichetta"], "categoria": f["categoria"],
            })
        out.sort(key=lambda m: m["distanza"])
        return out

    def delete_markers(self, profile_name):
        lyr = self._open(self.LAYER_MARKERS)
        if not lyr:
            return
        req = QgsFeatureRequest(QgsExpression(f'"profile_name" = \'{_esc(profile_name)}\''))
        ids = [f.id() for f in lyr.getFeatures(req)]
        if ids:
            with edit(lyr):
                lyr.deleteFeatures(ids)


def _safe_ref_auto(feat):
    """Legge il campo 'ref_auto' in modo sicuro anche su archivi creati con
    versioni precedenti del plugin (campo assente o valore NULL => True di default)."""
    try:
        val = feat["ref_auto"]
    except KeyError:
        return True
    return True if val is None else bool(val)


def _esc(s):
    return str(s).replace("'", "''")


def default_storage_path():
    from qgis.core import QgsApplication
    base = os.path.join(QgsApplication.qgisSettingsDirPath(), "topoprofilestudio")
    return os.path.join(base, "profili.gpkg")
