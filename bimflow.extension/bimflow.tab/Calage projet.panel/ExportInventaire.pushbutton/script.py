# -*- coding: utf-8 -*-
"""B15 — Export de l'inventaire, element par element. LECTURE SEULE.

Repo bimflow — extension pyRevit. Portee : GENERIQUE (toute maquette Revit).
Cas d'origine : affaire A_049_TheStudy, 2026-09-10.

Ecrit un CSV avec UNE LIGNE PAR ELEMENT : identifiant, categorie, type,
sous-projet, specifique a une vue. Passe sur deux etats d'un meme modele,
il permet de savoir NOMMEMENT ce qui a change entre les deux — et pas
seulement combien.

Les ElementId sont stables dans un meme lignage de document (copie,
detachement, Enregistrer sous), donc la comparaison par identifiant est
fiable entre une copie locale et le modele d'origine.

Ce que ca rend actionnable : un identifiant retrouve dans l'etat ancien et
absent du nouveau se selectionne dans l'ancien par
Gerer > Selectionner par ID — on VOIT ce qui a disparu.

Contrainte d'environnement (bimflow_CONTEXT, 2026-08-27) : moteur IPY342,
aucun CPython en netcore. PAS de ligne shebang « python3 » en tete.
Niveau de langage Python 3.4 : pas de f-strings.
"""

__title__ = "Export\ninventaire"
__doc__ = "B15 - Un CSV, une ligne par element (Id, categorie, type, sous-projet). Lecture seule."
__author__ = "Keovia Solutions"

import io
import os
import datetime

from System import Environment

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FilteredWorksetCollector,
    WorksetId,
    WorksetKind,
)

from pyrevit import revit, script

doc = revit.doc
out = script.get_output()
out.set_title("Keovia — export de l'inventaire")

out.print_md("# Export de l'inventaire — lecture seule")
out.print_md("Modele : **{}**".format(doc.Title))
out.print_md("Date : {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))

if not doc.IsWorkshared:
    out.print_md("> Ce modele n'est pas en travail partage — la colonne sous-projet sera vide.")

# --------------------------------------------------- avertissement prealable
if doc.IsWorkshared:
    fermes = [ws.Name for ws in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
              if not ws.IsOpen]
    if fermes:
        out.print_md(
            "> **ATTENTION — {} sous-projet(s) ferme(s) : {}.** Leurs elements ne "
            "sont pas charges en memoire et n'apparaitront PAS dans l'export. "
            "Ouvre tous les sous-projets et relance, sinon la comparaison sera "
            "fausse.".format(len(fermes), ", ".join(fermes))
        )

# ------------------------------------------------------------------- cache
wst = doc.GetWorksetTable() if doc.IsWorkshared else None
_cache = {}


def infos_ws(wsid_int):
    if wsid_int not in _cache:
        nom, genre = "", ""
        if wst is not None:
            try:
                ws = wst.GetWorkset(WorksetId(wsid_int))
                nom, genre = ws.Name, str(ws.Kind)
            except Exception:
                nom, genre = "(id {})".format(wsid_int), "?"
        _cache[wsid_int] = (nom, genre)
    return _cache[wsid_int]


def texte(valeur):
    """Neutralise les separateurs pour ne pas casser le CSV."""
    if valeur is None:
        return u""
    return u"{}".format(valeur).replace(u";", u",").replace(u"\n", u" ").replace(u"\r", u" ")


def nom_de(el):
    try:
        return el.Name
    except Exception:
        return u""


# ------------------------------------------------------------------ passe
lignes = []
par_genre = {}

for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
    try:
        eid = el.Id.IntegerValue
    except Exception:
        continue

    try:
        wsid = el.WorksetId.IntegerValue
    except Exception:
        wsid = -1
    ws_nom, ws_genre = infos_ws(wsid) if wsid >= 0 else (u"", u"")
    par_genre[ws_genre] = par_genre.get(ws_genre, 0) + 1

    cat = u""
    try:
        if el.Category is not None:
            cat = el.Category.Name
    except Exception:
        pass

    type_nom = u""
    try:
        tid = el.GetTypeId()
        if tid is not None and tid.IntegerValue > 0:
            t = doc.GetElement(tid)
            if t is not None:
                type_nom = nom_de(t)
    except Exception:
        pass

    spec_vue = u"1"
    try:
        spec_vue = u"1" if el.ViewSpecific else u"0"
    except Exception:
        spec_vue = u""

    lignes.append(u";".join([
        texte(eid), texte(cat), texte(type_nom),
        texte(nom_de(el)), texte(ws_nom), texte(ws_genre), spec_vue,
    ]))

# ------------------------------------------------------------------- CSV
bureau = Environment.GetFolderPath(Environment.SpecialFolder.Desktop)
horo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
titre = "".join(c for c in doc.Title if c.isalnum() or c in "-_")
chemin = os.path.join(bureau, "inventaire_{}_{}.csv".format(titre, horo))

try:
    with io.open(chemin, "w", encoding="utf-8-sig") as f:
        f.write(u"Id;Categorie;Type;Nom;SousProjet;GenreSousProjet;SpecVue\n")
        for l in lignes:
            f.write(l + u"\n")
    out.print_md("**{} elements exportes.**".format(len(lignes)))
    out.print_md("CSV ecrit : `{}`".format(chemin))
except Exception as ex:
    out.print_md("> **Echec de l'ecriture du CSV** : `{}`".format(ex))
    script.exit()

# ---------------------------------------------------------------- resume
resume = [[g if g else u"(inconnu)", n] for g, n in sorted(par_genre.items(), key=lambda x: -x[1])]
out.print_table(
    table_data=resume,
    title="Repartition par genre de sous-projet",
    columns=["Genre", "Elements"],
)

out.print_md(
    "\n---\n"
    "**Mode d'emploi.** Passe ce bouton sur les DEUX etats a comparer (par exemple "
    "la sauvegarde datee et le modele courant), tous sous-projets ouverts. Les deux "
    "CSV portent le nom du modele et l'horodatage : ils ne s'ecrasent pas.\n\n"
    "Un identifiant present dans l'etat ancien et absent du nouveau se retrouve "
    "dans l'ancien par **Gerer > Selectionner par ID** — c'est la seule facon de "
    "_voir_ ce qui a disparu."
)
