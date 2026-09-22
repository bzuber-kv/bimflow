#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_sitemodel.py - Construit un site_model Ivion a partir de l'audit des
volumes de zone Revit produit par le bouton pyRevit AuditVolumes.

REGLE STRUCTURANTE (fiche de liaison 2026-09-22, ivion_api) :
  Un BUILDING est une PILE - une suite ordonnee de tranches partageant UNE
  MEME suite d'elevations de separation. Ce n'est pas un conteneur.
  Regle P : deux zones partagent un BUILDING si et seulement si
     (a) meme signature d'elevations, a la tolerance d'accrochage pres, ET
     (b) union de leurs emprises simplement connexe (un seul polygone).
  Sinon : un BUILDING par zone.
  C'est l'etape 1 du generateur, et la seule qui ne se deduit pas de
  SITE_MODEL.md v8.

Entree  : <audit>.json  {zones: {nom_zone: [{etage, coords[mm], aire, zmin,
                                             zmax, incl, vol}]}}
Sortie  : site_model_<batiment>.json  (tableau racine, format de l'export)

Autres regles (references = SITE_MODEL.md v8) :
  - le NOM des FLOOR regroupe la visite (C7) : name = REF_Etage
  - l'identite va dans attributes (C8), jamais dans name (5.4)
  - polygon_inherited = true quand le contour egale celui du batiment
  - separation non horizontale : coupe au NIVEAU LE PLUS BAS (arbitrage Bruno
    2026-09-22), tranche marquee pour retraitement
  - unites : Revit mm -> Ivion m. Sans --scs, aucune transformation (repere
    interne Revit, sandbox). Avec --scs, rotation THETA puis translation
    DX/DY/DZ vers le SCS Ivion - verifie sur site le 2026-09-22.
  - validation C1/C2/C3/C6/C10 AVANT envoi (5.6 : l'import teste la
    conformite, il ne diagnostique pas)

REPERE (mesure, GEOREFERENCEMENT.md + TheStudy_PEP.md v1.9) :
  Les coordonnees d'un site_model sont en METRES et RELATIVES au Site Base
  Point d'Ivion - jamais absolues. L'audit pyRevit lit la geometrie via
  l'API Revit, donc dans le REPERE INTERNE DU MODELE ; c'est ce repere dont
  l'origine coincide avec l'ancien point de base Ivion
  (296952.161 ; 5038971.768 ; 123.760), d'ou la translation.
  A ne pas confondre avec Level.Elevation, que l'audit n'emploie pas : cette
  lecture compte depuis la base d'elevation du TYPE de niveau et differe de
  la geometrie de 29 065 mm sur The Study (R16 §1.1).
  Le point de base ACTUEL est a
  (296934.640 ; 5038973.460 ; 125.000). D'ou la translation connue
  DX/DY/DZ ci-dessous - identique au vecteur applique au site_model reel
  le 2026-08-25.
  ROTATION appliquee AVANT la translation, puisque celle-ci est exprimee en
  axes MTM8. Le SCS est aligne sur le nord grille MTM8 (la fiche du point de
  base Ivion declare une rotation de 0 deg).
  Par defaut le script n'applique RIEN (sortie sandbox) ; --scs produit la
  sortie georeferencee.

  LA TRANSFORMATION N'EST PLUS EN DUR. Elle se lit dans l'audit, ou Revit
  l'a mesuree (entete.emplacement_partage, reporte par audit_to_zones) :
  l'angle au nord vrai donne THETA, et l'origine interne en coordonnees
  partagees donne la translation par difference avec POINT_BASE_IVION - la
  seule valeur qui reste a fournir, parce qu'elle appartient au site Ivion
  et non a la maquette. Un audit sans emplacement_partage fait retomber sur
  les valeurs de repli, et le rapport le DIT.

Usage : python3 gen_sitemodel.py <zones.json> [nom_batiment] [--scs]
        --scs applique la transformation ; sans lui, sortie sandbox.
"""
import json, math, pathlib, sys
from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = pathlib.Path(__file__).parent
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "junior.json"

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SCS = "--scs" in sys.argv
BATIMENT = ARGS[1] if len(ARGS) > 1 else "Junior"
SITE = "The Study"

# POINT DE BASE IVION du site, en coordonnees partagees (m). C'est le SEUL
# parametre qui ne se lit nulle part dans la maquette : il appartient au site
# Ivion, pas au modele Revit. Valeur The Study, fiche du point de base -
# le SCS est aligne sur le nord GRILLE MTM8 (rotation declaree 0 deg).
POINT_BASE_IVION = (296934.640, 5038973.460, 125.000)

# Repli employe SEULEMENT si l'audit ne porte pas son emplacement partage.
# Valeurs mesurees le 2026-09-22 sur The Study.
THETA_REPLI = -0.5504768                            # radians
DXYZ_REPLI = (17.521326, -1.691684, -1.240)         # metres

# THETA, DX, DY, DZ sont etablis plus bas, a la lecture du fichier : ils
# sortent de l'audit, mesures par Revit. Voir section 1.
THETA = None
DX = DY = DZ = 0.0

MM = 1000.0
EPS = 1e-6
ORDRE = {"FLOOR_1": 1, "FLOOR_2": 2, "FLOOR_3": 3, "FLOOR_4": 4,
         "FLOOR_5": 5, "FLOOR_6": 6, "ROOF": 90}


PREC = 6 if True else 4      # decimales de sortie : micrometre apres rotation


def m(v):
    return round(v / MM, PREC)


def xy(x, y):
    """mm dans le repere de l'origine interne Revit -> m dans le repere de sortie."""
    if not SCS:
        return round(x / MM, PREC), round(y / MM, PREC)
    t = THETA                     # deja en RADIANS, applique tel quel
    u, v = x / MM, y / MM
    return (round(u * math.cos(t) - v * math.sin(t) + DX, PREC),
            round(u * math.sin(t) + v * math.cos(t) + DY, PREC))


def z(v):
    return round(v / MM + (DZ if SCS else 0.0), PREC)


def ring(coords):
    r = [list(xy(x, y)) for x, y in coords]
    if r[0] != r[-1]:
        r.append(r[0])
    return r


def gj(ext, trous=()):
    return {"type": "Polygon",
            "coordinates": [ring(ext)] + [ring(t) for t in trous]}


# ---------------------------------------------------------------- 1. lecture
donnees = json.loads(SRC.read_text(encoding="utf-8"))
zones = donnees["zones"]

# FILTRE D'EXPORT (arbitrage Bruno du 2026-09-22). Ne part vers Ivion que ce
# qui est un espace de visite : ETAGE, TOITURE, ENTRE_TOIT, EXTERIEUR.
# ENVELOPPE est exclue - un volume d'enveloppe LOD100 n'est ni un etage ni
# une toiture. Une tranche SANS nature n'est pas exportee non plus : une
# nature ne se devine pas.
NATURES_EXPORTEES = ("ETAGE", "TOITURE", "ENTRE_TOIT", "EXTERIEUR")

ecartes = {}
zones_filtrees = {}
for _zn, _tr in zones.items():
    gardees = []
    for _t in _tr:
        _nature = _t.get("nature")
        if _nature in NATURES_EXPORTEES:
            gardees.append(_t)
        else:
            _motif = _nature if _nature else "sans nature"
            ecartes[_motif] = ecartes.get(_motif, 0) + 1
    if gardees:
        zones_filtrees[_zn] = gardees
    elif _tr:
        ecartes["zone entiere ecartee : " + _zn] = 0

zones = zones_filtrees
if not zones:
    sys.exit("REFUS : aucune tranche exportable. Les natures lues sont %s, "
             "et seules %s partent vers Ivion."
             % (", ".join(sorted(ecartes.keys())) or "(aucune)",
                ", ".join(NATURES_EXPORTEES)))

INFO_FILTRE = ("filtre d'export : %d tranche(s) ecartee(s)%s"
               % (sum(ecartes.values()),
                  (" - " + ", ".join("%s: %d" % (k, v)
                                     for k, v in sorted(ecartes.items()) if v))
                  if any(ecartes.values()) else ""))

# La transformation vers le SCS n'est PAS en dur : elle se lit dans l'audit,
# ou Revit l'a mesuree (entete.emplacement_partage, reporte ici par
# audit_to_zones).
#   angle_nord_vrai_rad -> THETA, applique TEL QUEL aux coordonnees
#   est_ouest / nord_sud / elevation -> l'origine interne du modele, en
#   coordonnees PARTAGEES ; la translation est son ecart au point de base
#   Ivion, seule valeur qui reste a fournir.
_emplacement = (donnees.get("_entete") or {}).get("emplacement_partage") or {}
_angle = _emplacement.get("angle_nord_vrai_rad")
_est = _emplacement.get("est_ouest_mm")
_nord = _emplacement.get("nord_sud_mm")
_elev = _emplacement.get("elevation_mm")

if _angle is not None and None not in (_est, _nord, _elev):
    THETA = _angle
    DX = _est / MM - POINT_BASE_IVION[0]
    DY = _nord / MM - POINT_BASE_IVION[1]
    DZ = _elev / MM - POINT_BASE_IVION[2]
    INFO_REPERE = ("transformation LUE DANS L'AUDIT (mesuree par Revit) : "
                   "origine interne (%.3f ; %.3f ; %.3f) en coordonnees "
                   "partagees, point de base Ivion (%.3f ; %.3f ; %.3f)"
                   % (_est / MM, _nord / MM, _elev / MM,
                      POINT_BASE_IVION[0], POINT_BASE_IVION[1],
                      POINT_BASE_IVION[2]))
else:
    THETA = THETA_REPLI
    DX, DY, DZ = DXYZ_REPLI
    INFO_REPERE = ("ATTENTION : l'audit ne porte pas son emplacement partage "
                   "(entete.emplacement_partage). Transformation de REPLI, "
                   "valeurs en dur mesurees le 2026-09-22 sur The Study - "
                   "elles ne valent que pour cette affaire, et pour ce point "
                   "de base.")

THETA_DEG = math.degrees(THETA)

if SCS and THETA is None:
    sys.exit("REFUS : --scs demande mais aucun angle disponible, ni dans "
             "l'audit ni en repli. Relancer l'audit des volumes : son en-tete "
             "porte emplacement_partage.angle_nord_vrai_rad.")

# ------------------------------------- 2. arbitrage des separations inclinees
retraiter = []
for zn, tr in zones.items():
    tr.sort(key=lambda t: t["zmin"])
    for a, b in zip(tr, tr[1:]):
        if a["zmax"] > b["zmin"] + 1e-6:
            a["zmax_brut"] = a["zmax"]
            a["zmax"] = b["zmin"]
            a["flag"] = b["flag"] = "separation_non_horizontale"
            retraiter.append((zn, a["etage"], b["etage"], a["zmax_brut"] - b["zmin"]))
    for t in tr:
        if t.get("incl") and "flag" not in t:
            t["flag"] = "face_non_horizontale_isolee"

# ------------------------------- 2bis. noeudification (sommets en T)
#  Un sommet d'une zone pose au milieu de l'arete d'une voisine est colineaire
#  tant que l'arete est axee, et cesse de l'etre des qu'on la tourne : il
#  apparait alors un recouvrement de quelques dixiemes de micrometre, qu'Ivion
#  refuse (emprises de BUILDING secantes). On insere donc ce sommet dans
#  l'arete de la voisine AVANT toute rotation : les deux contours portent
#  alors exactement les memes points, et la rotation les deplace ensemble.
#  L'aire est inchangee (points colineaires).
TOL = 0.5   # mm

tous = {(round(x, 3), round(y, 3))
        for tr in zones.values() for x, y in tr[0]["coords"]}


def noeudifier(anneau):
    out = []
    for a, b in zip(anneau, anneau[1:]):
        out.append(a)
        ax, ay = a
        bx, by = b
        L2 = (bx - ax) ** 2 + (by - ay) ** 2
        if L2 == 0:
            continue
        sur = []
        for px, py in tous:
            t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / L2
            if not (1e-9 < t < 1 - 1e-9):
                continue
            d = abs((px - ax) * (by - ay) - (py - ay) * (bx - ax)) / L2 ** 0.5
            if d <= TOL:
                sur.append((t, (px, py)))
        out.extend(q for _, q in sorted(sur))
    out.append(anneau[-1])
    return out


n_ins = 0
for zn, tr in zones.items():
    ref = noeudifier([tuple(c) for c in tr[0]["coords"]])
    n_ins += len(ref) - len(tr[0]["coords"])
    for t in tr:
        t["coords"] = [list(c) for c in ref]

# ---------------------------------------------------- 3. contours et controle
polys = {}
for zn, tr in zones.items():
    polys[zn] = Polygon([(x, y) for x, y in tr[0]["coords"]])
    for t in tr[1:]:
        p = Polygon([(x, y) for x, y in t["coords"]])
        assert p.equals(polys[zn]), "contour non constant sur %s / %s" % (zn, t["etage"])

# Union GLOBALE des emprises : une INFORMATION, pas un controle. Sur un site
# a plusieurs batiments elle est naturellement un MultiPolygon - l'audit du
# 2026-09-22 (Junior + SC_atelier + SE_office) en donne 3 parties, et c'est
# normal. La seule union qui doive etre simple est celle d'un GROUPE de la
# regle P, et c'est elle qui decide du regroupement, plus bas.
union = unary_union(list(polys.values()))
if union.geom_type == "Polygon":
    INFO_UNION = "union des emprises : Polygon (1 partie)"
else:
    INFO_UNION = ("union des emprises : %s (%d partie(s))"
                  % (union.geom_type, len(union.geoms)))


def attrs_floor(zn, t):
    a = {"keovia_ref_batiment": BATIMENT,
         "keovia_ref_zone": zn,
         "keovia_ref_etage": t["etage"],
         # la nature du volume, telle que son NOM la porte - plus aucune
         # valeur inventee ici
         "keovia_cls_nature_volume": t.get("nature", ""),
         "keovia_src": "A_VOL / audit 2026-09-22"}
    if "flag" in t:
        a["keovia_geom_flag"] = t["flag"]
    if "zmax_brut" in t:
        a["keovia_geom_zmax_brut_m"] = str(m(t["zmax_brut"]))
    return a


def floor(zn, t, herite):
    return {"type": "FLOOR",
            "name": t["etage"],
            "scs_polygon": gj(t["coords"]),
            "scs_z_min": z(t["zmin"]),
            "scs_z_max": z(t["zmax"]),
            "polygon_inherited": herite,
            "attributes": attrs_floor(zn, t),
            "children": []}


# ------------------------------------- 4. REGLE P : partition en BUILDING
def signature(tr):
    """Suite ordonnee des elevations de separation, arrondie a la tolerance."""
    return tuple(round(v, 4) for t in tr for v in (t["zmin"], t["zmax"]))


# (a) grouper par signature d'elevations
par_sig = {}
for zn, tr in zones.items():
    par_sig.setdefault(signature(tr), []).append(zn)

# (b) dans chaque groupe, scinder par composante connexe des emprises
groupes = []
for sig, noms in par_sig.items():
    reste = list(noms)
    while reste:
        comp = [reste.pop(0)]
        geom = polys[comp[0]]
        bouge = True
        while bouge:
            bouge = False
            for zn in list(reste):
                u = unary_union([geom, polys[zn]])
                if u.geom_type == "Polygon":      # contact reel, union connexe
                    comp.append(zn)
                    reste.remove(zn)
                    geom = u
                    bouge = True
        # PAS de simplify() : il supprimerait les points colineaires inseres a
        # l'etape 2bis, qui sont ce qui garantit des aretes exactement
        # coincidentes une fois la rotation appliquee.
        groupes.append((sorted(comp), geom, sig))

groupes.sort(key=lambda g: g[0][0])

# --------------------------------------------------------- 5. les entites
doc = []
for noms, emprise, sig in groupes:
    nom_bat = noms[0] if len(noms) == 1 else "+".join(noms)
    ch = []
    for zn in noms:
        for t in zones[zn]:
            herite = polys[zn].equals(emprise)
            ch.append(floor(zn, t, herite))
    ch.sort(key=lambda c: (c["scs_z_min"], c["attributes"]["keovia_ref_zone"]))
    doc.append({
        "type": "BUILDING",
        "name": nom_bat,
        "scs_polygon": gj(list(emprise.exterior.coords),
                          [list(i.coords) for i in emprise.interiors]),
        "scs_z_min": None, "scs_z_max": None,
        "polygon_inherited": False,
        "attributes": {
            "keovia_ref_batiment": BATIMENT,
            "keovia_ref_zones": ";".join(noms),
            "keovia_site": SITE,
            # un BUILDING est une PILE, pas un volume : il n'a pas de nature
            # propre. Les natures sont portees par ses FLOOR.
            "keovia_cls_nature_volume": ";".join(
                sorted(set(f["attributes"]["keovia_cls_nature_volume"]
                           for f in ch))),
            "keovia_repere": ("SCS Ivion (DX %.6f DY %.6f DZ %.3f, rotation "
                              "%.4f deg)" % (DX, DY, DZ, THETA_DEG)) if SCS else
                             "ORIGINE INTERNE REVIT, metres, AUCUNE transformation "
                             "- non georeference, sandbox uniquement",
            "keovia_src": "A_VOL / %s" % SRC.name,
        },
        "children": ch,
    })

DST = HERE / ("site_model_%s.json" % BATIMENT.lower())
DST.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

print(INFO_FILTRE)
print(INFO_UNION)
print("Repere : %s" % INFO_REPERE)
print("         THETA %.7f rad (%.4f deg) - DX/DY/DZ %.3f / %.3f / %.3f m%s"
      % (THETA, THETA_DEG, DX, DY, DZ,
         "" if SCS else "  [NON APPLIQUES : sortie sandbox]"))
print()
print("Regle P : %d zone(s) -> %d signature(s) d'elevations -> %d BUILDING"
      % (len(zones), len(par_sig), len(groupes)))
for noms, _, sig in groupes:
    print("    %-40s %s" % ("+".join(noms),
                            " ".join("%.3f" % m(v) for v in sorted(set(sig)))))
print()

# ------------------------------------------------------ 4. validation amont
def valider(nom, doc):
    print("=" * 72)
    print("SITE_MODEL %s — validation amont" % nom)
    print("=" * 72)
    bats = doc
    fls = [f for b in bats for f in b["children"]]
    print("%d BUILDING + %d FLOOR · %d noms d'etage distincts : %s"
          % (len(bats), len(fls), len({f['name'] for f in fls}),
             ", ".join(sorted({f['name'] for f in fls}, key=lambda n: ORDRE.get(n, 50)))))
    ko = []

    # C1 : interieurs des BUILDING disjoints
    n1 = 0
    for i, a in enumerate(bats):
        pa = Polygon(a["scs_polygon"]["coordinates"][0])
        for b in bats[i + 1:]:
            ia = pa.intersection(Polygon(b["scs_polygon"]["coordinates"][0])).area
            if ia > 1e-6:                      # 1 mm2 : au-dela, c'est reel
                n1 += 1
                ko.append("C1 %s recoupe %s sur %.3g m2" % (a["name"], b["name"], ia))
            elif ia > 0:
                ko.append("C1 note : %s / %s se touchent a %.3g m2 "
                          "(sommet en T apres rotation, sous la tolerance "
                          "d'accrochage Ivion ~8e-7 m)" % (a["name"], b["name"], ia))
    print("C1  interieurs des BUILDING disjoints .......................... %s"
          % ("OK" if n1 == 0 else "ECHEC (%d)" % n1))

    # C3 : chaque FLOOR inclus dans son BUILDING
    n3 = 0
    for b in bats:
        pb = Polygon(b["scs_polygon"]["coordinates"][0]).buffer(EPS)
        for f in b["children"]:
            if not pb.contains(Polygon(f["scs_polygon"]["coordinates"][0])):
                n3 += 1
                ko.append("C3 %s/%s hors de %s" % (f["attributes"]["keovia_ref_zone"],
                                                   f["name"], b["name"]))
    print("C3  contour de chaque etage inclus dans son batiment ........... %s"
          % ("OK" if n3 == 0 else "ECHEC (%d)" % n3))

    # C6 : aucune superposition 3D entre freres
    n6 = 0
    for b in bats:
        ch = b["children"]
        for i, a in enumerate(ch):
            pa = Polygon(a["scs_polygon"]["coordinates"][0])
            for c in ch[i + 1:]:
                if (a["scs_z_max"] <= c["scs_z_min"] + EPS
                        or c["scs_z_max"] <= a["scs_z_min"] + EPS):
                    continue
                if pa.intersection(Polygon(c["scs_polygon"]["coordinates"][0])).area > 1e-6:
                    n6 += 1
                    ko.append("C6 %s/%s recoupe %s/%s dans %s"
                              % (a["attributes"]["keovia_ref_zone"], a["name"],
                                 c["attributes"]["keovia_ref_zone"], c["name"], b["name"]))
    print("C6  aucune superposition 3D entre etages freres ................ %s"
          % ("OK" if n6 == 0 else "ECHEC (%d)" % n6))

    # C2 : pile ordonnee et contigue a l'interieur de chaque BUILDING
    trous, chev = 0, 0
    for b in bats:
        p = sorted(b["children"], key=lambda f: f["scs_z_min"])
        for x, y in zip(p, p[1:]):
            if Polygon(x["scs_polygon"]["coordinates"][0]).intersection(
                    Polygon(y["scs_polygon"]["coordinates"][0])).area < 1e-6:
                continue                      # pas superposes en plan : pas une pile
            d = y["scs_z_min"] - x["scs_z_max"]
            if d > EPS:
                trous += 1
            elif d < -EPS:
                chev += 1
    print("C2  pile verticale : %d intervalle(s), %d chevauchement(s) ...... %s"
          % (trous, chev, "OK" if chev == 0 else "ECHEC"))

    # C10 / 5.1 / 2a
    bas = [f for f in fls if f["scs_z_max"] - f["scs_z_min"] < 1.0]
    print("C10 toutes les tranches font au moins 1 m (editable) ........... %s"
          % ("OK" if not bas else "%d sous le metre" % len(bas)))
    MIN = {"type", "name", "scs_polygon", "polygon_inherited", "attributes", "children"}
    print("5.1 les 6 champs minimum + cotes presents partout .............. %s"
          % ("OK" if all(MIN <= set(e) for e in bats + fls) else "MANQUE"))
    bad = [e["name"] for e in bats + fls
           for r in e["scs_polygon"]["coordinates"]
           if r[0] != r[-1] or any(len(q) != 2 for q in r)]
    print("2a  anneaux fermes et strictement 2D ........................... %s"
          % ("OK" if not bad else "ECHEC"))

    v = sum(Polygon(f["scs_polygon"]["coordinates"][0]).area
            * (f["scs_z_max"] - f["scs_z_min"]) for f in fls)
    print("Volume total : %.1f m3 · emprise cumulee : %.2f m2"
          % (v, sum(Polygon(b["scs_polygon"]["coordinates"][0]).area for b in bats)))
    if ko:
        print("ANOMALIES :")
        for k in ko:
            print("  -", k)
    print()


valider(BATIMENT, doc)
print("Fichier : %s (%d octets)" % (DST.name, DST.stat().st_size))
print("Separations non horizontales arbitrees au niveau le plus bas : %d"
      % len(retraiter))
for zn, ea, eb, d in retraiter:
    print("    %-18s %s | %s  -> %.0f mm bascules vers le haut" % (zn, ea, eb, d))
