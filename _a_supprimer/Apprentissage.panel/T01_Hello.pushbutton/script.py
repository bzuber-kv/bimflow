# -*- coding: utf-8 -*-
__title__ = "T01\nHello"

from pyrevit import revit, DB

doc = revit.doc
sel = revit.get_selection()

if len(sel) != 1:
    print("Selectionne exactement UN element.")
else:
    e = sel.first
    p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    print("Avant :", p.AsString())
    with revit.Transaction("bimflow - T01 ecrire commentaire"):
        p.Set("test bimflow 2026-08-27")
    print("Apres :", p.AsString())