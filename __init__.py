# -*- coding: utf-8 -*-
"""TopoProfile Studio - plugin QGIS per profili altimetrici professionali."""


def classFactory(iface):
    from .topoprofilestudio import TopoProfileStudio
    return TopoProfileStudio(iface)
