# -*- coding: utf-8 -*-
"""bimflow_geometrie - lire la geometrie d'un volume de zone dans Revit.

UN SEUL ENDROIT lit les faces d'un volume. Jusqu'au 2026-09-28, ce code
vivait dans le bouton AuditVolumes ; il en a ete extrait TEL QUEL pour que
le bouton MajParamsVolumes, qui ecrit CAR_Surface_sol, lise la meme chose
que l'audit qui la controle :

    Revit --faces_du_volume()--> faces (format du JSON d'audit)
          --bimflow_contour.contour_du_volume()--> contour, aire

Un instrument de mesure et l'operation mesuree qui divergent, c'est la
cause de la quasi-totalite des defauts de bimflow : d'ou ce point de
passage unique.

Toutes les coordonnees sont celles de la GEOMETRIE (coordonnees internes du
modele), converties en mm ; les aires en m2.

Ce module importe l'API Revit : il ne tourne que dans Revit, contrairement a
bimflow_contour, qui tourne aussi sous CPython.

bimflow - Keovia Solutions inc. - 2026-09-28
"""

from collections import OrderedDict

from Autodesk.Revit.DB import (
    Options,
    ViewDetailLevel,
    GeometryInstance,
    Solid,
    Face,
    PlanarFace,
    Line,
    StorageType,
    UV,
)

# --------------------------------------------------------------------------
# Identite du parametre ecrit et controle - SOURCE :
# shared_parameters/keovia_socle_parametres.txt. Ne jamais remplacer ce GUID.
# --------------------------------------------------------------------------

GUID_SURFACE_SOL = "65b6caa6-9169-4029-840a-73a221bead34"   # CAR_Surface_sol

# --------------------------------------------------------------------------
# Reglages de lecture - publies dans l'en-tete du JSON d'audit
# --------------------------------------------------------------------------

# Classement des faces sur la composante Z de la normale unitaire.
NZ_HORIZONTALE = 0.999      # |nz| au-dessus : horizontale
NZ_VERTICALE = 0.001        # |nz| au-dessous : verticale ; entre les deux : inclinee

# Segment projete en XY plus court que ceci : arete verticale, ecartee.
TOL_SEGMENT_MM = 1.0

# Arrondi des coordonnees publiees.
DECIMALES_MM = 1

# --------------------------------------------------------------------------
# Unites
# --------------------------------------------------------------------------

MM_PAR_PIED = 304.8
M2_PAR_PIED2 = 0.09290304
M3_PAR_PIED3 = 0.028316846592

try:
    from Autodesk.Revit.DB import UnitUtils, UnitTypeId
    _UNITE_MM = UnitTypeId.Millimeters
    _UNITE_M2 = UnitTypeId.SquareMeters
except Exception:
    UnitUtils = None
    _UNITE_MM = None
    _UNITE_M2 = None


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


def m2_vers_interne(valeur_m2):
    """m2 -> pieds carres, l'unite dans laquelle Revit stocke une Surface."""
    if UnitUtils is not None and _UNITE_M2 is not None:
        try:
            return UnitUtils.ConvertToInternalUnits(valeur_m2, _UNITE_M2)
        except Exception:
            pass
    return valeur_m2 / M2_PAR_PIED2


def interne_vers_m2(valeur_pieds2):
    """Pieds carres -> m2, SANS arrondi : sert aux comparaisons."""
    if valeur_pieds2 is None:
        return None
    if UnitUtils is not None and _UNITE_M2 is not None:
        try:
            return UnitUtils.ConvertFromInternalUnits(valeur_pieds2, _UNITE_M2)
        except Exception:
            pass
    return valeur_pieds2 * M2_PAR_PIED2


# --------------------------------------------------------------------------
# Parametres - identite par GUID, jamais par nom (fiche R08)
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


def est_une_surface(p):
    """(True, None) si le parametre est de type Surface, sinon (False, motif).

    Le stockage Double ne suffit pas : une longueur ou un volume sont aussi
    des Double, et y ecrire des pieds carres serait faux sans bruit."""
    if p.StorageType != StorageType.Double:
        return False, u"parametre non numerique ({0})".format(p.StorageType)
    try:
        from Autodesk.Revit.DB import SpecTypeId
        spec = p.Definition.GetDataType()
    except Exception as err:
        return False, u"type de donnees illisible : {0}".format(err)
    if spec != SpecTypeId.Area:
        return False, u"parametre qui n'est pas une Surface ({0})".format(
            spec.TypeId if spec is not None else None)
    return True, None


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------

OPTIONS = Options()
OPTIONS.ComputeReferences = False
OPTIONS.IncludeNonVisibleObjects = False
OPTIONS.DetailLevel = ViewDetailLevel.Fine


def classe_de(nz):
    if abs(nz) > NZ_HORIZONTALE:
        return u"HORIZONTALE_HAUTE" if nz > 0 else u"HORIZONTALE_BASSE"
    if abs(nz) < NZ_VERTICALE:
        return u"VERTICALE"
    return u"INCLINEE"


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


def faces_du_volume(pleins, sur_erreur=None):
    """Les faces des solides pleins, decrites comme dans le JSON d'audit, et
    DANS LE MEME ORDRE - solide par solide, face par face. L'ordre n'est pas
    un detail : c'est lui qui designe les sommets canoniques du contour.

    Une face illisible est passee a sur_erreur(etiquette, erreur) et ecartee ;
    sans sur_erreur, l'erreur remonte."""
    faces = []
    for i_s, solide in enumerate(pleins):
        for i_f, face in enumerate(solide.Faces):
            try:
                faces.append(decrire_face(face, i_s, i_f))
            except Exception as err:
                if sur_erreur is None:
                    raise
                sur_erreur(u"face {0}.{1}".format(i_s, i_f), err)
    return faces
