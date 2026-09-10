# -*- coding: utf-8 -*-
"""B18 - Sonde de dependance. Repond a : "si cet objet disparait, quoi d'autre ?"

Repo bimflow - extension pyRevit. Portee : GENERIQUE.
Cas d'origine : affaire A_049_TheStudy, 2026-09-10.

LA QUESTION
-----------
B16 dit ce qu'un element EST (classe, categorie, type). Il ne dit pas ce
qu'il PORTE. Or c'est la seule chose qui decide de son sous-projet : la
regle du PEP est "un objet dont depend un objet livre est lui-meme livre".
Sans reponse, ranger revient a deviner - et un sous-projet devine faux
paraitra faire autorite.

Le cas concret : 462 plans d'esquisse et 240 composants de legende dans le
fourre-tout de thestudy_CO_BAT. Combien tiennent un sol, un toit, une
feuille ? Combien sont des orphelins, restes d'objets supprimes ?

LA METHODE
----------
Document.Delete(id) retourne l'ensemble des identifiants que Revit
supprimerait EN CASCADE. C'est la reponse exacte a la question. La
transaction est ensuite ANNULEE - systematiquement, sans condition, y
compris en cas d'erreur. Rien n'est jamais valide.

  - n'emporte que lui-meme  -> orphelin, candidat purge
  - emporte un sol, un toit -> porteur : il est livre avec son hote
  - suppression refusee     -> Revit le protege : il est structurant

C'est une mesure, pas une deduction : Revit repond lui-meme.

AVERTISSEMENT - OU LE LANCER
-----------------------------
Sur un modele en travail partage, meme annulee, une tentative de
suppression EMPRUNTE l'element. L'annulation rend la main, mais sur un
modele central (ACC / Forma) partage avec Tony et Maoake, la prudence
commande de lancer cette sonde sur une COPIE LOCALE DETACHEE.
Le script le rappelle au lancement.

CONTRAINTES D'ENVIRONNEMENT
---------------------------
Moteur IPY342. Pas de shebang. Python 3.4 : pas de f-strings. ASCII pur.
"""

__title__ = "Sonde de\ndependance"
__doc__ = "B18 - Si cet objet disparait, quoi d'autre disparait ? Transaction TOUJOURS annulee. A lancer sur copie detachee."
__author__ = "Keovia Solutions"

import datetime

from Autodesk.Revit.DB import (
    BuiltInParameter,
    ElementWorksetFilter,
    FilteredElementCollector,
    FilteredWorksetCollector,
    Transaction,
    WorksetKind,
)

from pyrevit import revit, script, forms

# =========================================================================
# REGLAGES
# =========================================================================
SOURCES = ["ZW_Defaut", "Sous-projet 1", "Workset1"]

# Classes .NET et categories a sonder. Ce sont les inconnues de B16 :
# celles qu'on ne sait pas ranger parce qu'on ignore ce qu'elles portent.
CLASSES_SONDEES = ["SketchPlane", "NumberingSchema", "Element"]
CATEGORIES_SONDEES = ["composants de legende", "(sans categorie)"]

# Nombre d'elements sondes par groupe. Chaque sonde est une transaction
# annulee : c'est lent. 25 suffit largement a etablir une doctrine ; monter
# a 10000 pour un inventaire exhaustif, en sachant que ce sera long.
ECHANTILLON = 25
# =========================================================================


def sans_accent(t):
    table = {
        u"\xe0": u"a", u"\xe2": u"a", u"\xe4": u"a", u"\xe7": u"c",
        u"\xe8": u"e", u"\xe9": u"e", u"\xea": u"e", u"\xeb": u"e",
        u"\xee": u"i", u"\xef": u"i", u"\xf4": u"o", u"\xf6": u"o",
        u"\xf9": u"u", u"\xfb": u"u", u"\xfc": u"u",
    }
    return u"".join([table.get(c, c) for c in t.lower()])


def id_de(eid):
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


doc = revit.doc
out = script.get_output()
out.set_title("Keovia - sonde de dependance")

if not doc.IsWorkshared:
    out.print_md("> Ce modele n'est pas en travail partage - sonde inutile ici.")
    script.exit()

ok = forms.alert(
    "B18 - SONDE DE DEPENDANCE\n\n"
    "Ce script demande a Revit ce que la suppression de chaque objet "
    "emporterait, puis ANNULE systematiquement. Rien n'est jamais valide.\n\n"
    "MAIS : sur un modele partage, meme annulee, une tentative de "
    "suppression emprunte l'element. A lancer de preference sur une COPIE "
    "LOCALE DETACHEE, pas sur le modele central.\n\n"
    "Modele ouvert : " + doc.Title + "\n\nContinuer ?",
    title="B18 - sonde de dependance",
    ok=False, yes=True, no=True, exitscript=True,
)
if not ok:
    script.exit()

out.print_md("# Sonde de dependance")
out.print_md("Modele : **{}** - {}".format(
    doc.Title, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
out.print_md("_Chaque sonde est une transaction annulee. Aucune ecriture ne "
             "sera validee, quoi qu'il arrive._")

user_ws = list(FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset))
fermes = [ws.Name for ws in user_ws if not ws.IsOpen]
if fermes:
    out.print_md("> **ARRET - sous-projet(s) ferme(s) : {}.** Ouvre-les et "
                 "relance.".format(", ".join(fermes)))
    script.exit()

sources = [ws for ws in user_ws
           if sans_accent(ws.Name) in [sans_accent(s) for s in SOURCES]]
if not sources:
    out.print_md("> Aucun des sous-projets sources n'existe.")
    script.exit()

# ---- etape 1 : materialiser (aucune propriete lue pendant l'iteration)
ids = []
for ws in sources:
    col = FilteredElementCollector(doc) \
        .WherePasses(ElementWorksetFilter(ws.Id)) \
        .WhereElementIsNotElementType()
    for eid in col.ToElementIds():
        ids.append(eid)

# ---- etape 2 : constituer les groupes a sonder
groupes = {}
for eid in ids:
    elem = doc.GetElement(eid)
    if elem is None:
        continue
    try:
        cls = elem.GetType().Name
    except Exception:
        cls = u"?"
    cat = u"(sans categorie)"
    try:
        if elem.Category is not None:
            cat = elem.Category.Name
    except Exception:
        pass
    if cls not in CLASSES_SONDEES and sans_accent(cat) not in \
            [sans_accent(c) for c in CATEGORIES_SONDEES]:
        continue
    cle = u"{} / {}".format(cls, cat)
    groupes.setdefault(cle, []).append(eid)

if not groupes:
    out.print_md("> Aucun element des classes sondees dans ces sous-projets.")
    script.exit()

out.print_md("**{} groupes a sonder**, {} elements au maximum par groupe."
             .format(len(groupes), ECHANTILLON))

# ---- etape 3 : sonder
resultats = []
for cle in sorted(groupes.keys()):
    lot = groupes[cle]
    echant = lot[:ECHANTILLON]
    orphelins = 0
    porteurs = 0
    proteges = 0
    emportes_max = 0
    exemple_porteur = u""
    exemple_orphelin = u""

    for eid in echant:
        t = Transaction(doc, "Keovia B18 - sonde (annulee)")
        try:
            t.Start()
            try:
                emportes = doc.Delete(eid)
            except Exception:
                emportes = None
            if emportes is None:
                proteges += 1
            else:
                n = 0
                autres_cats = set()
                for oid in emportes:
                    if id_de(oid) == id_de(eid):
                        continue
                    n += 1
                    if len(autres_cats) < 4:
                        o = doc.GetElement(oid)
                        if o is not None:
                            try:
                                if o.Category is not None:
                                    autres_cats.add(o.Category.Name)
                            except Exception:
                                pass
                if n == 0:
                    orphelins += 1
                    if not exemple_orphelin:
                        exemple_orphelin = u"{}".format(id_de(eid))
                else:
                    porteurs += 1
                    if n > emportes_max:
                        emportes_max = n
                    if not exemple_porteur:
                        exemple_porteur = u"{} -> {} ({})".format(
                            id_de(eid), n,
                            u", ".join(sorted(autres_cats)) or u"?")
        finally:
            # ANNULATION INCONDITIONNELLE. C'est le contrat du script.
            try:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
            except Exception:
                pass

    resultats.append([
        cle, len(lot), len(echant), orphelins, porteurs, proteges,
        exemple_porteur or exemple_orphelin,
    ])

out.print_table(
    table_data=resultats,
    title="Ce que chaque groupe PORTE",
    columns=["Classe / categorie", "Total", "Sondes", "Orphelins",
             "Porteurs", "Proteges", "Exemple"],
)

out.print_md(
    "\n---\n"
    "**Lecture.**\n\n"
    "- **Orphelin** : sa suppression n'emporte rien. Reste d'un objet "
    "disparu. Il ne porte aucun livrable - donc aucune raison de lui donner "
    "un sous-projet metier, et il est candidat a la purge.\n"
    "- **Porteur** : sa suppression emporte d'autres elements, dont la "
    "colonne Exemple donne les categories. Il est **livre avec son hote** - "
    "et son sous-projet doit suivre celui de l'hote, pas une case a part.\n"
    "- **Protege** : Revit refuse de le supprimer seul. Il est structurant ; "
    "il ne se range pas, il se laisse ou il est.\n\n"
    "**Ce qu'on en fait.** Un groupe majoritairement orphelin se purge. Un "
    "groupe majoritairement porteur n'a pas besoin d'etre range : il suivra. "
    "Dans les deux cas, on n'invente **aucune** affirmation.\n\n"
    "_Toutes les transactions ont ete annulees. Le modele est dans l'etat ou "
    "tu l'as ouvert._"
)
