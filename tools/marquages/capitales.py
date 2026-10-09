#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tools/marquages/capitales.py
"""Lignes de texte d'une vue redressee et hauteur de capitale (mm) de chacune.

Repris du pilote (caps.py). Une ligne = un groupe de lettres alignees ; sa
hauteur de capitale est la mediane des hauteurs de ses lettres. Les tailles
en pixels ont ete calees a 2 px/mm et sont mises a l'echelle de la vue.
"""
from __future__ import annotations

import cv2
import numpy as np

CONTRASTE_GRAVURE = 28  # niveaux de gris sous le fond lisse


def gravure(g: np.ndarray, k: float, sigma_fin: float = 1.2, seuil: float = CONTRASTE_GRAVURE) -> np.ndarray:
    """Masque des traits graves : nettement plus sombres que le fond lisse."""
    g = g.astype(np.float32)
    fond = cv2.GaussianBlur(g, (0, 0), 25 * k)
    return ((fond - cv2.GaussianBlur(g, (0, 0), sigma_fin * k)) > seuil).astype(np.uint8)


def lignes(g: np.ndarray, px_par_mm: float) -> list[tuple[int, float, int, int, int]]:
    """Lignes de texte : (y mm, capitale mm, x0 mm, x1 mm, nombre de lettres)."""
    k = px_par_mm / 2.0
    e = gravure(g, k)
    e = cv2.morphologyEx(e, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    m = int(round(40 * k))
    e[:m] = 0
    e[-m:] = 0
    e[:, :m] = 0
    e[:, -m:] = 0
    n, _, st, cen = cv2.connectedComponentsWithStats(e)
    L = [(st[i, 1], st[i, 3], st[i, 0], st[i, 2], cen[i]) for i in range(1, n)
         if st[i, 4] > 40 * k * k and 10 * k < st[i, 3] < 130 * k and st[i, 2] < 160 * k]
    L.sort(key=lambda t: t[4][1])
    groupes, cur = [], []
    for t in L:
        if cur and abs(t[4][1] - np.median([u[4][1] for u in cur])) > max(
                10 * k, 0.6 * np.median([u[1] for u in cur])):
            groupes.append(cur)
            cur = []
        cur.append(t)
    if cur:
        groupes.append(cur)
    res = []
    for grp in groupes:
        if len(grp) < 3:
            continue
        h = np.median([u[1] for u in grp]) / px_par_mm
        y = np.median([u[4][1] for u in grp]) / px_par_mm
        x0 = min(u[2] for u in grp) / px_par_mm
        x1 = max(u[2] + u[3] for u in grp) / px_par_mm
        res.append((round(y), round(float(h), 1), round(x0), round(x1), len(grp)))
    return res
