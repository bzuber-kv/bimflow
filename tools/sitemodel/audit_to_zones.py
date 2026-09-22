#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_to_zones.py - Le maillon qui raccorde la chaine : convertit la sortie
native du bouton pyRevit AuditVolumes en l'entree attendue par
gen_sitemodel.py.

    AuditVolumes (dans Revit)  ->  audit_volumes_zone_*.json
    audit_to_zones.py (ici)    ->  <...>_zones.json
    gen_sitemodel.py           ->  site_model_<batiment>.json

Entree  : {entete, volumes[{family_name, segments, bbox, faces[...]}], ...}
Sortie  : {"zones": {nom_zone: [{etage, coords, aire, zmin, zmax, incl, vol}]}}
          coords = anneau FERME en mm, repere interne du modele Revit.

COMMENT LE CONTOUR EST RECONSTRUIT
  1. les faces VERTICALES du volume donnent chacune leurs aretes projetees
     en (x, y) - l'audit les a deja projetees et deduplique ;
  2. les extremites sont fusionnees a la tolerance (1 mm par defaut), puis
     chainees en cycle : chaque sommet doit avoir exactement DEUX voisins,
     et le parcours doit revenir a son point de depart en consommant TOUTES
     les aretes. Sinon le contour est refuse.
  3. zmin / zmax viennent de la boite englobante du volume ;
  4. incl = 1 si une separation haute ou basse n'est pas plane en z, c'est
     a dire si l'audit a classe une face INCLINEE, ou une face horizontale
     non plane ;
  5. aire = aire du contour reconstruit (formule du lacet) ; vol = volume du
     solide, tel que Revit l'a calcule ;
  6. zone et etage sont DEDUITS DU NOM DE FAMILLE, par le module partage
     bimflow_noms - le meme que le bouton d'ecriture.

CE QUI N'EST JAMAIS FAIT : reparer un contour. Un cycle qui ne se referme
pas, une zone dont le contour varie d'une tranche a l'autre, un ecart de
partition : c'est signale, et rien n'est ecrit pour le volume ou la zone en
cause. Un contour repare en silence produirait un site_model plausible et
faux, que seul Ivion refuserait - ou pire, accepterait.

HORS REVIT. Ce script travaille sur le JSON, il ne touche a aucune maquette.
CPython 3 ; shapely n'est utilise que pour l'aire de l'union (controle de
partition).

Usage : python3 audit_to_zones.py <audit.json> [sortie.json]

bimflow - volumes de zone, conversion - Keovia Solutions inc.
2026-09-22 - NON EPROUVE sur une sortie d'audit reelle : au 2026-09-22 le
bouton AuditVolumes n'a jamais tourne dans Revit.
"""
import json
import math
import pathlib
import sys

# Le decoupage des noms vit dans le lib\ de l'extension pyRevit : un seul
# endroit decoupe VOL__<zone>__<etage>__<attribut>, ici comme dans Revit.
RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "bimflow.extension" / "lib"))
try:
    from bimflow_noms import lire as lire_nom
except ImportError:
    sys.exit("REFUS : module partage bimflow_noms introuvable. Attendu dans "
             "%s" % (RACINE / "bimflow.extension" / "lib"))

# --------------------------------------------------------------------------
# Reglages
# --------------------------------------------------------------------------

TOL_SOMMET_MM = 1.0        # fusion de deux extremites d'aretes
DEC_SOMMET = 1             # arrondi de la cle d'un sommet, en dixieme de mm
TOL_AIRE_M2 = 0.5          # ecart admis contour reconstruit / face horizontale
TOL_CONTOUR_MM = 1.0       # ecart admis entre deux tranches d'une meme zone
TOL_PARTITION_M2 = 0.05    # ecart admis somme des zones / union des zones

# --------------------------------------------------------------------------


def aire_lacet(anneau):
    """Aire algebrique d'un anneau ferme, en mm2 (positive si sens trigo)."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(anneau, anneau[1:]):
        s += x1 * y2 - x2 * y1
    return s / 2.0


class Sommets(object):
    """Fusionne les extremites proches en UN sommet canonique.

    Grille de TOL mm : pour un point donne, on ne compare qu'aux sommets des
    neuf cases voisines. Le cout reste lineaire, et la fusion ne depend pas
    de l'ordre de lecture a la tolerance pres."""

    def __init__(self, tol=TOL_SOMMET_MM):
        self.tol = tol
        self.cases = {}

    def _case(self, x, y):
        return (int(math.floor(x / self.tol)), int(math.floor(y / self.tol)))

    def canonique(self, x, y):
        cx, cy = self._case(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py in self.cases.get((cx + dx, cy + dy), []):
                    if math.hypot(px - x, py - y) <= self.tol:
                        return (px, py)
        point = (round(x, DEC_SOMMET), round(y, DEC_SOMMET))
        self.cases.setdefault(self._case(*point), []).append(point)
        return point


def chainer(segments, sommets):
    """(anneau ferme, None) ou (None, motif du refus).

    Un contour de volume est un cycle simple : chaque sommet a exactement
    deux voisins, et le parcours consomme toutes les aretes."""
    voisins = {}
    aretes = set()
    for (x1, y1), (x2, y2) in segments:
        a = sommets.canonique(x1, y1)
        b = sommets.canonique(x2, y2)
        if a == b:
            continue                      # arete degeneree apres fusion
        cle = (a, b) if a <= b else (b, a)
        if cle in aretes:
            continue                      # doublon : deja vue
        aretes.add(cle)
        voisins.setdefault(a, []).append(b)
        voisins.setdefault(b, []).append(a)

    if not aretes:
        return None, "aucune arete exploitable"

    degres = {}
    for point, liste in voisins.items():
        degres.setdefault(len(liste), 0)
        degres[len(liste)] += 1
    mauvais = [(p, len(v)) for p, v in voisins.items() if len(v) != 2]
    if mauvais:
        return None, ("contour non refermable : %d sommet(s) de degre != 2 "
                      "(degres observes : %s)"
                      % (len(mauvais),
                         ", ".join("%d->%dx" % (d, n)
                                   for d, n in sorted(degres.items()))))

    depart = min(voisins)
    anneau = [depart]
    precedent = None
    courant = depart
    vues = set()
    while True:
        suite = [v for v in voisins[courant] if v != precedent]
        if not suite:
            return None, "contour interrompu : cul-de-sac"
        suivant = suite[0]
        cle = (courant, suivant) if courant <= suivant else (suivant, courant)
        vues.add(cle)
        anneau.append(suivant)
        precedent, courant = courant, suivant
        if courant == depart:
            break
        if len(anneau) > len(aretes) + 1:
            return None, "contour interrompu : parcours non convergent"

    if len(vues) != len(aretes):
        return None, ("plusieurs contours fermes : %d arete(s) sur %d "
                      "parcourues - le volume porte-t-il plusieurs solides, "
                      "ou un trou ?" % (len(vues), len(aretes)))

    if aire_lacet(anneau) < 0:
        anneau.reverse()                  # sens trigonometrique, par convention
    return anneau, None


def contours_egaux(a, b):
    """Deux anneaux decrivent-ils le meme contour, a la tolerance pres ?"""
    ea = set(a[:-1])
    eb = set(b[:-1])
    if len(ea) != len(eb):
        return False
    for point in ea:
        if point in eb:
            continue
        if not any(math.hypot(point[0] - q[0], point[1] - q[1]) <= TOL_CONTOUR_MM
                   for q in eb):
            return False
    return True


# --------------------------------------------------------------------------
# 1. Lecture de l'audit
# --------------------------------------------------------------------------

if len(sys.argv) < 2:
    sys.exit("Usage : python3 audit_to_zones.py <audit.json> [sortie.json]")

SRC = pathlib.Path(sys.argv[1])
DST = (pathlib.Path(sys.argv[2]) if len(sys.argv) > 2
       else SRC.with_name(SRC.stem + "_zones.json"))

audit = json.loads(SRC.read_text(encoding="utf-8"))
volumes = audit.get("volumes", [])
entete = audit.get("entete", {})

sommets = Sommets()
zones = {}
refus = []          # (identifiant, nom de famille, motif)
ecarts_aire = []    # (nom, ecart m2)
retenus = 0

for v in volumes:
    ident = v.get("id")
    nom = v.get("family_name")

    lu, motif = lire_nom(nom or "")
    if lu is None:
        refus.append((ident, nom, "nom hors motif : %s" % motif))
        continue
    zone, etage, _attribut = lu

    faces = v.get("faces") or []
    if not faces:
        refus.append((ident, nom, "aucune face lue par l'audit"))
        continue

    segments = []
    for f in faces:
        if f.get("classe") == "VERTICALE":
            segments.extend(f.get("segments_xy") or [])
    if not segments:
        refus.append((ident, nom, "aucune face verticale : contour "
                                  "impossible a reconstruire"))
        continue

    anneau, motif = chainer(segments, sommets)
    if anneau is None:
        refus.append((ident, nom, motif))
        continue

    bbox = v.get("bbox") or {}
    zmin, zmax = bbox.get("zmin"), bbox.get("zmax")
    if zmin is None or zmax is None:
        refus.append((ident, nom, "boite englobante absente : zmin/zmax "
                                  "inconnus"))
        continue

    # une separation non plane en z : l'audit l'a classee INCLINEE, ou bien
    # a classe horizontale une face non plane
    incl = 0
    for f in faces:
        classe = f.get("classe")
        if classe == "INCLINEE":
            incl = 1
        elif classe and classe.startswith("HORIZONTALE") and not f.get("planaire"):
            incl = 1

    aire_mm2 = abs(aire_lacet(anneau))
    aire_m2 = aire_mm2 / 1e6

    # controle : le contour reconstruit contre l'aire que Revit donne a la
    # face horizontale du volume
    aires_h = [f.get("aire_m2") for f in faces
               if f.get("classe", "").startswith("HORIZONTALE")
               and f.get("aire_m2") is not None]
    if aires_h:
        ecarts_aire.append((nom, abs(aire_m2 - max(aires_h))))

    zones.setdefault(zone, []).append({
        "etage": etage,
        "coords": [list(p) for p in anneau],
        "aire": round(aire_m2, 4),
        "zmin": zmin,
        "zmax": zmax,
        "incl": incl,
        "vol": v.get("volume_solides_m3") or v.get("volume_brut_m3"),
        "_id_revit": ident,
        "_family_name": nom,
    })
    retenus += 1

# --------------------------------------------------------------------------
# 2. Controles - ce sont eux qui disent si la reconstruction est bonne
# --------------------------------------------------------------------------

print("=" * 72)
print("AUDIT -> ZONES  ·  %s" % SRC.name)
print("=" * 72)
print("Maquette : %s  ·  audit du %s"
      % (entete.get("maquette", "?"), entete.get("date", "?")))
print()

ok_contours = (retenus == len(volumes))
print("contours reconstruits ......................... %d/%d %s"
      % (retenus, len(volumes), "OK" if ok_contours else "INCOMPLET"))

ok_aire = True
if ecarts_aire:
    pire_nom, pire = max(ecarts_aire, key=lambda t: t[1])
    ok_aire = pire <= TOL_AIRE_M2
    print("ecart contour / face horizontale .............. %.3f m2 max (%s) %s"
          % (pire, pire_nom, "OK" if ok_aire else "ECHEC"))
else:
    print("ecart contour / face horizontale .............. aucune face "
          "horizontale a comparer")

# R1 : le contour est CONSTANT sur toutes les tranches d'une meme zone
zones_variables = []
for zone, tranches in zones.items():
    reference = [tuple(p) for p in tranches[0]["coords"]]
    for t in tranches[1:]:
        if not contours_egaux(reference, [tuple(p) for p in t["coords"]]):
            zones_variables.append((zone, t["etage"]))
print("R1  contour constant sur toutes les tranches ... %s"
      % ("OK (%d zone(s))" % len(zones)
         if not zones_variables else "ECHEC (%d tranche(s))" % len(zones_variables)))

# partition en plan : somme des aires de zone == aire de l'union
somme = sum(z[0]["aire"] for z in zones.values())
union_aire = None
try:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    union = unary_union([Polygon([(x / 1000.0, y / 1000.0)
                                  for x, y in z[0]["coords"]])
                         for z in zones.values()])
    union_aire = union.area
except ImportError:
    print("partition en plan ............................. NON VERIFIEE "
          "(shapely absent : pip install -r requirements.txt)")

ok_partition = True
if union_aire is not None:
    ecart = abs(somme - union_aire)
    ok_partition = ecart <= TOL_PARTITION_M2
    print("partition en plan ............................. %.2f m2 (zones) / "
          "%.2f m2 (union), ecart %.2f m2 %s"
          % (somme, union_aire, ecart, "OK" if ok_partition else "ECHEC"))

if refus:
    print()
    print("VOLUMES ECARTES - rien n'est ecrit pour eux :")
    for ident, nom, motif in refus:
        print("  - %-10s %-34s %s" % (ident, nom or "(sans nom)", motif))

if zones_variables:
    print()
    print("ZONES A CONTOUR VARIABLE - ecartees en entier (R1) :")
    for zone, etage in zones_variables:
        print("  - %-20s tranche %s" % (zone, etage))

# --------------------------------------------------------------------------
# 3. Ecriture - refusee si un controle structurant echoue
# --------------------------------------------------------------------------

for zone, _etage in zones_variables:
    zones.pop(zone, None)

if not zones:
    sys.exit("\nREFUS : aucune zone exploitable. Rien n'est ecrit.")

if not ok_partition:
    sys.exit("\nREFUS : la partition en plan ne ferme pas. Les zones se "
             "recouvrent ou laissent un trou, et gen_sitemodel produirait un "
             "site_model qu'Ivion refuse (C1, emprises secantes). Rien n'est "
             "ecrit - reprendre les volumes dans Revit.")

sortie = {
    "_entete": {
        "outil": "audit_to_zones",
        "source": SRC.name,
        "maquette": entete.get("maquette"),
        "date_audit": entete.get("date"),
        "repere": "coordonnees internes du modele Revit, mm - aucune "
                  "transformation (c'est gen_sitemodel qui transforme)",
        "volumes_lus": len(volumes),
        "volumes_retenus": retenus,
        "volumes_ecartes": len(refus),
    },
    "zones": {zone: tranches for zone, tranches in sorted(zones.items())},
}

DST.write_text(json.dumps(sortie, ensure_ascii=False, indent=1),
               encoding="utf-8")

print()
print("Ecrit : %s  ·  %d zone(s), %d tranche(s)"
      % (DST.name, len(zones), sum(len(t) for t in zones.values())))
for zone in sorted(zones):
    tranches = sorted(zones[zone], key=lambda t: t["zmin"])
    print("    %-20s %2d tranche(s)  %8.2f m2  %s"
          % (zone, len(tranches), tranches[0]["aire"],
             " ".join(t["etage"] for t in tranches)))
if not (ok_contours and ok_aire):
    print()
    print("ATTENTION : un controle au moins n'est pas au vert. Le fichier est "
          "ecrit avec les seules zones retenues - lire les ecarts ci-dessus "
          "avant de le passer a gen_sitemodel.")
