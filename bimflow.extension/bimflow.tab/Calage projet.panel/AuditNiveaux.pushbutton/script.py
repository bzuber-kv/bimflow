# -*- coding: utf-8 -*-
"""Inventaire de toutes les references de niveau du modele.

LECTURE SEULE - aucune transaction n'est ouverte, rien n'est ecrit dans la maquette.

Ce que l'outil rapporte :
  - pour chaque element, quel(s) parametre(s) portent un niveau, lequel, et si
    ce parametre est modifiable ou en lecture seule (auquel cas l'element suit
    son hote) ;
  - X, Y, Zmin, Zmax de la boite englobante, et l'ecart a l'altitude du
    niveau - mesure sur Zmax quand le parametre designe un niveau HAUT
    (contrainte superieure), sur Zmin sinon ;
  - ce qui reference un niveau SANS etre de la geometrie : vues en plan
    associees et plages de vue. Supprimer un niveau supprime aussi ses vues.
  - un controle de cadre de reference (voir CONTROLE ci-dessous).

Sortie : un CSV (une ligne par reference) + une synthese a l'ecran.

bimflow - B18a mode lecture - Keovia Solutions
v3 - 2026-09-12 : calibration du repere mesuree, comparaison Zmin/Zmax
selon le parametre, bande grise, correctif linkify.
"""

__title__ = "Audit\nniveaux"
__author__ = "Keovia Solutions inc."

# --------------------------------------------------------------------------
# PARAMETRES DE L'AUDIT - a ajuster ici, pas dans le corps du script
# --------------------------------------------------------------------------

# Ecart Zmin <-> altitude du niveau au-dela duquel on parle d'erreur d'etage.
ECART_ETAGE_MM = 3000.0

# Niveaux que l'on prevoit de supprimer ou de fusionner. Tout ce qui les
# reference sera signale, geometrie ET vues. Ex. : ["NS_0-1", "Niveau 1"]
NIVEAUX_CONDAMNES = []

# Categories exclues du bilan geometrique (comparaison sans accent ni casse).
# Elles portent des references de niveau et des plages de vue aberrantes
# (-1000 pieds) qui polluent toute statistique altimetrique.
CATEGORIES_HORS_BILAN = [
    "vues", "views",
    "parametres energetiques", "energy analysis settings",
    "analyse energetique", "energy analysis",
]

# Resolution du nom de famille (un GetElement par type, mis en cache).
RESOUDRE_FAMILLE = True

# Plafond de securite. 0 = pas de plafond.
PLAFOND_ELEMENTS = 0

# --------------------------------------------------------------------------

from pyrevit import revit, script, forms

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FilteredWorksetCollector,
    WorksetKind,
    Level,
    View,
    ViewPlan,
    PlanViewPlane,
    StorageType,
    BuiltInParameter,
    BuiltInCategory,
)

doc = revit.doc
out = script.get_output()

# --------------------------------------------------------------------------
# Petits outils
# --------------------------------------------------------------------------

MM_PAR_PIED = 304.8

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


def id_de(eid):
    """R15 fait 7 : ElementId.Value en Revit 2024+, .IntegerValue avant."""
    if eid is None:
        return -1
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


_ACCENTS = {
    u"à": "a", u"â": "a", u"ä": "a",
    u"é": "e", u"è": "e", u"ê": "e", u"ë": "e",
    u"î": "i", u"ï": "i",
    u"ô": "o", u"ö": "o",
    u"ù": "u", u"û": "u", u"ü": "u",
    u"ç": "c",
}


def norm(texte):
    """Minuscules, sans accent - pour comparer des noms de categorie."""
    if not texte:
        return ""
    resultat = []
    for c in texte.lower():
        resultat.append(_ACCENTS.get(c, c))
    return "".join(resultat)


def nb(valeur, decimales=1):
    """Nombre au format CSV francais (virgule decimale)."""
    if valeur is None:
        return ""
    gabarit = "%." + str(decimales) + "f"
    return (gabarit % valeur).replace(".", ",")


def csv_champ(valeur):
    """Un champ CSV sur separateur ';' - on neutralise le separateur."""
    if valeur is None:
        return ""
    texte = u"{0}".format(valeur)
    texte = texte.replace(";", ",").replace("\r", " ").replace("\n", " ")
    return texte.strip()


def mediane(valeurs):
    if not valeurs:
        return None
    tri = sorted(valeurs)
    n = len(tri)
    milieu = n // 2
    if n % 2 == 1:
        return tri[milieu]
    return (tri[milieu - 1] + tri[milieu]) / 2.0


MOTS_DECALAGE = ("decalage", "offset", "elevation", "hauteur par rapport")

# Un parametre qui designe le niveau HAUT d'un objet ne se compare pas a Zmin
# mais a Zmax. Sans cette distinction, tout mur dont la contrainte superieure
# est un niveau superieur sort en faux positif - mesure du 2026-09-12 sur
# thestudy_CO_BAT : 153 faux positifs sur 286, soit plus de la moitie.
MOTS_NIVEAU_HAUT = ("superieur", "sommet", "pointe", "upper", "top")

# Bande dans laquelle l'altitude ne tranche rien : de l'ordre de l'intervalle
# median entre niveaux consecutifs.
BANDE_GRISE_MM = 800.0

# --------------------------------------------------------------------------
# 0. Garde-fou : sous-projets fermes
# --------------------------------------------------------------------------

avertissements = []

if doc.IsWorkshared:
    try:
        worksets = list(
            FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
        )
        fermes = [w.Name for w in worksets if not w.IsOpen]
        if fermes:
            avertissements.append(
                u"**{0} sous-projet(s) ferme(s)** : leurs elements ne sont pas "
                u"charges en memoire et compteraient ZERO sans le dire - "
                u"{1}".format(len(fermes), u", ".join(fermes))
            )
    except Exception as err:
        avertissements.append(
            u"Etat des sous-projets illisible : {0}".format(err)
        )

# --------------------------------------------------------------------------
# 1. Table des niveaux
# --------------------------------------------------------------------------

ids_niveaux = list(
    FilteredElementCollector(doc)
    .OfClass(Level)
    .WhereElementIsNotElementType()
    .ToElementIds()
)

niveaux = {}
for eid in ids_niveaux:
    lvl = doc.GetElement(eid)
    if lvl is None:
        continue
    z_projet = None
    try:
        z_projet = mm(lvl.ProjectElevation)
    except Exception:
        z_projet = None
    niveaux[id_de(eid)] = {
        "nom": lvl.Name,
        "z": mm(lvl.Elevation),
        "z_projet": z_projet,
        "refs": 0,
        "elements": set(),
        "vues": [],
        "plages": 0,
        "condamne": lvl.Name in NIVEAUX_CONDAMNES,
    }

if not niveaux:
    forms.alert("Aucun niveau dans ce modele - rien a auditer.", exitscript=True)

noms_condamnes_absents = [
    n for n in NIVEAUX_CONDAMNES
    if not any(v["nom"] == n for v in niveaux.values())
]
if noms_condamnes_absents:
    avertissements.append(
        u"NIVEAUX_CONDAMNES cite des noms absents du modele : {0}".format(
            u", ".join(noms_condamnes_absents)
        )
    )

# --------------------------------------------------------------------------
# 1 bis. CALIBRATION DU REPERE ALTIMETRIQUE - mesuree, jamais supposee
#
# Rien ne garantit que Level.Elevation et la boite englobante soient exprimes
# dans le meme repere : l'un peut compter depuis le point de base du projet,
# l'autre depuis l'origine interne. On ne suppose pas, on MESURE, sur les murs :
#     ecart = Zmin - (altitude du niveau + decalage inferieur)
# On essaie les deux lectures d'altitude disponibles, on garde celle qui annule
# l'ecart, et s'il reste une constante on la retranche - a condition qu'elle
# soit vraiment constante, ce qui se verifie par la dispersion.
# --------------------------------------------------------------------------

MAX_MURS_CALIBRATION = 800
TOL_CONSTANTE_MM = 5.0      # dispersion admise autour de la mediane
PART_SERREE_MINI = 0.80     # proportion de mesures dans cette bande


def _mesures_murs():
    """(id_niveau, decalage_mm, zmin_mm) pour un echantillon de murs."""
    mesures = []
    try:
        ids_murs = list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Walls)
            .WhereElementIsNotElementType()
            .ToElementIds()
        )
    except Exception:
        return mesures
    for eid in ids_murs[:MAX_MURS_CALIBRATION]:
        el = doc.GetElement(eid)
        if el is None:
            continue
        try:
            p_base = el.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
            p_off = el.get_Parameter(BuiltInParameter.WALL_BASE_OFFSET)
            if p_base is None or p_off is None:
                continue
            k = id_de(p_base.AsElementId())
            if k not in niveaux:
                continue
            bb = el.get_BoundingBox(None)
            if bb is None:
                continue
            mesures.append((k, mm(p_off.AsDouble()), mm(bb.Min.Z)))
        except Exception:
            continue
    return mesures


mesures_murs = _mesures_murs()


def _stats_repere(cle):
    """(mediane, part serree, n) des ecarts pour une lecture d'altitude."""
    ecarts = []
    for k, off, zmin in mesures_murs:
        z = niveaux[k].get(cle)
        if z is None:
            continue
        ecarts.append(zmin - (z + off))
    if not ecarts:
        return None
    med = mediane(ecarts)
    serres = len([e for e in ecarts if abs(e - med) <= TOL_CONSTANTE_MM])
    return (med, float(serres) / len(ecarts), len(ecarts))


_candidats = []
for _cle, _nom in (("z", u"Level.Elevation"),
                   ("z_projet", u"Level.ProjectElevation")):
    _s = _stats_repere(_cle)
    if _s is not None:
        _candidats.append((_cle, _nom, _s))

CLE_Z = "z"
NOM_Z = u"Level.Elevation"
CORRECTION_MM = 0.0
CALIBRATION = None
CALIBRATION_APPLIQUEE = False

if _candidats:
    _candidats.sort(key=lambda c: abs(c[2][0]))
    CLE_Z, NOM_Z, CALIBRATION = _candidats[0]
    _med, _part, _n = CALIBRATION
    if abs(_med) > 1.0:
        if _part >= PART_SERREE_MINI:
            # decalage constant entre les deux reperes : il se retranche
            CORRECTION_MM = _med
            CALIBRATION_APPLIQUEE = True
        else:
            avertissements.append(
                u"**Repere altimetrique non calibre.** L'ecart mesure sur les "
                u"murs n'est pas constant ({0:.0f} % seulement des mesures a "
                u"+/-{1:.0f} mm de la mediane) : ce n'est donc pas un simple "
                u"decalage de repere. **Les colonnes d'ecart sont a lire comme "
                u"relatives.**".format(_part * 100.0, TOL_CONSTANTE_MM)
            )

# altitude de chaque niveau EXPRIMEE DANS LE REPERE DE LA GEOMETRIE
for _k in niveaux:
    _z = niveaux[_k].get(CLE_Z)
    if _z is None:
        _z = niveaux[_k].get("z")
    niveaux[_k]["z_geo"] = None if _z is None else _z + CORRECTION_MM

# --------------------------------------------------------------------------
# 2. Perimetre : modele entier ou selection courante
# --------------------------------------------------------------------------

selection = revit.get_selection()
ids_selection = [eid for eid in selection.element_ids] if selection else []

perimetre = u"modele entier"
if ids_selection:
    choix = forms.alert(
        u"{0} element(s) selectionne(s).\n\n"
        u"Auditer quoi ?".format(len(ids_selection)),
        options=[u"Le modele entier", u"La selection seulement"],
    )
    if choix is None:
        script.exit()
    if choix == u"La selection seulement":
        ids = list(ids_selection)
        perimetre = u"selection courante ({0} elements)".format(len(ids))
    else:
        ids = list(
            FilteredElementCollector(doc)
            .WhereElementIsNotElementType()
            .ToElementIds()
        )
else:
    ids = list(
        FilteredElementCollector(doc)
        .WhereElementIsNotElementType()
        .ToElementIds()
    )

# R15 fait 8 : le collecteur est consomme AVANT toute resolution de propriete.
# A partir d'ici on ne travaille que sur une liste Python d'identifiants.

if PLAFOND_ELEMENTS and len(ids) > PLAFOND_ELEMENTS:
    avertissements.append(
        u"Plafond de securite : {0} elements sur {1} traites.".format(
            PLAFOND_ELEMENTS, len(ids)
        )
    )
    ids = ids[:PLAFOND_ELEMENTS]

# --------------------------------------------------------------------------
# 3. Balayage
# --------------------------------------------------------------------------

lignes = []
cache_type = {}

nb_elements_avec_niveau = 0
nb_references = 0
nb_sans_geometrie = 0
nb_hors_bilan = 0
nb_lecture_seule = 0
ecarts_etage = []          # (ElementId, categorie, niveau, ecart_mm)
zone_grise = set()         # objets que l'altitude ne tranche pas
par_categorie = {}

PAS = 250
total = len(ids)

with forms.ProgressBar(title=u"Audit des niveaux - {value}/{max_value}",
                       cancellable=True) as pb:

    for position, eid in enumerate(ids):

        if position % PAS == 0:
            if pb.cancelled:
                script.exit()
            pb.update_progress(position, total)

        el = doc.GetElement(eid)
        if el is None:
            continue

        classe = el.GetType().Name

        categorie = u""
        try:
            cat = el.Category
            if cat is not None:
                categorie = cat.Name
        except Exception:
            categorie = u""

        est_vue = isinstance(el, View)
        hors_bilan = est_vue or (norm(categorie) in CATEGORIES_HORS_BILAN)

        # --- references de niveau portees par les parametres -------------
        refs = []
        try:
            parametres = el.Parameters
        except Exception:
            parametres = []

        decalages = []
        for p in parametres:
            try:
                st = p.StorageType
            except Exception:
                continue

            if st == StorageType.ElementId:
                try:
                    cible = id_de(p.AsElementId())
                except Exception:
                    continue
                if cible in niveaux:
                    try:
                        nom_p = p.Definition.Name
                    except Exception:
                        nom_p = u"(parametre sans definition)"
                    try:
                        verrou = bool(p.IsReadOnly)
                    except Exception:
                        verrou = True
                    refs.append((nom_p, cible, verrou))

            elif st == StorageType.Double:
                try:
                    nom_p = p.Definition.Name
                except Exception:
                    continue
                nom_n = norm(nom_p)
                if any(mot in nom_n for mot in MOTS_DECALAGE):
                    try:
                        decalages.append(
                            u"{0}={1}".format(nom_p, nb(mm(p.AsDouble()), 1))
                        )
                    except Exception:
                        pass

        # --- reference portee par la propriete .LevelId ------------------
        try:
            lid = id_de(el.LevelId)
            if lid in niveaux and not any(r[1] == lid for r in refs):
                refs.append((u".LevelId (propriete)", lid, True))
        except Exception:
            pass

        # Revit expose parfois DEUX parametres de meme nom pointant le meme
        # niveau - mesure du 2026-09-12 : les poteaux porteurs portent
        # "Niveau de base" et "Niveau superieur" en double (parametre
        # d'instance ET parametre de nomenclature). Meme nom + meme niveau =
        # un seul fait d'ancrage.
        vus = set()
        uniques = []
        for r in refs:
            cle_r = (r[0], r[1])
            if cle_r in vus:
                continue
            vus.add(cle_r)
            uniques.append(r)
        refs = uniques

        if not refs:
            continue

        nb_elements_avec_niveau += 1

        # --- geometrie ----------------------------------------------------
        bb = None
        if not est_vue:
            try:
                bb = el.get_BoundingBox(None)
            except Exception:
                bb = None

        x = y = zmin = zmax = None
        if bb is not None:
            try:
                x = mm((bb.Min.X + bb.Max.X) / 2.0)
                y = mm((bb.Min.Y + bb.Max.Y) / 2.0)
                zmin = mm(bb.Min.Z)
                zmax = mm(bb.Max.Z)
            except Exception:
                x = y = zmin = zmax = None

        if hors_bilan:
            nature = u"VUE" if est_vue else u"HORS_BILAN"
            nb_hors_bilan += 1
        elif bb is None:
            nature = u"SANS_GEOMETRIE"
            nb_sans_geometrie += 1
        else:
            nature = u"GEOMETRIE"

        # --- identite -----------------------------------------------------
        type_nom = u""
        famille = u""
        try:
            type_nom = el.Name
        except Exception:
            type_nom = u""

        if RESOUDRE_FAMILLE:
            try:
                tid = id_de(el.GetTypeId())
                if tid > 0:
                    if tid not in cache_type:
                        t = doc.GetElement(el.GetTypeId())
                        f = u""
                        n = u""
                        if t is not None:
                            try:
                                f = t.FamilyName
                            except Exception:
                                f = u""
                            try:
                                n = t.Name
                            except Exception:
                                n = u""
                        cache_type[tid] = (f, n)
                    famille, nom_type_cache = cache_type[tid]
                    if nom_type_cache:
                        type_nom = nom_type_cache
            except Exception:
                pass

        # --- verrous d'ecriture (matiere premiere du mode ecriture) -------
        epingle = u""
        try:
            epingle = u"OUI" if el.Pinned else u""
        except Exception:
            pass

        groupe = u""
        try:
            gid = id_de(el.GroupId)
            if gid > 0:
                groupe = u"{0}".format(gid)
        except Exception:
            pass

        hote = u""
        try:
            h = el.Host
            if h is not None:
                hote = u"{0}".format(id_de(h.Id))
        except Exception:
            pass
        try:
            if el.HostFace is not None:
                hote = u"FACE:{0}".format(hote) if hote else u"FACE"
        except Exception:
            pass

        # --- une ligne par reference --------------------------------------
        for nom_p, cible, verrou in refs:

            nb_references += 1
            niveaux[cible]["refs"] += 1
            niveaux[cible]["elements"].add(id_de(eid))

            z_niveau = niveaux[cible]["z_geo"]

            # un niveau HAUT se compare a Zmax, tout le reste a Zmin
            vers_le_haut = any(
                mot in norm(nom_p) for mot in MOTS_NIVEAU_HAUT
            )
            z_objet = zmax if vers_le_haut else zmin
            extremite = u"Zmax" if vers_le_haut else u"Zmin"

            ecart = None
            if z_objet is not None and z_niveau is not None:
                ecart = z_objet - z_niveau

            if verrou:
                nb_lecture_seule += 1

            if niveaux[cible]["condamne"]:
                statut = u"NIVEAU_CONDAMNE"
            elif est_vue:
                statut = u"VUE_ASSOCIEE"
            elif hors_bilan:
                statut = u"HORS_BILAN"
            elif verrou:
                statut = u"SUIT_SON_HOTE"
            elif bb is None:
                statut = u"SANS_GEOMETRIE"
            elif ecart is not None and abs(ecart) > ECART_ETAGE_MM:
                statut = u"ECART_ETAGE"
                ecarts_etage.append(
                    (eid, categorie, niveaux[cible]["nom"], ecart)
                )
            elif ecart is not None and abs(ecart) > BANDE_GRISE_MM:
                statut = u"BANDE_GRISE"
                zone_grise.add(id_de(eid))
            else:
                # NB : "non detecte" n'est PAS "correct". L'ecart median entre
                # niveaux consecutifs peut etre inferieur au metre : l'altitude
                # seule ne sait pas identifier le bon niveau.
                statut = u"NON_DETECTE_PAR_ALTIMETRIE"

            if nature == u"GEOMETRIE":
                cle = categorie or classe
                par_categorie[cle] = par_categorie.get(cle, 0) + 1

            lignes.append(u";".join([
                csv_champ(id_de(eid)),
                csv_champ(classe),
                csv_champ(categorie),
                csv_champ(famille),
                csv_champ(type_nom),
                csv_champ(nature),
                csv_champ(nom_p),
                csv_champ(u"LECTURE_SEULE" if verrou else u"MODIFIABLE"),
                csv_champ(niveaux[cible]["nom"]),
                nb(z_niveau),
                nb(x), nb(y), nb(zmin), nb(zmax),
                csv_champ(extremite), nb(ecart),
                csv_champ(u" | ".join(decalages)),
                csv_champ(epingle),
                csv_champ(groupe),
                csv_champ(hote),
                csv_champ(statut),
                u"",   # Niveau_cible : a remplir a la main, relu par le mode ecriture
            ]))

    pb.update_progress(total, total)

# --------------------------------------------------------------------------
# 4. Ce qui reference un niveau sans etre de la geometrie : vues et plages
# --------------------------------------------------------------------------

PLANS_DE_VUE = [
    (u"TopClipPlane", PlanViewPlane.TopClipPlane),
    (u"CutPlane", PlanViewPlane.CutPlane),
    (u"BottomClipPlane", PlanViewPlane.BottomClipPlane),
    (u"ViewDepthPlane", PlanViewPlane.ViewDepthPlane),
]

ids_vues = list(
    FilteredElementCollector(doc).OfClass(ViewPlan).ToElementIds()
)

for vid in ids_vues:
    v = doc.GetElement(vid)
    if v is None:
        continue

    gabarit = False
    try:
        gabarit = bool(v.IsTemplate)
    except Exception:
        gabarit = False

    nom_vue = u""
    try:
        nom_vue = v.Name
    except Exception:
        pass

    # 4a. niveau generateur : supprimer le niveau supprime la vue
    try:
        g = v.GenLevel
    except Exception:
        g = None
    if g is not None:
        k = id_de(g.Id)
        if k in niveaux:
            niveaux[k]["vues"].append(nom_vue)
            lignes.append(u";".join([
                csv_champ(id_de(vid)), csv_champ(v.GetType().Name),
                csv_champ(u"Vues"), u"", csv_champ(nom_vue),
                csv_champ(u"GABARIT_DE_VUE" if gabarit else u"VUE"),
                csv_champ(u"GenLevel"), csv_champ(u"LECTURE_SEULE"),
                csv_champ(niveaux[k]["nom"]), nb(niveaux[k]["z_geo"]),
                u"", u"", u"", u"", u"", u"", u"", u"", u"", u"",
                csv_champ(
                    u"VUE_DETRUITE_SI_NIVEAU_SUPPRIME"
                    if niveaux[k]["condamne"] else u"VUE_ASSOCIEE"
                ),
                u"",
            ]))

    # 4b. plages de vue : elles peuvent pointer d'AUTRES niveaux
    try:
        vr = v.GetViewRange()
    except Exception:
        vr = None
    if vr is not None:
        for nom_plan, plan in PLANS_DE_VUE:
            try:
                k = id_de(vr.GetLevelId(plan))
            except Exception:
                continue
            if k in niveaux:
                niveaux[k]["plages"] += 1
                lignes.append(u";".join([
                    csv_champ(id_de(vid)), csv_champ(v.GetType().Name),
                    csv_champ(u"Vues"), u"", csv_champ(nom_vue),
                    csv_champ(u"PLAGE_DE_VUE"),
                    csv_champ(u"ViewRange:" + nom_plan),
                    csv_champ(u"LECTURE_SEULE"),
                    csv_champ(niveaux[k]["nom"]), nb(niveaux[k]["z_geo"]),
                    u"", u"", u"", u"", u"", u"", u"", u"", u"", u"",
                    csv_champ(
                        u"PLAGE_ORPHELINE_SI_NIVEAU_SUPPRIME"
                        if niveaux[k]["condamne"] else u"PLAGE_DE_VUE"
                    ),
                    u"",
                ]))

# --------------------------------------------------------------------------
# 5. Synthese a l'ecran
# --------------------------------------------------------------------------

out.print_md(u"# Audit des references de niveau")
out.print_md(
    u"Maquette : **{0}** &nbsp;|&nbsp; perimetre : {1} &nbsp;|&nbsp; "
    u"lecture seule, aucune transaction".format(doc.Title, perimetre)
)

if avertissements:
    out.print_md(u"## Avertissements")
    for a in avertissements:
        out.print_md(u"- {0}".format(a))

out.print_md(u"## Bilan")
out.print_md(
    u"- **{0}** elements portent au moins une reference de niveau\n"
    u"- **{1}** references au total (un element peut en porter plusieurs)\n"
    u"- dont **{2}** en lecture seule : ces elements **suivent leur hote**, "
    u"leur niveau ne se change pas directement\n"
    u"- **{3}** sans geometrie, **{4}** hors bilan (vues, parametres "
    u"energetiques)".format(
        nb_elements_avec_niveau, nb_references, nb_lecture_seule,
        nb_sans_geometrie, nb_hors_bilan
    )
)

# 5a. calibration du repere altimetrique
out.print_md(u"## Repere altimetrique - calibration mesuree")

if not _candidats:
    out.print_md(
        u"*Aucun mur exploitable : le repere n'a pas pu etre calibre. "
        u"**Les ecarts ci-dessous ne sont pas valides sur ce modele.***"
    )
else:
    lignes_cal = [u"| Lecture d'altitude | Ecart median | Dispersion | Mesures |",
                  u"|---|---:|---:|---:|"]
    for _cle, _nom, (_med, _part, _n) in _candidats:
        lignes_cal.append(
            u"| {0}{1} | {2} mm | {3} % a +/-{4:.0f} mm | {5} |".format(
                _nom, u" **(retenue)**" if _cle == CLE_Z else u"",
                nb(_med, 1), int(round(_part * 100.0)), TOL_CONSTANTE_MM, _n
            )
        )
    out.print_md(u"\n".join(lignes_cal))

    _med, _part, _n = CALIBRATION
    if CALIBRATION_APPLIQUEE:
        out.print_md(
            u"> **Decalage de repere constant, mesure et retranche.** "
            u"`{0}` et la boite englobante different de **{1} mm**, et cet "
            u"ecart est constant ({2} % des mesures a +/-{3:.0f} mm). C'est un "
            u"changement de repere, pas une erreur de modele : les deux "
            u"altitudes ne comptent pas depuis la meme origine.\n\n"
            u"> **Tous les ecarts publies ci-dessous sont corriges de cette "
            u"constante** et sont donc absolus. La colonne `Z_niveau_mm` du CSV "
            u"est elle aussi exprimee dans le repere de la geometrie.".format(
                NOM_Z, nb(_med, 1), int(round(_part * 100.0)), TOL_CONSTANTE_MM
            )
        )
    elif abs(_med) > 1.0:
        out.print_md(
            u"> **Repere NON calibre.** L'ecart n'est pas constant : ce n'est "
            u"donc pas un simple changement d'origine, et rien n'a ete "
            u"retranche. **Les ecarts ci-dessous sont relatifs, pas absolus.** "
            u"A diagnostiquer avant toute ecriture (fiche R16)."
        )
    else:
        out.print_md(
            u"> `{0}` et la boite englobante partagent le meme repere "
            u"(ecart median {1} mm). Aucune correction necessaire.".format(
                NOM_Z, nb(_med, 1)
            )
        )

# 5b. table des niveaux
out.print_md(u"## Niveaux")
tri = sorted(
    [(v["z_geo"], k) for k, v in niveaux.items() if v["z_geo"] is not None]
)
entetes = (
    u"| Niveau | Z lu dans Revit | Z repere geometrie | Intervalle au precedent "
    u"| Elements | References | Vues en plan | Plages de vue |\n"
    u"|---|---:|---:|---:|---:|---:|---:|---:|\n"
)
corps = []
intervalles = []
precedent = None
for z, k in tri:
    v = niveaux[k]
    inter = u""
    if precedent is not None:
        d = z - precedent
        intervalles.append(d)
        inter = nb(d, 0)
    precedent = z
    corps.append(
        u"| {0}{1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
            v["nom"],
            u" **(condamne)**" if v["condamne"] else u"",
            nb(v.get(CLE_Z), 0), nb(z, 0), inter,
            len(v["elements"]), v["refs"], len(v["vues"]), v["plages"],
        )
    )
out.print_md(entetes + u"\n".join(corps))

if intervalles:
    med_i = mediane(intervalles)
    petits = len([i for i in intervalles if i < 1000.0])
    out.print_md(
        u"**Intervalle median entre niveaux consecutifs : {0} mm** - "
        u"{1} intervalle(s) sur {2} font moins d'un metre.".format(
            nb(med_i, 0), petits, len(intervalles)
        )
    )
    if med_i is not None and med_i < 2000.0:
        out.print_md(
            u"> **Consequence de methode.** A cette densite, l'altitude seule "
            u"ne permet pas d'identifier le bon niveau : cet audit ne voit que "
            u"les erreurs d'un etage. Le statut "
            u"`NON_DETECTE_PAR_ALTIMETRIE` ne veut pas dire *correct*. Le "
            u"controle qui tranche est le controle de ZONE (voir la note de "
            u"methode `volumes de zone`)."
        )

# 5c. niveaux condamnes
condamnes = [v for v in niveaux.values() if v["condamne"]]
if condamnes:
    out.print_md(u"## Niveaux condamnes - ce qu'emporterait la suppression")
    for v in condamnes:
        out.print_md(
            u"### {0}\n"
            u"- **{1} element(s)** a deplacer avant toute suppression\n"
            u"- **{2} vue(s) en plan** seraient **supprimees avec le niveau** : "
            u"{3}\n"
            u"- **{4} plage(s) de vue** deviendraient orphelines".format(
                v["nom"], len(v["elements"]), len(v["vues"]),
                u", ".join(v["vues"][:15]) + (u" ..." if len(v["vues"]) > 15 else u"")
                if v["vues"] else u"aucune",
                v["plages"],
            )
        )

# 5d. erreurs d'un etage
out.print_md(u"## Ecarts superieurs a {0} mm".format(nb(ECART_ETAGE_MM, 0)))
if ecarts_etage:
    ecarts_etage.sort(key=lambda t: -abs(t[3]))
    out.print_md(
        u"**{0}** reference(s). Les 40 plus gros ecarts "
        u"(cliquer l'identifiant pour selectionner l'element) :".format(
            len(ecarts_etage)
        )
    )
    for eid_v, cat, nom_niv, ecart in ecarts_etage[:40]:
        # out.linkify attend un ElementId, pas un entier : on lui passe l'objet.
        try:
            lien = out.linkify(eid_v)
        except Exception:
            lien = u"`{0}`".format(id_de(eid_v))
        out.print_md(
            u"- {0} &nbsp; {1} &nbsp;|&nbsp; niveau **{2}** &nbsp;|&nbsp; "
            u"ecart **{3} mm**".format(
                lien, cat or u"(sans categorie)", nom_niv, nb(ecart, 0)
            )
        )
else:
    out.print_md(u"*Aucun.*")

# 5d bis. la bande que l'altitude ne tranche pas
out.print_md(u"## Ce que l'altitude ne tranche pas")
out.print_md(
    u"**{0}** objets portent au moins une reference dont l'ecart au niveau "
    u"tombe entre {1} mm et {2} mm.\n\n"
    u"> Ce ne sont **pas** {0} suspects : un plafond a 2,7 m ou une "
    u"canalisation sous dalle sont normalement dans cette bande. C'est la "
    u"mesure de ce que l'altimetrie **ne peut pas decider** - a comparer aux "
    u"{3} ecarts francs ci-dessus. Le controle de ZONE est ce qui tranche "
    u"cette population.".format(
        len(zone_grise), nb(BANDE_GRISE_MM, 0), nb(ECART_ETAGE_MM, 0),
        len(ecarts_etage)
    )
)

# 5e. repartition par categorie
if par_categorie:
    out.print_md(u"## Repartition des references geometriques par categorie")
    rangs = sorted(par_categorie.items(), key=lambda t: -t[1])
    tableau = u"| Categorie | References |\n|---|---:|\n"
    tableau += u"\n".join(
        [u"| {0} | {1} |".format(c, n) for c, n in rangs[:30]]
    )
    out.print_md(tableau)

# --------------------------------------------------------------------------
# 6. Export CSV - jamais un chemin construit depuis le profil utilisateur
# --------------------------------------------------------------------------

ENTETE = u";".join([
    u"Id", u"Classe", u"Categorie", u"Famille", u"Type", u"Nature",
    u"Parametre", u"Verrou", u"Niveau", u"Z_niveau_mm",
    u"X_mm", u"Y_mm", u"Zmin_mm", u"Zmax_mm",
    u"Extremite_comparee", u"Ecart_niveau_mm",
    u"Decalages_mm", u"Epingle", u"Groupe", u"Hote", u"Statut",
    u"Niveau_cible",
])

chemin = forms.save_file(
    file_ext="csv",
    default_name="audit_niveaux_{0}".format(
        doc.Title.replace(" ", "_")
    ),
)

if chemin:
    # B16 : le codec utf-8-sig ecrit le BOM a CHAQUE write() sous IronPython 3.
    # On assemble puis on ecrit une seule fois.
    texte = ENTETE + u"\n" + u"\n".join(lignes)
    import io
    f = io.open(chemin, "w", encoding="utf-8-sig", newline="")
    try:
        f.write(texte)
    finally:
        f.close()
    out.print_md(
        u"## Export\n{0} ligne(s) ecrite(s) dans `{1}`".format(
            len(lignes), chemin
        )
    )
else:
    out.print_md(
        u"## Export\n*Annule - la synthese ci-dessus reste valable.*"
    )
