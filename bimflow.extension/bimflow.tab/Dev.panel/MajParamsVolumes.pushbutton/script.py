# -*- coding: utf-8 -*-
"""maj_params_volumes - Parametres des volumes de zone, deduits de leur NOM.

Ecrit le 2026-09-22.

OBJET. Lire le nom de famille de chaque volume in situ et en deduire les
parametres de referencement. Ne touche JAMAIS a la geometrie, ni au nom de
famille, ni a CLS_Usage.

#############################################################################
# STATUT : NON EPROUVE - JAMAIS EXECUTE DANS REVIT au 2026-09-22.           #
# Ce script ECRIT dans le modele. Essai sur COPIE DETACHEE uniquement.      #
# Le succes affiche ici NE PROUVE RIEN : la verification se fait en         #
# nomenclature de Volumes, dans Revit.                                      #
#############################################################################

MOTIF DE NOM (arbitrage Bruno du 2026-09-22) :

    VOL__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>
    ex. VOL__JU_Bj-Fj-1j-5j__FLOOR_3__ETAGE

Separateur : DOUBLE underscore. Un underscore simple appartient au segment
(JU_Bj-Fj-1j-5j, FLOOR_3, ENTRE_TOIT) et ne se decoupe jamais. Le 4e segment
porte EXACTEMENT une valeur de la liste fermee - aucune table de
correspondance n'existe, et c'est le but. Les volumes dont il vaut encore
"0" sont hors motif : le bouton Renommer volumes les traite d'abord.

CE QUI EST ECRIT, volume par volume :
    REF_Zone           segment 1, rafraichi a chaque passage
    REF_Etage          segment 2, rafraichi a chaque passage
    REF_Batiment       table BATIMENT_DU_PREFIXE ci-dessous, sur le prefixe
                       de REF_Zone avant le premier underscore simple
    REF_Id             uuid4, ecrit UNE SEULE FOIS si le champ est vide.
                       JAMAIS reecrit, JAMAIS regenere : c'est la cle de
                       jointure vers Ivion, elle doit survivre aux
                       renommages.
    CLS_Nature_volume  segment 4, recopie TEL QUEL, si le champ est vide ;
                       deja renseigne = laisse tel quel et signale
    CLS_Usage          jamais ecrit (saisie metier)

CONTROLE SIGNALE, JAMAIS BLOQUANT : la redondance entre le 3e et le 4e
segment sert de garde-fou. Un REF_Etage ROOF dont la nature n'est pas
TOITURE, ou une nature TOITURE ailleurs qu'a ROOF, sort au rapport - le
volume est ecrit quand meme, parce que le nom fait foi et qu'un outil
n'arbitre pas a la place du modeleur.

GARDE-FOUS :
  - passage 1 en LECTURE SEULE : le tableau des ecritures prevues (volume,
    parametre, valeur avant, valeur apres) s'affiche AVANT toute transaction ;
  - la Transaction ne s'ouvre qu'apres confirmation explicite, par un
    TaskDialog qui nomme la maquette ;
  - UN SEUL commit pour tout le lot, annulation complete (RollBack) si une
    seule ecriture echoue - aucun resultat partiel ;
  - un volume dont le nom ne respecte pas le motif n'est pas modifie du tout,
    et il est liste ;
  - un prefixe de zone absent de la table n'est pas devine : le volume entier
    est ignore et liste.

bimflow - volumes de zone, mode ecriture - Keovia Solutions inc.
"""

__title__ = "MAJ params\nvolumes"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES - a ajuster ici, pas dans le corps du script
# --------------------------------------------------------------------------

# Prefixe de REF_Zone (avant le premier underscore simple) -> REF_Batiment.
# Un prefixe absent de cette table n'est JAMAIS devine.
# CINQ prefixes : la maquette en porte cinq sur ses 23 niveaux. SE avait ete
# oublie le 2026-09-22, et SE_office s'en trouvait ignore a tort.
BATIMENT_DU_PREFIXE = {
    "JU": "Junior",
    "MI": "Middle",
    "SC": "Senior_Central",
    "SE": "Senior_East",
    "EXT": "SITE",
}

NOM_ZONE = "REF_Zone"
NOM_ETAGE = "REF_Etage"
NOM_BATIMENT = "REF_Batiment"
NOM_ID = "REF_Id"
NOM_NATURE = "CLS_Nature_volume"

# Une maquette collaborative doit etre traitee sur une COPIE DETACHEE (R17).
AUTORISER_NON_DETACHE = False

# --------------------------------------------------------------------------

from pyrevit import revit, script, forms

# Le decoupage du nom vit dans UN seul module, partage avec le bouton d'audit
# et avec tools/sitemodel/audit_to_zones.py (dossier lib\ de l'extension,
# ajoute au chemin par pyRevit).
try:
    from bimflow_noms import (
        lire as lire_nom,
        batiment_du as batiment_de_zone,
        incoherence_etage_nature,
    )
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


# --------------------------------------------------------------------------
# 0. Garde-fous : document, copie detachee
# --------------------------------------------------------------------------

if doc.IsFamilyDocument:
    forms.alert(u"Document famille : rien a traiter.", exitscript=True)

collaboratif = bool(doc.IsWorkshared)
detache = None
try:
    detache = bool(doc.IsDetached)
except Exception:
    detache = None

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
# 1. Lecture du motif de nom
# --------------------------------------------------------------------------


# Le decoupage lui-meme est dans bimflow_noms (lire_nom, batiment_de_zone) :
# lire_nom est la lecture STRICTE - au moindre defaut de nom, elle refuse, et
# c'est bien ce qu'il faut a un outil qui ecrit.


# --------------------------------------------------------------------------
# 2. Passage 1 - LECTURE SEULE : ce qui serait ecrit
# --------------------------------------------------------------------------

ids = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Mass)
    .WhereElementIsNotElementType()
    .ToElementIds()
)
# R15 fait 8 : le collecteur est consomme AVANT toute resolution de propriete.

# Le passage 2 RELIT le parametre par son nom, il ne conserve pas l'objet
# Parameter du passage 1 : on ne depend pas de sa duree de vie.
prevues = []        # (eid, nom_famille, nom_param, avant, apres)
ignores = []        # (eid, nom_famille, motif)
inchanges = []      # (eid, nom_famille, nom_param, motif)
nature_deja = []    # (eid, nom_famille, valeur en place)
incoherences = []   # (eid, nom_famille, motif) - signale, jamais bloquant
sans_parametre = {}  # nom de parametre -> [eid]


def noter_absence(nom_param, eid):
    sans_parametre.setdefault(nom_param, []).append(eid)


def lire_texte(el, nom_param, eid):
    """(parametre, valeur ou None, motif de refus ou None)."""
    p = el.LookupParameter(nom_param)
    if p is None:
        noter_absence(nom_param, eid)
        return None, None, u"parametre absent de ce volume (non lie ?)"
    if p.StorageType != StorageType.String:
        return None, None, u"parametre non textuel ({0})".format(p.StorageType)
    if p.IsReadOnly:
        return p, p.AsString(), u"parametre en lecture seule"
    return p, p.AsString(), None


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
    zone, etage, nature = lu

    batiment, refus_bat = batiment_de_zone(zone, BATIMENT_DU_PREFIXE)
    if batiment is None:
        ignores.append((eid, nom_famille, refus_bat))
        continue

    # --- garde-fou : le 3e et le 4e segment doivent s'accorder -------------
    incoherence = incoherence_etage_nature(etage, nature)
    if incoherence is not None:
        incoherences.append((eid, nom_famille, incoherence))

    # --- les trois champs rafraichis a chaque passage ---------------------
    for nom_param, valeur in ((NOM_ZONE, zone),
                              (NOM_ETAGE, etage),
                              (NOM_BATIMENT, batiment)):
        p, avant, refus_p = lire_texte(el, nom_param, eid)
        if refus_p is not None:
            inchanges.append((eid, nom_famille, nom_param, refus_p))
            continue
        if texte(avant) == valeur:
            inchanges.append((eid, nom_famille, nom_param, u"deja a la valeur voulue"))
            continue
        prevues.append((eid, nom_famille, nom_param, texte(avant), valeur))

    # --- la cle de jointure : une seule fois, jamais regeneree ------------
    p, avant, refus_p = lire_texte(el, NOM_ID, eid)
    if refus_p is not None:
        inchanges.append((eid, nom_famille, NOM_ID, refus_p))
    elif texte(avant).strip():
        inchanges.append((eid, nom_famille, NOM_ID,
                          u"deja renseigne - JAMAIS regenere"))
    else:
        prevues.append((eid, nom_famille, NOM_ID, texte(avant),
                        nouvel_identifiant()))

    # --- la nature : seulement si vide ------------------------------------
    p, avant, refus_p = lire_texte(el, NOM_NATURE, eid)
    if refus_p is not None:
        inchanges.append((eid, nom_famille, NOM_NATURE, refus_p))
    elif texte(avant).strip():
        nature_deja.append((eid, nom_famille, texte(avant)))
        inchanges.append((eid, nom_famille, NOM_NATURE,
                          u"deja renseigne (\"{0}\") - laisse tel quel".format(
                              texte(avant))))
    else:
        # recopie TELLE QUELLE du 4e segment : aucune correspondance, aucune
        # traduction - c'est ce qui rend le nom lisible sans decodeur
        prevues.append((eid, nom_famille, NOM_NATURE, texte(avant), nature))

volumes_touches = sorted(set([id_de(e) for e, n, p, a, b in prevues]))

# --------------------------------------------------------------------------
# 3. Rapport du passage 1
# --------------------------------------------------------------------------

out.print_md(u"# Parametres des volumes - passage 1, LECTURE SEULE")
out.print_md(
    u"Maquette : **{0}** &nbsp;|&nbsp; {1} &nbsp;|&nbsp; **rien n'est encore "
    u"ecrit**".format(
        doc.Title,
        u"copie detachee" if detache else
        (u"collaborative NON detachee" if collaboratif else u"non collaborative"))
)
out.print_md(
    u"- **{0}** element(s) de categorie Volumes\n"
    u"- **{1}** ecriture(s) prevue(s) sur **{2}** volume(s)\n"
    u"- **{3}** champ(s) deja conforme(s) ou non modifiable(s)\n"
    u"- **{4}** volume(s) ignore(s)".format(
        len(ids), len(prevues), len(volumes_touches), len(inchanges),
        len(ignores))
)

out.print_md(u"## Ecritures prevues")
if not prevues:
    out.print_md(u"*Aucune. Rien a ecrire, la transaction ne sera pas ouverte.*")
else:
    lignes = [u"| Volume | Nom de famille | Parametre | Avant | Apres |",
              u"|---|---|---|---|---|"]
    for eid, nom, nom_param, avant, apres in prevues:
        try:
            lien = out.linkify(eid)
        except Exception:
            lien = u"`{0}`".format(id_de(eid))
        lignes.append(u"| {0} | `{1}` | `{2}` | {3} | **{4}** |".format(
            lien, texte(nom), nom_param,
            u"*(vide)*" if not avant else u"`{0}`".format(avant), apres))
    out.print_md(u"\n".join(lignes))

out.print_md(u"## Volumes ignores - aucun ne sera modifie")
if not ignores:
    out.print_md(u"*Aucun.*")
else:
    for eid, nom, motif in ignores:
        try:
            lien = out.linkify(eid)
        except Exception:
            lien = u"`{0}`".format(id_de(eid))
        out.print_md(u"- {0} `{1}` : {2}".format(lien, texte(nom), motif))

if incoherences:
    out.print_md(
        u"## Etage et nature ne s'accordent pas - signale, PAS bloquant")
    out.print_md(
        u"Ces volumes sont ecrits quand meme : le nom fait foi, et un outil "
        u"n'arbitre pas a la place du modeleur. Mais l'un des deux segments "
        u"est faux, et c'est dans Revit que cela se corrige.")
    for eid, nom, motif in incoherences:
        try:
            lien = out.linkify(eid)
        except Exception:
            lien = u"`{0}`".format(id_de(eid))
        out.print_md(u"- {0} `{1}` : {2}".format(lien, texte(nom), motif))

if nature_deja:
    out.print_md(u"## `CLS_Nature_volume` deja renseigne - laisse tel quel")
    for eid, nom, valeur in nature_deja:
        out.print_md(u"- `{0}` `{1}` : **`{2}`**".format(
            id_de(eid), texte(nom), valeur))

if sans_parametre:
    out.print_md(u"## Parametres absents des volumes")
    for nom_param in sorted(sans_parametre.keys()):
        liste = sans_parametre[nom_param]
        out.print_md(
            u"- `{0}` : absent de **{1}** volume(s). Le parametre partage "
            u"est-il lie a la categorie Volumes, en instance ?".format(
                nom_param, len(liste))
        )

if not prevues:
    out.print_md(
        u"---\n**Fin.** Aucune transaction n'a ete ouverte, rien n'a ete "
        u"ecrit dans la maquette."
    )
    script.exit()

# --------------------------------------------------------------------------
# 4. Confirmation explicite - la transaction n'existe pas avant ce oui
# --------------------------------------------------------------------------

dialogue = TaskDialog(u"bimflow - MAJ des parametres de volumes")
dialogue.MainInstruction = u"Ecrire {0} valeur(s) sur {1} volume(s) ?".format(
    len(prevues), len(volumes_touches))
dialogue.MainContent = (
    u"Maquette : {0}\n"
    u"Fichier : {1}\n\n"
    u"Le detail des {2} ecritures est affiche dans la fenetre de sortie "
    u"(valeur avant, valeur apres).\n\n"
    u"Un seul commit pour tout le lot : si une ecriture echoue, TOUT est "
    u"annule.\n\n"
    u"Script NON EPROUVE. Verifier le resultat en nomenclature de Volumes, "
    u"pas sur ce que le script affichera.".format(
        doc.Title, doc.PathName or u"(jamais enregistree)", len(prevues))
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
# 5. Passage 2 - ECRITURE : une transaction, un commit, tout ou rien
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
    for eid, nom, nom_param, avant, apres in prevues:
        # le compteur AVANT l'appel qui peut lever : un echec ne doit pas
        # rapporter "0 ecrit" alors que des valeurs sont passees
        ecrits += 1
        el = doc.GetElement(eid)
        if el is None:
            raise Exception(
                u"volume {0} introuvable au moment d'ecrire".format(id_de(eid)))
        p = el.LookupParameter(nom_param)
        if p is None:
            raise Exception(
                u"{0} introuvable sur le volume {1} (`{2}`) au moment "
                u"d'ecrire".format(nom_param, id_de(eid), texte(nom)))
        if not p.Set(apres):
            raise Exception(
                u"Set() a rendu False sur {0} du volume {1} (`{2}`)".format(
                    nom_param, id_de(eid), texte(nom)))
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
# 6. Rapport final
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
    u"(`REF_Id`, `CLS_Nature_volume`), ou non modifiables |\n"
    u"| **Ignores** | {2} | nom hors motif, prefixe de zone inconnu, ou "
    u"volume non in situ |".format(len(prevues), len(inchanges), len(ignores))
)
out.print_md(
    u"**{0}** valeur(s) ecrite(s) sur **{1}** volume(s), en un seul commit.".format(
        ecrits, len(volumes_touches))
)
if incoherences:
    out.print_md(
        u"**{0} volume(s) dont l'etage et la nature ne s'accordent pas** - "
        u"ecrits, et listes plus haut. A reprendre dans Revit : c'est le nom "
        u"qu'il faut corriger, puis relancer ce bouton.".format(
            len(incoherences))
    )

out.print_md(
    u"> **Ce que ce resultat ne prouve pas.** Le script rapporte ce que "
    u"l'API lui a rendu, pas ce que la maquette contient. La verification "
    u"se fait en **nomenclature de Volumes** : colonnes `REF_Zone`, "
    u"`REF_Etage`, `REF_Batiment`, `REF_Id`, `CLS_Nature_volume`.\n\n"
    u"> `REF_Id` n'est ecrit qu'une fois. Un volume renomme garde son "
    u"identifiant : c'est la cle de jointure vers Ivion.\n\n"
    u"> `CLS_Usage` n'est jamais touche par ce script - c'est une saisie "
    u"metier."
)
