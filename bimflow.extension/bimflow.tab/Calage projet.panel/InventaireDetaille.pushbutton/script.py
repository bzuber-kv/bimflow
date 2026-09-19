# -*- coding: utf-8 -*-
"""B16 v2 - Inventaire detaille d'un ou plusieurs sous-projets. LECTURE SEULE.

Repo bimflow - extension pyRevit. Portee : GENERIQUE (toute maquette Revit).
Cas d'origine : affaire A_049_TheStudy, 2026-09-10.

A QUOI CA SERT
--------------
B15 dit COMBIEN et OU. B16 dit QUOI. On ne peut pas ecrire une regle de
reclassement sans savoir ce qu'il y a dans le fourre-tout : la regle se
DEDUIT de l'inventaire, elle ne se devine pas.

Le script se restreint volontairement a quelques sous-projets (par defaut le
sous-projet poubelle et le sous-projet par defaut de Revit). Sur quelques
milliers d'elements, resoudre categorie / type / niveau est instantane et
sur. Sur 21 000, c'etait ce qui faisait tomber B15 v1.

CE QUI A TUE B15 v1, ET POURQUOI CE SCRIPT NE LE REFAIT PAS
------------------------------------------------------------
B15 v1 resolvait des proprietes PENDANT qu'un FilteredElementCollector
iterait. Le collecteur evalue paresseusement ; aller chercher d'AUTRES
elements du document au milieu de son iteration produit une
AccessViolationException - non rattrapable par try/except, le processus
meurt.

La lecon n'est PAS "ne jamais lire de propriete". Elle est : materialiser
d'abord la liste d'identifiants (ToElementIds() copie dans une liste
Python, le collecteur est alors consomme), PUIS boucler sur cette liste.
C'est ce que fait ce script, et c'est pour cela qu'il peut se permettre ce
que B15 ne peut pas.

CONTRAINTES D'ENVIRONNEMENT
---------------------------
bimflow_CONTEXT 2026-08-27 : moteur IPY342, aucun CPython en netcore.
PAS de ligne shebang python3. Niveau de langage Python 3.4 : pas de
f-strings. Fichier en ASCII pur (orientation O5, etendue le 2026-09-10 aux
noms de sous-projets).
"""

__title__ = "Inventaire\ndetaille"
__doc__ = "B16 v2 - Ce qu'il y a VRAIMENT dans le fourre-tout, et combien est reellement a reclasser (le reste suit son hote). Lecture seule."
__author__ = "Keovia Solutions inc."

import io
import os
import datetime

from System import Environment

from Autodesk.Revit.DB import (
    BuiltInParameter,
    ElementWorksetFilter,
    FilteredElementCollector,
    FilteredWorksetCollector,
    WorksetKind,
    WorksharingUtils,
)

from pyrevit import revit, script, forms

# =========================================================================
# REGLAGES
# =========================================================================
# Sous-projets a inventorier. La casse et les accents sont ignores a la
# comparaison : la forme accentuee, la forme nue et la casse indifferente
# meme cible. Mettre la liste a vide pour choisir dans une boite de dialogue.
CIBLES = [
    "ZW_Defaut",
    "Sous-projet 1",
    "Workset1",
]

# Le proprietaire coute un appel Revit par element. Sur quelques milliers
# c'est acceptable ; le passer a False si l'attente devient sensible.
AVEC_PROPRIETAIRE = True

# Garde-fou : au-dela, le script s'arrete et propose de reduire la cible.
# Resoudre les proprietes de dizaines de milliers d'elements est exactement
# le terrain sur lequel B15 v1 est tombee.
PLAFOND = 20000
# =========================================================================


def id_de(eid):
    """Revit 2024+ : ElementId.Value (Int64). ATTENTION : WorksetId.IntegerValue
    existe toujours - autre classe. Ne pas "corriger" B13 avec ceci."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def sans_accent(texte):
    """Comparaison tolerante aux accents, sans dependance externe."""
    table = {
        u"\xe0": u"a", u"\xe2": u"a", u"\xe4": u"a",
        u"\xe7": u"c",
        u"\xe8": u"e", u"\xe9": u"e", u"\xea": u"e", u"\xeb": u"e",
        u"\xee": u"i", u"\xef": u"i",
        u"\xf4": u"o", u"\xf6": u"o",
        u"\xf9": u"u", u"\xfb": u"u", u"\xfc": u"u",
    }
    sortie = []
    for c in texte.lower():
        sortie.append(table.get(c, c))
    return u"".join(sortie)


doc = revit.doc
out = script.get_output()
out.set_title("Keovia - inventaire detaille")

out.print_md("# Inventaire detaille - lecture seule")
out.print_md("Modele : **{}**".format(doc.Title))
out.print_md("Date : {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))

if not doc.IsWorkshared:
    out.print_md("> **Ce modele n'est pas en travail partage.** Rien a inventorier.")
    script.exit()

# ------------------------------------------------- choix des sous-projets
user_ws = list(FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset))

fermes = [ws.Name for ws in user_ws if not ws.IsOpen]
if fermes:
    out.print_md(
        "> **ARRET - {} sous-projet(s) ferme(s).** Leurs elements ne sont pas "
        "charges en memoire : ils manqueraient a l'inventaire sans le dire. "
        "Collaborer > Sous-projets > Ouvrir, puis relance.\n>\n> {}"
        .format(len(fermes), ", ".join(fermes))
    )
    script.exit()

if CIBLES:
    voulus = [sans_accent(n) for n in CIBLES]
    retenus = [ws for ws in user_ws if sans_accent(ws.Name) in voulus]
    if not retenus:
        out.print_md(
            "> **Aucun des sous-projets de la liste CIBLES n'existe dans ce "
            "modele.** Ouvre le script (clic droit sur le bouton > Edit Script) "
            "et corrige la liste, ou vide-la pour choisir dans une boite de "
            "dialogue.\n>\n> Cherches : `{}`".format(u"`, `".join(CIBLES))
        )
        script.exit()
else:
    noms = sorted([ws.Name for ws in user_ws], key=lambda s: s.lower())
    choix = forms.SelectFromList.show(
        noms, title="Sous-projets a inventorier",
        multiselect=True, button_name="Inventorier",
    )
    if not choix:
        script.exit()
    retenus = [ws for ws in user_ws if ws.Name in choix]

out.print_md("Sous-projets retenus : **{}**".format(
    ", ".join([ws.Name for ws in retenus])))

# ---------------------------------------------------------------------
# ETAPE 1 - materialiser les identifiants. AUCUNE propriete n'est lue ici.
# C'est la separation stricte des deux etapes qui rend le script sur.
# ---------------------------------------------------------------------
paquets = []
total = 0
for ws in retenus:
    col = FilteredElementCollector(doc) \
        .WherePasses(ElementWorksetFilter(ws.Id)) \
        .WhereElementIsNotElementType()
    liste = []
    for eid in col.ToElementIds():
        liste.append(eid)
    paquets.append((ws.Name, liste))
    total += len(liste)

if total == 0:
    out.print_md("> Les sous-projets retenus sont **vides**. Rien a inventorier.")
    script.exit()

if total > PLAFOND:
    out.print_md(
        "> **ARRET - {} elements, au-dela du plafond de {}.**\n>\n"
        "> Resoudre les proprietes de cette masse est exactement ce qui a fait "
        "tomber Revit avec B15 v1. Restreins la liste CIBLES, ou releve "
        "PLAFOND en connaissance de cause.".format(total, PLAFOND)
    )
    script.exit()

out.print_md("**{} elements a inventorier.** Resolution des proprietes...".format(total))

# ---------------------------------------------------------------------
# ETAPE 2 - les collecteurs sont consommes. On peut resoudre.
# ---------------------------------------------------------------------
cache_type = {}
cache_niveau = {}


def nom_du_type(elem):
    try:
        tid = elem.GetTypeId()
    except Exception:
        return u"(sans type)"
    cle = id_de(tid)
    if cle in cache_type:
        return cache_type[cle]
    valeur = u"(sans type)"
    if cle > 0:
        t = doc.GetElement(tid)
        if t is not None:
            fam = u""
            try:
                fam = t.FamilyName
            except Exception:
                fam = u""
            nom = u""
            try:
                nom = t.Name
            except Exception:
                nom = u""
            if fam and nom:
                valeur = fam + u" : " + nom
            elif nom:
                valeur = nom
    cache_type[cle] = valeur
    return valeur


def nom_du_niveau(elem):
    lid = None
    try:
        lid = elem.LevelId
    except Exception:
        lid = None
    if lid is None:
        return u"(sans niveau)"
    cle = id_de(lid)
    if cle <= 0:
        return u"(sans niveau)"
    if cle in cache_niveau:
        return cache_niveau[cle]
    valeur = u"(sans niveau)"
    n = doc.GetElement(lid)
    if n is not None:
        try:
            valeur = n.Name
        except Exception:
            valeur = u"(niveau sans nom)"
    cache_niveau[cle] = valeur
    return valeur


def assignable(elem):
    """LE chiffre qui dimensionne le travail de reclassement.

    Beaucoup d'elements ne portent pas leur sous-projet : ils SUIVENT leur
    hote (lignes d'axe de reseau, esquisses, cotes automatiques, sous-elements
    d'escalier, objets systeme). Leur parametre de sous-projet est en lecture
    seule. Les compter dans la charge de travail serait une erreur de
    dimensionnement ; essayer de les ecrire serait une erreur tout court.

    Lecture de IsReadOnly : n'ouvre aucune transaction, ne modifie rien."""
    try:
        p = elem.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
    except Exception:
        return u"?"
    if p is None:
        return u"non"
    try:
        return u"non" if p.IsReadOnly else u"oui"
    except Exception:
        return u"?"


def nom_du_systeme(elem):
    """Pour le MEP, la CATEGORIE ne suffit pas : un raccord de canalisation
    peut relever du chauffage, de la plomberie ou de la protection incendie.
    C'est le systeme qui tranche - donc il doit etre dans le CSV."""
    for bip in (BuiltInParameter.RBS_SYSTEM_NAME_PARAM,
                BuiltInParameter.RBS_SYSTEM_CLASSIFICATION_PARAM,
                BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM,
                BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM):
        try:
            p = elem.get_Parameter(bip)
        except Exception:
            p = None
        if p is None:
            continue
        try:
            v = p.AsString()
            if not v:
                v = p.AsValueString()
            if v:
                return v
        except Exception:
            pass
    return u""


def classe_dotnet(elem):
    """Identifie les elements que Revit ne classe dans aucune categorie.
    Sans cela, "(sans categorie)" est un trou noir dans l'inventaire."""
    try:
        return elem.GetType().Name
    except Exception:
        return u"?"


lignes = []           # pour le CSV
par_categorie = {}    # nom sous-projet -> categorie -> [nb, type vu, nb assignables]
proprietaires = {}
bilan = {}            # nom sous-projet -> {oui/non/?: nb}

for nom_ws, ids in paquets:
    par_categorie.setdefault(nom_ws, {})
    bilan.setdefault(nom_ws, {})
    for eid in ids:
        elem = doc.GetElement(eid)
        if elem is None:
            continue

        cat = u"(sans categorie)"
        try:
            if elem.Category is not None:
                cat = elem.Category.Name
        except Exception:
            pass

        typ = nom_du_type(elem)
        niv = nom_du_niveau(elem)
        cls = classe_dotnet(elem)
        sys = nom_du_systeme(elem)
        asg = assignable(elem)
        bilan[nom_ws][asg] = bilan[nom_ws].get(asg, 0) + 1

        vue = u""
        try:
            vue = u"oui" if elem.ViewSpecific else u"non"
        except Exception:
            vue = u"?"

        prop = u""
        if AVEC_PROPRIETAIRE:
            try:
                info = WorksharingUtils.GetWorksharingTooltipInfo(doc, eid)
                prop = info.Owner or u""
            except Exception:
                prop = u"?"
            if prop:
                proprietaires[prop] = proprietaires.get(prop, 0) + 1

        lignes.append((id_de(eid), nom_ws, asg, cat, cls, typ, sys, niv, vue, prop))

        entree = par_categorie[nom_ws].get(cat)
        if entree is None:
            par_categorie[nom_ws][cat] = [1, typ, 1 if asg == u"oui" else 0]
        else:
            entree[0] += 1
            if asg == u"oui":
                entree[2] += 1

# ------------------------------------------------------------------- CSV
bureau = Environment.GetFolderPath(Environment.SpecialFolder.Desktop)
horo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
titre = "".join(c for c in doc.Title if c.isalnum() or c in "-_")
chemin = os.path.join(bureau, "detail_{}_{}.csv".format(titre, horo))


def sur(v):
    """Le point-virgule est le separateur du CSV : il ne doit pas survivre
    dans une valeur. Le retour a la ligne non plus."""
    return u"{}".format(v).replace(u";", u",").replace(u"\n", u" ")


# v2 : le codec utf-8-sig d'IronPython 3 ecrit le BOM a CHAQUE write(). On
# assemble donc tout le texte, puis on ecrit une seule fois en utf-8 nu avec
# un BOM place a la main - ce que Excel attend.
morceaux = [u"Id;SousProjet;Assignable;Categorie;Classe;Type;Systeme;"
            u"Niveau;VueSpecifique;Proprietaire"]
for l in lignes:
    morceaux.append(u";".join([sur(x) for x in l]))

try:
    with io.open(chemin, "w", encoding="utf-8") as f:
        f.write(u"\ufeff" + u"\n".join(morceaux) + u"\n")
except Exception as ex:
    out.print_md("> **Echec de l'ecriture du CSV** : `{}`".format(ex))
    script.exit()

# --------------------------------------------------------------- resume
# La charge de travail reelle en premier : elle vaut mieux que le total brut.
donnees = []
for nom_ws in sorted(bilan.keys(), key=lambda s: s.lower()):
    b = bilan[nom_ws]
    donnees.append([nom_ws,
                    b.get(u"oui", 0) + b.get(u"non", 0) + b.get(u"?", 0),
                    b.get(u"oui", 0),
                    b.get(u"non", 0) + b.get(u"?", 0)])
out.print_table(
    table_data=donnees,
    title="Charge de travail reelle",
    columns=["Sous-projet", "Elements", "A RECLASSER", "Suivent leur hote"],
)
out.print_md(
    "> Seule la colonne **A RECLASSER** compte. Les autres elements ne "
    "portent pas leur sous-projet : il est en lecture seule et suit l'hote "
    "(lignes d'axe de reseau, esquisses, cotes automatiques, sous-elements "
    "d'escalier, objets systeme). Ils se deplaceront **tout seuls** quand "
    "leur hote se deplacera."
)

for nom_ws in sorted(par_categorie.keys(), key=lambda s: s.lower()):
    cats = par_categorie[nom_ws]
    if not cats:
        continue
    donnees = []
    for c in sorted(cats.keys(), key=lambda s: -cats[s][2]):
        donnees.append([c, cats[c][0], cats[c][2], cats[c][1]])
    out.print_table(
        table_data=donnees,
        title="{} - {} elements".format(nom_ws, sum([v[0] for v in cats.values()])),
        columns=["Categorie", "Nb", "A reclasser", "Un type rencontre"],
    )

if AVEC_PROPRIETAIRE and proprietaires:
    donnees = []
    for p in sorted(proprietaires.keys(), key=lambda s: -proprietaires[s]):
        donnees.append([p, proprietaires[p]])
    out.print_table(
        table_data=donnees,
        title="Elements empruntes (proprietaire declare)",
        columns=["Proprietaire", "Nb"],
    )
    out.print_md(
        "> Un element emprunte par quelqu'un d'autre **ne peut pas etre "
        "reassigne** tant qu'il n'a pas synchronise et rendu la main."
    )
else:
    out.print_md("_Aucun element emprunte, ou lecture du proprietaire desactivee._")

out.print_md("**{} lignes ecrites.**".format(len(lignes)))
out.print_md("CSV : `{}`".format(chemin))

out.print_md(
    "\n---\n"
    "**Ce qu'on en fait.** Une categorie qui tombe entierement dans un seul "
    "sous-projet cible se traite en une ligne de regle. Celle qui se partage "
    "est le vrai travail : pour le MEP c'est le **systeme** qui tranche - un "
    "raccord de canalisation peut relever du chauffage, de la plomberie ou de "
    "la protection incendie, et sa categorie n'en dit rien. La colonne "
    "**Classe** identifie les elements que Revit ne range dans aucune "
    "categorie.\n\n"
    "**Renvoie le CSV.** La regle s'ecrit dessus, pas avant."
)
