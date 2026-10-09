#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tests/fixtures/marquages/synthese.py
"""Vues et photos SYNTHETIQUES pour les tests de tools/marquages.

Aucune donnee d'affaire : le grain est un bruit aleatoire a graine fixe, le
texte grave est « KEOVIA TEST ». Les tailles suivent le pilote : module
300 x 600 mm, vue a 2 px/mm, joint de 10 mm, capitales de 20 mm.

Lancer ce fichier regenere les trois vues temoins du dossier :
    vue_valide_pave.jpg     cadrage correct : 4 joints, une ligne lisible
    vue_zoom_pave.jpg       zoom : lettres de 50 mm, joints absents de deux cotes
    vue_doublon_pave.jpg    meme module que vue_valide, repris sous un autre angle
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ICI = Path(__file__).resolve().parent
PX_PAR_MM = 2.0
LARGEUR_MM, LONGUEUR_MM = 300.0, 600.0
JOINT_MM = 10.0
GRIS_FOND, GRIS_JOINT, GRIS_GRAVURE = 150, 55, 80


def grain(h: int, w: int, graine: int) -> np.ndarray:
    """Moucheture de granit : bruit multi-echelle et grains sombres ou clairs.

    Les grains restent sous le contraste de la gravure (28 niveaux) : un grain
    plus marque serait compte comme une lettre par le controle."""
    rng = np.random.default_rng(graine)
    im = np.full((h, w), float(GRIS_FOND), np.float32)
    for sigma, amp in ((1.0, 5.0), (3.0, 7.0), (8.0, 8.0)):
        n = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigma)
        im += amp * n / (n.std() + 1e-6)
    for _ in range(h * w // 400):
        y, x = int(rng.integers(0, h)), int(rng.integers(0, w))
        r = int(rng.integers(1, 4))
        cv2.circle(im, (x, y), r, float(rng.choice([125.0, 190.0])), -1)
    return im


def graver(im: np.ndarray, texte: str, cap_mm: float, centre: tuple[float, float],
           px_par_mm: float = PX_PAR_MM) -> None:
    """Grave une ligne de texte centree, capitales de cap_mm (Hershey simplex)."""
    police = cv2.FONT_HERSHEY_SIMPLEX
    ech = cap_mm * px_par_mm / 22.0  # une capitale Hershey simplex mesure ~22 px a l'echelle 1
    ep = max(2, int(round(cap_mm * px_par_mm / 10)))
    (tw, th), _ = cv2.getTextSize(texte, police, ech, ep)
    org = (int(centre[0] - tw / 2), int(centre[1] + th / 2))
    # putText n'ecrit que sur du 8 bits (OpenCV 5) : masque, puis melange
    masque = np.zeros(im.shape, np.uint8)
    cv2.putText(masque, texte, org, police, ech, 255, ep, cv2.LINE_AA)
    a = masque.astype(np.float32) / 255.0
    im[...] = im * (1 - a) + GRIS_GRAVURE * a


def vue_module(graine: int, texte: str, cap_mm: float,
               joints: tuple[str, ...] = ("haut", "bas", "gauche", "droite")) -> np.ndarray:
    """Vue redressee d'un module, decoupee sur les axes des joints."""
    h, w = int(LARGEUR_MM * PX_PAR_MM), int(LONGUEUR_MM * PX_PAR_MM)
    im = grain(h, w, graine)
    graver(im, texte, cap_mm, (w / 2, h / 2))
    demi = int(JOINT_MM * PX_PAR_MM / 2)
    zones = {"haut": (slice(0, demi), slice(None)), "bas": (slice(h - demi, h), slice(None)),
             "gauche": (slice(None), slice(0, demi)), "droite": (slice(None), slice(w - demi, w))}
    for j in joints:
        im[zones[j]] = GRIS_JOINT
    return np.clip(im, 0, 255).astype(np.uint8)


def reprise(vue: np.ndarray, graine: int) -> np.ndarray:
    """Meme module photographie une seconde fois : leger decalage, rotation, exposition, bruit."""
    rng = np.random.default_rng(graine)
    h, w = vue.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 1.2, 1.01)
    M[:, 2] += (6, -4)
    im = cv2.warpAffine(vue.astype(np.float32), M, (w, h), borderMode=cv2.BORDER_REFLECT)
    im = im * 0.9 + 12 + rng.normal(0, 3, im.shape)
    return np.clip(im, 0, 255).astype(np.uint8)


def photo_dallage(graine: int = 7, largeur_px: int = 2016, hauteur_px: int = 1512,
                  focale_sur_diagonale: float = 0.552661, hauteur_m: float = 0.8,
                  inclinaison_deg: float = 12.0, lacet_deg: float = 4.0) -> np.ndarray:
    """Photo d'un dallage en appareil decale, vue d'en haut legerement inclinee.

    Le sol est dessine a 2 px/mm (joints continus le long des longueurs, joints
    de bout decales d'une demi-longueur d'une rangee a l'autre), le module
    central porte le texte, puis la camera stenope le projette.
    """
    cote_mm = 2400.0
    n = int(cote_mm * PX_PAR_MM)
    sol = grain(n, n, graine)
    j = int(JOINT_MM * PX_PAR_MM)
    pl, pL = int(LARGEUR_MM * PX_PAR_MM), int(LONGUEUR_MM * PX_PAR_MM)
    c = n // 2
    # le module central est cale sur le centre du sol
    for k, y in enumerate(range(c - pl // 2 - 4 * pl, n, pl)):
        if y >= 0:
            sol[max(0, y - j // 2):y + j // 2] = GRIS_JOINT
        decal = 0 if k % 2 == 0 else pL // 2
        for x in range(c - pL // 2 - 2 * pL + decal, n, pL):
            if 0 <= x < n:
                sol[max(0, y):min(n, y + pl), max(0, x - j // 2):x + j // 2] = GRIS_JOINT
    graver(sol, "KEOVIA TEST", 20.0, (c, c))
    sol = np.clip(sol, 0, 255).astype(np.uint8)
    # camera : axe optique incline par rapport a la verticale, lacet autour de la verticale
    f = focale_sur_diagonale * np.hypot(largeur_px, hauteur_px)
    K = np.array([[f, 0, largeur_px / 2], [0, f, hauteur_px / 2], [0, 0, 1]])
    ti, tl = np.radians(inclinaison_deg), np.radians(lacet_deg)
    Rz = np.array([[np.cos(tl), -np.sin(tl), 0], [np.sin(tl), np.cos(tl), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(ti), -np.sin(ti)], [0, np.sin(ti), np.cos(ti)]])
    R = Rx @ Rz  # sol -> camera ; z camera vers le sol
    t = np.array([0.0, 0.0, hauteur_m * 1000.0])
    # pixel du sol (u, v) -> mm sol centres sur le module central
    S = np.array([[1 / PX_PAR_MM, 0, -c / PX_PAR_MM], [0, 1 / PX_PAR_MM, -c / PX_PAR_MM], [0, 0, 1]])
    Hsol = K @ np.c_[R[:, 0], R[:, 1], t] @ S
    photo = cv2.warpPerspective(sol, Hsol, (largeur_px, hauteur_px), flags=cv2.INTER_AREA,
                                borderValue=GRIS_FOND)
    bruit = np.random.default_rng(graine + 1).normal(0, 2, photo.shape)
    return cv2.cvtColor(np.clip(photo + bruit, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def generer(dossier: Path = ICI) -> dict[str, Path]:
    dossier = Path(dossier)
    valide = vue_module(11, "KEOVIA TEST", 20.0)
    zoom = vue_module(23, "KEOVIA", 50.0, joints=("haut", "gauche"))
    doublon = reprise(valide, 31)
    sorties = {}
    for nom, im in (("valide", valide), ("zoom", zoom), ("doublon", doublon)):
        chemin = dossier / f"vue_{nom}_pave.jpg"
        cv2.imwrite(str(chemin), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        sorties[nom] = chemin
    return sorties


if __name__ == "__main__":
    for nom, chemin in generer().items():
        print(nom, chemin)
