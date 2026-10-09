#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tools/marquages/tables.py
"""Tables qui font foi (C-MP4) : une ligne par photo, une ligne par marquage.

Les marquages sont les groupes de vues dont le grain s'apparie (union des
paires au-dessus du seuil). Le texte et le format ne sont pas lus par
l'outil (lecture visuelle, F4) : ils sont ecrits NON_LU, jamais laisses vides.
Une vue que le controle n'a pas acceptee passe « A_VALIDER_A_LA_MAIN » (C-MP2).
"""
from __future__ import annotations

import csv
from pathlib import Path

NON_LU = "NON_LU"


def regrouper(vues: list[str], paires: list[dict]) -> list[list[str]]:
    """Groupes de vues reliees par au moins une paire « meme_pave » (union-find)."""
    parent = {v: v for v in vues}

    def racine(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for pr in paires:
        if pr["meme_pave"] and pr["a"] in parent and pr["b"] in parent:
            parent[racine(pr["a"])] = racine(pr["b"])
    groupes: dict[str, list[str]] = {}
    for v in vues:
        groupes.setdefault(racine(v), []).append(v)
    return sorted((sorted(g) for g in groupes.values()), key=lambda g: g[0])


def _ecrire_csv(chemin: Path, entetes: list[str], lignes: list[list]) -> None:
    # UTF-8 avec BOM, separateur ; (lisible tel quel dans Excel)
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(entetes)
        w.writerows(lignes)


def construire(redressement: list[dict], controle: list[dict], paires: list[dict],
               px_par_mm: float, dossier: Path) -> tuple[Path, Path]:
    """Ecrit photos.csv et marquages.csv dans dossier ; rend leurs chemins."""
    dossier = Path(dossier)
    ctl = {c["vue"]: c for c in controle}
    acceptees = sorted(v for v, c in ctl.items() if c["ok"])
    groupes = regrouper(acceptees, paires)
    id_de_vue = {}
    lignes_m = []
    points = {(pr["a"], pr["b"]): pr["points"] for pr in paires}
    for i, g in enumerate(groupes, 1):
        ident = f"M{i:03d}"
        for v in g:
            id_de_vue[v] = ident
        pmax = max((points.get((a, b), 0) for a in g for b in g if a < b), default=0)
        lignes_m.append([ident, len(g), ",".join(g), pmax, NON_LU, NON_LU])
    lignes_p = []
    for r in redressement:
        vue = r.get("vue", "")
        c = ctl.get(vue)
        if not r.get("ok"):
            statut, raison = "ECHEC_REDRESSEMENT", r.get("raison", "")
        elif c is None:
            statut, raison = "NON_CONTROLE", "vue absente du controle"
        elif c["ok"]:
            statut, raison = "ACCEPTE", ""
        else:
            statut, raison = "A_VALIDER_A_LA_MAIN", c.get("raison", "")
        lignes_p.append([r["photo"], vue, statut, raison, r.get("mode", ""), r.get("ratio", ""),
                         px_par_mm if r.get("ok") else "", r.get("px_par_mm_source", ""),
                         id_de_vue.get(vue, "")])
    photos = dossier / "photos.csv"
    marquages = dossier / "marquages.csv"
    _ecrire_csv(photos, ["photo", "vue", "statut", "raison", "mode", "ratio",
                         "px_par_mm_vue", "px_par_mm_source", "id_marquage"], lignes_p)
    _ecrire_csv(marquages, ["id_marquage", "n_vues", "vues", "points_max",
                            "texte", "format"], lignes_m)
    return photos, marquages
