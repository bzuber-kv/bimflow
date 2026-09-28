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
    from bimflow_noms import lire as lire_nom, NATURES_EXPORTEES
    # La reconstruction du contour vit dans bimflow_contour depuis le
    # 2026-09-28 : le bouton d'ecriture en tire CAR_Surface_sol, et l'audit
    # le controle, avec ce meme code.
    from bimflow_contour import (aire_lacet, Sommets, chainer,
                                 contours_egaux, segments_verticaux)
except ImportError:
    sys.exit("REFUS : modules partages bimflow_noms / bimflow_contour "
             "introuvables. Attendus dans %s"
             % (RACINE / "bimflow.extension" / "lib"))

# --------------------------------------------------------------------------
# Reglages - fusion des sommets et egalite de contours : bimflow_contour
# --------------------------------------------------------------------------

TOL_AIRE_M2 = 0.5          # ecart admis contour reconstruit / face horizontale
TOL_PARTITION_M2 = 0.05    # ecart admis somme des zones / union des zones

# --------------------------------------------------------------------------


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
    zone, etage, nature, cle = lu

    faces = v.get("faces") or []
    if not faces:
        refus.append((ident, nom, "aucune face lue par l'audit"))
        continue

    segments = segments_verticaux(faces)
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

    # LE GROUPE EST LA ZONE. Pas le batiment : REF_Batiment dit de quel
    # batiment reel releve le volume, il ne regroupe rien. Et la cle "sup"
    # ne change ni le groupe ni l'etage - c'est un discriminant de nom.
    zones.setdefault(zone, []).append({
        "etage": etage,
        "nature": nature,
        "cle": cle,
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

# Les deux controles qui suivent ne portent que sur ce qui PART vers Ivion.
# Une ENVELOPPE recouvre en plan les etages qu'elle enveloppe : la compter
# ferait echouer la partition et, si elle partage la zone d'un etage, la
# regle R1 - deux faux echecs sur une maquette pourtant juste. Elle reste
# dans le fichier ecrit ; c'est gen_sitemodel qui l'ecarte de l'export.


def exportables(tranches):
    return [t for t in tranches if t.get("nature") in NATURES_EXPORTEES]


mises_de_cote = [t for tr in zones.values() for t in tr
                 if t.get("nature") not in NATURES_EXPORTEES]
if mises_de_cote:
    print("natures hors export mises de cote pour les controles ... %d "
          "tranche(s) : %s"
          % (len(mises_de_cote),
             ", ".join(sorted(set(str(t.get("nature")) for t in mises_de_cote)))))

# R1 : le contour est CONSTANT sur toutes les tranches d'une meme zone
zones_variables = []
for zone, tranches in zones.items():
    retenues = exportables(tranches)
    if not retenues:
        continue
    reference = [tuple(p) for p in retenues[0]["coords"]]
    for t in retenues[1:]:
        if not contours_egaux(reference, [tuple(p) for p in t["coords"]]):
            zones_variables.append((zone, t["etage"]))
print("R1  contour constant sur toutes les tranches ... %s"
      % ("OK (%d zone(s))" % len([z for z in zones.values() if exportables(z)])
         if not zones_variables else "ECHEC (%d tranche(s))" % len(zones_variables)))

# partition en plan : somme des aires de zone == aire de l'union
nommees = [(nom, exportables(tr)[0])
           for nom, tr in zones.items() if exportables(tr)]
contours_zone = [t for _nom, t in nommees]
somme = sum(t["aire"] for t in contours_zone)
union_aire = None
emprises = None
try:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    emprises = [(nom, Polygon([(x / 1000.0, y / 1000.0) for x, y in t["coords"]]))
                for nom, t in nommees]
    union = unary_union([p for _nom, p in emprises])
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


# OU se recouvrent-elles ? Le total ne repare rien : ce qui sert, c'est le
# NOM des deux zones et l'epaisseur de la bande commune. Une bande de 104 mm
# sur quinze metres, c'est un bord trace sur la mauvaise face d'un mur ; un
# rectangle de 1,2 m sur 1,2 m, c'est un vrai conflit de trace. Les deux se
# corrigent dans Revit, mais pas du meme geste.
# Ajoute le 2026-09-25 : le lanceur promettait que "les lignes rouges nomment
# les volumes en cause", et pour la partition c'etait faux.
SEUIL_CONTACT_M2 = 0.01     # en deca, c'est un contact d'aretes, pas un
                            # recouvrement : deux zones mitoyennes se touchent


def couples_qui_se_recouvrent(emprises_nommees):
    """[(aire, zone A, zone B, epaisseur mm, longueur m)], du plus grand."""
    trouves = []
    for i, (nom_a, poly_a) in enumerate(emprises_nommees):
        for nom_b, poly_b in emprises_nommees[i + 1:]:
            if not poly_a.intersects(poly_b):
                continue
            commun = poly_a.intersection(poly_b)
            if commun.area <= SEUIL_CONTACT_M2:
                continue
            x0, y0, x1, y1 = commun.bounds
            cotes = sorted([x1 - x0, y1 - y0])
            trouves.append((commun.area, nom_a, nom_b, cotes[0] * 1000.0,
                            cotes[1]))
    trouves.sort(reverse=True)
    return trouves


if not ok_partition and emprises is not None:
    couples = couples_qui_se_recouvrent(emprises)
    print()
    if not couples:
        print("AUCUN COUPLE NE SE RECOUVRE de plus de %.2f m2." % SEUIL_CONTACT_M2)
        print("L'ecart vient donc d'un TROU entre les zones, pas d'un")
        print("recouvrement : il manque un volume, ou un bord ne rejoint pas")
        print("son voisin. Chercher le vide, pas le doublon.")
    else:
        print("ZONES QUI SE RECOUVRENT EN PLAN - a corriger dans Revit :")
        print()
        cumul = 0.0
        for aire, nom_a, nom_b, epaisseur, longueur in couples:
            cumul += aire
            print("  %7.3f m2   %-24s X  %s" % (aire, nom_a, nom_b))
            print("              bande de %.0f mm sur %.2f m"
                  % (epaisseur, longueur))
        print()
        print("  %7.3f m2   TOTAL, pour un ecart de %.3f m2" % (cumul, ecart))
        reste = ecart - cumul
        if abs(reste) <= TOL_PARTITION_M2:
            print("              le recouvrement explique tout l'ecart.")
        else:
            print("              il reste %.3f m2 : il y a AUSSI un trou."
                  % reste)

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

# UN REFUS QUI SUIT UN RAPPORT S'IMPRIME SUR STDOUT, puis sort par un code.
# Motif mesure le 2026-09-25 : sys.exit("message") ecrit sur STDERR, et quand
# le lanceur fusionne les deux flux par 2>&1, PowerShell les reordonne - la
# ligne REFUS tombait entre le troisieme et le quatrieme couple recouvrant,
# donc au milieu de la liste qu'elle est censee conclure. Vider stdout avant
# de sortir n'y change rien : le desordre vient de la fusion, pas du tampon.
# Un seul flux, un seul ordre. Les deux sorties du debut de fichier (module
# manquant, usage) restent sur stderr : rien ne les precede.

if not zones:
    print("\nREFUS : aucune zone exploitable. Rien n'est ecrit.")
    sys.exit(1)

if not ok_partition:
    print("\nREFUS : la partition en plan ne ferme pas. Les zones se "
          "recouvrent ou laissent un trou, et gen_sitemodel produirait un "
          "site_model qu'Ivion refuse (C1, emprises secantes). Rien n'est "
          "ecrit - reprendre les volumes dans Revit.")
    sys.exit(1)

sortie = {
    "_entete": {
        "outil": "audit_to_zones",
        "source": SRC.name,
        "maquette": entete.get("maquette"),
        "date_audit": entete.get("date"),
        "repere": "coordonnees internes du modele Revit, mm - aucune "
                  "transformation (c'est gen_sitemodel qui transforme)",
        # Reporte TEL QUEL depuis l'audit : c'est Revit qui l'a mesure, et
        # c'est de la que gen_sitemodel tire THETA et la translation.
        "emplacement_partage": entete.get("emplacement_partage"),
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
