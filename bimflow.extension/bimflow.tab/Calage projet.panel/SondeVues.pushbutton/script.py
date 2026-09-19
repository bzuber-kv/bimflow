# -*- coding: utf-8 -*-
"""Pourquoi un parametre du socle est-il en lecture seule sur certaines vues ?

Outil BLEU : lecture seule, aucune transaction.

Question a laquelle il repond. Lors de la migration de « Classement Vues »
vers DOC_Classement_vue, 35 vraies vues (16 coupes, 13 vues 3D, 6 plans) ont
refuse l'ecriture, cible en lecture seule, sans explication. Cet outil dresse
le tableau complet des vues et de leurs proprietes, pour que la comparaison
entre les vues qui acceptent et celles qui refusent saute aux yeux.

Il ne conclut pas. Il met les deux populations cote a cote.

pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de shebang.
"""

__title__ = "Sonde\nvues"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-09-19n"

import codecs

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import FilteredElementCollector, View, Viewport

doc = revit.doc
out = script.get_output()

# Le parametre observe. Modifier ici si la question se repose sur un autre.
PARAM_CIBLE = u"DOC_Classement_vue"
PARAM_SOURCE = u"Classement Vues"


def oui_non(v):
    return u"oui" if v else u"non"


def sur_feuille():
    """{id de vue: nom de feuille} pour toutes les vues placees."""
    place = {}
    for vp in list(FilteredElementCollector(doc).OfClass(Viewport).ToElements()):
        try:
            vid = vp.ViewId
            sid = vp.SheetId
        except Exception:
            continue
        feuille = u"?"
        try:
            f = doc.GetElement(sid)
            if f is not None:
                feuille = f.Name
        except Exception:
            pass
        try:
            place[vid.Value] = feuille
        except Exception:
            continue
    return place


placees = sur_feuille()

out.print_md(u"# Sonde — vues et parametre `" + PARAM_CIBLE + u"`")
out.print_md(u"**Version de l'outil** : `" + VERSION + u"`")
out.print_md(u"**Maquette** : `" + doc.Title + u"`")
out.print_md(u"> Lecture seule. Rien n'a ete modifie.")

vues = list(FilteredElementCollector(doc).OfClass(View).ToElements())

lignes = []
compte = {}

for v in vues:
    try:
        nom = v.Name
    except Exception:
        nom = u"?"
    try:
        classe = v.GetType().Name
    except Exception:
        classe = u"?"

    gabarit = False
    try:
        gabarit = v.IsTemplate
    except Exception:
        pass

    dependante = False
    try:
        pid = v.GetPrimaryViewId()
        dependante = pid is not None and pid.Value > 0
    except Exception:
        pass

    gabarit_applique = u""
    try:
        tid = v.ViewTemplateId
        if tid is not None and tid.Value > 0:
            t = doc.GetElement(tid)
            gabarit_applique = t.Name if t is not None else u"(inconnu)"
    except Exception:
        pass

    feuille = u""
    try:
        feuille = placees.get(v.Id.Value, u"")
    except Exception:
        pass

    etat_cible = u"absent"
    try:
        p = v.LookupParameter(PARAM_CIBLE)
        if p is not None:
            etat_cible = u"LECTURE SEULE" if p.IsReadOnly else u"inscriptible"
    except Exception:
        etat_cible = u"erreur"

    valeur_source = u""
    try:
        s = v.LookupParameter(PARAM_SOURCE)
        if s is not None:
            valeur_source = s.AsString() or u""
    except Exception:
        pass

    lignes.append([
        nom, classe, oui_non(gabarit), oui_non(dependante),
        gabarit_applique, feuille, etat_cible, valeur_source,
    ])
    compte[etat_cible] = compte.get(etat_cible, 0) + 1

out.print_md(u"## Bilan")
for k in sorted(compte.keys()):
    out.print_md(u"- **" + k + u"** : " + str(compte[k]) + u" vues")

# Croisements qui reveleraient la cause d'un coup d'oeil
def croiser(titre, indice):
    tableau = {}
    for l in lignes:
        cle = (l[indice] if l[indice] else u"(vide)", l[6])
        tableau[cle] = tableau.get(cle, 0) + 1
    donnees = [[k[0], k[1], str(n)] for k, n in tableau.items()]
    donnees.sort(key=lambda x: (x[0], x[1]))
    out.print_md(u"### " + titre)
    out.print_table(table_data=donnees,
                    columns=[titre, u"Etat de la cible", u"Nombre"])

out.print_md(u"## Croisements")
croiser(u"Classe", 1)
croiser(u"Gabarit de vue", 2)
croiser(u"Dependante", 3)
croiser(u"Gabarit applique", 4)
croiser(u"Placee sur feuille", 5)

lignes.sort(key=lambda x: (x[6], x[1], x[0]))
out.print_md(u"## Detail — les vues en lecture seule d'abord")
out.print_table(
    table_data=[l for l in lignes if l[6] == u"LECTURE SEULE"][:60],
    columns=[u"Vue", u"Classe", u"Gabarit", u"Dependante",
             u"Gabarit applique", u"Feuille", u"Cible", u"Valeur source"],
)

chemin = forms.save_file(file_ext="csv", default_name="sonde_vues")
if chemin:
    f = codecs.open(chemin, "w", "utf-8")
    try:
        f.write(u"﻿")
        f.write(u";".join([u"Vue", u"Classe", u"Gabarit", u"Dependante",
                           u"Gabarit_applique", u"Feuille", u"Etat_cible",
                           u"Valeur_source"]) + u"\n")
        for l in lignes:
            f.write(u";".join([x.replace(u";", u",") for x in l]) + u"\n")
    finally:
        f.close()
    out.print_md(u"---")
    out.print_md(u"CSV ecrit : `" + chemin + u"`")
