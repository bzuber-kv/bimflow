#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tools/marquages/empreintes.py
"""Identite d'un module par son grain : appariement SIFT, gravure masquee, filtre RANSAC.

Repris du pilote (same2.py et allpairs.py). Le texte n'identifie pas un
module (F7, C-MP1) : deux photos montrent le meme module si leur grain
s'apparie. On masque la gravure (sinon deux textes identiques s'apparient)
et la marge des joints, puis on compte les points qui suivent une meme
homographie. Mesure du pilote (F6) : 150 a 440 points pour un meme pave,
10 au plus pour deux paves differents.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import cv2
import numpy as np

from capitales import gravure
from parametres import Parametres


class Empreintes:
    def __init__(self, p: Parametres):
        self.p = p
        self.sift = cv2.SIFT_create(nfeatures=p.points_sift)
        self._cache: dict[Path, tuple] = {}

    def _calculer(self, vue: Path):
        g = cv2.imread(str(vue), cv2.IMREAD_GRAYSCALE)
        if g is None:
            raise ValueError(f"vue illisible : {vue}")
        k = self.p.echelle
        trait = gravure(g, k, sigma_fin=3.0, seuil=22)
        d = max(1, int(round(21 * k)))
        masque = (~(cv2.dilate(trait, np.ones((d, d), np.uint8)) > 0)).astype(np.uint8) * 255
        m = int(round(40 * k))
        masque[:m] = 0
        masque[-m:] = 0
        masque[:, :m] = 0
        masque[:, -m:] = 0
        return self.sift.detectAndCompute(g, masque)

    def points(self, vue: Path):
        vue = Path(vue)
        if vue not in self._cache:
            self._cache[vue] = self._calculer(vue)
        return self._cache[vue]

    def apparier(self, a: Path, b: Path) -> tuple[int, int]:
        """(points RANSAC, bons appariements apres le test de Lowe)."""
        ka, da = self.points(a)
        kb, db = self.points(b)
        if da is None or db is None or len(da) < 2 or len(db) < 2:
            return 0, 0
        paires = cv2.BFMatcher().knnMatch(da, db, k=2)
        bons = [x for x, *y in paires if y and x.distance < self.p.rapport_lowe * y[0].distance]
        if len(bons) < 8:
            return 0, len(bons)
        pa = np.float32([ka[x.queryIdx].pt for x in bons])
        pb = np.float32([kb[x.trainIdx].pt for x in bons])
        _, masque = cv2.findHomography(pa, pb, cv2.RANSAC, self.p.tolerance_ransac_px)
        return (int(masque.sum()) if masque is not None else 0), len(bons)


def toutes_paires(vues: list[Path], p: Parametres) -> list[dict]:
    """Appariement de toutes les paires (n(n-1)/2) ; chaque paire est rendue, meme a 0."""
    emp = Empreintes(p)
    res = []
    for a, b in itertools.combinations(sorted(vues), 2):
        n, bons = emp.apparier(a, b)
        res.append({"a": Path(a).name, "b": Path(b).name, "points": n, "bons": bons,
                    "meme_pave": n >= p.seuil_meme_pave})
    return res
