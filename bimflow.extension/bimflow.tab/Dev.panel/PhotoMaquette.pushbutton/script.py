# -*- coding: utf-8 -*-
"""BLEU - lecture seule : aucune transaction, rien n'est ecrit dans la
maquette. La seule ecriture est le fichier JSON, hors du modele.

Photo maquette - etat du modele actif a un instant, en un fichier JSON :
  en-tete ...... modele, chemin, date, version de Revit, utilisateur, etat
                 collaboratif, transformation interne -> partage retenue ;
  niveaux ...... nom, Id, elevation (mm) par rapport au point de base du
                 projet, REF_Batiment, REF_Etage ;
  quadrillages . nom exact, Id, extremites en coordonnees PARTAGEES (m),
                 orientation (deg), type ;
  volumes ...... (categorie Volumes) nom, famille, Id, REF_Zone, REF_Etage,
                 REF_Batiment, CLS_Nature_volume, REF_Id, boite englobante ;
  pieces ....... numero, nom, niveau, surface, point de localisation ;
  sous_projets . nom, nombre d'elements ;
  liens ........ nom, type, epingle ou non.

#############################################################################
# STATUT : NON EPROUVE - ecrit le 2026-10-12, jamais execute dans Revit.    #
# Recette prevue : thestudy_G_AN puis thestudy_G_VZ. Les comptes obtenus    #
# s'inscrivent dans docs\\photo_maquette.md, section Recette.                #
#############################################################################

RIEN N'EST DEDUIT D'UN NOM. Les parametres REF_ / CLS_ sont lus par GUID,
et les GUID viennent du socle versionne (shared_parameters\\
keovia_socle_parametres.txt), cherches par NOM de parametre : aucun GUID
n'est ecrit dans ce fichier. Un parametre absent de l'element vaut null ;
present sans valeur, null aussi ; une lecture qui leve une exception vaut
NON_LU. Les trois cas sont distingues dans le JSON (statut) et comptes au
rapport.

SORTIE. Le dossier est demande a CHAQUE execution (decision Bruno du
2026-10-12). Le dernier choisi est rappele dans le titre de la boite, lu
dans %APPDATA%\\bimflow\\photo_maquette.json - un simple rappel, jamais
utilise sans etre choisi. Annuler la boite : rien n'est ecrit. Le fichier s'appelle
<modele>_<AAAA-MM-JJ_HHMM>.json et n'ecrase jamais une photo precedente.
Le chemin complet s'affiche en fin de rapport.

REPERES.
  - elevation_pbp_mm = Level.ProjectElevation - Z interne du point de base
    du projet. Level.Elevation, qui compte depuis la base d'elevation du
    TYPE de niveau (R10, docs\\niveaux.md §1.1), est publie a cote, avec
    cette base, pour controle - il n'est pas la valeur demandee.
  - Coordonnees partagees : ActiveProjectLocation.GetTotalTransform(). Le
    SENS de cette transformation (directe ou inverse) n'est pas suppose :
    il est choisi sur le point topographique et le point de base, dont
    Revit donne les deux positions. Aucun sens sous la tolerance : les
    coordonnees partagees valent null, et le rapport le dit.
  - Orientation d'un quadrillage : azimut de la ligne debut -> fin dans le
    repere partage, 0 = nord partage, sens horaire, en degres [0, 360).
    direction_deg la ramene dans [0, 180). Un quadrillage en arc n'a pas
    d'orientation (null, courbe = "arc").
  - Boites englobantes et points de pieces : coordonnees INTERNES du
    modele, en mm (repere de la geometrie) ; le point de piece est aussi
    publie en partage, en m.

MAQUETTE CENTRALE. Lecture seule : rien a confirmer. Mais la photo decrit
l'etat SYNCHRONISE a l'instant de la lecture ; le travail non synchronise
des autres n'y est pas. Le constat part dans l'en-tete du JSON.

SOUS-PROJETS FERMES. Leurs elements ne sont pas charges : ils manquent a
TOUS les comptes. Ils sont detectes et annonces avant tout chiffre, et leur
nombre d'elements vaut null.

bimflow - Keovia Solutions inc. - v1 2026-10-12
"""

__title__ = "Photo\nmaquette"
__author__ = "Keovia Solutions inc."

VERSION = u"2026-10-12a"

# Ecart admis entre la position partagee annoncee par Revit et celle que la
# transformation calcule, sur les points de controle, en mm.
TOL_TRANSFORMATION_MM = 1.0

# pyRevit 6.5.5 / IronPython 3.4 (IPY342) - pas de f-string, pas de shebang.
# Regles tenues ici :
# - aucune Transaction, aucun emprunt, aucune synchronisation ;
# - ElementId.Value (WorksetId.IntegerValue seule exception) ;
# - collecteurs MATERIALISES (ToElementIds) avant toute resolution.

import datetime
import os
from collections import OrderedDict

import System

from pyrevit import revit, forms, script

from Autodesk.Revit.DB import (
    BasePoint, BuiltInCategory, BuiltInParameter, Element,
    ElementWorksetFilter, FilteredElementCollector, FilteredWorksetCollector,
    Grid, ImportInstance, Level, LocationPoint, PointCloudInstance,
    RevitLinkInstance, RevitLinkType, StorageType, WorksetKind,
)

import bimflow_photo as photo

doc = revit.doc
app = doc.Application
sortie = script.get_output()

PIED_MM = photo.PIED_MM
PIED_M = PIED_MM / 1000.0
PIED2_M2 = 0.09290304


# --------------------------------------------------------------------------
# Petits lecteurs
# --------------------------------------------------------------------------

def id_de(eid):
    try:
        return int(eid.Value)
    except Exception:
        return None


def nom_de(el):
    """Element.Name, y compris sur les types ou la propriete Python echoue."""
    if el is None:
        return None
    try:
        return el.Name
    except Exception:
        pass
    try:
        return Element.Name.GetValue(el)
    except Exception:
        return photo.NON_LU


def mm(v):
    return None if v is None else round(v * PIED_MM, 1)


def point_mm(p):
    if p is None:
        return None
    return OrderedDict([("x", mm(p.X)), ("y", mm(p.Y)), ("z", mm(p.Z))])


def point_m(p):
    if p is None:
        return None
    return OrderedDict([("x", round(p.X * PIED_M, 4)),
                        ("y", round(p.Y * PIED_M, 4)),
                        ("z", round(p.Z * PIED_M, 4))])


def ids(collecteur):
    return list(collecteur.ToElementIds())


GUIDS_CACHE = {}


def guid(texte):
    g = GUIDS_CACHE.get(texte)
    if g is None:
        g = System.Guid(texte)
        GUIDS_CACHE[texte] = g
    return g


def lire_parametre(el, guid_texte):
    """Parametre partage lu par GUID, instance puis type.

    Rend {valeur, statut, porteur}. Rien n'est deduit : absent -> null."""
    res = OrderedDict([("valeur", None), ("statut", photo.ABSENT),
                       ("porteur", None)])
    try:
        g = guid(guid_texte)
        p = el.get_Parameter(g)
        porteur = u"instance"
        if p is None:
            type_id = el.GetTypeId()
            t = doc.GetElement(type_id) if type_id is not None else None
            if t is not None:
                p = t.get_Parameter(g)
                porteur = u"type"
        if p is None:
            return res
        res["porteur"] = porteur
        if not p.HasValue:
            res["statut"] = photo.VIDE
            return res
        if p.StorageType == StorageType.String:
            v = p.AsString()
        else:
            v = p.AsValueString()
        if v is None or v == u"":
            res["statut"] = photo.VIDE
            return res
        res["valeur"] = v
        res["statut"] = photo.LU
    except Exception as err:
        res["valeur"] = photo.NON_LU
        res["statut"] = photo.ILLISIBLE
        res["erreur"] = u"{0}".format(err)
    return res


def parametres(el, guids):
    d = OrderedDict()
    for nom, g in guids.items():
        d[nom] = lire_parametre(el, g)
    return d


def valeurs_a_plat(enregistrement, params):
    """Recopie la valeur de chaque parametre au premier niveau, pour un JSON
    directement lisible ; le detail (statut, porteur) reste dans
    `parametres`."""
    for nom, p in params.items():
        enregistrement[nom] = p["valeur"]


signalements = []


def signaler(texte):
    signalements.append(texte)


# --------------------------------------------------------------------------
# 0. Etat du document, sous-projets fermes - AVANT tout chiffre
# --------------------------------------------------------------------------

collaboratif = bool(doc.IsWorkshared)
detache = None
try:
    detache = bool(doc.IsDetached)
except Exception:
    detache = None
centrale = collaboratif and detache is not True

ss_projets_user = []
fermes = []
if collaboratif:
    try:
        ss_projets_user = list(FilteredWorksetCollector(doc)
                               .OfKind(WorksetKind.UserWorkset))
        fermes = [w.Name for w in ss_projets_user if not w.IsOpen]
    except Exception as err:
        signaler(u"Etat des sous-projets ILLISIBLE : {0}".format(err))

sortie.print_md(u"# Photo maquette - {0}".format(doc.Title))
if fermes:
    sortie.print_md(
        u"**ATTENTION - {0} sous-projet(s) ferme(s)** : leurs elements ne sont "
        u"pas charges et MANQUENT a tous les comptes ci-dessous : {1}".format(
            len(fermes), u", ".join(fermes)))
    signaler(u"{0} sous-projet(s) ferme(s), elements absents de la photo : "
             u"{1}".format(len(fermes), u", ".join(fermes)))
if centrale:
    sortie.print_md(
        u"*Maquette centrale (non detachee) : la photo decrit l'etat "
        u"synchronise a l'instant de la lecture.*")

# --------------------------------------------------------------------------
# 1. Socle : GUID lus par nom
# --------------------------------------------------------------------------

dossier_lib = os.path.dirname(os.path.abspath(photo.__file__))
fichier_socle = photo.chemin_socle(dossier_lib)
socle = OrderedDict()
try:
    socle = photo.lire_socle(fichier_socle)
except Exception as err:
    signaler(u"Socle de parametres ILLISIBLE ({0}) : {1} - aucun parametre "
             u"REF_/CLS_ ne sera lu".format(fichier_socle, err))
guids_niveau, manque_n = photo.guids_requis(socle, photo.PARAMS_NIVEAU)
guids_volume, manque_v = photo.guids_requis(socle, photo.PARAMS_VOLUME)
for nom in sorted(set(manque_n + manque_v)):
    signaler(u"`{0}` absent du socle : non lu, champ null partout".format(nom))

# --------------------------------------------------------------------------
# 2. Reperes : point de base, point topographique, transformation
# --------------------------------------------------------------------------


def lire_bp(methode):
    try:
        return getattr(BasePoint, methode)(doc)
    except Exception as err:
        signaler(u"BasePoint.{0} illisible : {1}".format(methode, err))
        return None


pbp = lire_bp("GetProjectBasePoint")
topo = lire_bp("GetSurveyPoint")

z_pbp = None
if pbp is not None:
    try:
        z_pbp = pbp.Position.Z
    except Exception as err:
        signaler(u"Position du point de base illisible : {0}".format(err))

transfo = None
sens_retenu = None
motif_transfo = None
residus = OrderedDict()
try:
    total = doc.ActiveProjectLocation.GetTotalTransform()
    candidats_t = OrderedDict([(u"directe", total),
                               (u"inverse", total.Inverse)])
    candidats = []
    for nom_c, t in candidats_t.items():
        pire = None
        for bp in (topo, pbp):
            if bp is None:
                continue
            try:
                calc = t.OfPoint(bp.Position)
                ann = bp.SharedPosition
                d = calc.DistanceTo(ann) * PIED_MM
            except Exception:
                continue
            pire = d if pire is None else max(pire, d)
        residus[nom_c] = None if pire is None else round(pire, 3)
        candidats.append((nom_c, pire))
    sens_retenu, info = photo.choisir_sens(candidats, TOL_TRANSFORMATION_MM)
    if sens_retenu is not None:
        transfo = candidats_t[sens_retenu]
    else:
        motif_transfo = info
except Exception as err:
    motif_transfo = u"GetTotalTransform illisible : {0}".format(err)
if transfo is None:
    signaler(u"Transformation interne -> partage NON ETABLIE ({0}) : "
             u"coordonnees partagees null".format(motif_transfo))


def partage_m(p):
    if p is None or transfo is None:
        return None
    try:
        return point_m(transfo.OfPoint(p))
    except Exception:
        return None


def repere(bp):
    if bp is None:
        return None
    r = OrderedDict([("id", id_de(bp.Id))])
    try:
        r["position_interne_mm"] = point_mm(bp.Position)
    except Exception:
        r["position_interne_mm"] = photo.NON_LU
    try:
        r["position_partagee_m"] = point_m(bp.SharedPosition)
    except Exception:
        r["position_partagee_m"] = photo.NON_LU
    return r


# --------------------------------------------------------------------------
# 3. Niveaux
# --------------------------------------------------------------------------

niveaux = []
for eid in ids(FilteredElementCollector(doc).OfClass(Level)
               .WhereElementIsNotElementType()):
    lvl = doc.GetElement(eid)
    if lvl is None:
        continue
    n = OrderedDict([("nom", nom_de(lvl)), ("id", id_de(eid))])
    z_proj = None
    try:
        z_proj = lvl.ProjectElevation
    except Exception:
        pass
    n["elevation_pbp_mm"] = (mm(z_proj - z_pbp)
                             if z_proj is not None and z_pbp is not None
                             else None)
    n["project_elevation_mm"] = mm(z_proj)
    try:
        n["level_elevation_mm"] = mm(lvl.Elevation)
    except Exception:
        n["level_elevation_mm"] = photo.NON_LU
    base = None
    try:
        t = doc.GetElement(lvl.GetTypeId())
        pb = t.get_Parameter(BuiltInParameter.LEVEL_RELATIVE_BASE_TYPE)
        if pb is not None:
            base = {0: u"point de base du projet",
                    1: u"point topographique"}.get(pb.AsInteger(),
                                                   pb.AsValueString())
    except Exception:
        base = photo.NON_LU
    n["base_elevation_type"] = base
    params = parametres(lvl, guids_niveau)
    valeurs_a_plat(n, params)
    n["parametres"] = params
    niveaux.append(n)
niveaux.sort(key=lambda n: (n["elevation_pbp_mm"] is None,
                            n["elevation_pbp_mm"], n["nom"]))

# --------------------------------------------------------------------------
# 4. Quadrillages
# --------------------------------------------------------------------------

quadrillages = []
for eid in ids(FilteredElementCollector(doc).OfClass(Grid)
               .WhereElementIsNotElementType()):
    g = doc.GetElement(eid)
    if g is None:
        continue
    q = OrderedDict([("nom", nom_de(g)), ("id", id_de(eid))])
    debut = fin = None
    courbe = None
    try:
        c = g.Curve
        debut = c.GetEndPoint(0)
        fin = c.GetEndPoint(1)
        courbe = u"arc" if g.IsCurved else u"ligne"
    except Exception as err:
        signaler(u"Quadrillage {0} : courbe illisible ({1})".format(
            q["nom"], err))
    q["courbe"] = courbe
    q["debut_partage_m"] = partage_m(debut)
    q["fin_partage_m"] = partage_m(fin)
    q["debut_interne_mm"] = point_mm(debut)
    q["fin_interne_mm"] = point_mm(fin)
    az = None
    if courbe == u"ligne" and q["debut_partage_m"] and q["fin_partage_m"]:
        a, b = q["debut_partage_m"], q["fin_partage_m"]
        az = photo.azimut_deg(b["x"] - a["x"], b["y"] - a["y"])
    q["orientation_deg"] = az
    q["direction_deg"] = photo.direction_deg(az)
    az_int = None
    if courbe == u"ligne" and debut is not None and fin is not None:
        az_int = photo.azimut_deg(fin.X - debut.X, fin.Y - debut.Y)
    q["orientation_interne_deg"] = az_int
    try:
        q["type"] = nom_de(doc.GetElement(g.GetTypeId()))
    except Exception:
        q["type"] = photo.NON_LU
    quadrillages.append(q)
quadrillages.sort(key=lambda q: q["nom"] or u"")

# --------------------------------------------------------------------------
# 5. Volumes (categorie Volumes, OST_Mass)
# --------------------------------------------------------------------------

volumes = []
for eid in ids(FilteredElementCollector(doc)
               .OfCategory(BuiltInCategory.OST_Mass)
               .WhereElementIsNotElementType()):
    el = doc.GetElement(eid)
    if el is None:
        continue
    v = OrderedDict([("nom", nom_de(el)), ("id", id_de(eid))])
    famille = None
    try:
        famille = el.Symbol.Family.Name
    except Exception:
        famille = None
    v["famille"] = famille
    params = parametres(el, guids_volume)
    valeurs_a_plat(v, params)
    boite = None
    try:
        bb = el.get_BoundingBox(None)
        if bb is not None:
            boite = OrderedDict([("min", point_mm(bb.Min)),
                                 ("max", point_mm(bb.Max))])
    except Exception:
        boite = photo.NON_LU
    v["boite_mm"] = boite
    v["parametres"] = params
    volumes.append(v)
volumes.sort(key=lambda v: (v["famille"] or u"", v["nom"] or u""))

# --------------------------------------------------------------------------
# 6. Pieces
# --------------------------------------------------------------------------

pieces = []
for eid in ids(FilteredElementCollector(doc)
               .OfCategory(BuiltInCategory.OST_Rooms)
               .WhereElementIsNotElementType()):
    r = doc.GetElement(eid)
    if r is None:
        continue
    p = OrderedDict([("id", id_de(eid))])
    try:
        p["numero"] = r.Number or None
    except Exception:
        p["numero"] = photo.NON_LU
    try:
        pn = r.get_Parameter(BuiltInParameter.ROOM_NAME)
        p["nom"] = (pn.AsString() or None) if pn is not None else None
    except Exception:
        p["nom"] = photo.NON_LU
    try:
        p["niveau"] = nom_de(r.Level) if r.Level is not None else None
    except Exception:
        p["niveau"] = photo.NON_LU
    surface = None
    try:
        surface = round(r.Area * PIED2_M2, 3)
    except Exception:
        surface = photo.NON_LU
    p["surface_m2"] = surface
    pt = None
    try:
        loc = r.Location
        if isinstance(loc, LocationPoint):
            pt = loc.Point
    except Exception:
        pt = None
    p["point_mm"] = point_mm(pt)
    p["point_partage_m"] = partage_m(pt)
    # Etat lu sur l'API, pas sur le nom : sans emplacement = non placee ;
    # placee de surface nulle = non fermee (ou redondante).
    if pt is None:
        p["etat"] = u"non placee"
    elif surface == 0:
        p["etat"] = u"surface nulle"
    else:
        p["etat"] = u"placee"
    pieces.append(p)

# --------------------------------------------------------------------------
# 7. Sous-projets
# --------------------------------------------------------------------------

sous_projets = []
for w in ss_projets_user:
    s = OrderedDict([("nom", w.Name), ("id", w.Id.IntegerValue),
                     ("ouvert", bool(w.IsOpen))])
    if not w.IsOpen:
        s["nombre_elements"] = None
    else:
        try:
            s["nombre_elements"] = (
                FilteredElementCollector(doc)
                .WherePasses(ElementWorksetFilter(w.Id))
                .WhereElementIsNotElementType()
                .GetElementCount())
        except Exception:
            s["nombre_elements"] = photo.NON_LU
    sous_projets.append(s)
sous_projets.sort(key=lambda s: s["nom"])
if not collaboratif:
    signaler(u"Maquette non collaborative : aucun sous-projet")

# --------------------------------------------------------------------------
# 8. Liens
# --------------------------------------------------------------------------

liens = []


def epingle(el):
    try:
        return bool(el.Pinned)
    except Exception:
        return photo.NON_LU


for eid in ids(FilteredElementCollector(doc).OfClass(RevitLinkInstance)):
    el = doc.GetElement(eid)
    if el is None:
        continue
    l = OrderedDict([("nom", nom_de(el)), ("id", id_de(eid)),
                     ("type", u"Revit"), ("epingle", epingle(el))])
    try:
        l["charge"] = bool(RevitLinkType.IsLoaded(doc, el.GetTypeId()))
    except Exception:
        l["charge"] = photo.NON_LU
    liens.append(l)

for eid in ids(FilteredElementCollector(doc).OfClass(ImportInstance)):
    el = doc.GetElement(eid)
    if el is None:
        continue
    try:
        if not el.IsLinked:
            continue
    except Exception:
        continue
    nom = None
    try:
        nom = nom_de(doc.GetElement(el.GetTypeId()))
    except Exception:
        nom = nom_de(el)
    liens.append(OrderedDict([("nom", nom), ("id", id_de(eid)),
                              ("type", u"CAO"), ("epingle", epingle(el))]))

for eid in ids(FilteredElementCollector(doc).OfClass(PointCloudInstance)):
    el = doc.GetElement(eid)
    if el is None:
        continue
    liens.append(OrderedDict([("nom", nom_de(el)), ("id", id_de(eid)),
                              ("type", u"Nuage de points"),
                              ("epingle", epingle(el))]))
liens.sort(key=lambda l: (l["type"], l["nom"] or u""))

# --------------------------------------------------------------------------
# 9. Assemblage, bilan
# --------------------------------------------------------------------------

maintenant = datetime.datetime.now()
utilisateur_windows = None
try:
    utilisateur_windows = System.Environment.UserName
except Exception:
    pass

en_tete = OrderedDict([
    ("outil", u"bimflow - Photo maquette"),
    ("version_outil", VERSION),
    ("modele", doc.Title),
    ("chemin", doc.PathName or None),
    ("date", maintenant.strftime(u"%Y-%m-%dT%H:%M:%S")),
    ("revit_version", u"{0}".format(app.VersionNumber)),
    ("revit_build", u"{0}".format(app.VersionBuild)),
    ("utilisateur_revit", app.Username or None),
    ("utilisateur_windows", utilisateur_windows),
    ("collaboratif", collaboratif),
    ("detache", detache),
    ("maquette_centrale", centrale),
    ("sous_projets_fermes", fermes),
    ("unites", OrderedDict([
        ("longueurs_internes", u"mm"), ("coordonnees_partagees", u"m"),
        ("surfaces", u"m2"), ("angles", u"degres")])),
    ("reperes", OrderedDict([
        ("point_de_base", repere(pbp)),
        ("point_topographique", repere(topo)),
        ("transformation_interne_partage", OrderedDict([
            ("sens_retenu", sens_retenu),
            ("residus_mm", residus),
            ("tolerance_mm", TOL_TRANSFORMATION_MM),
            ("motif_si_absente", motif_transfo)])),
        ("orientation", u"azimut, 0 = nord du repere partage, sens horaire"),
    ])),
    ("socle", OrderedDict([("fichier", fichier_socle),
                           ("niveaux", guids_niveau),
                           ("volumes", guids_volume)])),
])
if centrale:
    en_tete["avertissement"] = (
        u"Maquette centrale : etat synchronise a l'instant de la lecture, "
        u"sans le travail non synchronise des autres utilisateurs.")

donnees = OrderedDict([
    ("en_tete", en_tete),
    ("niveaux", niveaux),
    ("quadrillages", quadrillages),
    ("volumes", volumes),
    ("pieces", pieces),
    ("sous_projets", sous_projets),
    ("liens", liens),
])
comptes, sig_bilan = photo.bilan(donnees)
donnees["comptes"] = comptes
donnees["signalements"] = signalements + sig_bilan

# --------------------------------------------------------------------------
# 10. Dossier de sortie, ecriture du JSON
# --------------------------------------------------------------------------

# Le dossier est DEMANDE A CHAQUE EXECUTION (decision Bruno, 2026-10-12) :
# une photo se range dans l'affaire de la maquette, et un dossier retenu
# d'une fois sur l'autre finirait par ranger une maquette dans la mauvaise
# affaire. Le dernier dossier choisi n'est qu'un RAPPEL, affiche dans le
# titre de la boite ; il n'est jamais utilise sans qu'on le choisisse.
fichier_memo = photo.chemin_config()
dernier, brut, motif = photo.lire_config(fichier_memo)
titre = u"Photo maquette - {0} - dossier de sortie".format(doc.Title)
if dernier:
    titre = u"{0} (dernier : {1})".format(titre, dernier)
dossier = forms.pick_folder(title=titre)
if dossier:
    try:
        photo.ecrire_config(fichier_memo, dossier)
    except Exception as err:
        sortie.print_md(u"*Rappel du dernier dossier non enregistre ({0}).*"
                        .format(err))
else:
    sortie.print_md(u"*Aucun dossier choisi : la photo n'est pas ecrite.*")

chemin_json = None
if dossier:
    chemin_json = photo.chemin_libre(
        dossier, photo.nom_fichier(doc.Title, maintenant))
    try:
        photo.ecrire_json(chemin_json, donnees)
    except Exception as err:
        sortie.print_md(u"**ECHEC de l'ecriture du JSON** : {0}".format(err))
        chemin_json = None

# --------------------------------------------------------------------------
# 11. Rapport
# --------------------------------------------------------------------------

sortie.print_md(u"## Comptes par rubrique")
lignes = []
for rubrique, r in comptes.items():
    nuls = u", ".join(u"{0} : {1}".format(c, n)
                      for c, n in r[u"champs_nuls"].items()) or u"-"
    lignes.append([rubrique, r[u"nombre"], nuls])
sortie.print_table(table_data=lignes,
                   columns=[u"Rubrique", u"Nombre", u"Champs null"])

for rubrique in (u"niveaux", u"volumes"):
    stat = comptes[rubrique].get(u"parametres") or OrderedDict()
    if not stat:
        continue
    sortie.print_md(u"### Parametres - {0}".format(rubrique))
    sortie.print_table(
        table_data=[[nom, s[photo.LU], s[photo.VIDE], s[photo.ABSENT],
                     s[photo.ILLISIBLE]] for nom, s in stat.items()],
        columns=[u"Parametre", u"lu", u"vide", u"absent", u"NON_LU"])

if pieces:
    etats = OrderedDict()
    for p in pieces:
        etats[p["etat"]] = etats.get(p["etat"], 0) + 1
    sortie.print_md(u"Pieces : " + u", ".join(
        u"{0} {1}".format(n, e) for e, n in etats.items()))

sortie.print_md(u"## Signalements ({0})".format(len(donnees["signalements"])))
if donnees["signalements"]:
    for s in donnees["signalements"]:
        sortie.print_md(u"- {0}".format(s))
else:
    sortie.print_md(u"Aucun.")

sortie.print_md(u"## Sortie")
if chemin_json:
    sortie.print_md(u"JSON : `{0}`".format(chemin_json))
else:
    sortie.print_md(u"**Aucun fichier ecrit** (pas de dossier de sortie).")
sortie.print_md(u"*Lecture seule - aucune transaction ouverte. {0}*".format(
    VERSION))
