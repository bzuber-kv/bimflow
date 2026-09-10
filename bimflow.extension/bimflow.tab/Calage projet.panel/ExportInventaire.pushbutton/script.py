# -*- coding: utf-8 -*-
"""B15 - Export de l'inventaire, element par element. LECTURE SEULE.

Repo bimflow - extension pyRevit. Portee : GENERIQUE (toute maquette Revit).
Cas d'origine : affaire A_049_TheStudy, 2026-09-10.

Ecrit un CSV : une ligne par element, avec son identifiant et son
sous-projet. Passe sur deux etats d'un meme modele, il dit NOMMEMENT ce
qui a change entre les deux, et pas seulement combien.

Les ElementId sont stables dans un meme lignage de document (copie,
detachement, Enregistrer sous) : la comparaison par identifiant est donc
fiable entre une copie locale et son original.

Un identifiant present dans l'etat ancien et absent du nouveau se
selectionne dans l'ancien par Gerer > Selectionner par ID : on VOIT ce qui
a disparu, avec sa categorie et son type, sans que le script ait besoin de
les lire.

-------------------------------------------------------------------------
VERSION 2 - 2026-09-10. La v1 faisait planter Revit 2026.4.

Cause : la v1 resolvait, pour chacun des 21000 elements, sa categorie, son
type (via GetTypeId puis doc.GetElement) et son nom - donc elle allait
chercher d'AUTRES elements du document pendant qu'un FilteredElementCollector
etait en cours d'iteration. Le collecteur evalue paresseusement ; ce motif
est une source documentee d'instabilite et produit une AccessViolationException
(lecture en memoire protegee). Ce type d'erreur N'EST PAS RATTRAPABLE par un
try/except : le processus meurt. Les gardes de la v1 donnaient une illusion
de robustesse.

Correction : cette version ne touche AUCUNE propriete d'element. Elle
demande a Revit, sous-projet par sous-projet, la collection d'identifiants
qu'il contient (ElementWorksetFilter + ToElementIds). Aucune instanciation,
aucun GetElement, aucun acces a .Name, .Category ou .ViewSpecific.
-------------------------------------------------------------------------

Contrainte d'environnement (bimflow_CONTEXT, 2026-08-27) : moteur IPY342,
aucun CPython en netcore. PAS de ligne shebang python3 en tete.
Niveau de langage Python 3.4 : pas de f-strings.

Ce fichier est volontairement ecrit en ASCII pur : test de l'hypothese
selon laquelle le parseur de metadonnees de pyRevit sous IronPython 3
echoue sur les caracteres non-ASCII des docstrings (erreur AttributeError
ligne 0/0 au chargement).
"""

__title__ = "Export\ninventaire"
__doc__ = "B15 - Un CSV, une ligne par element (Id, sous-projet). Lecture seule, aucune propriete lue."
__author__ = "Keovia Solutions"

import io
import os
import datetime

from System import Environment

from Autodesk.Revit.DB import (
    ElementWorksetFilter,
    FilteredElementCollector,
    FilteredWorksetCollector,
    WorksetKind,
)

from pyrevit import revit, script

def id_de(eid):
    """Identifiant entier d'un ElementId, quelle que soit la version de Revit.

    Revit 2024+ : .Value (Int64). Le .IntegerValue (Int32) historique est
    supprime - mesure sur Revit 2026.4 le 2026-09-10 : AttributeError.
    ATTENTION : WorksetId.IntegerValue, lui, existe toujours - c'est une
    autre classe. Ne pas "corriger" B13 qui s'en sert.
    """
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


doc = revit.doc
out = script.get_output()
out.set_title("Keovia - export de l'inventaire")

out.print_md("# Export de l'inventaire - lecture seule")
out.print_md("Modele : **{}**".format(doc.Title))
out.print_md("Date : {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
out.print_md("_Version 2 : aucune propriete d'element n'est lue._")

if not doc.IsWorkshared:
    out.print_md("> **Ce modele n'est pas en travail partage.** Rien a inventorier par sous-projet.")
    script.exit()

# ------------------------------------------------------- controle prealable
user_ws = list(FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset))

fermes = [ws.Name for ws in user_ws if not ws.IsOpen]
if fermes:
    out.print_md(
        "> **ARRET - {} sous-projet(s) ferme(s) : {}.**\n"
        "> Leurs elements ne sont pas charges en memoire : ils manqueraient a "
        "l'export, et la comparaison inventerait des disparitions. Ouvre tous "
        "les sous-projets (Collaborer > Sous-projets > Ouvrir) et relance."
        .format(len(fermes), ", ".join(fermes))
    )
    script.exit()

# --------------------------------------------------------- collecte des Id
# Total du document : une seule collection materialisee, aucune propriete lue.
ids_tous = set()
for eid in FilteredElementCollector(doc).WhereElementIsNotElementType().ToElementIds():
    ids_tous.add(id_de(eid))

# Par sous-projet utilisateur : c'est Revit qui filtre, pas nous.
par_ws = {}
for ws in user_ws:
    col = FilteredElementCollector(doc) \
        .WherePasses(ElementWorksetFilter(ws.Id)) \
        .WhereElementIsNotElementType()
    ids = set()
    for eid in col.ToElementIds():
        ids.add(id_de(eid))
    par_ws[ws.Name] = ids

dans_user = set()
for ids in par_ws.values():
    dans_user |= ids
hors_user = ids_tous - dans_user

# ------------------------------------------------------------------- CSV
bureau = Environment.GetFolderPath(Environment.SpecialFolder.Desktop)
horo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
titre = "".join(c for c in doc.Title if c.isalnum() or c in "-_")
chemin = os.path.join(bureau, "inventaire_{}_{}.csv".format(titre, horo))

try:
    with io.open(chemin, "w", encoding="utf-8-sig") as f:
        f.write(u"Id;SousProjet\n")
        for nom in sorted(par_ws.keys(), key=lambda s: s.lower()):
            for i in sorted(par_ws[nom]):
                f.write(u"{};{}\n".format(i, nom.replace(u";", u",")))
        for i in sorted(hors_user):
            f.write(u"{};(hors sous-projet utilisateur)\n".format(i))
except Exception as ex:
    out.print_md("> **Echec de l'ecriture du CSV** : `{}`".format(ex))
    script.exit()

# ---------------------------------------------------------------- resume
lignes = []
for nom in sorted(par_ws.keys(), key=lambda s: s.lower()):
    lignes.append([nom, len(par_ws[nom])])
lignes.append([u"(hors sous-projet utilisateur)", len(hors_user)])

out.print_table(
    table_data=lignes,
    title="Elements par sous-projet",
    columns=["Sous-projet", "Elements"],
)

out.print_md("**Total dans les sous-projets utilisateur : {}**".format(len(dans_user)))
out.print_md("**Total instances du document : {}**".format(len(ids_tous)))
out.print_md("**{} lignes ecrites.**".format(len(ids_tous)))
out.print_md("CSV : `{}`".format(chemin))

out.print_md(
    "\n---\n"
    "**Mode d'emploi.** Passe ce bouton sur les DEUX etats a comparer, tous "
    "sous-projets ouverts. Les deux CSV portent le nom du modele et "
    "l'horodatage : ils ne s'ecrasent pas.\n\n"
    "Un identifiant present dans l'etat ancien et absent du nouveau se "
    "retrouve dans l'ancien par **Gerer > Selectionner par ID**. C'est la "
    "seule facon de _voir_ ce qui a disparu - et c'est plus sur que de faire "
    "lire au script des proprietes qu'il n'a pas besoin de connaitre."
)
