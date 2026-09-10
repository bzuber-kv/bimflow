# -*- coding: utf-8 -*-
"""B14 — Migration des sous-projets pilotee par une table de correspondance.

Repo bimflow — extension pyRevit. Portee : GENERIQUE (toute maquette en
travail partage). Cas d'origine : affaire A_049_TheStudy, 2026-09-10.
Audit prealable obligatoire : B13.

Quatre actions, et une seule touche des elements :

    CREER      cible          cree un sous-projet s'il n'existe pas
    RENOMMER   source, cible  renomme — NE DEPLACE AUCUN ELEMENT
    VIDER      source, cible  deplace tout le contenu de source vers cible
    GARDER     source         ne fait rien (la ligne sert de trace)

RENOMMER ne touche pas un seul element : c'est l'operation a preferer chaque
fois que la correspondance est 1 pour 1. VIDER ecrit sur chaque element, donc
c'est la seule qui peut buter sur un element possede par un autre utilisateur.

Ce script NE SUPPRIME AUCUN SOUS-PROJET. La suppression reste manuelle
(Collaborer > Sous-projets > Supprimer) — et c'est voulu : si Revit propose
encore « supprimer les elements / les reassigner », c'est que le sous-projet
n'etait pas vide, donc que ce script a rate quelque chose. Le dialogue de
Revit est notre controle.

Contrainte d'environnement (bimflow_CONTEXT, 2026-08-27) : moteur IPY342,
aucun CPython en netcore. PAS de ligne shebang « python3 » en tete. Python 3.4 maximum.
"""

__title__ = "Migration\nsous-projets"
__doc__ = "B14 - Renomme, cree et vide les sous-projets selon une table. Simulation par defaut."
__author__ = "Keovia Solutions"

from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    BuiltInParameter,
    CheckoutStatus,
    ElementId,
    ElementWorksetFilter,
    FilteredElementCollector,
    FilteredWorksetCollector,
    Transaction,
    Workset,
    WorksetId,
    WorksetKind,
    WorksetTable,
    WorksharingUtils,
)

from pyrevit import revit, script, forms

# ==========================================================================
#  REGLAGES
# ==========================================================================

# True  = on annonce ce qui serait fait, RIEN n'est modifie.  <-- par defaut
# False = on execute.
SIMULATION = True

# Tente de s'approprier les elements possedes par un autre utilisateur avant
# de les deplacer. Ne fonctionne que si leur proprietaire a synchronise.
TENTER_APPROPRIATION = False

# ==========================================================================
#  TABLE DE CORRESPONDANCE — brouillon 50 -> 35 (PLAN rev. g, §3.2 et §3.3)
#
#  /!\ Les noms sources sont ceux attendus, PAS ceux lus dans le modele.
#      Lance d'abord le bouton « 01 Audit » : il imprime la meme table avec
#      les noms exacts. Ce script refuse de s'executer si un nom ne colle pas.
# ==========================================================================

TABLE = [
    # ---- Architecture : 5 renommages, 2 conserves (aucun element deplace)
    ("RENOMMER", u"A_Cloisons et Enveloppe",     u"A_Murs"),
    ("RENOMMER", u"A_Sol",                       u"A_Sols"),
    ("RENOMMER", u"A_Toiture",                   u"A_Toitures"),
    ("RENOMMER", u"A_Plafonds et Sous-couverts", u"A_Plafonds_Sous_couverts"),
    ("RENOMMER", u"A_Escaliers et Rambardes",    u"A_Escaliers_Rambardes"),
    ("GARDER",   u"A_Menuiseries",               None),
    ("GARDER",   u"A_Mobilier",                  None),

    # ---- Structure : 8 S_ fusionnes dans STRU, + STRU_Fondations (vide)
    ("CREER",    None,                           u"STRU"),
    ("VIDER",    u"S_Béton",                     u"STRU"),
    ("VIDER",    u"S_Acier",                     u"STRU"),
    ("VIDER",    u"S_Acier_bardage",             u"STRU"),
    ("VIDER",    u"S_Acier_int",                 u"STRU"),
    ("VIDER",    u"S_Acier_toit",                u"STRU"),
    ("VIDER",    u"S_Bois",                      u"STRU"),
    ("VIDER",    u"S_Chevrons",                  u"STRU"),
    ("VIDER",    u"S_Maçonnerie",                u"STRU"),
    ("CREER",    None,                           u"STRU_Fondations"),

    # ---- Site : 3 renommages
    ("RENOMMER", u"T_Aménagement",               u"SITE_Amenagement"),
    ("RENOMMER", u"T_Terrain",                   u"SITE_Terrain"),
    ("RENOMMER", u"T_Végétation",                u"SITE_Vegetation"),

    # ---- Equipements
    ("CREER",    None,                           u"ELEC"),
    ("VIDER",    u"E_Distribution",              u"ELEC"),
    ("VIDER",    u"E_Eclairage",                 u"ELEC"),
    ("VIDER",    u"E_Communication",             u"ELEC"),
    ("VIDER",    u"E_Sécurité",                  u"ELEC"),

    ("CREER",    None,                           u"M_CH"),
    ("VIDER",    u"C_Chaud",                     u"M_CH"),
    ("VIDER",    u"C_Froid",                     u"M_CH"),
    ("RENOMMER", u"C_Ventilation",               u"M_VE"),

    ("CREER",    None,                           u"M_PL"),
    ("VIDER",    u"PB_Sanitaires",               u"M_PL"),
    ("VIDER",    u"PB_EP",                       u"M_PL"),
    ("VIDER",    u"PB_EU",                       u"M_PL"),

    ("CREER",    None,                           u"M_PI"),
    ("VIDER",    u"PI_réseau",                   u"M_PI"),
    ("VIDER",    u"PI_équipement",               u"M_PI"),

    # ---- Referentiel livre
    ("RENOMMER", u"ZG_Niveaux et Quadrillages",  u"ZG_Niveaux_Quadrillages"),
    ("VIDER",    u"ZW_Quadrillages",             u"ZG_Niveaux_Quadrillages"),
    ("RENOMMER", u"ZG_Pièces",                  u"ZG_Pieces"),
    ("GARDER",   u"ZG_Zones",                    None),

    # ---- Livre, non visible
    ("RENOMMER", u"Z_Fictif_Ne-pas-voir",        u"ZS_Supports"),

    # ---- Liens : les 9 existants sont conserves, ZL_EQU est cree d'avance
    ("GARDER",   u"ZL_ARCH",                     None),
    ("GARDER",   u"ZL_STRU",                     None),
    ("GARDER",   u"ZL_SITE",                     None),
    ("GARDER",   u"ZL_GENE",                     None),
    ("GARDER",   u"ZL_ELEC",                     None),
    ("GARDER",   u"ZL_M_CH",                     None),
    ("GARDER",   u"ZL_M_PL",                     None),
    ("GARDER",   u"ZL_M_PI",                     None),
    ("GARDER",   u"ZL_M_VE",                     None),
    ("CREER",    None,                           u"ZL_EQU"),

    # ---- Non livre
    ("RENOMMER", u"ZW_Défaut",                  u"ZW_Defaut"),
    ("RENOMMER", u"ZW_Nuages de points",         u"ZW_Nuages_de_points"),
    ("GARDER",   u"ZW_Construction",             None),
    # ZW_volumes_approx : son contenu part dans la maquette A_VOL a l'etape 4.
    # On ne touche a rien ici.
    ("GARDER",   u"ZW_volumes_approx",           None),

    # ---- Imposes par Revit — option A : on ne renomme pas Workset1
    ("GARDER",   u"Sous-projet 1",               None),
    ("GARDER",   u"Vues, niveaux et grilles partagés", None),
]

# ==========================================================================

doc = revit.doc
out = script.get_output()
out.set_title("Keovia — migration des sous-projets")

ACTIONS = ("CREER", "RENOMMER", "VIDER", "GARDER")

out.print_md("# Migration des sous-projets")
out.print_md("Modele : **{}**".format(doc.Title))
out.print_md(
    "Mode : **{}**".format(
        "SIMULATION — rien ne sera modifie" if SIMULATION else "EXECUTION REELLE"
    )
)

if not doc.IsWorkshared:
    out.print_md("> **Ce modele n'est pas en travail partage.** Rien a faire.")
    script.exit()

# ------------------------------------------------------- etat de depart
def lire_worksets():
    d = {}
    for ws in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset):
        d[ws.Name] = ws
    return d


existants = lire_worksets()

fermes = [n for n, ws in existants.items() if not ws.IsOpen]
if fermes:
    out.print_md(
        "> **ARRET — sous-projet(s) ferme(s) : {}.** Les elements d'un "
        "sous-projet ferme ne sont pas charges : ils seraient ignores "
        "silencieusement. Ouvre tous les sous-projets et relance."
        .format(", ".join(sorted(fermes)))
    )
    script.exit()

# ------------------------------------------------- validation de la table
erreurs, avertissements = [], []
cibles_prevues = set()

for i, ligne in enumerate(TABLE, 1):
    if len(ligne) != 3:
        erreurs.append("Ligne {} : il faut exactement 3 valeurs.".format(i))
        continue
    action, src, cible = ligne
    if action not in ACTIONS:
        erreurs.append(u"Ligne {} : action inconnue « {} ».".format(i, action))
        continue

    if action == "CREER":
        if not cible:
            erreurs.append("Ligne {} : CREER exige une cible.".format(i))
        else:
            cibles_prevues.add(cible)
    elif action in ("RENOMMER", "VIDER"):
        if not src or not cible:
            erreurs.append("Ligne {} : {} exige une source ET une cible.".format(i, action))
            continue
        if src not in existants:
            erreurs.append(u"Ligne {} : le sous-projet source « {} » n'existe pas "
                           u"dans ce modele.".format(i, src))
        if action == "RENOMMER":
            if cible in existants and cible != src:
                erreurs.append(u"Ligne {} : impossible de renommer « {} » en "
                               u"« {} » — ce nom est deja pris. Utilise VIDER."
                               .format(i, src, cible))
            cibles_prevues.add(cible)
        else:
            cibles_prevues.add(cible)
    elif action == "GARDER":
        if src and src not in existants:
            avertissements.append(u"Ligne {} : « {} » est marque GARDER mais "
                                  u"n'existe pas — ligne sans effet.".format(i, src))

# les cibles de VIDER doivent exister ou etre creees par une ligne CREER
for i, ligne in enumerate(TABLE, 1):
    if len(ligne) == 3 and ligne[0] == "VIDER":
        cible = ligne[2]
        renomme_vers = any(l[0] == "RENOMMER" and l[2] == cible for l in TABLE if len(l) == 3)
        cree = any(l[0] == "CREER" and l[2] == cible for l in TABLE if len(l) == 3)
        if cible not in existants and not cree and not renomme_vers:
            erreurs.append(u"Ligne {} : la cible « {} » n'existe pas et aucune "
                           u"ligne CREER ne la produit.".format(i, cible))

non_traites = sorted(set(existants) - set(
    l[1] for l in TABLE if len(l) == 3 and l[1]
))
if non_traites:
    avertissements.append(
        u"{} sous-projet(s) du modele n'apparaissent pas dans la table : {}. "
        u"Ils seront laisses tels quels."
        .format(len(non_traites), u", ".join(non_traites))
    )

if avertissements:
    out.print_md("## Avertissements")
    for a in avertissements:
        out.print_md("- " + a)

if erreurs:
    out.print_md("## ARRET — la table ne correspond pas au modele")
    for e in erreurs:
        out.print_md("- " + e)
    out.print_md(
        "\n_Lance le bouton **01 Audit** : il imprime la table avec les noms "
        "exacts du modele, a copier-coller ici._"
    )
    script.exit()

# --------------------------------------------- inventaire avant execution
def elements_de(ws):
    col = FilteredElementCollector(doc) \
        .WherePasses(ElementWorksetFilter(ws.Id)) \
        .WhereElementIsNotElementType()
    return list(col.ToElementIds())


plan = []
total_a_deplacer = 0
total_bloques = 0

for action, src, cible in TABLE:
    if action == "CREER":
        if cible in existants:
            plan.append([action, u"—", cible, 0, 0, u"existe deja, ignore"])
        else:
            plan.append([action, u"—", cible, 0, 0, u"a creer"])
    elif action == "RENOMMER":
        n = len(elements_de(existants[src]))
        note = u"aucun element deplace" if src != cible else u"deja au bon nom"
        plan.append([action, src, cible, n, 0, note])
    elif action == "VIDER":
        ids = elements_de(existants[src])
        bloques = []
        for eid in ids:
            try:
                if WorksharingUtils.GetCheckoutStatus(doc, eid) == CheckoutStatus.OwnedByOtherUser:
                    bloques.append(eid)
            except Exception:
                pass
        total_a_deplacer += len(ids)
        total_bloques += len(bloques)
        note = u"OK" if not bloques else u"{} possede(s) par un autre".format(len(bloques))
        plan.append([action, src, cible, len(ids), len(bloques), note])
    else:
        n = len(elements_de(existants[src])) if src in existants else 0
        plan.append([action, src or u"—", u"—", n, 0, u""])

out.print_table(
    table_data=plan,
    title="Plan d'execution",
    columns=["Action", "Source", "Cible", "Elements", "Bloques", "Note"],
)

out.print_md("**Elements a deplacer : {}**".format(total_a_deplacer))
if total_bloques:
    out.print_md(
        "> **{} element(s) sont possedes par un autre utilisateur.** Sans "
        "appropriation, ils resteront dans leur sous-projet d'origine — et "
        "le compte final ne collera pas. Fais synchroniser leur proprietaire, "
        "ou passe TENTER_APPROPRIATION a True.".format(total_bloques)
    )

if SIMULATION:
    out.print_md(
        "\n---\n**SIMULATION — aucune modification n'a ete faite.** "
        "Pour executer : ouvre ce script (bouton droit sur le bouton > "
        "Edit Script) et passe `SIMULATION = True` a `False`."
    )
    script.exit()

# --------------------------------------------------------------- execution
if not forms.alert(
    "EXECUTION REELLE sur « {} ».\n\n"
    "{} element(s) vont changer de sous-projet.\n"
    "Aucun sous-projet ne sera supprime.\n\n"
    "As-tu une sauvegarde datee hors Forma ?".format(doc.Title, total_a_deplacer),
    yes=True, no=True,
):
    script.exit()

if TENTER_APPROPRIATION and total_bloques:
    a_prendre = List[ElementId]()
    for action, src, cible in TABLE:
        if action == "VIDER":
            for eid in elements_de(existants[src]):
                a_prendre.Add(eid)
    try:
        pris = WorksharingUtils.CheckoutElements(doc, a_prendre)
        out.print_md("Appropriation : {} element(s) obtenus.".format(len(list(pris))))
    except Exception as ex:
        out.print_md("_Appropriation impossible ({})._".format(ex))

journal = []
t = Transaction(doc, "Keovia — migration des sous-projets")
t.Start()
try:
    # 1. creations
    for action, src, cible in TABLE:
        if action == "CREER" and cible not in lire_worksets():
            Workset.Create(doc, cible)
            journal.append([u"CREE", u"—", cible, 0, u""])

    # 2. renommages
    for action, src, cible in TABLE:
        if action == "RENOMMER" and src != cible:
            ws = lire_worksets().get(src)
            if ws is not None:
                WorksetTable.RenameWorkset(doc, ws.Id, cible)
                journal.append([u"RENOMME", src, cible, 0, u"aucun element touche"])

    # 3. deplacements
    courants = lire_worksets()
    for action, src, cible in TABLE:
        if action != "VIDER":
            continue
        ws_src = courants.get(src)
        ws_cib = courants.get(cible)
        if ws_src is None or ws_cib is None:
            journal.append([u"ECHEC", src, cible, 0, u"sous-projet introuvable"])
            continue
        cible_id = ws_cib.Id.IntegerValue
        deplaces, refuses = 0, 0
        for eid in elements_de(ws_src):
            el = doc.GetElement(eid)
            if el is None:
                continue
            p = el.get_Parameter(BuiltInParameter.ELEM_PARTITION_PARAM)
            if p is None or p.IsReadOnly:
                refuses += 1
                continue
            try:
                p.Set(cible_id)
                deplaces += 1
            except Exception:
                refuses += 1
        note = u"" if not refuses else u"{} refuse(s)".format(refuses)
        journal.append([u"VIDE", src, cible, deplaces, note])

    t.Commit()
except Exception as ex:
    t.RollBack()
    out.print_md("## ECHEC — tout a ete annule\n\n`{}`".format(ex))
    script.exit()

out.print_table(
    table_data=journal,
    title="Ce qui a ete fait",
    columns=["Action", "Source", "Cible", "Elements deplaces", "Note"],
)

# ------------------------------------------------------------- controle
restes = []
for action, src, cible in TABLE:
    if action == "VIDER":
        ws = lire_worksets().get(src)
        if ws is not None:
            n = len(elements_de(ws))
            if n:
                restes.append([src, n])

if restes:
    out.print_table(
        table_data=restes,
        title="Sous-projets qui ne sont PAS vides",
        columns=["Sous-projet", "Elements restants"],
    )
    out.print_md(
        "> Ne les supprime pas tant qu'ils ne sont pas a zero : Revit "
        "proposerait de reassigner ou de supprimer leur contenu, et c'est "
        "exactement la ou des elements se perdent."
    )
else:
    out.print_md(
        "## Controle : tous les sous-projets a vider sont a zero\n\n"
        "Tu peux maintenant les supprimer a la main dans "
        "**Collaborer > Sous-projets > Supprimer**. Revit doit les supprimer "
        "**sans poser de question** : s'il propose « supprimer les elements / "
        "les reassigner », arrete-toi — c'est qu'il reste quelque chose dedans."
    )

out.print_md(
    "\n_Rappel : `Sous-projet 1` et `Vues, niveaux et grilles partagés` ne se "
    "suppriment pas. Option A retenue : on ne les renomme pas non plus._"
)
