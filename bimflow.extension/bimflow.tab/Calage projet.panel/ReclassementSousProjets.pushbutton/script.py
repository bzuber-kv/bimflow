# -*- coding: utf-8 -*-
"""B17 v3 - Reclassement des sous-projets par regles. ECRIT DANS LE MODELE.

Repo bimflow - extension pyRevit. Portee : GENERIQUE, table specifique a
l'affaire. Cas d'origine : A_049_TheStudy, 2026-09-10.

CE QUE FAIT CE SCRIPT
---------------------
Il vide un sous-projet fourre-tout en repartissant son contenu vers les
sous-projets metier, selon trois familles de regles evaluees DANS CET
ORDRE :

  1. TYPE DE SYSTEME  (MEP) - un raccord de canalisation peut relever du
     chauffage, de la plomberie ou de la protection incendie. Sa categorie
     n'en dit rien ; son type de systeme, oui.
  2. FAMILLE ou TYPE  - pour les objets qu'aucune categorie ne qualifie
     (sprinklers en Equipement de genie climatique, colonnes en Modele
     generique).
  3. CATEGORIE  - le bati, ou la categorie suffit.

Ce qu'aucune regle ne couvre N'EST PAS DEPLACE et figure au rapport avec
son motif. Un sous-projet est une affirmation (PEP 4.4, garde-fou 2) :
mieux vaut un element non classe qu'un element mal classe.

POURQUOI LE TYPE DE SYSTEME ET PAS SON NOM
-------------------------------------------
Mesure du 2026-09-10 sur thestudy_CO_BAT : le nommage des systemes de la
maquette est incoherent. Le prefixe "ECA" porte 18 systemes de type
"ECA - Alimentation Eau de Chauffage" mais aussi un "EFS - Eau Froide
Domestique" ; "GAZ" porte des cloches hydrauliques ; "EU" porte un ECA.
Classer sur le nom d'instance introduirait des erreurs silencieuses. Le
script lit donc le TYPE, dans le modele, au moment de s'executer - il ne
depend d'aucune liste d'identifiants preetablie.

ELEMENTS QUI NE PORTENT PAS LEUR SOUS-PROJET
---------------------------------------------
Lignes d'axe de reseau, esquisses, cotes automatiques, isolations,
sous-elements d'escalier, plans de reference : leur parametre de
sous-projet est en lecture seule, ils SUIVENT leur hote. Le script les
ignore explicitement - ils se deplaceront tout seuls.

CONTRAINTES D'ENVIRONNEMENT
---------------------------
Moteur IPY342, pas de CPython. Pas de shebang. Python 3.4 : pas de
f-strings. Fichier en ASCII pur.
"""

__title__ = "Reclasser\nsous-projets"
__doc__ = "B17 v3 - Vide un sous-projet fourre-tout par regles (systeme, famille, categorie). SIMULATION PAR DEFAUT. Ecrit dans le modele une fois desarme."
__author__ = "Keovia Solutions inc."

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
# REGLAGE PRINCIPAL
# =========================================================================
# True  : aucune ecriture. Le script imprime ce qu'il FERAIT.
# False : il ecrit. Une confirmation est demandee au lancement.
SIMULATION = True
# =========================================================================

# Sous-projets a vider.
SOURCES = ["ZW_Defaut", "Sous-projet 1", "Workset1"]

# Ou part le residu technique qui n'a aucune vocation metier : plans
# d'esquisse invisibles, composants de legende, schemas de numerotation.
#
# HISTORIQUE DE CE REGLAGE - il vaut la peine d'etre lu avant d'y toucher.
#   v1 : residu -> ZW_Defaut.   Faute. Un ZW_ est ce qu'on supprime avant de
#        livrer ; or un composant de legende porte une legende posee sur une
#        feuille. On l'aurait inscrit sur la liste de suppression.
#   v2 : residu -> ZS_Supports. Faute aussi, dans l'autre sens. ZS_Supports a
#        une definition precise (murs fictifs, vides de decoupe, plans
#        porteurs de coupes : des objets qu'on modelise VOLONTAIREMENT). Y
#        verser 705 objets crees automatiquement par Revit en ferait un
#        second fourre-tout, livre celui-la.
#   v3 : None. On ne range pas ce qu'on ne connait pas.
#
# PEP 4.4, garde-fou 2 : "un sous-projet est une affirmation ; y ranger un
# objet, c'est declarer qu'on connait sa fonction. Un sous-projet absent vaut
# mieux qu'un sous-projet faux."
#
# Le residu reste donc ou il est, et B18 (sonde de dependance) etablit ce
# qu'il porte. On ne renseignera ce reglage qu'apres cette mesure.
RESIDU_VERS = None

# ---- 1. TYPE DE SYSTEME -> sous-projet -------------------------------
# La cle est cherchee comme SOUS-CHAINE du nom du type, en minuscules et
# sans accent : une variante de nommage ne fait pas echouer la regle.
PAR_SYSTEME = [
    # protection incendie
    ("protection contre les incendies", "M_PI"),
    ("cloche hydraulique",              "M_PI"),
    ("sprinkler",                       "M_PI"),
    # chauffage (et froid avec lui, PEP 4.4)
    ("alimentation eau de chauffage",   "M_CH"),
    ("retour eau de chauffage",         "M_CH"),
    ("retour hydraulique",              "M_CH"),
    ("alimentation hydraulique",        "M_CH"),
    # plomberie et sanitaires
    ("eau froide domestique",           "M_PL"),
    ("eau chaude sanitaire",            "M_PL"),
    ("eaux usees",                      "M_PL"),
    ("eau pluviale",                    "M_PL"),
    # ventilation
    ("soufflage",                       "M_VE"),
    ("reprise",                         "M_VE"),
    ("air neuf",                        "M_VE"),
    ("extraction",                      "M_VE"),
    # --- NON TRANCHE au 2026-09-10 : le PEP n'a pas de lot gaz. ---
    # Decommenter la ligne retenue apres arbitrage de Bruno.
    # ("gaz",                           "M_CH"),
]

# ---- 2. FAMILLE ou TYPE -> sous-projet --------------------------------
PAR_FAMILLE = [
    ("sprinkler",          "M_PI"),
    ("radiateur",          "M_CH"),
    ("convecteur",         "M_CH"),
    ("tableau chaudiere",  "M_CH"),
    ("pump-end suction",   "M_CH"),
    ("circulator",         "M_CH"),
    # --- NON TRANCHE : arbitrage Bruno en attente ---
    # ("colonne n",        "?"),   # 109 modeles generiques "Colonne N1/N2"
    # ("volume n",         "?"),   #  29 modeles generiques "Volume N1/N2/N3"
    # ("couronne n",       "?"),   #   1
    # ("detendeur gaz",    "?"),   #   1
]

# ---- 3. CATEGORIE -> sous-projet --------------------------------------
PAR_CATEGORIE = {
    "murs":                 "A_Murs",
    "sols":                 "A_Sols",
    "plafonds":             "A_Plafonds_Sous-couverts",
    "toits":                "A_Toitures",
    "gouttieres":           "A_Toitures",
    "fenetres":             "A_Menuiseries",
    "portes":               "A_Menuiseries",
    "escalier":             "A_Escaliers_Rambardes",
    "escaliers":            "A_Escaliers_Rambardes",
    "garde-corps":          "A_Escaliers_Rambardes",
    "poteaux porteurs":     "STRU",
    "ossature":             "STRU",
    "niveaux":              "ZG_Niveaux_Quadrillages",
    "quadrillages":         "ZG_Niveaux_Quadrillages",
    "pieces":               "ZG_Pieces",
    "zones":                "ZG_Zones",
    "zones cvc":            "ZG_Zones",
    "circuit electrique":   "ELEC",
    "installations electriques": "ELEC",
    "equipement electrique":     "ELEC",
    "luminaires":           "ELEC",
    "appareils sanitaires": "M_PL",
    "bouche d'aeration":    "M_VE",
    "gaine":                "M_VE",
    "gaines":               "M_VE",
    "gaine flexible":       "M_VE",
    "raccords de gaine":    "M_VE",
    "systemes de gaines":   "M_VE",
    "nuage de points":      "ZW_Nuages_de_points",
    "nuages de points":     "ZW_Nuages_de_points",
}

# Classes .NET considerees comme residu technique (regle 0, avant tout).
RESIDU_CLASSES = ["SketchPlane", "NumberingSchema"]
RESIDU_CATEGORIES = ["composants de legende"]
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
    """Revit 2024+ : ElementId.Value (Int64). WorksetId.IntegerValue existe
    toujours - autre classe, ne pas confondre."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


doc = revit.doc
out = script.get_output()
out.set_title("Keovia - reclassement des sous-projets")

if not doc.IsWorkshared:
    out.print_md("> **Ce modele n'est pas en travail partage.** Rien a faire.")
    script.exit()

# ---------------------------------------------------------- garde-fou UX
if SIMULATION:
    out.print_md("# Reclassement - **SIMULATION**")
    out.print_md("_Aucune ecriture. Le script imprime ce qu'il ferait._")
else:
    ok = forms.alert(
        "MODE REEL - ce bouton va MODIFIER le modele.\n\n"
        "Il reaffecte des elements a d'autres sous-projets. L'operation est "
        "annulable par Ctrl+Z tant que le modele n'est pas synchronise.\n\n"
        "Modele : " + doc.Title + "\n\nContinuer ?",
        title="B17 - reclassement des sous-projets",
        ok=False, yes=True, no=True, exitscript=True,
    )
    if not ok:
        script.exit()
    out.print_md("# Reclassement - **MODE REEL**")

out.print_md("Modele : **{}** - {}".format(
    doc.Title, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))

# --------------------------------------------------- table des sous-projets
user_ws = list(FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset))

fermes = [ws.Name for ws in user_ws if not ws.IsOpen]
if fermes:
    out.print_md(
        "> **ARRET - {} sous-projet(s) ferme(s).** Un sous-projet ferme n'est "
        "pas charge : le script travaillerait sur une population partielle "
        "sans le dire. Collaborer > Sous-projets > Ouvrir, puis relance."
        "\n>\n> {}".format(len(fermes), ", ".join(fermes)))
    script.exit()

par_nom = {}
for ws in user_ws:
    par_nom[sans_accent(ws.Name)] = ws

# Toutes les cibles nommees dans les regles doivent exister AVANT d'ecrire.
cibles = set()
for _, c in PAR_SYSTEME:
    cibles.add(c)
for _, c in PAR_FAMILLE:
    cibles.add(c)
for c in PAR_CATEGORIE.values():
    cibles.add(c)
if RESIDU_VERS:
    cibles.add(RESIDU_VERS)

# Garde-fou de doctrine : le residu technique est LIVRE (il porte des objets
# livres). L'envoyer dans un ZW_ l'inscrirait sur la liste de ce qu'on
# supprime avant de figer une maquette de livraison.
if RESIDU_VERS and sans_accent(RESIDU_VERS).startswith("zw"):
    out.print_md(
        "> **ARRET - RESIDU_VERS pointe vers `{}`, un sous-projet `ZW_`.**\n>\n"
        "> Les plans d'esquisse et les composants de legende sont des objets "
        "**dont depend un objet livre** : une legende sur une feuille, "
        "l'esquisse d'un sol. Un `ZW_` est ce qu'on supprime avant de livrer. "
        "Vise `ZS_Supports`.".format(RESIDU_VERS))
    script.exit()

manquantes = sorted([c for c in cibles if sans_accent(c) not in par_nom])
if manquantes:
    out.print_md(
        "> **ARRET - sous-projet(s) cible(s) absent(s) du modele :**\n>\n"
        "> `{}`\n>\n"
        "> Cree-les d'abord (ou corrige la table en tete de script). Le script "
        "ne cree aucun sous-projet : creer sur une faute de frappe produirait "
        "un doublon durable.".format(u"`, `".join(manquantes)))
    script.exit()

sources = [ws for ws in user_ws if sans_accent(ws.Name) in
           [sans_accent(s) for s in SOURCES]]
if not sources:
    out.print_md("> **Aucun des sous-projets sources n'existe.** Rien a faire.")
    script.exit()

out.print_md("Sources : **{}**".format(", ".join([ws.Name for ws in sources])))

# ------------------------------------------- etape 1 : materialiser les Id
# (separation stricte : aucune propriete n'est lue tant qu'un collecteur itere)
a_traiter = []
for ws in sources:
    col = FilteredElementCollector(doc) \
        .WherePasses(ElementWorksetFilter(ws.Id)) \
        .WhereElementIsNotElementType()
    for eid in col.ToElementIds():
        a_traiter.append((ws.Name, eid))

out.print_md("**{} elements examines.**".format(len(a_traiter)))

# ------------------------------------------------- etape 2 : decider
cache_sys = {}


def type_de_systeme(elem, cls):
    """Le TYPE de systeme, jamais son nom d'instance - voir l'en-tete.

    Retourne "" pour tout ce qui n'est pas un objet de reseau : sans cette
    reserve, le repli sur GetTypeId ferait passer un mur pour un systeme
    nomme "Mur de base" et bloquerait toutes les regles suivantes."""
    for bip in (BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM,
                BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM):
        try:
            p = elem.get_Parameter(bip)
        except Exception:
            p = None
        if p is None:
            continue
        try:
            v = p.AsValueString()
            if v:
                return v
        except Exception:
            pass

    # Les objets systeme EUX-MEMES portent leur type par GetTypeId. Cette
    # branche leur est reservee : PipingSystem, MechanicalSystem,
    # ElectricalSystem, et rien d'autre.
    if not cls.endswith("System"):
        return u""
    try:
        tid = elem.GetTypeId()
    except Exception:
        return u""
    cle = id_de(tid)
    if cle in cache_sys:
        return cache_sys[cle]
    valeur = u""
    if cle > 0:
        t = doc.GetElement(tid)
        if t is not None:
            try:
                valeur = t.Name
            except Exception:
                valeur = u""
    cache_sys[cle] = valeur
    return valeur


def decide(elem, cat, cls, nom_type):
    """Retourne (cible ou None, motif). L'ordre des regles est le contrat."""
    # regle 0 - residu technique
    if cls in RESIDU_CLASSES or sans_accent(cat) in RESIDU_CATEGORIES:
        if RESIDU_VERS:
            return RESIDU_VERS, u"residu technique ({})".format(cls)
        return None, u"residu technique, laisse sur place"

    # regle 1 - type de systeme
    sys = type_de_systeme(elem, cls)
    if sys:
        s = sans_accent(sys)
        trouves = set()
        for cle, cible in PAR_SYSTEME:
            if cle in s:
                trouves.add(cible)
        if len(trouves) == 1:
            return list(trouves)[0], u"systeme : " + sys
        if len(trouves) > 1:
            return None, u"systeme ambigu ({}) -> {}".format(
                sys, u", ".join(sorted(trouves)))
        # un systeme est renseigne mais aucune regle ne le couvre : on le dit.
        return None, u"type de systeme non couvert : " + sys

    # regle 2 - famille ou type
    nt = sans_accent(nom_type)
    for cle, cible in PAR_FAMILLE:
        if cle in nt:
            return cible, u"famille/type : " + nom_type

    # regle 3 - categorie
    c = sans_accent(cat)
    if c in PAR_CATEGORIE:
        return PAR_CATEGORIE[c], u"categorie : " + cat

    return None, u"aucune regle (categorie : {})".format(cat)


plan = {}        # cible -> [ (eid, source) ]
refus = {}       # motif -> nb
non_portes = 0
exemples = {}    # motif -> un Id

for nom_src, eid in a_traiter:
    elem = doc.GetElement(eid)
    if elem is None:
        continue

    try:
        p = elem.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
    except Exception:
        p = None
    if p is None or p.IsReadOnly:
        non_portes += 1
        continue

    cat = u"(sans categorie)"
    try:
        if elem.Category is not None:
            cat = elem.Category.Name
    except Exception:
        pass
    try:
        cls = elem.GetType().Name
    except Exception:
        cls = u"?"
    nom_type = u""
    try:
        tid = elem.GetTypeId()
        if id_de(tid) > 0:
            t = doc.GetElement(tid)
            if t is not None:
                fam = u""
                try:
                    fam = t.FamilyName
                except Exception:
                    fam = u""
                nm = u""
                try:
                    nm = t.Name
                except Exception:
                    nm = u""
                nom_type = (fam + u" " + nm).strip()
    except Exception:
        nom_type = u""

    cible, motif = decide(elem, cat, cls, nom_type)

    if cible is None:
        refus[motif] = refus.get(motif, 0) + 1
        exemples.setdefault(motif, id_de(eid))
        continue

    if sans_accent(cible) == sans_accent(nom_src):
        continue  # deja au bon endroit

    plan.setdefault(cible, []).append(eid)

# ------------------------------------------------------- rapport du plan
donnees = []
total_a_ecrire = 0
for cible in sorted(plan.keys(), key=lambda s: (-len(plan[s]), s.lower())):
    donnees.append([cible, len(plan[cible])])
    total_a_ecrire += len(plan[cible])

if donnees:
    out.print_table(table_data=donnees, title="Plan d'execution",
                    columns=["Sous-projet cible", "Elements deplaces"])
else:
    out.print_md("> **Rien a deplacer** : aucune regle ne s'applique.")

out.print_md("**{} elements a ecrire.**".format(total_a_ecrire))
out.print_md("_{} elements ne portent pas leur sous-projet (lecture seule) : "
             "ils suivent leur hote et sont ignores._".format(non_portes))

if refus:
    donnees = []
    for motif in sorted(refus.keys(), key=lambda s: -refus[s]):
        donnees.append([refus[motif], motif, exemples.get(motif, u"")])
    out.print_table(
        table_data=donnees, title="NON DEPLACES - a arbitrer",
        columns=["Nb", "Motif", "Un Id pour aller voir"],
    )
    out.print_md(
        "> Ces elements restent ou ils sont. **C'est voulu** : un sous-projet "
        "est une affirmation, et une affirmation fausse fait plus de degats "
        "qu'une case vide. Chaque ligne se solde en ajoutant une regle en "
        "tete de script - pas en forcant la main au script."
    )

# ------------------------------------------------------------- ecriture
if SIMULATION:
    out.print_md(
        "\n---\n**SIMULATION - rien n'a ete ecrit.**\n\n"
        "Pour executer : clic droit sur le bouton > **Edit Script**, passer "
        "`SIMULATION = True` a `False` en tete de fichier, enregistrer, "
        "pyRevit > Reload. Une confirmation sera demandee au lancement."
    )
    script.exit()

if total_a_ecrire == 0:
    out.print_md("\n---\nRien a ecrire.")
    script.exit()

t = Transaction(doc, "Keovia B17 - reclassement des sous-projets")
t.Start()
ecrits = 0
echecs = []
try:
    for cible, ids in plan.items():
        ws = par_nom[sans_accent(cible)]
        # ELEM_PARTITION_PARAM est un entier : l'IntegerValue du WorksetId.
        valeur = ws.Id.IntegerValue
        for eid in ids:
            elem = doc.GetElement(eid)
            if elem is None:
                continue
            p = elem.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
            if p is None or p.IsReadOnly:
                continue
            try:
                p.Set(valeur)
                ecrits += 1
            except Exception as ex:
                echecs.append((id_de(eid), cible, u"{}".format(ex)))
    t.Commit()
except Exception as ex:
    t.RollBack()
    out.print_md("> **ECHEC - transaction annulee, le modele est intact.**\n>\n"
                 "> `{}`".format(ex))
    script.exit()

out.print_md("\n---\n**{} elements reaffectes.**".format(ecrits))
if echecs:
    out.print_table(
        table_data=[[a, b, c[:90]] for a, b, c in echecs[:40]],
        title="Echecs individuels ({})".format(len(echecs)),
        columns=["Id", "Cible visee", "Message"],
    )

out.print_md(
    "**Suite.** Relancer **B16** pour verifier ce qui reste, puis : supprimer "
    "le sous-projet source devenu vide, et renommer le sous-projet indestructible "
    "en `ZW_Defaut`. Ce renommage n'ecrit sur aucun element.\n\n"
    "> **Controle de fin de course.** Revit doit supprimer le sous-projet "
    "**sans poser de question**. S'il propose de supprimer les elements ou de "
    "les reassigner, il reste quelque chose dedans : ne pas repondre au "
    "hasard, annuler et relancer B16.\n\n"
    "_Annulable par Ctrl+Z tant que le modele n'est pas synchronise._"
)
