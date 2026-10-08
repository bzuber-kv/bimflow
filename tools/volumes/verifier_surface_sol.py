#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verifier_surface_sol.py - Le rapport de validation de CAR_Surface_sol, en
dix lignes au plus, depuis un JSON du bouton AuditVolumes.

CE QU'IL RAPPROCHE, pour chaque volume :
  - CAR_Surface_sol, tel que l'audit l'a relu PAR GUID dans la maquette
    (volumes[].surface_sol) ;
  - le contour recalcule ICI, hors Revit, par lib/bimflow_contour a partir
    des faces du JSON - le code meme dont le bouton d'ecriture s'est servi.
    Un desaccord entre ce calcul et celui de l'audit dirait qu'IronPython et
    CPython ne rendent pas la meme chose : c'est verifie, pas suppose ;
  - l'emprise que audit_to_zones envoie a Ivion, dont la fusion des sommets
    est partagee entre volumes (voir l'en-tete de bimflow_contour).
Puis les sommes par REF_Batiment x REF_Etage, et le total des volumes ETAGE.

SUR UN AUDIT ANTERIEUR A L'ECRITURE (pas de cle surface_sol), il rend la
PREVISION : ce que l'outil ecrira, et les sommes attendues. C'est ce qu'il
faut comparer au rapport d'apres ecriture.

Usage : python3 verifier_surface_sol.py <audit.json> [--detail]
Code de sortie : 0 si tous les volumes sont conformes (ou, en prevision,
tous reconstructibles), 1 sinon.

bimflow - Keovia Solutions inc. - 2026-09-28
"""
import json
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE / "bimflow.extension" / "lib"))
from bimflow_contour import (contour_du_volume, face_basse, Sommets,  # noqa
                             chainer, aire_lacet, segments_verticaux)

TOL_M2 = 0.01


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    detail = "--detail" in sys.argv
    if not args:
        sys.exit("Usage : python3 verifier_surface_sol.py <audit.json> [--detail]")
    src = pathlib.Path(args[0])
    audit = json.loads(src.read_text(encoding="utf-8"))
    volumes = audit.get("volumes", [])

    partage = Sommets()           # comme audit_to_zones : une fusion commune
    statuts = {}
    ecart_lib_audit = 0.0         # CPython contre IronPython, meme code
    ecart_car = 0.0               # valeur portee contre contour
    ecart_ivion = 0.0             # contour du volume contre emprise Ivion
    sans_contour = []
    inclinees = []
    sommes = {}
    ecrit = any("surface_sol" in v for v in volumes)

    for v in volumes:
        faces = v.get("faces") or []
        _anneau, aire, motif = contour_du_volume(faces)
        s = v.get("surface_sol") or {}
        statut = s.get("statut", "PREVU" if aire is not None else "SANS_CONTOUR")
        statuts[statut] = statuts.get(statut, 0) + 1
        if aire is None:
            sans_contour.append((v.get("family_name"), motif))
            continue
        if s.get("contour_aire_m2") is not None:
            ecart_lib_audit = max(ecart_lib_audit,
                                  abs(round(aire, 4) - s["contour_aire_m2"]))
        car = s.get("CAR_Surface_sol_m2")
        if car is not None:
            ecart_car = max(ecart_car, abs(car - aire))
        anneau_iv, _m = chainer(segments_verticaux(faces), partage)
        if anneau_iv is not None:
            ecart_ivion = max(ecart_ivion, abs(abs(aire_lacet(anneau_iv)) / 1e6 - aire))
        fb = face_basse(faces, aire)
        if fb["inclinee"]:
            inclinees.append("%s %+.2f" % (v.get("family_name", "?").split("__")[0],
                                           fb["ecart_m2"]))

        seg = v.get("segments") or {}
        bat = ((v.get("parametres") or {}).get("REF_Batiment") or {}).get("valeur") or "?"
        valeur = car if car is not None else round(aire, 4)
        for cle in [(bat, seg.get("REF_Etage") or "?")] + (
                [("TOTAL", "ETAGE")] if seg.get("CLS_Nature_volume") == "ETAGE" else []):
            ligne = sommes.setdefault(cle, [0, 0.0, 0.0])
            ligne[0] += 1
            ligne[1] += valeur
            ligne[2] += aire

    n = len(volumes)
    ok = statuts.get("OK", 0) if ecrit else statuts.get("PREVU", 0)
    cles = sorted(k for k in sommes if k[0] != "TOTAL")
    pire = max((abs(sommes[k][1] - sommes[k][2]), k) for k in cles) if cles else (0, None)
    tot = sommes.get(("TOTAL", "ETAGE"), [0, 0.0, 0.0])

    # --- dix lignes, pas une de plus ------------------------------------
    print("CAR_Surface_sol  ·  %s  ·  %s" % (audit.get("entete", {}).get("maquette"), src.name))
    print("%s : %d/%d %s" % ("ecrits et conformes" if ecrit else "PREVISION, reconstructibles",
                             ok, n, "OK" if ok == n else "INCOMPLET"))
    print("statuts : " + ", ".join("%s %d" % kv for kv in sorted(statuts.items())))
    print("ecart CAR / contour (max) ......... %.4f m2  (tolerance %.2f)" % (ecart_car, TOL_M2)
          if ecrit else "ecart CAR / contour ............... sans objet avant ecriture")
    print("ecart CPython / audit Revit (max) . %.4f m2" % ecart_lib_audit
          if ecrit else "ecart CPython / audit Revit ....... sans objet avant ecriture")
    print("ecart volume / emprise Ivion (max)  %.4f m2  (fusion de sommets partagee)" % ecart_ivion)
    print("sommes bat x etage : %d cases, ecart CAR/contour max %.4f m2 (%s)"
          % (len(cles), pire[0], " ".join(pire[1]) if pire[1] else "-"))
    print("total ETAGE : %d volumes, %.2f m2 (CAR) / %.2f m2 (contour), ecart %+.4f"
          % (tot[0], tot[1], tot[2], tot[1] - tot[2]))
    print("face basse inclinee : %d  %s" % (len(inclinees), "  ".join(inclinees)))
    print("sans contour : %d%s" % (len(sans_contour), "" if not sans_contour else
                                   "  " + "; ".join("%s (%s)" % t for t in sans_contour[:3])))

    if detail:
        print()
        print("%-16s %-20s %4s %12s %12s %9s" % ("REF_Batiment", "REF_Etage", "n",
                                                 "CAR m2", "contour m2", "ecart"))
        for k in cles + [("TOTAL", "ETAGE")]:
            if k in sommes:
                c = sommes[k]
                print("%-16s %-20s %4d %12.2f %12.2f %+9.4f" % (k[0], k[1], c[0], c[1], c[2],
                                                               c[1] - c[2]))
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
