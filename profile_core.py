# -*- coding: utf-8 -*-
"""
profile_core.py
Logica di campionamento del profilo altimetrico:
 - densificazione del tracciato ad intervalli regolari
 - calcolo distanze parziali e progressive
 - estrazione quota da DTM raster oppure da curve di livello (interpolazione IDW)
"""
import bisect
import math
from qgis.core import (
    QgsGeometry, QgsPointXY, QgsDistanceArea, QgsProject,
    QgsSpatialIndex, QgsFeatureRequest, QgsWkbTypes
)
from qgis.PyQt.QtCore import QCoreApplication

# Ogni quante iterazioni "respirare" processando gli eventi Qt in un ciclo
# potenzialmente lungo, per evitare di bloccare l'interfaccia del plugin.
_UI_BREATH_EVERY = 200


def _breathe(counter):
    """Lascia respirare l'interfaccia (eventi Qt) durante cicli lunghi, senza
    introdurre un vero multithreading (più rischioso con i provider QGIS)."""
    counter += 1
    if counter % _UI_BREATH_EVERY == 0:
        QCoreApplication.processEvents()
    return counter


class ProfileSample:
    """Un campione lungo il profilo."""
    __slots__ = ("x", "y", "z", "dist_progressiva", "dist_parziale")

    def __init__(self, x, y, z, dist_progressiva, dist_parziale):
        self.x = x
        self.y = y
        self.z = z
        self.dist_progressiva = dist_progressiva
        self.dist_parziale = dist_parziale


def smooth_profile_z(samples, window=7):
    """Smussa le quote con un filtro binomiale, mantenendo le progressive.

    ``window`` controlla il livello: valori dispari 3, 7 e 11 sono usati dal
    pannello. Il bordo viene riflesso e il risultato resta entro il range
    delle quote originali per evitare overshoot artificiali.
    """
    if not samples:
        return []
    z = [float(s.z) for s in samples]
    n = len(z)
    if n < 3 or not window or window <= 1:
        return z
    window = int(window)
    if window % 2 == 0:
        window += 1
    window = min(window, n if n % 2 else n - 1)
    window = max(3, window)
    # Coefficienti binomiali: 3=[1,2,1], 7 e 11 ottenuti da convoluzioni
    # successive, con comportamento stabile e senza dipendenze esterne.
    coeff = [1]
    kernel = [1, 2, 1]
    while len(coeff) < window:
        out = [0] * (len(coeff) + 2)
        for i, a in enumerate(coeff):
            for j, b in enumerate(kernel):
                out[i + j] += a * b
        coeff = out
    half = len(coeff) // 2
    norm = float(sum(coeff))
    out = []
    for i in range(n):
        value = 0.0
        for j, c in enumerate(coeff):
            k = i + j - half
            if k < 0:
                k = -k
            if k >= n:
                k = 2 * n - 2 - k
            k = max(0, min(n - 1, k))
            value += c * z[k]
        out.append(value / norm)
    lo, hi = min(z), max(z)
    return [max(lo, min(hi, v)) for v in out]


def _distance_area(crs):
    da = QgsDistanceArea()
    da.setSourceCrs(crs, QgsProject.instance().transformContext())
    da.setEllipsoid(QgsProject.instance().ellipsoid())
    return da


def densify_line(geom: QgsGeometry, interval: float) -> QgsGeometry:
    """Densifica la linea (anche multiparte, viene unita in una singola polilinea)."""
    if geom.isMultipart():
        parts = geom.asMultiPolyline()
        pts = []
        for part in parts:
            pts.extend(part)
        geom = QgsGeometry.fromPolylineXY(pts)
    if interval and interval > 0:
        try:
            geom = geom.densifyByDistance(interval)
        except Exception:
            geom = QgsGeometry(geom)
    return geom


def build_distance_table(geom: QgsGeometry, crs, interval: float):
    """Ritorna una lista di (x, y, dist_progressiva, dist_parziale) lungo la linea densificata."""
    dense = densify_line(geom, interval)
    pts = dense.asPolyline()
    if not pts:
        return []
    da = _distance_area(crs)
    out = []
    prog = 0.0
    prev = pts[0]
    counter = 0
    for i, p in enumerate(pts):
        if i == 0:
            partial = 0.0
        else:
            try:
                partial = da.measureLine(QgsPointXY(prev.x(), prev.y()), QgsPointXY(p.x(), p.y()))
            except Exception:
                partial = math.hypot(p.x() - prev.x(), p.y() - prev.y())
            prog += partial
        out.append((p.x(), p.y(), prog, partial))
        prev = p
        counter = _breathe(counter)
    return out


def sample_from_dtm(geom: QgsGeometry, crs, dtm_layer, interval: float):
    """Campiona la quota da un raster DTM lungo il tracciato."""
    table = build_distance_table(geom, crs, interval)
    provider = dtm_layer.dataProvider()
    band = 1
    samples = []
    xform = None
    if dtm_layer.crs() != crs:
        from qgis.core import QgsCoordinateTransform
        xform = QgsCoordinateTransform(crs, dtm_layer.crs(), QgsProject.instance())
    counter = 0
    for x, y, prog, partial in table:
        pt = QgsPointXY(x, y)
        # riproietta se necessario
        if xform is not None:
            try:
                pt = xform.transform(pt)
            except Exception:
                counter = _breathe(counter)
                continue
        val, ok = provider.sample(pt, band)
        z = float(val) if ok and val is not None else float("nan")
        samples.append(ProfileSample(x, y, z, prog, partial))
        counter = _breathe(counter)
    return _clean_samples(samples)


def sample_from_contours(geom: QgsGeometry, crs, contour_layer, elevation_field: str,
                          interval: float, idw_power: float = 2.0, idw_k: int = 8):
    """
    Campiona la quota lungo il tracciato usando SOLO le curve di livello che
    intersecano effettivamente il tracciato: per ciascuna intersezione si
    ricava la distanza progressiva e la quota della curva, quindi i valori
    intermedi tra due intersezioni successive vengono interpolati linearmente
    lungo il profilo. Questo approccio è molto più veloce dell'IDW su tutti i
    vertici del layer (specialmente su layer molto grandi) perché limita la
    lettura ai soli elementi la cui estensione (bounding box) è vicina al
    tracciato, e il calcolo per punto si riduce a una semplice interpolazione.
    In assenza di intersezioni sufficienti si ricade sull'interpolazione IDW
    (sui soli vertici già letti) come rete di sicurezza.
    """
    table = build_distance_table(geom, crs, interval)
    if not table:
        return []
    total_length = table[-1][2]

    field_idx = contour_layer.fields().indexOf(elevation_field)
    if field_idx < 0:
        raise ValueError("Campo elevazione non trovato nel layer curve di livello")

    trace_geom = QgsGeometry(geom)
    need_transform = contour_layer.crs() != crs
    xform_to_trace = None
    xform_to_layer = None
    if need_transform:
        from qgis.core import QgsCoordinateTransform
        xform_to_trace = QgsCoordinateTransform(contour_layer.crs(), crs, QgsProject.instance())
        xform_to_layer = QgsCoordinateTransform(crs, contour_layer.crs(), QgsProject.instance())

    # Limita la lettura del layer alle sole feature la cui bbox è vicina al
    # tracciato (con un piccolo margine), invece di scandire l'intero layer.
    bbox = trace_geom.boundingBox()
    if xform_to_layer is not None:
        try:
            bbox = xform_to_layer.transformBoundingBox(bbox)
        except Exception:
            pass
    margin = max(bbox.width(), bbox.height(), 1.0) * 0.02
    bbox.grow(margin)

    request = QgsFeatureRequest().setFilterRect(bbox).setSubsetOfAttributes([field_idx])

    crossings = []  # (distanza_progressiva, quota)
    idx = QgsSpatialIndex()
    vertex_lookup = {}
    fid_counter = 0
    trace_len = trace_geom.length() or 1.0
    counter = 0

    for feat in contour_layer.getFeatures(request):
        g = feat.geometry()
        if g is None or g.isEmpty():
            continue
        z_val = feat.attributes()[field_idx]
        try:
            z_val = float(z_val)
        except (TypeError, ValueError):
            continue
        if xform_to_trace is not None:
            try:
                g = QgsGeometry(g)
                g.transform(xform_to_trace)
            except Exception:
                continue

        # Punti di intersezione reali tra la curva e il tracciato: da qui si
        # ricava direttamente la distanza progressiva e la quota nota.
        try:
            inter = trace_geom.intersection(g)
        except Exception:
            inter = None
        if inter is not None and not inter.isEmpty():
            pts = []
            if inter.type() == QgsWkbTypes.PointGeometry:
                if inter.isMultipart():
                    pts = inter.asMultiPoint()
                else:
                    pts = [inter.asPoint()]
            for p in pts:
                frac = trace_geom.lineLocatePoint(QgsGeometry.fromPointXY(QgsPointXY(p.x(), p.y())))
                if frac is None or frac < 0:
                    continue
                dist = (frac / trace_len) * total_length if trace_len else 0.0
                crossings.append((dist, z_val))

        # Vertici della curva come rete di sicurezza per l'IDW di fallback
        # (usati solo se non si trovano abbastanza intersezioni dirette).
        if g.isMultipart():
            lines = g.asMultiPolyline()
        else:
            lines = [g.asPolyline()]
        for line in lines:
            for p in line:
                vf_geom = QgsGeometry.fromPointXY(QgsPointXY(p.x(), p.y()))
                from qgis.core import QgsFeature as _QF
                vf = _QF(fid_counter)
                vf.setGeometry(vf_geom)
                idx.insertFeature(vf)
                vertex_lookup[fid_counter] = (p.x(), p.y(), z_val)
                fid_counter += 1
        counter = _breathe(counter)

    if fid_counter == 0:
        raise ValueError("Nessun vertice utile trovato nel layer curve di livello vicino al tracciato")

    crossings.sort(key=lambda c: c[0])
    # Rimuove duplicati troppo vicini (stessa curva intersecata più volte quasi nello stesso punto)
    dedup = []
    for d, z in crossings:
        if dedup and abs(d - dedup[-1][0]) < 1e-6:
            continue
        dedup.append((d, z))
    crossings = dedup

    samples = []
    counter = 0
    if len(crossings) >= 2:
        crossing_distances = [c[0] for c in crossings]
        for x, y, prog, partial in table:
            z = _interp_crossings(crossings, crossing_distances, prog)
            samples.append(ProfileSample(x, y, z, prog, partial))
            counter = _breathe(counter)
    else:
        # Rete di sicurezza: tracciato con poche/nessuna intersezione diretta
        # (es. curve molto rade rispetto all'intervallo di campionamento).
        for x, y, prog, partial in table:
            z = _idw_at_point(idx, vertex_lookup, x, y, idw_power, idw_k)
            samples.append(ProfileSample(x, y, z, prog, partial))
            counter = _breathe(counter)
    return _clean_samples(samples)


def _interp_crossings(crossings, crossing_distances, dist):
    """Interpola linearmente la quota in ``dist`` tra le intersezioni note
    (ordinate per distanza progressiva, con l'elenco delle sole distanze
    precalcolato per una ricerca binaria O(log n)). Oltre gli estremi
    mantiene la quota dell'intersezione più vicina."""
    if not crossings:
        return float("nan")
    if dist <= crossings[0][0]:
        return crossings[0][1]
    if dist >= crossings[-1][0]:
        return crossings[-1][1]
    i = bisect.bisect_right(crossing_distances, dist)
    d0, z0 = crossings[i - 1]
    d1, z1 = crossings[i]
    if d1 - d0 <= 1e-9:
        return z0
    ratio = (dist - d0) / (d1 - d0)
    return z0 + ratio * (z1 - z0)


def _idw_at_point(idx: QgsSpatialIndex, lookup: dict, x: float, y: float, power: float, k: int):
    nearest = idx.nearestNeighbor(QgsPointXY(x, y), k)
    if not nearest:
        return float("nan")
    num = 0.0
    den = 0.0
    for fid in nearest:
        vx, vy, vz = lookup[fid]
        d = math.hypot(vx - x, vy - y)
        if d < 1e-6:
            return vz
        w = 1.0 / (d ** power)
        num += w * vz
        den += w
    return num / den if den > 0 else float("nan")


def _clean_samples(samples):
    """Rimuove/interpola eventuali NaN isolati (nodata) senza spezzare il profilo."""
    n = len(samples)
    for i in range(n):
        if math.isnan(samples[i].z):
            # cerca vicini validi
            prev_v = next((samples[j] for j in range(i - 1, -1, -1) if not math.isnan(samples[j].z)), None)
            next_v = next((samples[j] for j in range(i + 1, n) if not math.isnan(samples[j].z)), None)
            if prev_v and next_v:
                span = next_v.dist_progressiva - prev_v.dist_progressiva
                if span > 0:
                    ratio = (samples[i].dist_progressiva - prev_v.dist_progressiva) / span
                    samples[i].z = prev_v.z + ratio * (next_v.z - prev_v.z)
            elif prev_v:
                samples[i].z = prev_v.z
            elif next_v:
                samples[i].z = next_v.z
            else:
                samples[i].z = 0.0
    return samples


def compute_stats(samples):
    if not samples:
        return {"min_z": 0.0, "max_z": 0.0, "length": 0.0}
    zs = [s.z for s in samples]
    min_z = min(zs)
    max_z = max(zs)
    return {
        "min_z": min_z,
        "max_z": max_z,
        "length": samples[-1].dist_progressiva,
        "relief": max_z - min_z,
    }


def suggest_reference_elevation(samples, margin_ratio: float = 0.1):
    """Calcola una quota di riferimento automatica con margine adeguato sotto il minimo."""
    stats = compute_stats(samples)
    span = max(stats["max_z"] - stats["min_z"], 1.0)
    margin = span * margin_ratio
    ref = math.floor((stats["min_z"] - margin) / 5.0) * 5.0
    return ref
