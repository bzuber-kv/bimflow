#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dry_run_depuis_audit.py - Rejoue le classement et la numerotation des volumes
de zone A PARTIR D'UN AUDIT JSON, hors Revit.

POURQUOI CET OUTIL EXISTE. Le bouton Renommer volumes decide de 201 noms
d'un coup. Son classement ne doit pas se decouvrir dans Revit, une fois les
familles renommees : il se lit ici, sur l'audit, avant le moindre clic.

Et il passe par LE MEME CODE : bimflow_noms.extraire() et
bimflow_volumes.classer() sont importes du lib\\ de l'extension, ceux-la
memes que le bouton appelle. Un instrument de mesure qui emprunte un autre
chemin que l'operation reelle ne mesure pas l'operation reelle.

Entree : le JSON du bouton Audit volumes.
Sortie : le meme CSV que le dry-run du bouton, plus les controles.

Usage : python3 dry_run_depuis_audit.py <audit.json> [sortie.csv]

bimflow - Keovia Solutions inc. - 2026-09-24
"""
import csv
import json
import pathlib
import sys
from collections import Counter, defaultdict

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "bimflow.extension" / "lib"))
try:
    from bimflow_noms import (extraire, ref_batiment, nom_de_famille,
                              incoherence_etage_nature, ETAGES_CONNUS)
    from bimflow_volumes import classer
except ImportError as err:
    sys.exit("REFUS : modules partages introuvables dans %s (%s)"
             % (RACINE / "bimflow.extension" / "lib", err))

# --------------------------------------------------------------------------
# Table de correction - typos relevees a la main sur la maquette, au
# 2026-09-24. Elle vit AUSSI dans le bouton : ce sont les memes quatre
# lignes, et elles disparaitront des que les noms seront refaits.
# --------------------------------------------------------------------------

CORRECTIONS = {
    "Volume 019__SC_Bp_Cp_3p_3p__ROOF_TOITURE":
        ("SC_Bp_Cp_3p_3p", "ROOF", "TOITURE", None),
    "Volume 089__MI_Amg_Am_4mg_5m_ROOF__ENTRETOIT":
        ("MI_Amg_Am_4mg_5m", "ROOF", "ENTRETOIT", None),
    "Volume 100__MI_Dm_Emg_6m_7m__ROOF_ENTRETOIT":
        ("MI_Dm_Emg_6m_7m", "ROOF", "ENTRETOIT", None),
    # nature absente du nom ; ETAGE arbitre par Bruno le 2026-09-24
    "Volume 098__MI_Dm_Emg_6m_7m__FLOOR_1":
        ("MI_Dm_Emg_6m_7m", "FLOOR_1", "ETAGE", None),
}

ENTETE_CSV = ["element_id", "ancien_nom_famille", "nouveau_nom_famille",
              "ancien_nom_type", "BAT", "REF_Zone", "REF_Etage",
              "CLS_Nature_volume", "cle", "REF_Batiment", "xc", "yc", "zmin"]


def lire_audit(chemin):
    """(volumes exploitables, non resolus). Un volume sans geometrie ou sans
    nom lisible n'est pas devine : il sort en non resolu."""
    audit = json.loads(pathlib.Path(chemin).read_text(encoding="utf-8"))
    exploitables, non_resolus = [], []
    for v in audit.get("volumes", []):
        nom = v.get("family_name") or ""
        if v.get("in_situ") is not True:
            non_resolus.append((v.get("id"), nom, "volume qui n'est pas in situ"))
            continue
        lu, motif = extraire(nom, CORRECTIONS)
        if lu is None:
            non_resolus.append((v.get("id"), nom, motif))
            continue
        zone, etage, nature, cle = lu
        bb = v.get("bbox")
        if not bb:
            non_resolus.append((v.get("id"), nom, "boite englobante absente"))
            continue
        exploitables.append({
            "id": v.get("id"),
            "nom": nom,
            "type": v.get("type_name"),
            "zone": zone,
            "etage": etage,
            "nature": nature,
            "cle": cle,
            "xc": (bb["xmin"] + bb["xmax"]) / 2.0,
            "yc": (bb["ymin"] + bb["ymax"]) / 2.0,
            "zmin": bb["zmin"],
        })
    return exploitables, non_resolus, audit.get("entete", {})


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage : python3 dry_run_depuis_audit.py <audit.json> "
                 "[sortie.csv]")
    source = pathlib.Path(sys.argv[1])
    sortie = (pathlib.Path(sys.argv[2]) if len(sys.argv) > 2
              else source.with_name(source.stem + "_renommage.csv"))

    volumes, non_resolus, entete = lire_audit(source)
    ordonnes, colonnes = classer(volumes)

    for v in ordonnes:
        v["nouveau"] = nom_de_famille(v["numero"], v["zone"], v["etage"],
                                      v["nature"], v["cle"])

    # --- controles ------------------------------------------------------
    collisions = defaultdict(list)
    for v in ordonnes:
        collisions[v["nouveau"]].append(v["id"])
    collisions = {k: ids for k, ids in collisions.items() if len(ids) > 1}

    incoherences = [(v["id"], v["nom"], incoherence_etage_nature(v["etage"],
                                                                 v["nature"]))
                    for v in ordonnes
                    if incoherence_etage_nature(v["etage"], v["nature"])]
    etages_inconnus = sorted(set(v["etage"] for v in ordonnes
                                 if v["etage"] not in ETAGES_CONNUS))
    dispersees = [c for c in colonnes if c["dispersion"] > 1.0]

    # --- CSV ------------------------------------------------------------
    with open(str(sortie), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(ENTETE_CSV)
        for v in ordonnes:
            # BAT = prefixe de la zone, celui qui TRIE.
            # REF_Batiment = la cle si elle designe un batiment, celui qui
            # sera ECRIT dans le parametre. Les deux different sur 18
            # volumes, et c'est voulu.
            w.writerow([v["id"], v["nom"], v["nouveau"], v["type"],
                        v["bat"], v["zone"], v["etage"], v["nature"],
                        v["cle"] or "", ref_batiment(v["zone"], v["cle"]),
                        "%.1f" % v["xc"], "%.1f" % v["yc"],
                        "%.1f" % v["zmin"]])

    # --- rapport --------------------------------------------------------
    print("=" * 74)
    print("DRY-RUN du renommage  ·  %s" % source.name)
    print("=" * 74)
    print("Maquette : %s  ·  audit du %s  ·  detachee : %s"
          % (entete.get("maquette", "?"), entete.get("date", "?"),
             entete.get("copie_detachee")))
    print()
    print("volumes lus et classes ........................ %d" % len(ordonnes))
    print("colonnes (REF_Zone distincts) ................. %d" % len(colonnes))
    print("NON RESOLUS - aucun ne sera renomme ........... %d %s"
          % (len(non_resolus), "OK" if not non_resolus else "A TRAITER"))
    print("collisions de nom final ....................... %d %s"
          % (len(collisions), "OK" if not collisions else "A TRAITER"))

    print()
    print("Decompte par BAT - prefixe de zone, celui qui trie "
          "(REF_Batiment, lui, peut differer) :")
    par_bat = Counter(v["bat"] for v in ordonnes)
    col_bat = Counter(c["batiment"] for c in colonnes)
    premier, dernier = {}, {}
    for v in ordonnes:
        premier.setdefault(v["bat"], v["numero"])
        dernier[v["bat"]] = v["numero"]
    for bat in sorted(par_bat, key=lambda b: premier[b]):
        print("    %-4s %3d colonne(s)  %3d volume(s)   VOL_%03d -> VOL_%03d"
              % (bat, col_bat[bat], par_bat[bat], premier[bat], dernier[bat]))

    if dispersees:
        print()
        print("COLONNES DISPERSEES - leurs volumes ne partagent pas un centre :")
        for c in dispersees:
            print("    %-24s dispersion %.1f mm sur %d volume(s)"
                  % (c["zone"], c["dispersion"], len(c["volumes"])))

    if non_resolus:
        print()
        print("NON RESOLUS :")
        for ident, nom, motif in non_resolus:
            print("    %-10s %-48s %s" % (ident, nom, motif))

    if collisions:
        print()
        print("COLLISIONS - il manque une cle 'sup' :")
        for nom, ids in sorted(collisions.items()):
            print("    %-56s %s" % (nom, ids))

    if incoherences:
        print()
        print("ETAGE ET NATURE NE S'ACCORDENT PAS (signale, non bloquant) :")
        for ident, nom, motif in incoherences:
            print("    %-10s %-48s %s" % (ident, nom, motif))

    if etages_inconnus:
        print()
        print("ETAGES HORS DE LA LISTE CONNUE (liste ouverte, pour information) :")
        for e in etages_inconnus:
            print("    %s" % e)

    print()
    print("CSV : %s" % sortie)
    if non_resolus or collisions:
        print()
        print("Le bouton REFUSERA d'executer tant qu'il reste un non resolu "
              "ou une collision.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
