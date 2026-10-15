#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tools/marquages/controle.py
"""Controle d'un cadrage : joints sur les bords, lettres non coupees, tailles de lettres plausibles.

Repris du pilote (gate.py). Trois verifications sur la vue redressee (F5) :
  1. un joint visible sur au moins `joints_min` cotes (au pas, le joint est
     a cheval sur le bord de la vue) ;
  2. pas plus de `lettres_coupees_max` traits graves qui touchent le bord ;
  3. au moins une ligne de texte horizontale lisible, et aucune ligne aux
     lettres plus grandes que `capitale_max_mm` (signe d'un zoom : l'interligne
     a ete pris pour le pas).
Une vue refusee n'est pas fausse : elle passe « a valider a la main » (C-MP2).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from capitales import gravure, lignes
from parametres import Parametres


def controler(vue: Path, p: Parametres) -> dict:
    vue = Path(vue)
    g = cv2.imread(str(vue), cv2.IMREAD_GRAYSCALE)
    if g is None:
        return {"vue": vue.name, "ok": False, "raison": "vue illisible"}
    g = g.astype(np.float32)
    H, W = g.shape
    k = p.echelle
    px = lambda v: int(round(v * k))  # noqa: E731
    med = np.median(g[px(60):-px(60), px(60):-px(60)])
    # 1) joints : bande sombre au ras de chaque bord
    b, m = px(25), px(100)
    cotes = {"haut": g[:b, m:-m], "bas": g[-b:, m:-m], "gauche": g[m:-m, :b], "droite": g[m:-m, -b:]}
    contraste = {c: float(med - np.percentile(v, 20)) for c, v in cotes.items()}
    nj = sum(v > p.contraste_joint_min for v in contraste.values())
    # 2) gravure qui touche le bord interieur (lettre coupee)
    e = gravure(g, k)
    interieur = e.copy()
    z = px(22)
    interieur[:z] = 0
    interieur[-z:] = 0
    interieur[:, :z] = 0
    interieur[:, -z:] = 0
    n, _, st, _ = cv2.connectedComponentsWithStats(interieur)
    t = px(23)
    coupees = 0
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if (a > 150 * k * k and h > 20 * k
                and (x <= t or y <= t or x + w >= W - t or y + h >= H - t)
                and w < W * 0.5 and h < H * 0.5):
            coupees += 1
    # 3) hauteurs de capitale plausibles
    LL = lignes(g, p.px_par_mm)
    caps = [h for _, h, _, _, nn in LL if nn >= p.lettres_min_par_ligne]
    lisible = any(h >= ll.capitale_min_mm and nn >= ll.lettres_min
                  for _, h, _, _, nn in LL for ll in p.lignes_lisibles)
    trop_grandes = [h for h in caps if h > p.capitale_max_mm]
    ok = nj >= p.joints_min and coupees <= p.lettres_coupees_max and not trop_grandes and lisible
    raisons = []
    if nj < p.joints_min:
        raisons.append(f"joints {nj}/4")
    if coupees > p.lettres_coupees_max:
        raisons.append(f"lettres coupees ({coupees})")
    if trop_grandes:
        raisons.append(f"lettres trop grandes {trop_grandes} (zoom)")
    if not lisible:
        raisons.append("pas de ligne de texte horizontale lisible (vide, zoom ou mauvais sens)")
    return {"vue": vue.name, "ok": bool(ok), "joints": nj, "coupees": coupees,
            "capitales_mm": caps, "raison": "; ".join(raisons)}
