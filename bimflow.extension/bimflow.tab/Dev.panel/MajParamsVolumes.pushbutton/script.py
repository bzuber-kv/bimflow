# -*- coding: utf-8 -*-
"""maj_params_volumes - Parametres des volumes de zone, deduits de leur NOM.

Reecrit le 2026-09-24 : motif etendu (numero et cle), et identite des
parametres par GUID.

OBJET. Recopier dans les parametres partages ce que le nom de famille porte
deja. Ne touche JAMAIS a la geometrie, ni au nom de famille, ni au type.

    VOL_nnn__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>[__<cle>]
    ex. VOL_007__JU_Bj-Fj-1j-5j__FLOOR_3__ETAGE

#############################################################################
# STATUT : NON EPROUVE - JAMAIS EXECUTE DANS REVIT au 2026-09-24.           #
# Ce script ECRIT. Essai sur COPIE DETACHEE uniquement (R17). Le succes     #
# affiche ici NE PROUVE RIEN : la verification se fait en nomenclature.     #
#############################################################################

CE QUI EST ECRIT, volume par volume :
    REF_Zone           segment 1, rafraichi a chaque passage
    REF_Etage          segment 2, rafraichi a chaque passage
    CLS_Nature_volume  segment 3, rafraichi a chaque passage
    REF_Batiment       la CLE (segment 5) si elle designe un batiment,
                       sinon le prefixe de la zone - regle unique, ecrite
                       dans bimflow_noms.ref_batiment()
    REF_Id             uuid4, ecrit UNE SEULE FOIS si le champ est vide.
                       JAMAIS reecrit, JAMAIS regenere : c'est la cle de
                       jointure vers Ivion, elle doit survivre aux
                       renommages.
    CLS_Usage          jamais ecrit (saisie metier)

IDENTITE PAR GUID, JAMAIS PAR NOM (fiche R08). Un nom de parametre se
renomme, se traduit, se duplique ; le GUID, lui, EST le parametre. Les six
GUID ci-dessous sont ceux du socle Keovia - ils sont la source, et le
fichier shared_parameters/keovia_socle_parametres.txt en est le registre.
Consequence : un parametre local qui porterait le meme NOM sans le bon GUID
n'est PAS reconnu, et le volume sort en "parametre absent" plutot que de
recevoir une valeur dans le mauvais champ.

CONTROLE SIGNALE, JAMAIS BLOQUANT : a l'etage ROOF, TOITURE et ENTRETOIT
sont legitimes ; toute autre nature y est signalee, comme l'est une TOITURE
ailleurs qu'a ROOF. Le volume est ecrit quand meme - le nom fait foi.

bimflow - volumes de zone, mode ecriture - Keovia Solutions inc.
"""

__title__ = "MAJ params\nvolumes"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES
# --------------------------------------------------------------------------

# GUID du socle Keovia. SOURCE : shared_parameters/keovia_socle_parametres.txt
# Ne jamais remplacer un GUID : ce serait designer un autre parametre.
GUID_ZONE = "499a73ab-e323-42bf-807b-465c9165e62b"      # REF_Zone
GUID_ETAGE = "d7971f4d-dab0-4a07-bf53-df011895c4e4"     # REF_Etage
GUID_BATIMENT = "9b48114b-33fe-4eee-97ef-2369b17ea6ce"  # REF_Batiment
GUID_ID = "7414d6b1-6083-4145-9c1c-784e03243895"        # REF_Id
GUID_NATURE = "ba2e6c9e-506e-4b97-95aa-a5e3c10cbc40"    # CLS_Nature_volume
# CLS_Usage e3e496bc-5c59-4d02-b914-428692662dc7 : jamais ecrit par ce script

NOM_DU_GUID = {
    GUID_ZONE: "REF_Zone",
    GUID_ETAGE: "REF_Etage",
    GUID_BATIMENT: "REF_Batiment",
    GUID_ID: "REF_Id",
    GUID_NATURE: "CLS_Nature_volume",
}

# REF_Batiment : valeurs longues arretees pour l'affaire The Study
# (decision du 2026-09-19b). La regle du 2026-09-24 choisit le CODE - cle ou
# prefixe de zone - et cette table le traduit dans la valeur arretee.
# Mettre VALEURS_LONGUES a False pour ecrire le code brut (JU, MI, SC, SE).
VALEURS_LONGUES = True
BATIMENT_DU_CODE = {
    "JU": "Junior",
    "MI": "Middle",
    "SC": "Senior_Central",
    "SE": "Senior_East",
    "EXT": "Site",
}

# Une maquette collaborative doit etre traitee sur une COPIE DETACHEE (R17).
AUTORISER_NON_DETACHE = False

# --------------------------------------------------------------------------

from pyrevit import revit, script, forms

try:
    from bimflow_noms import (lire as lire_nom, ref_batiment,
                              incoherence_etage_nature)
except ImportError:
    from pyrevit import forms as _formulaires
    _formulaires.alert(
        u"Module partage bimflow_noms introuvable.\n\n"
        u"Il doit se trouver dans bimflow.extension\\lib\\. Sans lui, le "
        u"decoupage des noms de volumes n'est pas disponible et ce script "
        u"ne s'execute pas.",
        exitscript=True,
    )

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    FamilyInstance,
    StorageType,
    Transaction,
    TransactionStatus,
)
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommonButtons, TaskDialogResult

doc = revit.doc
out = script.get_output()


def nouvel_identifiant():
    """uuid4 au format standard 8-4-4-4-12."""
    try:
        import uuid
        return str(uuid.uuid4())
    except Exception:
        # repli .NET : Guid.NewGuid() est lui aussi un UUID de version 4
        from System import Guid
        return str(Guid.NewGuid())


def id_de(eid):
    """R15 fait 7 : ElementId.Value en Revit 2024+, .IntegerValue avant."""
    if eid is None:
        return -1
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


def texte(valeur):
    return u"" if valeur is None else u"{0}".format(valeur)


def lien_de(eid):
    try:
        return out.linkify(eid)
    except Exception:
        return u"`{0}`".format(id_de(eid))


# --------------------------------------------------------------------------
# 0. Garde-fous
# --------------------------------------------------------------------------

if doc.IsFamilyDocument:
    forms.alert(u"Document famille : rien a traiter.", exitscript=True)

collaboratif = bool(doc.IsWorkshared)
detache = None
try:
    detache = bool(doc.IsDetached)
except Exception:
    detache = None

# IsWorkshared reste True apres un detachement conservant les sous-projets :
# c'est IsDetached qui tranche.
if collaboratif and detache is not True and not AUTORISER_NON_DETACHE:
    forms.alert(
        u"Maquette collaborative, et ce n'est pas une copie detachee.\n\n"
        u"Ce script ECRIT dans le modele : il ne tourne que sur une copie "
        u"detachee (R17 - sur central inaccessible, Revit refuse la "
        u"transaction APRES avoir affiche le resultat).\n\n"
        u"Rouvrir la maquette avec \"Detacher du fichier central\", puis "
        u"relancer.",
        exitscript=True,
    )

# --------------------------------------------------------------------------
# 1. Lecture par GUID
# --------------------------------------------------------------------------


def parametre_par_guid(el, guid):
    """Le parametre PARTAGE dont le GUID est celui-la, ou None.

    On balaie les parametres de l'element : LookupParameter() chercherait
    par NOM, et c'est precisement ce qu'on refuse (R08)."""
    try:
        parametres = list(el.Parameters)
    except Exception:
        return None
    for p in parametres:
        try:
            if not p.IsShared:
                continue
            if str(p.GUID).lower() == guid:
                return p
        except Exception:
            continue
    return None


def lire_texte(el, guid, eid):
    """(parametre, valeur, motif de refus)."""
    p = parametre_par_guid(el, guid)
    if p is None:
        return None, None, u"parametre absent de ce volume (non lie, ou lie "\
                           u"sous un autre GUID)"
    if p.StorageType != StorageType.String:
        return None, None, u"parametre non textuel ({0})".format(p.StorageType)
    if p.IsReadOnly:
        return p, p.AsString(), u"parametre en lecture seule"
    return p, p.AsString(), None


ids = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Mass)
    .WhereElementIsNotElementType()
    .ToElementIds()
)
# R15 fait 8 : le collecteur est consomme AVANT toute resolution de propriete.

# Le passage 2 RELIT le parametre par son GUID : on ne conserve pas l'objet
# Parameter du passage 1.
prevues = []        # (eid, nom_famille, guid, avant, apres)
ignores = []        # (eid, nom_famille, motif)
inchanges = []      # (eid, nom_famille, guid, motif)
incoherences = []   # (eid, nom_famille, motif)
sans_parametre = {}  # guid -> [eid]

for eid in ids:
    el = doc.GetElement(eid)
    if el is None:
        continue

    nom_famille = None
    in_situ = None
    if isinstance(el, FamilyInstance):
        try:
            famille = el.Symbol.Family
            nom_famille = famille.Name
            in_situ = bool(famille.IsInPlace)
        except Exception as err:
            ignores.append((eid, None, u"identite illisible : {0}".format(err)))
            continue

    if in_situ is not True:
        ignores.append((eid, nom_famille, u"volume qui n'est pas in situ"))
        continue

    lu, refus = lire_nom(nom_famille)
    if lu is None:
        ignores.append((eid, nom_famille, u"nom hors motif : {0}".format(refus)))
        continue
    zone, etage, nature, cle = lu

    code = ref_batiment(zone, cle)
    if VALEURS_LONGUES:
        batiment = BATIMENT_DU_CODE.get(code)
        if batiment is None:
            ignores.append((eid, nom_famille,
                            u"code de batiment \"{0}\" absent de la table "
                            u"({1})".format(code, u", ".join(
                                sorted(BATIMENT_DU_CODE.keys())))))
            continue
    else:
        batiment = code

    motif = incoherence_etage_nature(etage, nature)
    if motif is not None:
        incoherences.append((eid, nom_famille, motif))

    # --- les quatre champs rafraichis a chaque passage --------------------
    for guid, valeur in ((GUID_ZONE, zone),
                         (GUID_ETAGE, etage),
                         (GUID_NATURE, nature),
                         (GUID_BATIMENT, batiment)):
        p, avant, refus_p = lire_texte(el, guid, eid)
        if p is None and refus_p is not None:
            sans_parametre.setdefault(guid, []).append(eid)
        if refus_p is not None:
            inchanges.append((eid, nom_famille, guid, refus_p))
            continue
        if texte(avant) == valeur:
            inchanges.append((eid, nom_famille, guid, u"deja a la valeur voulue"))
            continue
        prevues.append((eid, nom_famille, guid, texte(avant), valeur))

    # --- la cle de jointure : une seule fois, jamais regeneree ------------
    p, avant, refus_p = lire_texte(el, GUID_ID, eid)
    if p is None and refus_p is not None:
        sans_parametre.setdefault(GUID_ID, []).append(eid)
    if refus_p is not None:
        inchanges.append((eid, nom_famille, GUID_ID, refus_p))
    elif texte(avant).strip():
        inchanges.append((eid, nom_famille, GUID_ID,
                          u"deja renseigne - JAMAIS regenere"))
    else:
        prevues.append((eid, nom_famille, GUID_ID, texte(avant),
                        nouvel_identifiant()))

volumes_touches = sorted(set([id_de(e) for e, n, g, a, b in prevues]))

# --------------------------------------------------------------------------
# 2. Rapport du passage 1 - LECTURE SEULE
# --------------------------------------------------------------------------

out.print_md(u"# Parametres des volumes - passage 1, LECTURE SEULE")
out.print_md(
    u"Maquette : **{0}** &nbsp;|&nbsp; {1} &nbsp;|&nbsp; identite des "
    u"parametres **par GUID** &nbsp;|&nbsp; **rien n'est encore ecrit**".format(
        doc.Title,
        u"copie detachee" if detache else
        (u"collaborative NON detachee" if collaboratif else u"non collaborative"))
)
out.print_md(
    u"- **{0}** element(s) de categorie Volumes\n"
    u"- **{1}** ecriture(s) prevue(s) sur **{2}** volume(s)\n"
    u"- **{3}** champ(s) deja conforme(s) ou non modifiable(s)\n"
    u"- **{4}** volume(s) ignore(s)\n"
    u"- `REF_Batiment` ecrit en **{5}**".format(
        len(ids), len(prevues), len(volumes_touches), len(inchanges),
        len(ignores),
        u"valeurs longues (Junior, Middle, ...)" if VALEURS_LONGUES
        else u"codes courts (JU, MI, ...)")
)

out.print_md(u"## Ecritures prevues")
if not prevues:
    out.print_md(u"*Aucune. Rien a ecrire, la transaction ne sera pas ouverte.*")
else:
    lignes = [u"| Volume | Nom de famille | Parametre | Avant | Apres |",
              u"|---|---|---|---|---|"]
    for eid, nom, guid, avant, apres in prevues[:400]:
        lignes.append(u"| {0} | `{1}` | `{2}` | {3} | **{4}** |".format(
            lien_de(eid), texte(nom), NOM_DU_GUID.get(guid, guid),
            u"*(vide)*" if not avant else u"`{0}`".format(avant), apres))
    out.print_md(u"\n".join(lignes))
    if len(prevues) > 400:
        out.print_md(u"*... et {0} autre(s) ecriture(s), toutes au CSV du "
                     u"bouton Audit volumes.*".format(len(prevues) - 400))

out.print_md(u"## Volumes ignores - aucun ne sera modifie")
if not ignores:
    out.print_md(u"*Aucun.*")
else:
    for eid, nom, motif in ignores:
        out.print_md(u"- {0} `{1}` : {2}".format(lien_de(eid), texte(nom), motif))

if incoherences:
    out.print_md(u"## Etage et nature ne s'accordent pas - signale, PAS bloquant")
    out.print_md(
        u"Ces volumes sont ecrits quand meme : le nom fait foi, et un outil "
        u"n'arbitre pas a la place du modeleur. Mais l'un des deux segments "
        u"est faux, et c'est dans Revit que cela se corrige.")
    for eid, nom, motif in incoherences:
        out.print_md(u"- {0} `{1}` : {2}".format(lien_de(eid), texte(nom), motif))

if sans_parametre:
    out.print_md(u"## Parametres absents des volumes")
    for guid in sorted(sans_parametre.keys()):
        out.print_md(
            u"- `{0}` (GUID `{1}`) : absent de **{2}** volume(s). Le "
            u"parametre partage est-il lie a la categorie Volumes, en "
            u"instance, et charge depuis le BON fichier de parametres "
            u"partages ? Un champ de meme nom mais d'un autre GUID n'est pas "
            u"ce parametre.".format(
                NOM_DU_GUID.get(guid, u"?"), guid, len(sans_parametre[guid]))
        )

if not prevues:
    out.print_md(
        u"---\n**Fin.** Aucune transaction n'a ete ouverte, rien n'a ete "
        u"ecrit dans la maquette."
    )
    script.exit()

# --------------------------------------------------------------------------
# 3. Confirmation explicite
# --------------------------------------------------------------------------

dialogue = TaskDialog(u"bimflow - MAJ des parametres de volumes")
dialogue.MainInstruction = u"Ecrire {0} valeur(s) sur {1} volume(s) ?".format(
    len(prevues), len(volumes_touches))
dialogue.MainContent = (
    u"Maquette : {0}\n"
    u"Fichier : {1}\n\n"
    u"Le detail est affiche dans la fenetre de sortie (valeur avant, valeur "
    u"apres).\n\n"
    u"Un seul commit pour tout le lot : si une ecriture echoue, TOUT est "
    u"annule.\n\n"
    u"Script NON EPROUVE. Verifier le resultat en nomenclature de Volumes, "
    u"pas sur ce que le script affichera.".format(
        doc.Title, doc.PathName or u"(jamais enregistree)")
)
dialogue.CommonButtons = (TaskDialogCommonButtons.Yes |
                          TaskDialogCommonButtons.No)
dialogue.DefaultButton = TaskDialogResult.No

if dialogue.Show() != TaskDialogResult.Yes:
    out.print_md(
        u"---\n**Annule par l'utilisateur.** Aucune transaction n'a ete "
        u"ouverte, rien n'a ete ecrit."
    )
    script.exit()

# --------------------------------------------------------------------------
# 4. Passage 2 - ECRITURE : une transaction, un commit, tout ou rien
# --------------------------------------------------------------------------

ecrits = 0
echec = None

transaction = Transaction(doc, u"bimflow - parametres des volumes de zone")
if transaction.Start() != TransactionStatus.Started:
    forms.alert(
        u"Revit a refuse d'ouvrir la transaction. Rien n'a ete ecrit.",
        exitscript=True,
    )

try:
    for eid, nom, guid, avant, apres in prevues:
        # le compteur AVANT l'appel qui peut lever : un echec ne doit pas
        # rapporter "0 ecrit" alors que des valeurs sont passees
        ecrits += 1
        el = doc.GetElement(eid)
        if el is None:
            raise Exception(
                u"volume {0} introuvable au moment d'ecrire".format(id_de(eid)))
        p = parametre_par_guid(el, guid)
        if p is None:
            raise Exception(
                u"{0} (GUID {1}) introuvable sur le volume {2} au moment "
                u"d'ecrire".format(NOM_DU_GUID.get(guid, u"?"), guid,
                                   id_de(eid)))
        if not p.Set(apres):
            raise Exception(
                u"Set() a rendu False sur {0} du volume {1} (`{2}`)".format(
                    NOM_DU_GUID.get(guid, guid), id_de(eid), texte(nom)))
except Exception as err:
    echec = err

if echec is None:
    etat = transaction.Commit()
    if etat != TransactionStatus.Committed:
        echec = u"Commit refuse par Revit (etat : {0})".format(etat)
        ecrits = 0
else:
    transaction.RollBack()
    ecrits = 0

# --------------------------------------------------------------------------
# 5. Rapport final
# --------------------------------------------------------------------------

out.print_md(u"---")
out.print_md(u"# Passage 2 - ecriture")

if echec is not None:
    out.print_md(
        u"## ECHEC - tout a ete annule\n"
        u"`{0}`\n\n"
        u"**La maquette est dans l'etat ou elle etait avant le clic** : la "
        u"transaction a ete annulee en bloc, aucune valeur n'a survecu. "
        u"A diagnostiquer avant de relancer.".format(echec)
    )
    script.exit()

out.print_md(
    u"| Resultat | Nombre | Motif |\n|---|---:|---|\n"
    u"| **Ecrits** | {0} | valeurs deduites du nom de famille |\n"
    u"| **Inchanges** | {1} | deja a la valeur voulue, deja renseignes "
    u"(`REF_Id`), ou non modifiables |\n"
    u"| **Ignores** | {2} | nom hors motif, code de batiment inconnu, ou "
    u"volume non in situ |".format(len(prevues), len(inchanges), len(ignores))
)
out.print_md(
    u"**{0}** valeur(s) ecrite(s) sur **{1}** volume(s), en un seul commit.".format(
        ecrits, len(volumes_touches))
)
if incoherences:
    out.print_md(
        u"**{0} volume(s) dont l'etage et la nature ne s'accordent pas** - "
        u"ecrits, et listes plus haut.".format(len(incoherences)))
out.print_md(
    u"> **Ce que ce resultat ne prouve pas.** Le script rapporte ce que "
    u"l'API lui a rendu, pas ce que la maquette contient. La verification "
    u"se fait en **nomenclature de Volumes** : colonnes `REF_Zone`, "
    u"`REF_Etage`, `REF_Batiment`, `REF_Id`, `CLS_Nature_volume`.\n\n"
    u"> `REF_Id` n'est ecrit qu'une fois. Un volume renomme garde son "
    u"identifiant : c'est la cle de jointure vers Ivion.\n\n"
    u"> `CLS_Usage` n'est jamais touche par ce script - saisie metier."
)
