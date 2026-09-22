# -*- coding: utf-8 -*-
"""audit_volumes_zone - Audit des volumes de zone.

Ecrit le 2026-09-22.

OBJET. Extraire l'identite et la geometrie de tous les volumes de la
maquette courante (categorie Volumes, OST_Mass) vers un JSON, pour analyse
hors Revit : controle du nommage, alimentation du decoupage site_model
Ivion, surfaces par niveau.

#############################################################################
# STATUT : EXECUTE UNE FOIS dans Revit, le 2026-09-22 - 27 volumes,         #
# 9 zones, deux separations non horizontales. La sortie a ete exploitee par #
# la chaine site_model (tools/sitemodel), qui en a tire une partition en    #
# plan fermee a 0,00 m2 pres pour 326,2 m2.                                 #
# Une execution n'est pas une garantie : l'outil reste au panneau Dev tant  #
# qu'il n'a pas servi plusieurs fois, et le JSON de cette execution n'est   #
# pas encore verse a tools/sitemodel/exemples/.                             #
#############################################################################

LECTURE SEULE - aucune transaction n'est ouverte, rien n'est ecrit dans la
maquette. La seule ecriture est le fichier JSON, hors du modele.

HYPOTHESES POSEES A L'ECRITURE. L'execution du 2026-09-22 a prouve que le
script tourne et que les contours sont reconstructibles ; elle n'a pas
statue une a une sur les quatre hypotheses ci-dessous, qui se lisent dans le
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

Motif de nom attendu - quatre segments separes par un DOUBLE underscore :
    VOL__<REF_Zone>__<REF_Etage>__<REF_attribut>
    ex. VOL__JU_Bj-Fj_1j-5j__FLOOR_2__0
Le decoupage se fait sur "__" et doit rendre exactement 4 segments. Un
underscore simple a l'interieur d'un segment (JU_Bj-Fj_1j-5j, FLOOR_2) n'est
jamais un separateur. REF_attribut vaut "0" ; toute autre valeur est
probablement un suffixe de copie pose par Revit - signalee, jamais corrigee.

Ce que le JSON contient :
  - en-tete : maquette, unites, repere, points de base, niveaux ;
  - volumes : identite, parametres REF_ / CLS_ (meme vides), boite
    englobante, volume et surface bruts, solides et faces classees ;
  - mass_floors : planchers de volume EXISTANTS (aucun n'est cree), avec
    volume hote, niveau et contour XY de la face superieure.

Repere : toutes les coordonnees sont celles de la GEOMETRIE (coordonnees
internes du modele). Les altitudes ne passent jamais par Level.Elevation -
sur The Study, Level.Elevation et la geometrie different de 29 065 mm
(R16 §1.1). Les niveaux sont publies avec les deux lectures, pour controle.

bimflow - volumes de zone, audit - Keovia Solutions inc.
v1 - 2026-09-22 : NON EPROUVE (jamais execute dans Revit).
"""

__title__ = "Audit\nvolumes zone"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES DE L'AUDIT - a ajuster ici, pas dans le corps du script
# --------------------------------------------------------------------------

# Parametres releves sur chaque volume (instance ET type), meme vides.
PREFIXES_PARAMETRES = ("REF_", "CLS_")

# Classement des faces sur la composante Z de la normale unitaire.
NZ_HORIZONTALE = 0.999      # |nz| au-dessus : horizontale
NZ_VERTICALE = 0.001        # |nz| au-dessous : verticale ; entre les deux : inclinee

# Segment projete en XY plus court que ceci : arete verticale, ecartee.
TOL_SEGMENT_MM = 1.0

# Arrondi des coordonnees publiees.
DECIMALES_MM = 1

# Une maquette collaborative doit etre auditee sur une COPIE DETACHEE.
# Ne passer a True qu'en connaissance de cause.
AUTORISER_NON_DETACHE = False

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
        ATTRIBUT_DEFAUT as ATTRIBUT_ATTENDU,
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
    FilteredWorksetCollector,
    WorksetKind,
    BuiltInCategory,
    BuiltInParameter,
    FamilyInstance,
    Level,
    Options,
    ViewDetailLevel,
    GeometryInstance,
    Solid,
    Face,
    PlanarFace,
    Line,
    StorageType,
    UV,
    XYZ,
)

doc = revit.doc
out = script.get_output()

# --------------------------------------------------------------------------
# Petits outils
# --------------------------------------------------------------------------

MM_PAR_PIED = 304.8
M2_PAR_PIED2 = 0.09290304
M3_PAR_PIED3 = 0.028316846592

try:
    from Autodesk.Revit.DB import UnitUtils, UnitTypeId
    _UNITE_MM = UnitTypeId.Millimeters
except Exception:
    UnitUtils = None
    _UNITE_MM = None


def mm(valeur):
    """Pieds decimaux (unite interne Revit) -> millimetres."""
    if valeur is None:
        return None
    if UnitUtils is not None and _UNITE_MM is not None:
        try:
            return UnitUtils.ConvertFromInternalUnits(valeur, _UNITE_MM)
        except Exception:
            pass
    return valeur * MM_PAR_PIED


def rmm(valeur_pieds):
    """Pieds -> mm arrondis, pret pour le JSON."""
    v = mm(valeur_pieds)
    return None if v is None else round(v, DECIMALES_MM)


def m2(valeur_pieds2):
    return None if valeur_pieds2 is None else round(valeur_pieds2 * M2_PAR_PIED2, 4)


def m3(valeur_pieds3):
    return None if valeur_pieds3 is None else round(valeur_pieds3 * M3_PAR_PIED3, 4)


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


def classe_de(nz):
    if abs(nz) > NZ_HORIZONTALE:
        return u"HORIZONTALE_HAUTE" if nz > 0 else u"HORIZONTALE_BASSE"
    if abs(nz) < NZ_VERTICALE:
        return u"VERTICALE"
    return u"INCLINEE"


# --------------------------------------------------------------------------
# 0. Garde-fous : document, copie detachee, sous-projets fermes
# --------------------------------------------------------------------------

if doc.IsFamilyDocument:
    forms.alert(u"Document famille : rien a auditer.", exitscript=True)

collaboratif = bool(doc.IsWorkshared)
detache = None
try:
    detache = bool(doc.IsDetached)
except Exception:
    detache = None

if collaboratif and detache is not True and not AUTORISER_NON_DETACHE:
    forms.alert(
        u"Maquette collaborative, et ce n'est pas une copie detachee.\n\n"
        u"L'audit est en lecture seule, mais la discipline bimflow veut qu'il "
        u"tourne sur une copie detachee. Rouvrir la maquette avec "
        u"\"Detacher du fichier central\", puis relancer.\n\n"
        u"(Contournement : AUTORISER_NON_DETACHE en tete de script.)",
        exitscript=True,
    )

avertissements = []

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


OPTIONS = Options()
OPTIONS.ComputeReferences = False
OPTIONS.IncludeNonVisibleObjects = False
OPTIONS.DetailLevel = ViewDetailLevel.Fine


def parcourir_geometrie(element):
    """(solides pleins, faces libres, nb solides vides, autres types).

    Leve si get_Geometry leve : l'appelant consigne l'erreur."""
    pleins = []
    faces_libres = []
    vides = 0
    autres = []
    geo = element.get_Geometry(OPTIONS)
    if geo is None:
        return pleins, faces_libres, vides, autres
    pile = list(geo)
    while pile:
        g = pile.pop(0)
        if isinstance(g, Solid):
            if g.Volume > 1e-9:
                pleins.append(g)
            elif g.Faces.Size > 0:
                # solide de volume nul mais porteur de faces (plancher de volume ?)
                vides += 1
                for f in g.Faces:
                    faces_libres.append(f)
            else:
                vides += 1
        elif isinstance(g, GeometryInstance):
            pile.extend(list(g.GetInstanceGeometry()))
        elif isinstance(g, Face):
            faces_libres.append(g)
        else:
            autres.append(g.GetType().Name)
    return pleins, faces_libres, vides, autres


def centre_uv(face):
    bb = face.GetBoundingBox()
    return UV((bb.Min.U + bb.Max.U) / 2.0, (bb.Min.V + bb.Max.V) / 2.0)


def normale_de(face):
    """(XYZ unitaire, methode)."""
    if isinstance(face, PlanarFace):
        return face.FaceNormal.Normalize(), u"FaceNormal"
    return face.ComputeNormal(centre_uv(face)).Normalize(), u"ComputeNormal_centre_uv"


def boucle_exterieure(face, normale):
    """(CurveLoop exterieure, toutes les boucles, methode).

    Les boucles sont lues UNE fois : GetEdgesAsCurveLoops rend des objets
    neufs a chaque appel, on ne peut donc pas comparer d'un appel a l'autre."""
    boucles = list(face.GetEdgesAsCurveLoops())
    if not boucles:
        return None, boucles, None
    if len(boucles) == 1:
        return boucles[0], boucles, u"unique"
    if isinstance(face, PlanarFace):
        for b in boucles:
            try:
                if b.IsCounterclockwise(normale):
                    return b, boucles, u"sens_trigo_autour_normale"
            except Exception:
                pass
    plus_longue = max(boucles, key=lambda b: b.GetExactLength())
    return plus_longue, boucles, u"plus_longue"


def points_de_courbe(courbe):
    """(points, droite ?). Un arc est tessele."""
    if isinstance(courbe, Line):
        return [courbe.GetEndPoint(0), courbe.GetEndPoint(1)], True
    return list(courbe.Tessellate()), False


def segments_xy(boucle):
    """Aretes de la boucle projetees en XY, sans les aretes verticales et
    sans doublon (le haut et le bas d'une face verticale se projettent sur le
    meme segment)."""
    segments = []
    vus = set()
    nb_aretes = 0
    ecartes = 0
    tesseles = 0
    for courbe in boucle:
        nb_aretes += 1
        pts, droite = points_de_courbe(courbe)
        if not droite:
            tesseles += 1
        for a, b in zip(pts[:-1], pts[1:]):
            xa, ya, xb, yb = mm(a.X), mm(a.Y), mm(b.X), mm(b.Y)
            if ((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5 < TOL_SEGMENT_MM:
                ecartes += 1
                continue
            pa = (round(xa, DECIMALES_MM), round(ya, DECIMALES_MM))
            pb = (round(xb, DECIMALES_MM), round(yb, DECIMALES_MM))
            cle = (min(pa, pb), max(pa, pb))
            if cle in vus:
                continue
            vus.add(cle)
            segments.append([[pa[0], pa[1]], [pb[0], pb[1]]])
    return segments, nb_aretes, ecartes, tesseles


def anneau_xy(boucle):
    """Contour ferme projete en XY : [[x, y], ...], premier point repete."""
    pts = []
    for courbe in boucle:
        points, droite = points_de_courbe(courbe)
        for p in points[:-1]:
            pts.append([rmm(p.X), rmm(p.Y)])
    if pts:
        pts.append(list(pts[0]))
    return pts


def decrire_face(face, indice_solide, indice_face):
    d = OrderedDict()
    d["solide"] = indice_solide
    d["face"] = indice_face
    planaire = isinstance(face, PlanarFace)
    d["planaire"] = planaire
    n, methode = normale_de(face)
    d["normale"] = [round(n.X, 6), round(n.Y, 6), round(n.Z, 6)]
    if not planaire:
        d["normale_methode"] = methode
    classe = classe_de(n.Z)
    d["classe"] = classe
    d["aire_m2"] = m2(face.Area)
    if classe.startswith(u"HORIZONTALE"):
        if planaire:
            d["altitude_mm"] = rmm(face.Origin.Z)
        else:
            d["altitude_mm"] = rmm(face.Evaluate(centre_uv(face)).Z)
            d["altitude_methode"] = u"centre_uv_face_non_plane"
    elif classe == u"VERTICALE":
        boucle, boucles, methode_b = boucle_exterieure(face, n)
        d["nb_boucles"] = len(boucles)
        if len(boucles) > 1:
            d["boucle_exterieure_methode"] = methode_b
        if boucle is not None:
            segs, nb_aretes, ecartes, tesseles = segments_xy(boucle)
            d["segments_xy"] = segs
            d["nb_aretes_boucle"] = nb_aretes
            d["nb_aretes_verticales_ecartees"] = ecartes
            if tesseles:
                d["nb_courbes_tesselees"] = tesseles
    return d


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
attributs_hors_norme = []   # (eid, nom, attribut)
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


def noter_erreur(eid, etape, err):
    erreurs.append(OrderedDict([
        ("id", id_de(eid)), ("etape", etape), ("message", texte(err)),
    ]))


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
        ("REF_attribut", segments[3] if segments else None),
    ])
    if defauts:
        v["defauts_nom"] = defauts
        non_conformes.append((eid, family_name, defauts))
    if segments is not None:
        zone, etage, attribut = segments[1], segments[2], segments[3]
        par_zone[zone] = par_zone.get(zone, 0) + 1
        par_etage[etage] = par_etage.get(etage, 0) + 1
        par_zone_etage.setdefault((zone, etage), []).append((eid, family_name))
        if attribut != ATTRIBUT_ATTENDU:
            attributs_hors_norme.append((eid, family_name, attribut))

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

    v["nb_solides"] = len(pleins)
    if vides:
        v["nb_solides_vides"] = vides
    if autres:
        v["autres_geometries"] = sorted(set(autres))
    v["volume_solides_m3"] = m3(sum([s.Volume for s in pleins])) if pleins else None

    for i_s, solide in enumerate(pleins):
        for i_f, face in enumerate(solide.Faces):
            try:
                faces.append(decrire_face(face, i_s, i_f))
            except Exception as err:
                noter_erreur(eid, u"face {0}.{1}".format(i_s, i_f), err)
    v["faces"] = faces

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
    u"Noms non conformes au motif `VOL__<REF_Zone>__<REF_Etage>__<REF_attribut>`",
    [u"- {0} `{1}` : {2}".format(lien(e), n, u" ; ".join(d))
     for e, n, d in non_conformes],
)
liste_md(
    u"Attributs differents de \"{0}\" - copie Revit probable, rien n'est "
    u"corrige".format(ATTRIBUT_ATTENDU),
    [u"- {0} `{1}` : attribut **`{2}`**".format(lien(e), n, a)
     for e, n, a in attributs_hors_norme],
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
    ("motif_nom", u"VOL__<REF_Zone>__<REF_Etage>__<REF_attribut>"),
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
    ("attributs_differents_de_0", [
        OrderedDict([("id", id_de(e)), ("family_name", texte(n)), ("attribut", a)])
        for e, n, a in attributs_hors_norme]),
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
])
racine["erreurs"] = erreurs


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
else:
    out.print_md(u"## Export\n*Annule - le JSON n'est pas ecrit. La synthese "
                 u"ci-dessus reste valable.*")
