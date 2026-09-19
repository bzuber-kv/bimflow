# -*- coding: utf-8 -*-
"""Renomme sur place les parametres de projet non partages.

Outil ORANGE : il ecrit dans la maquette. Mais c'est la seule ecriture de la
serie qui soit REVERSIBLE — renommer ne perd aucune valeur, il suffit de
renommer dans l'autre sens.

Fait mesure le 2026-09-19 qui justifie cet outil : un parametre de projet NON
PARTAGE se renomme sur place, ses valeurs intactes. C'est le meme element du
document, il change d'etiquette. La recopie vers un nouveau parametre, elle,
butait sur 35 vues dont la cible etait en lecture seule.

Un parametre PARTAGE ne se renomme pas ainsi : son nom vient de sa definition,
identifiee par un GUID. L'outil le detecte et refuse, en le disant.

pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de shebang.
"""

__title__ = "Renommage\nparametres"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-09-19n"

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import FilteredElementCollector, Transaction

doc = revit.doc
out = script.get_output()

# ---------------------------------------------------------------------------
# La table des renommages. Modifier ici, jamais dans le corps du script.
#
# Regles de nommage arretees le 2026-09-19 :
#   ASCII sans accent · aucun espace, separateur _ · un seul prefixe de trois
#   lettres majuscules · premiere lettre du nom en capitale, le reste en
#   minuscules · singulier · pas d'abreviation hors prefixe · pas d'unite dans
#   le nom · le nom dit ce que la valeur DESIGNE, jamais d'ou elle vient.
# ---------------------------------------------------------------------------

TABLE = [
    (u"Classement Vues",     u"DOC_Classement_vue"),
    (u"Classement Feuille",  u"DOC_Classement_feuille"),
    (u"Sous-discipline",     u"DOC_Sous_discipline"),
]


try:
    if doc.IsWorkshared and not doc.IsDetached:
        if not forms.alert(
            u"Cette maquette est COLLABORATIVE et n'est pas detachee.\n\n"
            u"Si le modele central est inaccessible, Revit refusera le "
            u"renommage a la validation.\n\nContinuer quand meme ?",
            title=u"Maquette collaborative", yes=True, no=True,
        ):
            script.exit()
except Exception:
    pass


# ---------------------------------------------------------------------------
# 1. Lire les liaisons et les parametres partages
# ---------------------------------------------------------------------------

params = {}
it = doc.ParameterBindings.ForwardIterator()
it.Reset()
while it.MoveNext():
    d = it.Key
    cats = []
    try:
        for c in it.Current.Categories:
            cats.append(c.Name)
    except Exception:
        pass
    params[d.Name] = {"definition": d, "id": d.Id, "categories": sorted(cats)}

if not params:
    forms.alert(u"Aucun parametre de projet dans cette maquette.", exitscript=True)

partages = set()
try:
    from Autodesk.Revit.DB import SharedParameterElement
    for spe in list(FilteredElementCollector(doc)
                    .OfClass(SharedParameterElement).ToElements()):
        try:
            partages.add(spe.GetDefinition().Name)
        except Exception:
            continue
except Exception:
    partages = set()


# ---------------------------------------------------------------------------
# 2. Le plan, affiche AVANT toute ecriture
# ---------------------------------------------------------------------------

out.print_md(u"# Renommage des parametres de projet")
out.print_md(u"**Version de l'outil** : `" + VERSION + u"`")
out.print_md(u"**Maquette** : `" + doc.Title + u"`")
out.print_md(u"> Renommer ne perd aucune valeur. C'est la seule ecriture "
             u"reversible de la serie.")

plan = []
refus = []

for ancien, nouveau in TABLE:
    if ancien not in params:
        if nouveau in params:
            refus.append([ancien, nouveau, u"deja fait"])
        else:
            refus.append([ancien, nouveau, u"absent de cette maquette"])
        continue
    if nouveau in params:
        refus.append([ancien, nouveau,
                      u"le nouveau nom est DEJA pris par un autre parametre"])
        continue
    if ancien in partages:
        refus.append([ancien, nouveau,
                      u"parametre PARTAGE : son nom vient de sa definition "
                      u"(GUID), il ne se renomme pas sur place"])
        continue
    plan.append((ancien, nouveau, params[ancien]))

if plan:
    out.print_md(u"## A renommer")
    out.print_table(
        table_data=[[a, n, str(len(p["categories"])) + u" categories"]
                    for a, n, p in plan],
        columns=[u"Nom actuel", u"Nouveau nom", u"Portee"],
    )

if refus:
    out.print_md(u"## Ecartes — et pourquoi")
    out.print_table(table_data=refus,
                    columns=[u"Nom actuel", u"Nouveau nom", u"Motif"])

if not plan:
    forms.alert(u"Rien a renommer. Le detail est dans la fenetre de sortie.",
                title=u"Renommage", exitscript=True)

resume = u"\n".join([u"  " + a + u"  →  " + n for a, n, _p in plan])
if not forms.alert(
    u"%d renommage(s) :\n\n%s\n\n"
    u"Aucune valeur n'est perdue. Le classement de l'arborescence suit "
    u"automatiquement : c'est le meme parametre.\n\nEcrire maintenant ?"
    % (len(plan), resume),
    title=u"Renommage — confirmation", yes=True, no=True,
):
    out.print_md(u"**Annule. Rien n'a ete ecrit.**")
    script.exit()


# ---------------------------------------------------------------------------
# 3. Ecriture
# ---------------------------------------------------------------------------

faits = []
echecs = []

t = Transaction(doc, "Keovia - renommage des parametres de projet")
try:
    t.Start()
    for ancien, nouveau, p in plan:
        try:
            pe = doc.GetElement(p["id"])
        except Exception as err:
            echecs.append((ancien, u"element de definition introuvable : " + str(err)))
            continue
        if pe is None:
            echecs.append((ancien, u"element de definition introuvable"))
            continue
        try:
            pe.Name = nouveau
            faits.append((ancien, nouveau))
        except Exception as err:
            echecs.append((ancien, u"renommage refuse : " + str(err)))
    t.Commit()
except Exception as err:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    forms.alert(u"Echec, transaction annulee, rien n'a ete ecrit :\n\n" + str(err),
                exitscript=True)


# ---------------------------------------------------------------------------
# 4. Verification — on relit la maquette au lieu de croire le script
# ---------------------------------------------------------------------------

apres = set()
try:
    it2 = doc.ParameterBindings.ForwardIterator()
    it2.Reset()
    while it2.MoveNext():
        apres.add(it2.Key.Name)
except Exception:
    apres = None

out.print_md(u"## Resultat — relu dans la maquette")
if apres is None:
    for ancien, nouveau in faits:
        out.print_md(u"- `" + ancien + u"` → `" + nouveau +
                     u"` (verification impossible)")
else:
    confirmes = [x for x in faits if x[1] in apres and x[0] not in apres]
    rates = [x for x in faits if x not in confirmes]
    for ancien, nouveau in confirmes:
        out.print_md(u"- `" + ancien + u"` → **`" + nouveau + u"`** : confirme")
    for ancien, nouveau in rates:
        out.print_md(u"- **NON APPLIQUE** `" + ancien + u"` → `" + nouveau + u"`")
    if rates:
        forms.alert(
            u"%d renommage(s) annonces mais absents de la maquette.\n\n"
            u"Fermer SANS enregistrer et recommencer sur une copie detachee."
            % len(rates), title=u"Renommage non applique",
        )

for nom, motif in echecs:
    out.print_md(u"- **ECHEC** `" + nom + u"` : " + motif)

out.print_md(
    u"---\n"
    u"Le classement de l'arborescence n'a **rien a repointer** : le parametre "
    u"n'a pas ete remplace, il a change de nom. Verifier quand meme d'un coup "
    u"d'oeil que l'arborescence du projet est intacte."
)
