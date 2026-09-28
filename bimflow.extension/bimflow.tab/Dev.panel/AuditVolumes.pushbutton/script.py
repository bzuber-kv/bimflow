# -*- coding: utf-8 -*-
"""audit_volumes_zone - Audit des volumes de zone.

Ecrit le 2026-09-22.

OBJET. Extraire l'identite et la geometrie de tous les volumes de la
maquette courante (categorie Volumes, OST_Mass) vers un JSON, pour analyse
hors Revit : controle du nommage, alimentation du decoupage site_model
Ivion, surfaces par niveau.

#############################################################################
# STATUT : EPROUVE - quatre executions dans Revit, du 2026-09-22 au         #
# 2026-09-24. La derniere : 202 volumes, 53 zones, quatre batiments. La     #
# sortie alimente la chaine site_model (tools/sitemodel), qui en tire       #
# 202/202 contours reconstruits, une partition en plan fermee, et un        #
# site_model Ivion de 50 BUILDING accepte par tous ses controles.           #
# L'audit sert aussi de VERIFICATEUR des deux boutons d'ecriture : relance  #
# apres eux, il dit ce que la maquette porte vraiment - un rapport de       #
# script, lui, ne dit que ce que le script croit avoir fait. C'est ce role  #
# qu'il a tenu le 2026-09-24 sur la maquette CENTRALE thestudy_A_VOL, entre #
# chaque palier, jusqu'a la mise a jour du site_model dans Ivion.           #
#############################################################################

LECTURE SEULE - aucune transaction n'est ouverte, rien n'est ecrit dans la
maquette. La seule ecriture est le fichier JSON, hors du modele.

CE QU'IL VERIFIE EN PLUS DEPUIS LE 2026-09-25 - les contraintes du
site_model Ivion, anticipees DANS REVIT :
  superposition 3D de deux volumes .. C1 (interieurs disjoints) et C6
  vide entre deux tranches d'une colonne .. C2 (pile contigue)
  tranche de moins d'un metre ....... C10
Ces trois-la se corrigent sur le volume ; les decouvrir en aval, dans la
chaine, c'est refaire un tour complet pour rien. La fermeture de la
PARTITION EN PLAN, elle, reste en aval : elle demande de vraies operations
de polygones (shapely, indisponible sous IronPython).

CAR_SURFACE_SOL, DEPUIS LE 2026-09-28 - NON EPROUVE DANS REVIT. Chaque
volume voit son contour reconstruit ICI, par lib\\bimflow_contour - le code
dont le bouton MajParamsVolumes tire la valeur qu'il ecrit - et la valeur
portee, lue par GUID, doit s'en ecarter de moins de 0,01 m2. Les volumes a
face basse inclinee sont signales, avec l'ecart entre leur face basse et sa
projection. La lecture des faces a quitte ce fichier pour
lib\\bimflow_geometrie, sans changement : le JSON produit est le meme, plus
la cle surface_sol de chaque volume.

LE RAPPORT SE SAUVE, depuis le 2026-09-25, au meme endroit et sous le meme
nom de base que le JSON, en .html. Jusque-la, tout ce qui s'affichait mourait
avec la fenetre : le JSON porte la geometrie, pas le diagnostic. Or c'est le
diagnostic qu'on relit.

MAQUETTE CENTRALE. Depuis le 2026-09-24, l'audit ne refuse plus de tourner
sur une maquette collaborative non detachee. Ce qu'il signale alors n'est
pas un risque d'ecriture - il n'ecrit pas - mais un risque de VERITE : il
decrit l'etat SYNCHRONISE a l'instant de la lecture, le travail non
synchronise des autres n'y est pas, et le JSON portera pourtant une date qui
fera autorite. La confirmation nomme le fichier et annonce le nombre de
volumes vus (ACT-052 (2)) ; le constat part aussi dans le JSON.

HYPOTHESES POSEES A L'ECRITURE. Les executions ont prouve que le script
tourne et que les contours sont reconstructibles ; elles n'ont pas statue
une a une sur les quatre hypotheses ci-dessous, qui se lisent dans le
JSON produit (valeurs nulles, incoherence_hote, methode de boucle). Aucune
n'arrete le script : chacune rend None ou une erreur consignee.
  1. MASS_GROSS_VOLUME / MASS_GROSS_SURFACE_AREA / MASS_GROSS_AREA - noms de
     BuiltInParameter supposes, lus par getattr. Absents : les trois valeurs
     valent null. Recoupement disponible : volume_solides_m3, somme des
     volumes des solides lus.
  2. Geometrie d'un plancher de volume (MassLevelData) - forme inconnue,
     face libre ou solide mince. Les deux cas sont traites ; le compte des
     faces lues est publie (nb_faces_lues).
  3. OwningMassId - propriete supposee presente sur le plancher de volume.
     Lue par getattr, recoupee par MassInstanceUtils.GetMassLevelDataIds vu
     depuis le volume ; un desaccord sort en incoherence_hote.
  4. Boucle exterieure d'une face - reconnue a son sens trigonometrique
     autour de la normale (documente, non verifie). A defaut, la plus longue
     est retenue et la methode employee est publiee.

Motif de nom attendu - quatre segments separes par un DOUBLE underscore,
un cinquieme optionnel :
    VOL_nnn__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>[__<cle>]
    ex. VOL_007__JU_Bj-Fj_1j-5j__FLOOR_3__ETAGE
Le decoupage se fait sur "__" et doit rendre 4 ou 5 segments. Un
underscore simple a l'interieur d'un segment (JU_Bj-Fj_1j-5j, FLOOR_2) n'est
jamais un separateur. Le 4e segment porte EXACTEMENT une valeur de la liste
fermee de CLS_Nature_volume (arbitrage Bruno du 2026-09-22) : ETAGE,
TOITURE, ENTRETOIT, EXTERIEUR, ENVELOPPE. Un 5e segment optionnel porte une
cle (sup, JU, MI, SC, SE). Les noms qui ne sont pas au motif relevent du
bouton Renommer volumes. Tout est signale, rien n'est
corrige - cet outil ne touche a rien.

Ce que le JSON contient :
  - en-tete : maquette, unites, repere, points de base, niveaux ;
  - volumes : identite, parametres REF_ / CLS_ / CAR_ (meme vides), boite
    englobante, volume et surface bruts, solides et faces classees,
    controle surface_sol ;
  - mass_floors : planchers de volume EXISTANTS (aucun n'est cree), avec
    volume hote, niveau et contour XY de la face superieure.

Repere : toutes les coordonnees sont celles de la GEOMETRIE (coordonnees
internes du modele). Les altitudes ne passent jamais par Level.Elevation -
sur The Study, Level.Elevation et la geometrie different de 29 065 mm
(R16 §1.1). Les niveaux sont publies avec les deux lectures, pour controle.

bimflow - volumes de zone, audit - Keovia Solutions inc.
v1 - 2026-09-22 : premiere execution, 30 volumes.
v2 - 2026-09-24 : motif etendu (numero, cle), 202 volumes.
v3 - 2026-09-28 : controle CAR_Surface_sol ; lecture des faces dans lib\\.
"""

__title__ = "Audit\nvolumes zone"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES DE L'AUDIT - a ajuster ici, pas dans le corps du script
# --------------------------------------------------------------------------

# Parametres releves sur chaque volume (instance ET type), meme vides.
PREFIXES_PARAMETRES = ("REF_", "CLS_", "CAR_")

# Classement des faces (NZ_HORIZONTALE, NZ_VERTICALE), tolerance des aretes
# verticales (TOL_SEGMENT_MM) et arrondi (DECIMALES_MM) : lib\bimflow_geometrie,
# depuis le 2026-09-28 - le bouton d'ecriture lit la geometrie avec eux.

# Controle CAR_Surface_sol : ecart admis entre la valeur portee par le volume
# et l'aire de son contour reconstruit ICI, en m2.
TOL_SURFACE_SOL_M2 = 0.01

# --------------------------------------------------------------------------
# CONTROLES AMONT DES CONTRAINTES IVION - tolerances, en millimetres
#
# Ces trois controles existent pour une seule raison : ce que la chaine
# site_model refusera plus tard se corrige DANS REVIT, pas dans un JSON. Les
# decouvrir ici, c'est les voir a l'endroit ou on les repare.
# --------------------------------------------------------------------------

# Deux volumes qui se TOUCHENT ne se recouvrent pas. En deca de ce jeu, un
# recoupement de boites est un contact de faces mitoyennes, pas un defaut.
TOL_CONTACT_MM = 1.0

# Jeu admis entre deux tranches consecutives d'une meme colonne (C2). Au-dela,
# c'est un vide : dans Ivion, un visiteur ne peut pas y etre.
TOL_JOINT_MM = 1.0

# Volume commun en deca duquel on ne signale pas : bruit de calcul booleen.
TOL_VOLUME_COMMUN_M3 = 0.001

# C10 : une tranche de moins d'un metre n'est pas un etage visitable.
HAUTEUR_MINI_MM = 1000.0

# Une colonne est un groupe de volumes qui partagent la meme emprise en plan.
# Faute de shapely sous IronPython, l'emprise est approchee par la BOITE en
# plan, arrondie a ce pas. Deux zones de meme boite mais de forme differente
# seraient groupees a tort - le cas ne s'est pas presente, et le controle R1
# de la chaine, lui, compare les vrais contours.
PAS_COLONNE_MM = 10.0

# Le drapeau AUTORISER_NON_DETACHE a disparu le 2026-09-24 : l'audit ne
# refuse plus la maquette centrale, il la signale et fait confirmer
# (lib\bimflow_maquette.py pour l'etat du document).

# Le JSON ne s'ecrit ni dans OneDrive ni sous WORK (comparaison en minuscules).
FRAGMENTS_INTERDITS = ("onedrive", "\\work\\")

# --------------------------------------------------------------------------

import io
import json
import datetime
from collections import OrderedDict

from pyrevit import revit, script, forms

# Le decoupage du nom vit dans UN seul module, partage avec le bouton
# d'ecriture et avec tools/sitemodel/audit_to_zones.py (dossier lib\ de
# l'extension, ajoute au chemin par pyRevit).
try:
    from bimflow_noms import (
        decouper as decouper_nom,
        NATURE_A_RENOMMER,
        NATURES,
    )
    from bimflow_maquette import etat as etat_maquette
    # La lecture des faces et la reconstruction du contour vivent dans lib\
    # depuis le 2026-09-28 : le bouton MajParamsVolumes ecrit CAR_Surface_sol
    # avec ce meme code, et cet audit la controle.
    from bimflow_geometrie import (
        NZ_HORIZONTALE, NZ_VERTICALE, TOL_SEGMENT_MM,
        mm, rmm, m2, m3, interne_vers_m2,
        parcourir_geometrie, boucle_exterieure, anneau_xy, faces_du_volume,
        parametre_par_guid, est_une_surface, GUID_SURFACE_SOL,
    )
    from bimflow_contour import contour_du_volume, face_basse
except ImportError:
    from pyrevit import forms as _formulaires
    _formulaires.alert(
        u"Modules partages bimflow_noms / bimflow_maquette / "
        u"bimflow_geometrie / bimflow_contour introuvables.\n\n"
        u"Ils doivent se trouver dans bimflow.extension\\lib\\. Sans eux, ni "
        u"le decoupage des noms de volumes ni la lecture de leur geometrie "
        u"ne sont disponibles, et ce script ne s'execute pas.",
        exitscript=True,
    )

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FilteredWorksetCollector,
    WorksetKind,
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FamilyInstance,
    Level,
    PlanarFace,
    StorageType,
    XYZ,
)
from Autodesk.Revit.UI import (TaskDialog, TaskDialogCommonButtons,
                               TaskDialogResult)

# Intersection REELLE de deux solides, pour les controles amont. Absente sur
# une version d'API qui ne l'offrirait pas : le controle se declare alors
# indisponible plutot que de rendre un resultat approche sans le dire.
try:
    from Autodesk.Revit.DB import (BooleanOperationsUtils,
                                   BooleanOperationsType)
except ImportError:
    BooleanOperationsUtils = None
    BooleanOperationsType = None

doc = revit.doc
out = script.get_output()

# --------------------------------------------------------------------------
# Petits outils
# --------------------------------------------------------------------------

def id_de(eid):
    """R15 fait 7 : ElementId.Value en Revit 2024+, .IntegerValue avant."""
    if eid is None:
        return -1
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


def texte(valeur):
    if valeur is None:
        return None
    return u"{0}".format(valeur)


# --------------------------------------------------------------------------
# 0. Garde-fous : document, maquette centrale, sous-projets fermes
# --------------------------------------------------------------------------

if doc.IsFamilyDocument:
    forms.alert(u"Document famille : rien a auditer.", exitscript=True)

# IsWorkshared reste True apres un detachement conservant les sous-projets :
# c'est IsDetached qui tranche. La regle vit dans lib\bimflow_maquette.py.
collaboratif, detache, CENTRALE = etat_maquette(doc)

avertissements = []

# MAQUETTE CENTRALE. Ce bloc etait un REFUS jusqu'au 2026-09-24. L'audit ne
# modifie rien : ce qu'il faut signaler ici n'est pas un risque d'ecriture,
# c'est un risque de VERITE. Un audit de la maquette centrale decrit ce
# qu'elle contient a cet instant - le travail non synchronise des autres n'y
# est pas, et le fichier produit portera pourtant une date qui fera autorite.
if CENTRALE:
    nb_volumes_vus = 0
    try:
        nb_volumes_vus = len(list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Mass)
            .WhereElementIsNotElementType()
            .ToElementIds()
        ))
    except Exception:
        nb_volumes_vus = -1

    dialogue_centrale = TaskDialog(u"bimflow - MAQUETTE CENTRALE")
    dialogue_centrale.MainInstruction = u"Auditer la maquette de PRODUCTION ?"
    dialogue_centrale.MainContent = (
        u"Ce n'est PAS une copie detachee.\n\n"
        u"Maquette : {0}\n"
        u"Fichier : {1}\n\n"
        u"Volumes vus d'ici : {2}\n\n"
        u"L'audit NE MODIFIE RIEN - aucune transaction n'est ouverte. Mais il "
        u"decrira la maquette telle qu'elle est a cet instant : ce que les "
        u"autres n'ont pas encore synchronise n'y sera pas, et le JSON "
        u"produit portera une date qui fera autorite.\n\n"
        u"Recharger les derniers enregistrements avant de continuer.".format(
            doc.Title,
            doc.PathName or u"(jamais enregistree)",
            nb_volumes_vus if nb_volumes_vus >= 0 else u"(illisible)")
    )
    dialogue_centrale.CommonButtons = (TaskDialogCommonButtons.Yes |
                                       TaskDialogCommonButtons.No)
    dialogue_centrale.DefaultButton = TaskDialogResult.No
    if dialogue_centrale.Show() != TaskDialogResult.Yes:
        forms.alert(u"Audit annule. Rien n'a ete lu ni ecrit.", exitscript=True)

    avertissements.append(
        u"**Audit de la MAQUETTE CENTRALE**, pas d'une copie detachee : il "
        u"decrit l'etat synchronise a l'instant de la lecture. Le travail non "
        u"synchronise des autres utilisateurs n'y figure pas."
    )

if collaboratif:
    try:
        fermes = [
            w.Name for w in
            FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
            if not w.IsOpen
        ]
        if fermes:
            avertissements.append(
                u"**{0} sous-projet(s) ferme(s)** : leurs volumes ne sont pas "
                u"charges et manqueraient SANS LE DIRE - {1}".format(
                    len(fermes), u", ".join(fermes))
            )
    except Exception as err:
        avertissements.append(u"Etat des sous-projets illisible : {0}".format(err))

if "VOL" not in doc.Title.upper():
    avertissements.append(
        u"Le titre de la maquette (`{0}`) ne contient pas `VOL` : est-ce bien "
        u"la maquette des volumes de zone ?".format(doc.Title)
    )

table_ss_projets = doc.GetWorksetTable() if collaboratif else None


def nom_sous_projet(el):
    if table_ss_projets is None:
        return None
    try:
        return table_ss_projets.GetWorkset(el.WorksetId).Name
    except Exception:
        return None


# --------------------------------------------------------------------------
# 1. En-tete : repere, points de base, niveaux
# --------------------------------------------------------------------------

def point_json(p):
    if p is None:
        return None
    return OrderedDict([("x", rmm(p.X)), ("y", rmm(p.Y)), ("z", rmm(p.Z))])


def lire_point_de_base(methode):
    """BasePoint.GetProjectBasePoint / GetSurveyPoint (Revit 2021+)."""
    try:
        from Autodesk.Revit.DB import BasePoint
        bp = getattr(BasePoint, methode)(doc)
    except Exception as err:
        return OrderedDict([("erreur", texte(err))])
    if bp is None:
        return None
    resultat = OrderedDict()
    try:
        resultat["id"] = id_de(bp.Id)
    except Exception:
        pass
    try:
        resultat["position_interne_mm"] = point_json(bp.Position)
    except Exception as err:
        resultat["position_interne_mm"] = OrderedDict([("erreur", texte(err))])
    try:
        resultat["position_partagee_mm"] = point_json(bp.SharedPosition)
    except Exception as err:
        resultat["position_partagee_mm"] = OrderedDict([("erreur", texte(err))])
    return resultat


emplacement = OrderedDict()
try:
    loc = doc.ActiveProjectLocation
    emplacement["nom"] = texte(loc.Name)
    pp = loc.GetProjectPosition(XYZ.Zero)
    emplacement["est_ouest_mm"] = rmm(pp.EastWest)
    emplacement["nord_sud_mm"] = rmm(pp.NorthSouth)
    emplacement["elevation_mm"] = rmm(pp.Elevation)
    emplacement["angle_nord_vrai_rad"] = pp.Angle
except Exception as err:
    emplacement["erreur"] = texte(err)

ids_niveaux = list(
    FilteredElementCollector(doc).OfClass(Level)
    .WhereElementIsNotElementType().ToElementIds()
)
niveaux = OrderedDict()
ecarts_niveaux = []
for eid in ids_niveaux:
    lvl = doc.GetElement(eid)
    if lvl is None:
        continue
    z_elev = None
    z_proj = None
    try:
        z_elev = rmm(lvl.Elevation)
    except Exception:
        pass
    try:
        z_proj = rmm(lvl.ProjectElevation)
    except Exception:
        pass
    if z_elev is not None and z_proj is not None:
        ecarts_niveaux.append(z_elev - z_proj)
    niveaux[id_de(eid)] = OrderedDict([
        ("id", id_de(eid)),
        ("nom", texte(lvl.Name)),
        ("project_elevation_mm", z_proj),
        ("elevation_mm", z_elev),
    ])

# --------------------------------------------------------------------------
# 2. Lecteurs : nom, parametres, geometrie
# --------------------------------------------------------------------------

# Le decoupage lui-meme est dans bimflow_noms (decouper_nom) : lecture
# TOLERANTE - elle rend les segments des que leur nombre est bon et liste a
# cote tout ce qui cloche, ce qu'il faut a un audit, qui decrit sans juger.


def valeur_parametre(p, porteur):
    d = OrderedDict()
    d["porteur"] = porteur
    try:
        st = p.StorageType
    except Exception:
        st = None
    d["stockage"] = texte(st)
    try:
        d["a_valeur"] = bool(p.HasValue)
    except Exception:
        d["a_valeur"] = None
    valeur = None
    try:
        if st == StorageType.String:
            valeur = p.AsString()
        elif st == StorageType.Integer:
            valeur = p.AsInteger()
        elif st == StorageType.ElementId:
            valeur = id_de(p.AsElementId())
        elif st == StorageType.Double:
            valeur = p.AsDouble()
            d["valeur_en_unite_interne"] = True
    except Exception as err:
        d["erreur"] = texte(err)
    d["valeur"] = valeur
    try:
        d["valeur_affichee"] = p.AsValueString()
    except Exception:
        d["valeur_affichee"] = None
    try:
        d["partage"] = bool(p.IsShared)
    except Exception:
        d["partage"] = None
    try:
        d["lecture_seule"] = bool(p.IsReadOnly)
    except Exception:
        d["lecture_seule"] = None
    return d


def lire_parametres(element, porteur, cible, doublons):
    if element is None:
        return
    try:
        parametres = list(element.Parameters)
    except Exception:
        return
    for p in parametres:
        try:
            nom = p.Definition.Name
        except Exception:
            continue
        if not nom or not nom.startswith(PREFIXES_PARAMETRES):
            continue
        cle = nom
        rang = 2
        while cle in cible:
            cle = u"{0}#{1}".format(nom, rang)
            rang += 1
        if cle != nom:
            doublons.append(nom)
        cible[cle] = valeur_parametre(p, porteur)


def parametre_double(el, nom_bip):
    """Valeur d'un BuiltInParameter Double, ou None s'il n'existe pas."""
    bip = getattr(BuiltInParameter, nom_bip, None)
    if bip is None:
        return None
    try:
        p = el.get_Parameter(bip)
    except Exception:
        return None
    if p is None or not p.HasValue:
        return None
    try:
        return p.AsDouble()
    except Exception:
        return None


# --------------------------------------------------------------------------
# 3. Collecte - le collecteur est consomme AVANT toute resolution (R15 fait 8)
# --------------------------------------------------------------------------

ids_volumes = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_Mass)
    .WhereElementIsNotElementType()
    .ToElementIds()
)
ids_planchers = list(
    FilteredElementCollector(doc)
    .OfCategory(BuiltInCategory.OST_MassFloor)
    .WhereElementIsNotElementType()
    .ToElementIds()
)

try:
    from Autodesk.Revit.DB import MassInstanceUtils
except Exception:
    MassInstanceUtils = None

# --------------------------------------------------------------------------
# 4. Volumes
# --------------------------------------------------------------------------

volumes = []
erreurs = []

non_conformes = []          # (eid, nom, defauts)
a_renommer = []             # (eid, nom) - 4e segment encore "0"
natures_inconnues = []      # (eid, nom, valeur hors liste fermee)
multi_solides = []          # (eid, nom, n)
sans_geometrie = []         # (eid, nom, motif)
sans_haute = []             # (eid, nom)
avec_inclinee = []          # (eid, nom, n)
avec_non_plane = []         # (eid, nom, n)
non_in_situ = []            # (eid, nom)
par_zone = {}
par_etage = {}
par_zone_etage = {}         # (zone, etage) -> [(eid, nom)]
hote_de_plancher = {}       # id plancher -> id volume (vu depuis le volume)
solides_par_volume = {}     # id volume -> [Solid] - pour les controles amont


def noter_erreur(eid, etape, err):
    erreurs.append(OrderedDict([
        ("id", id_de(eid)), ("etape", etape), ("message", texte(err)),
    ]))


# CAR_Surface_sol - une liste par facon d'echouer, pour que le rapport dise
# QUOI faire et pas seulement combien.
surface_ok = []             # eid
surface_ecart = []          # (ecart m2, eid, nom, portee m2, contour m2)
surface_absente = []        # (eid, nom) - pas de parametre de ce GUID
surface_vide = []           # (eid, nom) - parametre present, jamais ecrit
surface_mauvais_type = []   # (eid, nom, motif)
surface_sans_contour = []   # (eid, nom, motif)
face_basse_inclinee = []    # (ecart m2, eid, nom, face basse m2, contour m2)


def controler_surface_sol(eid, el, family_name, faces, v):
    """Rapproche CAR_Surface_sol de l'aire du contour, et decrit la face
    basse. Remplit v["surface_sol"] et les listes ci-dessus."""
    s = OrderedDict()
    anneau, aire, motif = contour_du_volume(faces)
    s["contour_aire_m2"] = None if aire is None else round(aire, 4)
    if motif is not None:
        s["contour_refus"] = motif
        surface_sans_contour.append((eid, family_name, motif))

    fb = face_basse(faces, aire)
    s["face_basse"] = fb
    if fb["inclinee"]:
        face_basse_inclinee.append((fb["ecart_m2"], eid, family_name,
                                    fb["aire_m2"], s["contour_aire_m2"]))

    p = parametre_par_guid(el, GUID_SURFACE_SOL)
    if p is None:
        s["statut"] = u"ABSENT"
        surface_absente.append((eid, family_name))
    else:
        ok_type, motif_type = est_une_surface(p)
        if not ok_type:
            s["statut"] = u"MAUVAIS_TYPE"
            s["motif"] = motif_type
            surface_mauvais_type.append((eid, family_name, motif_type))
        elif not p.HasValue:
            s["statut"] = u"VIDE"
            surface_vide.append((eid, family_name))
        else:
            portee = interne_vers_m2(p.AsDouble())
            s["CAR_Surface_sol_m2"] = round(portee, 4)
            if aire is None:
                s["statut"] = u"NON_CONTROLABLE"
            else:
                ecart = abs(portee - aire)
                s["ecart_m2"] = round(ecart, 6)
                if ecart < TOL_SURFACE_SOL_M2:
                    s["statut"] = u"OK"
                    surface_ok.append(eid)
                else:
                    s["statut"] = u"ECART"
                    surface_ecart.append((ecart, eid, family_name, portee,
                                          aire))
    v["surface_sol"] = s


def auditer_volume(eid):
    el = doc.GetElement(eid)
    if el is None:
        return

    v = OrderedDict()
    v["id"] = id_de(eid)
    try:
        v["unique_id"] = el.UniqueId
    except Exception:
        v["unique_id"] = None
    v["classe_api"] = el.GetType().Name

    # --- identite ---------------------------------------------------
    family_name = None
    type_name = None
    in_situ = None
    type_el = None
    try:
        if isinstance(el, FamilyInstance):
            type_el = el.Symbol
            famille = type_el.Family
            family_name = famille.Name
            in_situ = bool(famille.IsInPlace)
        else:
            type_el = doc.GetElement(el.GetTypeId())
            if type_el is not None:
                try:
                    family_name = type_el.FamilyName
                except Exception:
                    family_name = None
        if type_el is not None:
            type_name = type_el.Name
    except Exception as err:
        noter_erreur(eid, u"identite", err)

    v["family_name"] = texte(family_name)
    v["in_situ"] = in_situ
    if in_situ is not True:
        non_in_situ.append((eid, family_name))

    segments, defauts = decouper_nom(family_name)
    v["nom_conforme"] = segments is not None and not defauts
    v["segments"] = OrderedDict([
        ("prefixe", segments[0] if segments else None),
        ("REF_Zone", segments[1] if segments else None),
        ("REF_Etage", segments[2] if segments else None),
        ("CLS_Nature_volume", segments[3] if segments else None),
    ])
    if defauts:
        v["defauts_nom"] = defauts
        non_conformes.append((eid, family_name, defauts))
    if segments is not None:
        zone, etage, nature = segments[1], segments[2], segments[3]
        par_zone[zone] = par_zone.get(zone, 0) + 1
        par_etage[etage] = par_etage.get(etage, 0) + 1
        par_zone_etage.setdefault((zone, etage), []).append((eid, family_name))
        if nature == NATURE_A_RENOMMER:
            a_renommer.append((eid, family_name))
        elif nature not in NATURES:
            natures_inconnues.append((eid, family_name, nature))

    v["type_name"] = texte(type_name)
    v["workset"] = nom_sous_projet(el)

    # --- parametres REF_ / CLS_ -------------------------------------
    parametres = OrderedDict()
    doublons = []
    try:
        lire_parametres(el, u"instance", parametres, doublons)
        lire_parametres(type_el, u"type", parametres, doublons)
    except Exception as err:
        noter_erreur(eid, u"parametres", err)
    v["parametres"] = parametres
    if doublons:
        v["parametres_nom_en_double"] = sorted(set(doublons))

    # --- boite englobante ---------------------------------------------
    try:
        bb = el.get_BoundingBox(None)
    except Exception as err:
        bb = None
        noter_erreur(eid, u"bbox", err)
    if bb is not None:
        v["bbox"] = OrderedDict([
            ("xmin", rmm(bb.Min.X)), ("ymin", rmm(bb.Min.Y)),
            ("zmin", rmm(bb.Min.Z)), ("xmax", rmm(bb.Max.X)),
            ("ymax", rmm(bb.Max.Y)), ("zmax", rmm(bb.Max.Z)),
        ])
    else:
        v["bbox"] = None

    # --- valeurs brutes calculees par Revit ---------------------------
    v["volume_brut_m3"] = m3(parametre_double(el, "MASS_GROSS_VOLUME"))
    v["surface_brute_m2"] = m2(parametre_double(el, "MASS_GROSS_SURFACE_AREA"))
    v["surface_plancher_brute_m2"] = m2(parametre_double(el, "MASS_GROSS_AREA"))

    # --- planchers de volume rattaches, vus depuis le volume ---------
    if MassInstanceUtils is not None:
        try:
            ids_pl = [id_de(i) for i in
                      MassInstanceUtils.GetMassLevelDataIds(doc, eid)]
            v["mass_floor_ids"] = ids_pl
            for i in ids_pl:
                hote_de_plancher[i] = id_de(eid)
        except Exception as err:
            noter_erreur(eid, u"GetMassLevelDataIds", err)

    # --- geometrie ----------------------------------------------------
    faces = []
    try:
        pleins, faces_libres, vides, autres = parcourir_geometrie(el)
    except Exception as err:
        pleins, faces_libres, vides, autres = [], [], 0, []
        noter_erreur(eid, u"get_Geometry", err)

    # Les solides sont gardes pour les controles amont : eux seuls comparent
    # les volumes ENTRE EUX, ce que la boucle ne fait jamais.
    if pleins:
        solides_par_volume[id_de(eid)] = pleins

    v["nb_solides"] = len(pleins)
    if vides:
        v["nb_solides_vides"] = vides
    if autres:
        v["autres_geometries"] = sorted(set(autres))
    v["volume_solides_m3"] = m3(sum([s.Volume for s in pleins])) if pleins else None

    faces = faces_du_volume(
        pleins, lambda etape, err: noter_erreur(eid, etape, err))
    v["faces"] = faces

    # --- CAR_Surface_sol contre le contour ------------------------------
    # Le contour est reconstruit ICI par le code qui a servi a l'ecrire
    # (bimflow_contour) ; la valeur portee est lue par GUID, jamais par nom.
    if pleins:
        controler_surface_sol(eid, el, family_name, faces, v)

    # --- constats ------------------------------------------------------
    if not pleins:
        motif = u"aucun solide plein"
        if bb is None:
            motif += u", pas de boite englobante"
        sans_geometrie.append((eid, family_name, motif))
    else:
        if len(pleins) > 1:
            multi_solides.append((eid, family_name, len(pleins)))
        classes = [f["classe"] for f in faces]
        if u"HORIZONTALE_HAUTE" not in classes:
            sans_haute.append((eid, family_name))
        n_incl = classes.count(u"INCLINEE")
        if n_incl:
            avec_inclinee.append((eid, family_name, n_incl))
        n_np = len([f for f in faces if not f["planaire"]])
        if n_np:
            avec_non_plane.append((eid, family_name, n_np))

    volumes.append(v)


total = len(ids_volumes)
PAS = 5

if total == 0:
    avertissements.append(
        u"**Aucun element de categorie Volumes dans cette maquette.** Le JSON "
        u"ne portera que l'en-tete et les planchers de volume."
    )
else:
    with forms.ProgressBar(title=u"Audit des volumes - {value}/{max_value}",
                           cancellable=True) as pb:
        for position, eid in enumerate(ids_volumes):
            if position % PAS == 0:
                if pb.cancelled:
                    script.exit()
                pb.update_progress(position, total)
            auditer_volume(eid)
        pb.update_progress(total, total)

doublons_zone_etage = [
    (cle, liste) for cle, liste in sorted(par_zone_etage.items())
    if len(liste) > 1
]

# --------------------------------------------------------------------------
# 2 bis. CONTROLES AMONT DES CONTRAINTES IVION
#
# OBJET. Un site_model Ivion obeit a des contraintes que la chaine verifie
# APRES coup, hors Revit - et qui se corrigent DANS Revit. Les trois
# controles ci-dessous les anticipent, a l'endroit ou on repare.
#
#   superposition 3D ....... C1 (interieurs de BUILDING disjoints) et
#                            C6 (aucune superposition entre etages freres)
#   vide dans une colonne .. C2 (pile verticale ordonnee et CONTIGUE)
#   tranche trop basse ..... C10 (au moins un metre)
#
# CE QUI RESTE EN AVAL, et pourquoi. La fermeture de la partition en plan
# demande de vraies operations de polygones - shapely, indisponible sous
# IronPython. Elle reste a audit_to_zones, qui nomme desormais les couples
# fautifs. Ces controles-ci ne la remplacent pas : ils attrapent ce qu'on
# peut attraper tot.
#
# LECTURE SEULE : aucune transaction. Les operations booleennes travaillent
# sur des copies de solides et ne touchent pas au modele.
# --------------------------------------------------------------------------

controles = OrderedDict()


def boite_de(v):
    b = v.get("bbox")
    if not b:
        return None
    return (b["xmin"], b["ymin"], b["zmin"], b["xmax"], b["ymax"], b["zmax"])


def recouvrement(a, b, i_min, i_max):
    """Longueur commune des deux boites sur un axe, en mm. <= 0 : disjointes."""
    return min(a[i_max], b[i_max]) - max(a[i_min], b[i_min])


def boites_se_recoupent(a, b, tol):
    """Vrai si les deux boites se recoupent dans LES TROIS dimensions.

    Les trois, jamais une seule : c'est la regle payee le 2026-09-24, quand
    un ecart de 3 620 mm mesure sur le seul axe Z s'est revele nul en plan."""
    return (recouvrement(a, b, 0, 3) > tol and
            recouvrement(a, b, 1, 4) > tol and
            recouvrement(a, b, 2, 5) > tol)


def volume_commun(id_a, id_b):
    """(volume m3, boite du commun en mm) ou (None, None) si indisponible.

    Leve None si l'API booleenne manque ou si Revit refuse l'operation - on
    ne remplace jamais une mesure par une estimation silencieuse."""
    if BooleanOperationsUtils is None:
        return None, None
    total = 0.0
    coins = []
    for sa in solides_par_volume.get(id_a, []):
        for sb in solides_par_volume.get(id_b, []):
            try:
                commun = BooleanOperationsUtils.ExecuteBooleanOperation(
                    sa, sb, BooleanOperationsType.Intersect)
            except Exception:
                return None, None
            if commun is None or commun.Volume <= 1e-9:
                continue
            total += commun.Volume
            try:
                bb = commun.GetBoundingBox()
                # La boite d'un solide est donnee dans SON repere : on la
                # ramene au repere du modele avant de la comparer a quoi que
                # ce soit.
                for p in (bb.Min, bb.Max):
                    q = bb.Transform.OfPoint(p)
                    coins.append((rmm(q.X), rmm(q.Y), rmm(q.Z)))
            except Exception:
                pass
    if total <= 0.0:
        return 0.0, None
    boite = None
    if coins:
        xs = [c[0] for c in coins]
        ys = [c[1] for c in coins]
        zs = [c[2] for c in coins]
        boite = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
    return m3(total), boite


# --- C1 / C6 : deux volumes ne peuvent pas occuper le meme espace ---------

superpositions = []         # (volume m3, id a, nom a, id b, nom b, boite)
superpositions_indecises = []   # couples dont Revit a refuse le booleen

avec_boite = [v for v in volumes if boite_de(v) is not None]
candidats = []
for i_a in range(len(avec_boite)):
    for i_b in range(i_a + 1, len(avec_boite)):
        ba = boite_de(avec_boite[i_a])
        bb_ = boite_de(avec_boite[i_b])
        if boites_se_recoupent(ba, bb_, TOL_CONTACT_MM):
            candidats.append((avec_boite[i_a], avec_boite[i_b]))

for va, vb in candidats:
    vol, boite = volume_commun(va["id"], vb["id"])
    if vol is None:
        superpositions_indecises.append(
            (va["id"], va.get("family_name"), vb["id"], vb.get("family_name")))
        continue
    if vol > TOL_VOLUME_COMMUN_M3:
        superpositions.append((vol, va["id"], va.get("family_name"),
                               vb["id"], vb.get("family_name"), boite))
superpositions.sort(reverse=True)

controles["superposition_3d"] = OrderedDict([
    ("nb_couples_candidats_par_boite", len(candidats)),
    ("nb_couples_en_superposition", len(superpositions)),
    ("nb_couples_non_calculables", len(superpositions_indecises)),
    ("tolerance_volume_m3", TOL_VOLUME_COMMUN_M3),
])


# --- C2 : dans une colonne, aucun vide entre deux tranches ---------------
#
# Une colonne, ici, est un groupe de volumes qui partagent la MEME EMPRISE
# EN PLAN - approchee par la boite en plan arrondie, faute de shapely. Le
# nom de zone ne sert pas de cle : un audit peut tourner AVANT le renommage,
# et la geometrie, elle, est toujours la.

def cle_colonne(v):
    b = boite_de(v)
    if b is None:
        return None
    return tuple(round(c / PAS_COLONNE_MM) for c in (b[0], b[1], b[3], b[4]))


colonnes = {}
for v in avec_boite:
    colonnes.setdefault(cle_colonne(v), []).append(v)

vides_colonne = []          # (jeu mm, zone, id bas, nom bas, id haut, nom haut)
for cle, membres in colonnes.items():
    if len(membres) < 2:
        continue
    empiles = sorted(membres, key=lambda v: boite_de(v)[2])
    for bas, haut in zip(empiles, empiles[1:]):
        jeu = boite_de(haut)[2] - boite_de(bas)[5]
        if jeu > TOL_JOINT_MM:
            vides_colonne.append((
                jeu,
                (bas.get("segments") or {}).get("REF_Zone"),
                bas["id"], bas.get("family_name"),
                haut["id"], haut.get("family_name")))
vides_colonne.sort(reverse=True)

controles["vide_dans_une_colonne"] = OrderedDict([
    ("nb_colonnes_a_plusieurs_tranches",
     len([m for m in colonnes.values() if len(m) > 1])),
    ("nb_vides", len(vides_colonne)),
    ("jeu_admis_mm", TOL_JOINT_MM),
    ("emprise_approchee_par", "boite en plan, pas de %g mm" % PAS_COLONNE_MM),
])


# --- C10 : une tranche fait au moins un metre ----------------------------

trop_basses = []            # (hauteur mm, id, nom)
for v in avec_boite:
    b = boite_de(v)
    hauteur = b[5] - b[2]
    if hauteur < HAUTEUR_MINI_MM:
        trop_basses.append((hauteur, v["id"], v.get("family_name")))
trop_basses.sort()

controles["tranche_sous_le_metre"] = OrderedDict([
    ("nb_tranches", len(trop_basses)),
    ("hauteur_mini_mm", HAUTEUR_MINI_MM),
])

# --------------------------------------------------------------------------
# 5. Planchers de volume EXISTANTS - aucun n'est cree
# --------------------------------------------------------------------------

mass_floors = []
planchers_sans_contour = []

for eid in ids_planchers:
    el = doc.GetElement(eid)
    if el is None:
        continue
    d = OrderedDict()
    d["id"] = id_de(eid)
    try:
        d["unique_id"] = el.UniqueId
    except Exception:
        d["unique_id"] = None
    d["classe_api"] = el.GetType().Name

    hote = None
    try:
        hote = id_de(getattr(el, "OwningMassId"))
    except Exception:
        hote = None
    if hote is not None and hote < 0:
        hote = None
    d["volume_hote_id"] = hote if hote is not None else hote_de_plancher.get(d["id"])
    vu_depuis_volume = hote_de_plancher.get(d["id"])
    if hote is not None and vu_depuis_volume is not None and hote != vu_depuis_volume:
        d["incoherence_hote"] = OrderedDict([
            ("OwningMassId", hote), ("GetMassLevelDataIds", vu_depuis_volume),
        ])

    niv = None
    try:
        niv = id_de(el.LevelId)
    except Exception:
        niv = None
    if niv in niveaux:
        d["niveau"] = niveaux[niv]
    else:
        d["niveau"] = None
        d["niveau_lu"] = niv

    try:
        pleins, faces_libres, vides, autres = parcourir_geometrie(el)
    except Exception as err:
        pleins, faces_libres, vides, autres = [], [], 0, []
        noter_erreur(eid, u"mass_floor get_Geometry", err)

    candidates = list(faces_libres)
    for s in pleins:
        for f in s.Faces:
            candidates.append(f)
    d["nb_faces_lues"] = len(candidates)

    haute = None
    for f in candidates:
        if not isinstance(f, PlanarFace):
            continue
        try:
            nz = f.FaceNormal.Normalize().Z
        except Exception:
            continue
        if nz > NZ_HORIZONTALE:
            if haute is None or f.Origin.Z > haute.Origin.Z:
                haute = f

    if haute is None:
        d["face_superieure"] = None
        planchers_sans_contour.append(eid)
    else:
        fs = OrderedDict()
        fs["altitude_mm"] = rmm(haute.Origin.Z)
        fs["aire_m2"] = m2(haute.Area)
        try:
            boucle, boucles, methode_b = boucle_exterieure(
                haute, haute.FaceNormal.Normalize())
            fs["contour_xy"] = anneau_xy(boucle) if boucle is not None else None
            if len(boucles) > 1:
                fs["boucle_exterieure_methode"] = methode_b
                fs["trous_xy"] = [
                    anneau_xy(b) for b in boucles if b is not boucle
                ]
        except Exception as err:
            noter_erreur(eid, u"mass_floor contour", err)
        d["face_superieure"] = fs

    mass_floors.append(d)

# --------------------------------------------------------------------------
# 6. Synthese a l'ecran
# --------------------------------------------------------------------------


def lien(eid):
    try:
        return out.linkify(eid)
    except Exception:
        return u"`{0}`".format(id_de(eid))


def lien_id(identifiant):
    """Comme lien(), mais depuis l'entier deja publie dans le JSON."""
    try:
        return out.linkify(ElementId(identifiant))
    except Exception:
        return u"`{0}`".format(identifiant)


def liste_md(titre, lignes, vide=u"*Aucun.*"):
    out.print_md(u"## {0}".format(titre))
    if not lignes:
        out.print_md(vide)
        return
    out.print_md(u"\n".join(lignes))


out.print_md(u"# Audit des volumes de zone")
out.print_md(
    u"Maquette : **{0}** &nbsp;|&nbsp; {1} &nbsp;|&nbsp; lecture seule, "
    u"aucune transaction".format(
        doc.Title,
        u"copie detachee" if detache else
        (u"collaborative NON detachee" if collaboratif else u"non collaborative"),
    )
)

if avertissements:
    liste_md(u"Avertissements", [u"- {0}".format(a) for a in avertissements])

out.print_md(u"## Bilan")
out.print_md(
    u"- **{0}** volume(s) de categorie Volumes, dont **{1}** in situ\n"
    u"- **{2}** plancher(s) de volume existant(s)\n"
    u"- **{3}** erreur(s) de lecture consignee(s) dans le JSON".format(
        len(volumes), len(volumes) - len(non_in_situ), len(mass_floors),
        len(erreurs))
)

if ecarts_niveaux:
    ecarts_niveaux.sort()
    med = ecarts_niveaux[len(ecarts_niveaux) // 2]
    out.print_md(
        u"> Repere : ecart `Level.Elevation - Level.ProjectElevation` mesure "
        u"sur {0} niveau(x) : mediane **{1:.1f} mm**, de {2:.1f} a {3:.1f} mm. Les "
        u"altitudes du JSON sont celles de la geometrie, aucune ne passe par "
        u"`Level.Elevation`.".format(
            len(ecarts_niveaux), med, ecarts_niveaux[0], ecarts_niveaux[-1])
    )


def table_repartition(titre, compte):
    out.print_md(u"## Repartition par {0}".format(titre))
    if not compte:
        out.print_md(u"*Aucun nom decoupable.*")
        return
    lignes = [u"| {0} | Volumes |".format(titre), u"|---|---:|"]
    for cle in sorted(compte.keys()):
        lignes.append(u"| `{0}` | {1} |".format(cle, compte[cle]))
    out.print_md(u"\n".join(lignes))


table_repartition(u"REF_Zone", par_zone)
table_repartition(u"REF_Etage", par_etage)

liste_md(
    u"Noms non conformes au motif "
    u"`VOL__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>`",
    [u"- {0} `{1}` : {2}".format(lien(e), n, u" ; ".join(d))
     for e, n, d in non_conformes],
)
liste_md(
    u"Volumes a renommer - 4e segment encore \"{0}\"".format(NATURE_A_RENOMMER),
    [u"- {0} `{1}`".format(lien(e), n) for e, n in a_renommer],
    vide=u"*Aucun : tous les noms portent deja leur nature.*",
)
liste_md(
    u"Natures hors de la liste fermee ({0})".format(u", ".join(NATURES)),
    [u"- {0} `{1}` : 4e segment **`{2}`**".format(lien(e), n, v)
     for e, n, v in natures_inconnues],
)
liste_md(
    u"Meme couple (REF_Zone, REF_Etage) porte par plusieurs volumes",
    [u"- `{0}` / `{1}` : {2}".format(
        cle[0], cle[1],
        u", ".join([u"{0} `{1}`".format(lien(e), n) for e, n in liste]))
     for cle, liste in doublons_zone_etage],
)
liste_md(
    u"Volumes sans geometrie - signales, l'audit a continue",
    [u"- {0} `{1}` : {2}".format(lien(e), n, m) for e, n, m in sans_geometrie],
)
liste_md(
    u"Volumes a plus d'un solide",
    [u"- {0} `{1}` : {2} solides".format(lien(e), n, k)
     for e, n, k in multi_solides],
)
liste_md(
    u"Volumes sans face horizontale haute",
    [u"- {0} `{1}`".format(lien(e), n) for e, n in sans_haute],
)
liste_md(
    u"Volumes avec au moins une face inclinee",
    [u"- {0} `{1}` : {2} face(s)".format(lien(e), n, k)
     for e, n, k in avec_inclinee],
)
if avec_non_plane:
    liste_md(
        u"Volumes avec au moins une face non plane (classe lue au centre de "
        u"la face seulement)",
        [u"- {0} `{1}` : {2} face(s)".format(lien(e), n, k)
         for e, n, k in avec_non_plane],
    )
if non_in_situ:
    liste_md(
        u"Volumes qui ne sont PAS in situ (familles chargeables ou autres)",
        [u"- {0} `{1}`".format(lien(e), n) for e, n in non_in_situ],
    )

# --------------------------------------------------------------------------
# CAR_Surface_sol - la valeur portee contre le contour reconstruit ici
# --------------------------------------------------------------------------

nb_controles = (len(surface_ok) + len(surface_ecart) + len(surface_absente)
                + len(surface_vide) + len(surface_mauvais_type)
                + len([v for v in volumes
                       if (v.get("surface_sol") or {}).get("statut")
                       == u"NON_CONTROLABLE"]))
out.print_md(u"## CAR_Surface_sol")
out.print_md(
    u"Projection horizontale du contour, ecrite par **MAJ params volumes**, "
    u"relue ici **par GUID** (`{0}`) et rapprochee du contour reconstruit par "
    u"le meme code (`lib\\bimflow_contour`). Tolerance : **{1} m²**.\n\n"
    u"| Resultat | Volumes |\n|---|---:|\n"
    u"| **Conformes** | {2} |\n"
    u"| Ecart au contour | {3} |\n"
    u"| Parametre absent (non lie, ou autre GUID) | {4} |\n"
    u"| Parametre present mais jamais ecrit | {5} |\n"
    u"| Parametre qui n'est pas une Surface | {6} |\n"
    u"| Contour non reconstruit | {7} |\n"
    u"| *Total controle* | *{8}* |".format(
        GUID_SURFACE_SOL, TOL_SURFACE_SOL_M2, len(surface_ok),
        len(surface_ecart), len(surface_absente), len(surface_vide),
        len(surface_mauvais_type), len(surface_sans_contour), nb_controles)
)
if surface_ecart:
    surface_ecart.sort(reverse=True)
    liste_md(
        u"CAR_Surface_sol en ecart avec le contour - relancer MAJ params "
        u"volumes, ou chercher qui a saisi a la main",
        [u"- **{0:.4f} m²** : {1} `{2}` porte {3:.4f}, contour {4:.4f}".format(
            e, lien(i), n, p, a) for e, i, n, p, a in surface_ecart],
    )
if surface_absente:
    liste_md(
        u"CAR_Surface_sol absent - lier le parametre (bouton Socle parametres)",
        [u"- {0} `{1}`".format(lien(e), n) for e, n in surface_absente[:40]]
        + ([u"- ... et {0} autre(s)".format(len(surface_absente) - 40)]
           if len(surface_absente) > 40 else []),
    )
if surface_vide:
    liste_md(
        u"CAR_Surface_sol jamais ecrit - lancer MAJ params volumes",
        [u"- {0} `{1}`".format(lien(e), n) for e, n in surface_vide[:40]]
        + ([u"- ... et {0} autre(s)".format(len(surface_vide) - 40)]
           if len(surface_vide) > 40 else []),
    )
if surface_mauvais_type:
    liste_md(
        u"Un parametre porte le GUID de CAR_Surface_sol sans etre une Surface",
        [u"- {0} `{1}` : {2}".format(lien(e), n, m)
         for e, n, m in surface_mauvais_type],
    )
if surface_sans_contour:
    liste_md(
        u"Contour non reconstruit - aucune surface au sol possible",
        [u"- {0} `{1}` : {2}".format(lien(e), n, m)
         for e, n, m in surface_sans_contour],
    )

liste_md(
    u"Volumes a face basse inclinee - la surface au sol est la PROJECTION",
    [u"- {0} `{1}` : face basse **{2:.3f} m²**, projection {3} m², "
     u"ecart **{4}**".format(
         lien(i), n, fb,
         u"?" if a is None else u"{0:.3f}".format(a),
         u"?" if e is None else u"{0:+.3f} m²".format(e))
     for e, i, n, fb, a in sorted(face_basse_inclinee,
                                  key=lambda t: -(t[0] or 0))],
    vide=u"*Aucun : toutes les faces basses sont horizontales, la face et sa "
         u"projection se confondent.*",
)
if face_basse_inclinee:
    out.print_md(
        u"> Sur ces volumes, `CAR_Surface_sol` est **l'ombre au sol** du "
        u"volume, pas l'aire de sa face basse, qui est plus grande. C'est la "
        u"definition retenue [H] ; a trancher si la nomenclature doit un jour "
        u"compter autre chose."
    )

# Sommes par REF_Batiment x REF_Etage : la valeur portee, et le contour.
# REF_Batiment est lu tel que la maquette le porte, REF_Etage dans le nom.
sommes = {}
for v in volumes:
    s = v.get("surface_sol") or {}
    etage = (v.get("segments") or {}).get("REF_Etage")
    nature = (v.get("segments") or {}).get("CLS_Nature_volume")
    bat = ((v.get("parametres") or {}).get("REF_Batiment") or {}).get("valeur")
    for cle in ((bat or u"?", etage or u"?"), (u"TOTAL ETAGE", u"")
                if nature == u"ETAGE" else None):
        if cle is None:
            continue
        ligne = sommes.setdefault(cle, [0, 0.0, 0.0])
        ligne[0] += 1
        ligne[1] += s.get("CAR_Surface_sol_m2") or 0.0
        ligne[2] += s.get("contour_aire_m2") or 0.0
if sommes:
    lignes = [u"| REF_Batiment | REF_Etage | Volumes | CAR_Surface_sol m² | "
              u"Contour m² | Ecart m² |", u"|---|---|---:|---:|---:|---:|"]
    for cle in sorted(sommes.keys(), key=lambda c: (c[0] == u"TOTAL ETAGE", c)):
        n, car, cnt = sommes[cle]
        lignes.append(u"| {0} | {1} | {2} | {3:.2f} | {4:.2f} | {5:+.3f} |".format(
            cle[0], cle[1], n, car, cnt, car - cnt))
    out.print_md(u"### Sommes par batiment et etage")
    out.print_md(u"\n".join(lignes))

# --------------------------------------------------------------------------
# Contraintes Ivion - ce qui se repare ICI plutot qu'en aval
# --------------------------------------------------------------------------

out.print_md(u"## Compatibilite site_model Ivion")
out.print_md(
    u"Ces trois controles anticipent, **dans Revit**, ce que la chaine "
    u"`site_model` refuserait plus tard. Un defaut trouve ici se corrige sur "
    u"le volume ; trouve en aval, il fait recommencer le tour.\n\n"
    u"| Controle | Contrainte Ivion | Resultat |\n|---|---|---|\n"
    u"| Superposition 3D | **C1** interieurs disjoints, **C6** etages freres | {0} |\n"
    u"| Vide dans une colonne | **C2** pile contigue | {1} |\n"
    u"| Tranche sous le metre | **C10** | {2} |\n".format(
        (u"**{0} couple(s)**".format(len(superpositions)) if superpositions
         else u"aucun sur {0} couple(s) examine(s)".format(len(candidats))),
        (u"**{0} vide(s)**".format(len(vides_colonne)) if vides_colonne
         else u"aucun sur {0} colonne(s)".format(
             len([m for m in colonnes.values() if len(m) > 1]))),
        (u"**{0} tranche(s)**".format(len(trop_basses)) if trop_basses
         else u"aucune"))
)

if BooleanOperationsUtils is None:
    out.print_md(
        u"> ⚠ **Superposition NON VERIFIEE** : l'API d'operations booleennes "
        u"n'est pas disponible sur cette version. Le controle ne rend aucun "
        u"resultat plutot qu'un resultat approche."
    )

liste_md(
    u"Volumes qui se superposent - C1 / C6",
    [u"- **{0:.3f} m³** : {1} `{2}` **X** {3} `{4}`{5}".format(
        vol, lien_id(ia), na, lien_id(ib), nb,
        u"" if not boite else
        u"<br>  bande de **{0:.0f} mm** sur {1:.0f} x {2:.0f} mm".format(
            min(boite[3] - boite[0], boite[4] - boite[1], boite[5] - boite[2]),
            boite[3] - boite[0], boite[4] - boite[1]))
     for vol, ia, na, ib, nb, boite in superpositions],
    vide=u"*Aucune : les {0} couple(s) dont les boites se recoupaient ont un "
         u"volume commun nul ou negligeable.*".format(len(candidats)),
)
if superpositions:
    out.print_md(
        u"> **L'epaisseur de la bande dit quoi corriger.** Quelques "
        u"centimetres sur plusieurs metres, c'est un bord trace sur la "
        u"mauvaise face d'un mur. Un bloc de plusieurs decimetres dans les "
        u"deux sens, c'est un conflit de trace - deux volumes se disputent le "
        u"meme espace."
    )

if superpositions_indecises:
    liste_md(
        u"Couples dont Revit a refuse l'intersection - **non conclus**",
        [u"- {0} `{1}` **X** {2} `{3}`".format(lien_id(ia), na, lien_id(ib), nb)
         for ia, na, ib, nb in superpositions_indecises],
    )

liste_md(
    u"Vides entre deux tranches d'une meme colonne - C2",
    [u"- **{0:.0f} mm** de vide{1} : au-dessus de {2} `{3}`, sous {4} `{5}`".format(
        jeu, u" (zone `{0}`)".format(zone) if zone else u"",
        lien_id(ib), nb, lien_id(ih), nh)
     for jeu, zone, ib, nb, ih, nh in vides_colonne],
    vide=u"*Aucun : dans chaque colonne, chaque tranche commence ou la "
         u"precedente s'arrete.*",
)
if vides_colonne:
    out.print_md(
        u"> Un vide dans une pile est un etage ou un visiteur ne peut pas "
        u"etre. La chaine le compte en **C2** sans bloquer ; Ivion, lui, "
        u"affichera un trou. Le bas du volume superieur doit rejoindre le "
        u"haut de l'inferieur."
    )

liste_md(
    u"Tranches de moins d'un metre - C10",
    [u"- **{0:.0f} mm** : {1} `{2}`".format(h, lien_id(i), n)
     for h, i, n in trop_basses],
    vide=u"*Aucune.*",
)

out.print_md(
    u"> **Ce qui reste en aval.** La fermeture de la **partition en plan** "
    u"demande de vraies operations de polygones (`shapely`, indisponible sous "
    u"IronPython) : elle reste a `audit_to_zones`, qui nomme les couples de "
    u"zones fautifs. Les controles ci-dessus ne la remplacent pas."
)

out.print_md(u"## Planchers de volume")
if not mass_floors:
    out.print_md(
        u"**Aucun plancher de volume dans cette maquette.** La section "
        u"`mass_floors` du JSON est une liste vide. Aucun n'a ete cree."
    )
else:
    out.print_md(
        u"**{0}** plancher(s) lu(s), dont **{1}** sans face superieure "
        u"exploitable.".format(len(mass_floors), len(planchers_sans_contour))
    )

if erreurs:
    liste_md(
        u"Erreurs de lecture (detail dans le JSON)",
        [u"- `{0}` - {1} : {2}".format(e["id"], e["etape"], e["message"])
         for e in erreurs[:40]]
        + ([u"- ... et {0} autre(s)".format(len(erreurs) - 40)]
           if len(erreurs) > 40 else []),
    )

# --------------------------------------------------------------------------
# 7. Export JSON - hors OneDrive, hors WORK
# --------------------------------------------------------------------------

horodatage = datetime.datetime.now()
nom_maquette = u"".join(c for c in doc.Title if c.isalnum() or c in u"-_")
nom_defaut = u"audit_volumes_zone_{0}_{1}".format(
    nom_maquette, horodatage.strftime("%Y%m%d_%H%M"))

try:
    version_revit = u"{0} ({1})".format(
        doc.Application.VersionNumber, doc.Application.VersionBuild)
except Exception:
    version_revit = None

racine = OrderedDict()
racine["entete"] = OrderedDict([
    ("outil", u"audit_volumes_zone"),
    ("version", u"v1 - 2026-09-22 - non eprouve"),
    ("maquette", texte(doc.Title)),
    ("chemin_maquette", texte(doc.PathName)),
    ("revit", version_revit),
    ("date", horodatage.strftime("%Y-%m-%dT%H:%M:%S")),
    ("lecture_seule", True),
    ("collaborative", collaboratif),
    ("copie_detachee", detache),
    ("unites", OrderedDict([
        ("longueur", u"mm"), ("aire", u"m2"), ("volume", u"m3"),
        ("normale", u"vecteur unitaire, sans unite"),
        ("valeur_en_unite_interne", u"pieds Revit - voir valeur_affichee"),
    ])),
    ("repere", u"coordonnees internes du modele (origine interne) : celui de "
               u"la geometrie et de Level.ProjectElevation. Aucune altitude "
               u"ne derive de Level.Elevation."),
    ("classement_faces", OrderedDict([
        ("horizontale_si_abs_nz_superieur_a", NZ_HORIZONTALE),
        ("verticale_si_abs_nz_inferieur_a", NZ_VERTICALE),
        ("segment_xy_ecarte_si_plus_court_que_mm", TOL_SEGMENT_MM),
    ])),
    ("motif_nom", u"VOL__<REF_Zone>__<REF_Etage>__<CLS_Nature_volume>"),
    ("natures_liste_fermee", list(NATURES)),
    ("point_de_base_projet", lire_point_de_base("GetProjectBasePoint")),
    ("point_topographique", lire_point_de_base("GetSurveyPoint")),
    ("emplacement_partage", emplacement),
    ("niveaux", list(niveaux.values())),
])
racine["volumes"] = volumes
racine["mass_floors"] = mass_floors
racine["constats"] = OrderedDict([
    ("nb_volumes", len(volumes)),
    ("repartition_REF_Zone", OrderedDict(sorted(par_zone.items()))),
    ("repartition_REF_Etage", OrderedDict(sorted(par_etage.items()))),
    ("noms_non_conformes", [
        OrderedDict([("id", id_de(e)), ("family_name", texte(n)), ("defauts", d)])
        for e, n, d in non_conformes]),
    ("a_renommer_4e_segment_zero", [
        OrderedDict([("id", id_de(e)), ("family_name", texte(n))])
        for e, n in a_renommer]),
    ("natures_hors_liste_fermee", [
        OrderedDict([("id", id_de(e)), ("family_name", texte(n)),
                     ("valeur", v)])
        for e, n, v in natures_inconnues]),
    ("couples_zone_etage_en_double", [
        OrderedDict([("REF_Zone", c[0]), ("REF_Etage", c[1]),
                     ("ids", [id_de(e) for e, n in l])])
        for c, l in doublons_zone_etage]),
    ("sans_geometrie", [id_de(e) for e, n, m in sans_geometrie]),
    ("plus_d_un_solide", [id_de(e) for e, n, k in multi_solides]),
    ("sans_face_horizontale_haute", [id_de(e) for e, n in sans_haute]),
    ("avec_face_inclinee", [id_de(e) for e, n, k in avec_inclinee]),
    ("avec_face_non_plane", [id_de(e) for e, n, k in avec_non_plane]),
    ("non_in_situ", [id_de(e) for e, n in non_in_situ]),
    ("mass_floors_vide", len(mass_floors) == 0),
    # Le detail par volume est dans volumes[].surface_sol ; ici, les listes.
    ("CAR_Surface_sol", OrderedDict([
        ("guid", GUID_SURFACE_SOL),
        ("tolerance_m2", TOL_SURFACE_SOL_M2),
        ("nb_conformes", len(surface_ok)),
        ("en_ecart", [OrderedDict([("id", id_de(i)), ("family_name", texte(n)),
                                   ("ecart_m2", round(e, 6))])
                      for e, i, n, p, a in surface_ecart]),
        ("absent", [id_de(e) for e, n in surface_absente]),
        ("jamais_ecrit", [id_de(e) for e, n in surface_vide]),
        ("pas_une_surface", [id_de(e) for e, n, m in surface_mauvais_type]),
        ("contour_non_reconstruit", [id_de(e) for e, n, m in surface_sans_contour]),
        ("face_basse_inclinee", [id_de(i) for e, i, n, fb, a
                                 in face_basse_inclinee]),
    ])),
])
racine["erreurs"] = erreurs

# Les controles amont partent dans le JSON, avec le DETAIL et pas seulement
# le compte : une chaine en aval, ou une relecture dans six mois, doit
# pouvoir dire QUELS volumes, pas seulement combien.
controles["superposition_3d"]["couples"] = [
    OrderedDict([
        ("volume_commun_m3", vol),
        ("a", OrderedDict([("id", ia), ("family_name", texte(na))])),
        ("b", OrderedDict([("id", ib), ("family_name", texte(nb))])),
        ("boite_commune_mm", None if not boite else OrderedDict([
            ("xmin", boite[0]), ("ymin", boite[1]), ("zmin", boite[2]),
            ("xmax", boite[3]), ("ymax", boite[4]), ("zmax", boite[5])])),
    ])
    for vol, ia, na, ib, nb, boite in superpositions
]
controles["superposition_3d"]["couples_non_calculables"] = [
    OrderedDict([("a", ia), ("b", ib)])
    for ia, _na, ib, _nb in superpositions_indecises
]
controles["vide_dans_une_colonne"]["vides"] = [
    OrderedDict([
        ("jeu_mm", jeu), ("REF_Zone", zone),
        ("dessous", OrderedDict([("id", ib), ("family_name", texte(nb))])),
        ("dessus", OrderedDict([("id", ih), ("family_name", texte(nh))])),
    ])
    for jeu, zone, ib, nb, ih, nh in vides_colonne
]
controles["tranche_sous_le_metre"]["tranches"] = [
    OrderedDict([("hauteur_mm", h), ("id", i), ("family_name", texte(n))])
    for h, i, n in trop_basses
]
controles["superposition_3d"]["disponible"] = BooleanOperationsUtils is not None
racine["controles_ivion"] = controles


def demander_chemin():
    for _ in range(3):
        chemin = forms.save_file(file_ext="json", default_name=nom_defaut)
        if not chemin:
            return None
        bas = chemin.lower()
        if any(fragment in bas for fragment in FRAGMENTS_INTERDITS):
            forms.alert(
                u"Le JSON ne s'ecrit ni dans OneDrive ni sous WORK.\n\n"
                u"Chemin refuse :\n{0}\n\nChoisir un autre dossier.".format(chemin)
            )
            continue
        return chemin
    return None


chemin = demander_chemin()

if chemin:
    # un seul write() : le JSON est assemble en memoire puis ecrit d'un bloc
    # default=texte : un type .NET inattendu devient une chaine au lieu de
    # faire echouer l'export apres tout le calcul
    contenu = json.dumps(racine, ensure_ascii=False, indent=1, default=texte)
    f = io.open(chemin, "w", encoding="utf-8", newline="\n")
    try:
        f.write(contenu)
    finally:
        f.close()
    out.print_md(u"## Export\n{0} volume(s), {1} plancher(s) de volume ecrits "
                 u"dans `{2}`".format(len(volumes), len(mass_floors), chemin))

    # LE RAPPORT SE SAUVE AUSSI, au meme endroit et sous le meme nom de base.
    # Jusqu'au 2026-09-25, tout ce qui s'affiche ici mourait avec la fenetre :
    # le JSON porte la geometrie, pas le diagnostic. Or c'est le diagnostic
    # qu'on relit - les superpositions, les vides, les noms non conformes.
    # save_contents ecrit le HTML de la fenetre telle qu'elle est a cet
    # instant : cet appel doit donc rester LE DERNIER du script.
    chemin_html = chemin
    if chemin_html.lower().endswith(u".json"):
        chemin_html = chemin_html[:-5]
    chemin_html += u".html"
    try:
        out.save_contents(chemin_html)
        out.print_md(u"Rapport : `{0}`".format(chemin_html))
    except Exception as err:
        out.print_md(
            u"> ⚠ **Rapport non sauve** : `{0}`\n>\n"
            u"> Le JSON, lui, est ecrit. Recopier la fenetre a la main si ce "
            u"diagnostic doit etre conserve.".format(texte(err)))
else:
    out.print_md(u"## Export\n*Annule - ni le JSON ni le rapport ne sont "
                 u"ecrits. La synthese ci-dessus reste valable, mais elle "
                 u"disparaitra avec cette fenetre.*")
