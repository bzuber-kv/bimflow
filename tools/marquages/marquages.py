#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tools/marquages/marquages.py
"""Chaine « marquages plans » : redresser -> controler -> empreintes -> tables.

Ligne de commande unique, CPython hors Revit. Chaque etape lit le resultat de
la precedente dans le dossier de travail et ecrit le sien a cote :

    <travail>/vues/              vues redressees (<photo>_pave.jpg)
    <travail>/redressement.json
    <travail>/controle.json
    <travail>/empreintes.json
    <travail>/photos.csv, marquages.csv

Exemples (PowerShell, depuis tools\\marquages) :
    python marquages.py chaine -p parametres_dallage_300x600.json -t D:\\travail D:\\photos
    python marquages.py redresser -p parametres_dallage_300x600.json -t D:\\travail D:\\photos\\IMG_0001.JPG
    python marquages.py controler -p parametres_dallage_300x600.json -t D:\\travail

Le dossier de travail recoit des donnees d'affaire (photos, noms graves) :
il ne se place jamais dans le depot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parametres import Parametres, lire_parametres  # noqa: E402

# HEIC non lu : Pillow ne le decode pas sans greffon. Exporter en JPEG.
EXTENSIONS_PHOTO = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _photos(entrees: list[str]) -> list[Path]:
    res = []
    for e in map(Path, entrees):
        if e.is_dir():
            res += sorted(f for f in e.iterdir() if f.suffix.lower() in EXTENSIONS_PHOTO)
        else:
            res.append(e)
    return res


def _lire_json(chemin: Path, etape: str):
    if not chemin.exists():
        raise SystemExit(f"ARRET : {chemin} introuvable. Lancer d'abord l'etape « {etape} ».")
    return json.loads(chemin.read_text(encoding="utf-8"))


def _ecrire_json(chemin: Path, donnees) -> None:
    chemin.write_text(json.dumps(donnees, indent=1, ensure_ascii=False), encoding="utf-8")


def etape_redresser(p: Parametres, travail: Path, vues: Path, photos: list[Path],
                    debug: bool = False) -> list[dict]:
    from redressement import redresser
    if not photos:
        raise SystemExit("ARRET : aucune photo en entree.")
    vues.mkdir(parents=True, exist_ok=True)
    res = []
    for ph in photos:
        dbg = vues / f"dbg_{ph.stem}.jpg" if debug else None
        try:
            r = redresser(ph, vues, p, debug=dbg)
        except Exception as e:  # une photo qui plante n'arrete pas le lot : elle est rendue en echec
            r = {"photo": ph.name, "ok": False, "raison": repr(e)[:120]}
        print(("OK    " if r["ok"] else "ECHEC ") + r["photo"]
              + ("" if r["ok"] else f" : {r['raison']}"))
        res.append(r)
    _ecrire_json(travail / "redressement.json", res)
    print(f"redresses : {sum(r['ok'] for r in res)} / {len(res)}")
    return res


def etape_controler(p: Parametres, travail: Path, vues: Path) -> list[dict]:
    from controle import controler
    red = _lire_json(travail / "redressement.json", "redresser")
    res = [controler(vues / r["vue"], p) for r in red if r.get("ok")]
    for c in res:
        if not c["ok"]:
            print(f"A VALIDER A LA MAIN  {c['vue']} : {c['raison']}")
    _ecrire_json(travail / "controle.json", res)
    print(f"acceptes : {sum(c['ok'] for c in res)} / {len(res)}")
    return res


def etape_empreintes(p: Parametres, travail: Path, vues: Path) -> list[dict]:
    from empreintes import toutes_paires
    ctl = _lire_json(travail / "controle.json", "controler")
    acceptees = [vues / c["vue"] for c in ctl if c["ok"]]
    paires = toutes_paires(acceptees, p)
    _ecrire_json(travail / "empreintes.json", paires)
    doublons = [pr for pr in paires if pr["meme_pave"]]
    for pr in doublons:
        print(f"MEME MODULE  {pr['a']} = {pr['b']} ({pr['points']} points)")
    print(f"{len(acceptees)} vues, {len(paires)} paires, {len(doublons)} doublon(s) "
          f"au seuil de {p.seuil_meme_pave} points")
    return paires


def etape_tables(p: Parametres, travail: Path) -> None:
    from tables import construire
    red = _lire_json(travail / "redressement.json", "redresser")
    ctl = _lire_json(travail / "controle.json", "controler")
    paires = _lire_json(travail / "empreintes.json", "empreintes")
    photos, marquages = construire(red, ctl, paires, p.px_par_mm, travail)
    print(photos)
    print(marquages)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sous = ap.add_subparsers(dest="etape", required=True)
    for nom in ("chaine", "redresser", "controler", "empreintes", "tables"):
        s = sous.add_parser(nom)
        s.add_argument("-p", "--parametres", required=True, type=Path,
                       help="fichier JSON des parametres de la surface")
        s.add_argument("-t", "--travail", required=True, type=Path,
                       help="dossier de travail (hors depot)")
        s.add_argument("--vues", type=Path, default=None,
                       help="dossier des vues redressees (defaut : <travail>/vues)")
        if nom in ("chaine", "redresser"):
            s.add_argument("photos", nargs="+", help="photos ou dossiers de photos")
            s.add_argument("--debug", action="store_true",
                           help="ecrit aussi la vue de dessus annotee de chaque photo")
    a = ap.parse_args(argv)
    p = lire_parametres(a.parametres)
    travail = a.travail
    travail.mkdir(parents=True, exist_ok=True)
    vues = a.vues or travail / "vues"
    print(f"parametres : {p.source}  (module {p.largeur_mm:g} x {p.longueur_mm:g} mm, "
          f"{p.px_par_mm:g} px/mm)")
    if a.etape in ("chaine", "redresser"):
        etape_redresser(p, travail, vues, _photos(a.photos), a.debug)
    if a.etape in ("chaine", "controler"):
        etape_controler(p, travail, vues)
    if a.etape in ("chaine", "empreintes"):
        etape_empreintes(p, travail, vues)
    if a.etape in ("chaine", "tables"):
        etape_tables(p, travail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
