# -*- coding: utf-8 -*-
"""Lie les parametres partages du socle Keovia aux categories de la maquette ouverte.

Outil ORANGE : il ecrit dans la maquette (il cree des liaisons de parametres de projet).
Il n'ecrit AUCUNE valeur : il rend les champs disponibles, vides.

Discipline :
  - le plan de liaison est affiche AVANT toute ecriture ;
  - ce qui ne peut pas passer est dit, jamais tu ;
  - la transaction est annulee explicitement en cas d'erreur.

pyRevit v6.5.5 / IronPython 3.4.2 (IPY342) - pas de f-string, pas de shebang python3.
"""

__title__ = "Socle\nparametres"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-09-19n"

import os

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import BuiltInCategory, Category, CategorySet, Transaction

doc = revit.doc
app = doc.Application
out = script.get_output()

# ---------------------------------------------------------------------------
# Socle : quel parametre va sur quelles categories.
# Modifier ici, jamais dans le corps du script.
# ---------------------------------------------------------------------------

# Objets du batiment + les deux porteurs de la matrice de passage (Niveaux) et
# les volumes de reference (Masses, Planchers de volume).
CATEGORIES_LARGE = [
    "OST_Levels",
    "OST_Mass", "OST_MassFloor",
    "OST_Walls", "OST_Floors", "OST_Roofs", "OST_Ceilings",
    "OST_Doors", "OST_Windows", "OST_CurtainWallPanels",
    "OST_Columns", "OST_StructuralColumns", "OST_StructuralFraming",
    "OST_StructuralFoundation", "OST_Stairs", "OST_StairsRailing",
    "OST_GenericModel", "OST_Furniture", "OST_Casework",
    "OST_SpecialityEquipment", "OST_Parts",
    "OST_PlumbingFixtures", "OST_MechanicalEquipment",
    "OST_LightingFixtures", "OST_ElectricalEquipment", "OST_ElectricalFixtures",
    "OST_PipeCurves", "OST_FlexPipeCurves", "OST_PipeFitting", "OST_PipeAccessory",
    "OST_DuctCurves", "OST_FlexDuctCurves", "OST_DuctFitting", "OST_DuctAccessory",
    "OST_DuctTerminal", "OST_CableTray", "OST_Conduit", "OST_Sprinklers",
]

# Volumes de reference seulement.
CATEGORIES_VOLUME = ["OST_Mass", "OST_MassFloor"]

# Livrable : l'arborescence du projet.
CATEGORIES_VUES = ["OST_Views"]
CATEGORIES_FEUILLES = ["OST_Sheets"]

SOCLE = [
    ("REF_Batiment", CATEGORIES_LARGE),
    ("REF_Etage", CATEGORIES_LARGE),
    ("REF_Id", CATEGORIES_VOLUME),
    ("CLS_Usage", CATEGORIES_VOLUME),
    ("CLS_Nature_volume", CATEGORIES_VOLUME),
    # Les DOC_ ne figurent PAS ici : ce sont des parametres de PROJET, portes
    # par le gabarit, pas par le fichier de parametres partages. Critere du
    # 2026-09-19 : rien hors du document ne doit les reconnaitre, donc ils
    # n'ont pas besoin d'un GUID. Sur The Study ils naissent du renommage de
    # « Classement Vues », « Classement Feuille » et « Sous-discipline ».
]

NOM_FICHIER_ATTENDU = "keovia_socle_parametres.txt"


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def categorie(nom_bic):
    """Retourne (categorie, motif_de_refus). L'un des deux est None."""
    bic = getattr(BuiltInCategory, nom_bic, None)
    if bic is None:
        return None, u"inconnue dans cette version de Revit"
    try:
        cat = Category.GetCategory(doc, bic)
    except Exception:
        cat = None
    if cat is None:
        return None, u"absente de cette maquette"
    if not cat.AllowsBoundParameters:
        return None, u"n'accepte pas de parametre de projet"
    return cat, None


def definitions_du_fichier(fichier):
    """{nom: ExternalDefinition} pour tous les groupes du fichier."""
    trouvees = {}
    for groupe in fichier.Groups:
        for d in groupe.Definitions:
            trouvees[d.Name] = d
    return trouvees


def avertir_si_collaboratif():
    """Un essai se fait sur une copie detachee. Sur un modele collaboratif,
    une ecriture peut etre refusee A LA VALIDATION, apres coup."""
    try:
        if not doc.IsWorkshared:
            return
    except Exception:
        return
    try:
        if doc.IsDetached:
            return
    except Exception:
        pass
    if not forms.alert(
        u"Cette maquette est COLLABORATIVE et n'est pas detachee.\n\n"
        u"Si le modele central est inaccessible, Revit refusera l'ecriture "
        u"AU MOMENT DE LA VALIDATION — apres que le script ait affiche son "
        u"resultat.\n\n"
        u"Un essai se fait sur une copie detachee :\n"
        u"Ouvrir → cocher « Detacher du central ».\n\n"
        u"Continuer quand meme sur cette maquette ?",
        title=u"Maquette collaborative", yes=True, no=True,
    ):
        script.exit()


def liaisons_existantes():
    """{nom du parametre: (Binding, [noms de categories])}."""
    existantes = {}
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        cle = it.Key
        binding = it.Current
        noms = []
        try:
            for c in binding.Categories:
                noms.append(c.Name)
        except Exception:
            pass
        existantes[cle.Name] = (binding, noms)
    return existantes


def inserer(definition, jeu, remplacer):
    """Insere ou remplace une liaison d'occurrence. Retourne True/False."""
    binding = app.Create.NewInstanceBinding(jeu)
    carte = doc.ParameterBindings

    # Revit 2024+ attend un ForgeTypeId ; les versions anterieures un
    # BuiltInParameterGroup. On tente le moderne, on retombe sur l'ancien.
    try:
        from Autodesk.Revit.DB import GroupTypeId
        groupe = GroupTypeId.IdentityData
    except Exception:
        groupe = None

    if groupe is not None:
        try:
            if remplacer:
                return carte.ReInsert(definition, binding, groupe)
            return carte.Insert(definition, binding, groupe)
        except Exception:
            pass

    from Autodesk.Revit.DB import BuiltInParameterGroup
    ancien = BuiltInParameterGroup.PG_IDENTITY_DATA
    if remplacer:
        return carte.ReInsert(definition, binding, ancien)
    return carte.Insert(definition, binding, ancien)


# ---------------------------------------------------------------------------
# 1. Le fichier de parametres partages
# ---------------------------------------------------------------------------

avertir_si_collaboratif()

actuel = app.SharedParametersFilename
chemin = None

if actuel and os.path.isfile(actuel) and \
        os.path.basename(actuel).lower() == NOM_FICHIER_ATTENDU.lower():
    chemin = actuel
else:
    chemin = forms.pick_file(
        file_ext="txt",
        title=u"Choisir le fichier de parametres partages du socle Keovia",
    )

if not chemin:
    script.exit()

if not os.path.isfile(chemin):
    forms.alert(u"Fichier introuvable :\n" + chemin, exitscript=True)

app.SharedParametersFilename = chemin
fichier = app.OpenSharedParameterFile()
if fichier is None:
    forms.alert(
        u"Revit n'a pas su ouvrir ce fichier comme fichier de parametres "
        u"partages.\n\nVerifier qu'il est bien tabule et qu'il porte un bloc "
        u"*META / *GROUP / *PARAM.",
        exitscript=True,
    )

disponibles = definitions_du_fichier(fichier)
deja = liaisons_existantes()


# ---------------------------------------------------------------------------
# 2. Le plan de liaison, calcule puis AFFICHE avant toute ecriture
# ---------------------------------------------------------------------------

plan = []        # (nom, definition, jeu, [categories retenues], remplacer)
manquants = []   # parametres absents du fichier
refus = {}       # nom de categorie -> motif (mutualise)

for nom, noms_cat in SOCLE:
    definition = disponibles.get(nom)
    if definition is None:
        manquants.append(nom)
        continue

    retenues = []
    jeu = app.Create.NewCategorySet()

    # Une liaison existante est ETENDUE, jamais reduite : on reprend ses
    # categories actuelles avant d'ajouter les notres.
    binding_existant = deja.get(nom)
    deja_liees = []
    if binding_existant is not None:
        binding, deja_liees = binding_existant
        try:
            for c in binding.Categories:
                jeu.Insert(c)
                retenues.append(c.Name)
        except Exception:
            pass

    for nom_bic in noms_cat:
        cat, motif = categorie(nom_bic)
        if cat is None:
            refus[nom_bic] = motif
            continue
        if cat.Name in retenues:
            continue
        jeu.Insert(cat)
        retenues.append(cat.Name)

    if jeu.IsEmpty:
        manquants.append(nom + u" (aucune categorie liable dans cette maquette)")
        continue

    ajoutees = len(retenues) - len(deja_liees)
    plan.append((nom, definition, jeu, sorted(retenues), binding_existant is not None,
                 ajoutees, len(deja_liees)))

out.print_md(u"# Socle de parametres - plan de liaison")
out.print_md(u"**Version de l'outil** : `" + VERSION + u"`")
out.print_md(u"**Maquette** : `" + doc.Title + u"`")
out.print_md(u"**Fichier** : `" + chemin + u"`")
out.print_md(u"> Cet outil rend les champs disponibles. Il n'ecrit **aucune valeur**.")

if plan:
    lignes = []
    for nom, _d, _j, retenues, existait, ajoutees, avant in plan:
        if not existait:
            etat = u"a creer"
        elif ajoutees > 0:
            etat = u"a etendre (+%d)" % ajoutees
        else:
            etat = u"deja conforme"
        lignes.append([nom, etat, str(avant), str(len(retenues))])
    out.print_table(
        table_data=lignes,
        title=u"Parametres",
        columns=[u"Parametre", u"Etat", u"Categories avant", u"Categories apres"],
    )

if manquants:
    out.print_md(u"## Absents du fichier - rien ne sera fait pour eux")
    for m in manquants:
        out.print_md(u"- `" + m + u"`")

if refus:
    out.print_md(u"## Categories ecartees")
    for nom_bic in sorted(refus.keys()):
        out.print_md(u"- `" + nom_bic + u"` : " + refus[nom_bic])

a_ecrire = [p for p in plan if (not p[4]) or p[5] > 0]

if not a_ecrire:
    forms.alert(
        u"Rien a ecrire : toutes les liaisons du socle sont deja en place "
        u"dans cette maquette.\n\nLe detail est dans la fenetre de sortie.",
        title=u"Socle deja en place",
    )
    script.exit()

resume = u"\n".join([u"  - " + p[0] for p in a_ecrire])
if not forms.alert(
    u"Maquette : %s\n\n"
    u"%d parametre(s) a lier :\n\n%s\n\n"
    u"Le fichier de parametres partages de Revit pointera desormais sur :\n%s\n\n"
    u"Ecrire maintenant ?" % (doc.Title, len(a_ecrire), resume, chemin),
    title=u"Socle de parametres - confirmation",
    yes=True, no=True,
):
    out.print_md(u"**Annule par l'utilisateur. Rien n'a ete ecrit.**")
    script.exit()


# ---------------------------------------------------------------------------
# 3. Ecriture
# ---------------------------------------------------------------------------

faits = []
echecs = []

t = Transaction(doc, "Keovia - liaison du socle de parametres")
try:
    t.Start()
    for nom, definition, jeu, retenues, existait, _aj, _av in a_ecrire:
        try:
            ok = inserer(definition, jeu, existait)
        except Exception as err:
            echecs.append((nom, str(err)))
            continue
        if ok:
            faits.append((nom, len(retenues)))
        else:
            echecs.append((nom, u"Revit a refuse la liaison sans message"))
    if faits:
        t.Commit()
    else:
        t.RollBack()
except Exception as err:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    forms.alert(u"Echec, rien n'a ete ecrit :\n\n" + str(err), exitscript=True)

# VERIFICATION APRES COUP. Une transaction validee par le script peut avoir
# ete refusee par Revit (modele central inaccessible, element emprunte).
# L'intention n'est pas le resultat : on relit la maquette.
verif = liaisons_existantes()

out.print_md(u"## Resultat — relu dans la maquette, pas annonce")
confirmes = []
perdus = []
for nom, n in faits:
    if nom in verif:
        confirmes.append((nom, len(verif[nom][1])))
    else:
        perdus.append(nom)

for nom, n in confirmes:
    out.print_md(u"- `" + nom + u"` : **present**, " + str(n) + u" categories")
for nom in perdus:
    out.print_md(u"- **ABSENT** `" + nom + u"` : le script l'a ecrit, la "
                 u"maquette ne le porte pas")
for nom, motif in echecs:
    out.print_md(u"- **ECHEC** `" + nom + u"` : " + motif)

if perdus:
    forms.alert(
        u"%d liaison(s) ont ete ecrites par le script mais N'EXISTENT PAS "
        u"dans la maquette.\n\n"
        u"Cause la plus frequente : modele collaboratif dont le central est "
        u"inaccessible — Revit refuse l'ecriture a la validation.\n\n"
        u"Fermer SANS enregistrer, et recommencer sur une copie detachee."
        % len(perdus),
        title=u"Ecriture non appliquee",
    )
elif echecs and not confirmes:
    out.print_md(u"**Transaction annulee : aucune liaison ecrite.**")

out.print_md(
    u"---\n"
    u"Prochaine etape : renseigner `REF_Batiment` et `REF_Etage` sur les "
    u"**niveaux**, dans la maquette d'axes et niveaux. C'est la matrice de "
    u"passage niveau Revit -> etage macro ; rien ne s'agrege sans elle."
)
