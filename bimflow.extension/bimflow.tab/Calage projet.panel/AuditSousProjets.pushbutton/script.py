# -*- coding: utf-8 -*-
"""B13 — Audit des sous-projets. LECTURE SEULE, aucune modification.

Repo bimflow — extension pyRevit. Portee : GENERIQUE (toute maquette en
travail partage). Cas d'origine : affaire A_049_TheStudy, 2026-09-10.

Discipline backlog bimflow : tout script qui ecrit est precede d'un script
d'audit en lecture seule sur le meme perimetre. Celui-ci est l'audit de
B14 (migration des sous-projets).

Compte les elements par sous-projet au niveau DOCUMENT, et non au niveau
d'une vue : c'est la seule mesure comparable d'un fichier a l'autre.

A passer DEUX FOIS : sur la sauvegarde datee, puis sur le modele courant.
C'est la difference des TOTAUX qui dit si quelque chose a disparu, jamais
une selection filtree dans une vue 3D.

Produit aussi le squelette de la table de correspondance a coller dans
B14 : les noms y sont exacts, plus de recopie a la main.

Contrainte d'environnement (bimflow_CONTEXT, 2026-08-27) : moteur IPY342,
aucun CPython en netcore. PAS de ligne shebang « python3 » en tete — le bouton ne se
chargerait pas. Niveau de langage plafonne a Python 3.4 : pas de f-strings.
"""

__title__ = "Audit\nsous-projets"
__doc__ = "B13 - Inventaire des sous-projets au niveau document. Lecture seule."
__author__ = "Keovia Solutions inc."

import io
import os
import datetime

from System import Environment

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FilteredWorksetCollector,
    WorksetKind,
    WorksetTable,
    WorksharingUtils,
    CheckoutStatus,
)

from pyrevit import revit, script

# ---------------------------------------------------------------- reglages
# Verification du proprietaire de chaque element : c'est le test decisif
# quand des elements refusent de changer de sous-projet. Couteux sur un gros
# modele (compter une a deux minutes) — passer a False pour un comptage seul.
VERIFIER_PROPRIETAIRE = True

# Ecrit un CSV horodate sur le Bureau, pour comparer deux etats hors Revit.
ECRIRE_CSV = True

doc = revit.doc
out = script.get_output()
out.set_title("Keovia — audit des sous-projets")

out.print_md("# Audit des sous-projets — lecture seule")
out.print_md("Modele : **{}**".format(doc.Title))
out.print_md("Date : {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))

if not doc.IsWorkshared:
    out.print_md("> **Ce modele n'est pas en travail partage.** Rien a auditer.")
    script.exit()

# ------------------------------------------------- sous-projets utilisateur
wst = doc.GetWorksetTable()

user_ws = list(FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset))
user_ids = set(ws.Id.IntegerValue for ws in user_ws)

fermes = [ws.Name for ws in user_ws if not ws.IsOpen]
if fermes:
    out.print_md(
        "> **ATTENTION — {} sous-projet(s) ferme(s) : {}.**\n"
        "> Les elements d'un sous-projet ferme ne sont pas charges en memoire : "
        "ils ne seront pas comptes. Ouvre TOUS les sous-projets "
        "(Collaborer > Sous-projets > Ouvrir) et relance."
        .format(len(fermes), ", ".join(fermes))
    )

# cache nom + genre par identifiant de sous-projet
_cache = {}


def infos_ws(wsid_int):
    if wsid_int not in _cache:
        nom, genre = "(id {})".format(wsid_int), "?"
        try:
            from Autodesk.Revit.DB import WorksetId
            ws = wst.GetWorkset(WorksetId(wsid_int))
            nom, genre = ws.Name, str(ws.Kind)
        except Exception:
            pass
        _cache[wsid_int] = (nom, genre)
    return _cache[wsid_int]


# --------------------------------------------------------- passe de comptage
stats = {}
hors_user = {}
total_general = 0

for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
    total_general += 1
    try:
        wsid = el.WorksetId.IntegerValue
    except Exception:
        continue

    if wsid not in user_ids:
        _, genre = infos_ws(wsid)
        hors_user[genre] = hors_user.get(genre, 0) + 1
        continue

    d = stats.setdefault(wsid, {"total": 0, "modele": 0, "vue": 0, "proprios": {}})
    d["total"] += 1
    try:
        if el.ViewSpecific:
            d["vue"] += 1
        else:
            d["modele"] += 1
    except Exception:
        d["modele"] += 1

    if VERIFIER_PROPRIETAIRE:
        try:
            if WorksharingUtils.GetCheckoutStatus(doc, el.Id) == CheckoutStatus.OwnedByOtherUser:
                info = WorksharingUtils.GetWorksharingTooltipInfo(doc, el.Id)
                qui = info.Owner or "(inconnu)"
                d["proprios"][qui] = d["proprios"].get(qui, 0) + 1
        except Exception:
            pass


def peut_supprimer(ws):
    try:
        return "oui" if WorksetTable.CanDeleteWorkset(doc, ws.Id) else "NON"
    except Exception:
        return "?"


# ------------------------------------------------------------------ rapport
lignes = []
total_user = 0
for ws in sorted(user_ws, key=lambda w: w.Name.lower()):
    k = ws.Id.IntegerValue
    d = stats.get(k, {"total": 0, "modele": 0, "vue": 0, "proprios": {}})
    total_user += d["total"]
    autres = sum(d["proprios"].values())
    detail = ", ".join(
        "{} ({})".format(u, n)
        for u, n in sorted(d["proprios"].items(), key=lambda x: -x[1])
    )
    lignes.append([
        ws.Name,
        d["total"],
        d["modele"],
        d["vue"],
        "oui" if ws.IsOpen else "FERME",
        "oui" if ws.IsVisibleByDefault else "non",
        peut_supprimer(ws),
        autres if autres else "",
        detail,
    ])

out.print_table(
    table_data=lignes,
    title="Sous-projets utilisateur",
    columns=["Sous-projet", "Total", "Modele", "Spec. vue", "Ouvert",
             "Visible", "Supprimable", "Autre proprio", "Qui"],
)

out.print_md("**Total dans les sous-projets utilisateur : {}**".format(total_user))
out.print_md("**Total instances du document : {}**".format(total_general))

if hors_user:
    autres_lignes = [[g, n] for g, n in sorted(hors_user.items(), key=lambda x: -x[1])]
    out.print_table(
        table_data=autres_lignes,
        title="Hors sous-projets utilisateur (vues, familles, normes du projet)",
        columns=["Genre de sous-projet", "Elements"],
    )
    out.print_md(
        "_Ces elements ne peuvent pas etre ranges dans un sous-projet utilisateur : "
        "chaque vue, chaque famille et les normes du projet ont leur propre "
        "sous-projet, gere par Revit. Ils n'entrent donc jamais dans les comptes "
        "ci-dessus._"
    )

bloques = sum(sum(d["proprios"].values()) for d in stats.values())
if VERIFIER_PROPRIETAIRE:
    if bloques:
        out.print_md(
            "> **{} element(s) appartiennent a un autre utilisateur.** Ils ne "
            "changeront pas de sous-projet tant qu'ils ne sont pas liberes "
            "(synchronisation de leur proprietaire, ou appropriation). "
            "**C'est la premiere cause a verifier devant un ecart de comptage.**"
            .format(bloques)
        )
    else:
        out.print_md(
            "> Aucun element possede par un autre utilisateur. "
            "L'hypothese « propriete des elements » est ecartee."
        )

# ------------------------------- squelette de la table pour le script 02
out.print_md("## Table de correspondance — squelette a coller dans le script 02")
out.print_md(
    "_Les noms ci-dessous sont ceux du modele, exacts. Remplace `GARDER` par "
    "l'action voulue et renseigne la cible._"
)
skel = ["TABLE = ["]
for ws in sorted(user_ws, key=lambda w: w.Name.lower()):
    skel.append(u'    ("GARDER",   u"{}", None),'.format(ws.Name))
skel.append("]")
print("\n".join(skel))

# ------------------------------------------------------------------- CSV
if ECRIRE_CSV:
    try:
        bureau = Environment.GetFolderPath(Environment.SpecialFolder.Desktop)
        horo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        titre = "".join(c for c in doc.Title if c.isalnum() or c in "-_")
        chemin = os.path.join(bureau, "audit_sousprojets_{}_{}.csv".format(titre, horo))
        with io.open(chemin, "w", encoding="utf-8-sig") as f:
            f.write(u"Sous-projet;Total;Modele;SpecVue;Ouvert;Visible;Supprimable;AutreProprio;Qui\n")
            for l in lignes:
                f.write(u";".join(u"{}".format(x) for x in l) + u"\n")
            f.write(u"\n")
            f.write(u"TOTAL sous-projets utilisateur;{}\n".format(total_user))
            f.write(u"TOTAL instances du document;{}\n".format(total_general))
        out.print_md("CSV ecrit : `{}`".format(chemin))
    except Exception as ex:
        out.print_md("_CSV non ecrit ({})._".format(ex))
