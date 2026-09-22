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
  ROTATION : +31.54 deg dans le sens TRIGONOMETRIQUE, repere projet ->
  repere SCS. Le SCS est aligne sur le nord grille MTM8 (la fiche du point
  de base Ivion declare une rotation de 0 deg). Applique AVANT la
  translation, puisque celle-ci est exprimee en axes MTM8.
  Par defaut le script n'applique RIEN (sortie sandbox) ; --scs produit la
  sortie georeferencee.

Usage : python3 gen_sitemodel.py <audit.json> [nom_batiment] [--scs]
        --scs applique DX/DY/DZ et THETA ; refuse tant que THETA est None.
"""
import json, pathlib, sys
from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = pathlib.Path(__file__).parent
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "junior.json"

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SCS = "--scs" in sys.argv
BATIMENT = ARGS[1] if len(ARGS) > 1 else "Junior"
SITE = "The Study"

# Origine interne Revit -> point de base Ivion actuel, en coordonnees partagees.
# Mesure : ivion_api (ancien point de base) + PEP v1.9 (controle K3).
DX, DY, DZ = 17.521326, -1.691684, -1.240
THETA = -31.54      # degres, rotation appliquee aux COORDONNEES, repere
                    # projet -> repere SCS. Attention au sens : l'angle au
                    # nord du projet est +31.54 deg dans le sens TRIGONO-
                    # METRIQUE pour amener le vecteur nord projet sur le nord
                    # geographique (le nord projet est dans le quart NE du
                    # reel). Transformer des COORDONNEES est l'operation
                    # inverse, d'ou le signe negatif. Verifie : seul ce signe
                    # place Junior dans l'emprise du site_model reel de
                    # The Study (X -56.9..-36.6, Y 29.1..58.9 dans
                    # X -58.3..24.8, Y -1.4..60.4).
                    # Le SCS est aligne sur le nord GRILLE MTM8 : la fiche du
                    # point de base Ivion declare une rotation de 0 deg.

if SCS and THETA is None:
    sys.exit("REFUS : --scs demande mais THETA n'est pas mesure. Lever l'angle "
             "par GET /api/site/{siteId}/affine_ref_sys ou POST /transform, "
             "ou par deux points communs au site_model existant et a la maquette.")
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
    import math
    t = math.radians(THETA)
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
zones = json.loads(SRC.read_text(encoding="utf-8"))["zones"]

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

union = unary_union(list(polys.values()))
if union.geom_type != "Polygon":
    sys.exit("ERREUR : union non simple (%s)" % union.geom_type)
union = union.simplify(0)


def attrs_floor(zn, t):
    a = {"keovia_ref_batiment": BATIMENT,
         "keovia_ref_zone": zn,
         "keovia_ref_etage": t["etage"],
         "keovia_cls_nature_volume": "ZONE_IVION",
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
            "keovia_cls_nature_volume": "ZONE_IVION",
            "keovia_repere": ("SCS Ivion (DX %.6f DY %.6f DZ %.3f, rotation %s deg)"
                              % (DX, DY, DZ, THETA)) if SCS else
                             "ORIGINE INTERNE REVIT, metres, AUCUNE transformation "
                             "- non georeference, sandbox uniquement",
            "keovia_src": "A_VOL / %s" % SRC.name,
        },
        "children": ch,
    })

DST = HERE / ("site_model_%s.json" % BATIMENT.lower())
DST.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

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
