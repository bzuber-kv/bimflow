#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tools/marquages/redressement.py
"""Redressement d'un module marque : points de fuite -> vue nadir -> grille de joints -> decoupe au pas.

Repris du pilote du 2026-10-09 (rectify.py). Etapes :
  1. segments de joints (LSD) sur l'image reduite de moitie ;
  2. deux points de fuite par RANSAC, d'ou l'orientation du sol (la focale
     vient des parametres, F1) ;
  3. vue de dessus provisoire, profil des pixels sombres : les joints
     continus donnent les rangees, leur ecart donne le pas ;
  4. choix de la rangee et de la case qui portent le texte, au plus pres du
     centre de la photo ;
  5. decoupe du module dans la photo PLEINE resolution, a l'echelle des
     parametres (px/mm), sur les axes des joints.
Le rapport longueur / largeur du module sert de controle (« 4 joints ») ou de
repli quand un joint de bout manque.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from parametres import Parametres

SUFFIXE_VUE = "_pave.jpg"


def charger(photo: Path) -> np.ndarray:
    """Image BGR, orientee selon l'EXIF (les photos de telephone en dependent)."""
    im = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def nom_vue(photo: Path) -> str:
    return Path(photo).stem + SUFFIXE_VUE


def segments(g: np.ndarray) -> np.ndarray:
    lsd = cv2.createLineSegmentDetector(0)
    L = lsd.detect(cv2.GaussianBlur(g, (5, 5), 0))[0]
    if L is None:
        return np.zeros((0, 4))
    L = L.reshape(-1, 4)
    ln = np.hypot(L[:, 2] - L[:, 0], L[:, 3] - L[:, 1])
    return L[ln > g.shape[1] * 0.04]


def point_de_fuite(L: np.ndarray, it: int = 3000, tol: float = 2.0, seed: int = 0):
    """Point de fuite dominant (RANSAC pondere par la longueur) et masque de ses segments."""
    rng = np.random.default_rng(seed)
    P = np.c_[L[:, :2], np.ones(len(L))]
    Q = np.c_[L[:, 2:], np.ones(len(L))]
    Ls = np.cross(P, Q)
    Ls /= np.linalg.norm(Ls[:, :2], axis=1)[:, None]
    ln = np.hypot(L[:, 2] - L[:, 0], L[:, 3] - L[:, 1])
    M = (P + Q) / 2

    def residu(v):
        l = np.cross(M, np.broadcast_to(v, M.shape))
        n = np.linalg.norm(l[:, :2], axis=1) + 1e-12
        return np.abs((P * l).sum(1)) / n

    best, bi = -1, None
    for _ in range(it):
        i, j = rng.choice(len(L), 2, replace=False)
        v = np.cross(Ls[i], Ls[j])
        v /= np.linalg.norm(v)
        inl = residu(v) < tol
        sc = ln[inl].sum()
        if sc > best:
            best, bi = sc, inl
    _, _, vt = np.linalg.svd(Ls[bi] * ln[bi, None])
    return vt[-1], bi


def _pics(p: np.ndarray, mind: float) -> np.ndarray:
    p = np.convolve(p, np.ones(3) / 3, "same")
    idx = []
    for i in np.argsort(-p):
        if p[i] < 0.25:
            break
        if all(abs(i - j) > mind for j in idx):
            idx.append(i)
    return np.sort(np.array(idx, dtype=int))


def redresser(photo: Path, dossier_vues: Path, p: Parametres,
              debug: Path | None = None) -> dict:
    """Redresse une photo et ecrit la vue du module dans dossier_vues.

    Returns
    -------
    dict : photo, ok, et selon le cas raison (echec) ou mode, ratio,
           coins_image, px_par_mm_source, vue.
    """
    photo = Path(photo)
    out: dict = {"photo": photo.name}
    im = charger(photo)
    H, W = im.shape[:2]
    f = p.focale_sur_diagonale * np.hypot(W, H)
    sc = 0.5
    sm = cv2.resize(im, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY)
    L = segments(g)
    if len(L) < 10:
        out.update(ok=False, raison="peu de joints")
        return out
    v1, i1 = point_de_fuite(L)
    if (~i1).sum() < 2:
        out.update(ok=False, raison="une seule famille de joints")
        return out
    v2, _ = point_de_fuite(L[~i1], seed=1)
    K = np.array([[f * sc, 0, W * sc / 2], [0, f * sc, H * sc / 2], [0, 0, 1]])
    Ki = np.linalg.inv(K)
    a = Ki @ v1
    a /= np.linalg.norm(a)
    b = Ki @ v2
    b -= a * (a @ b)
    b /= np.linalg.norm(b)
    u1 = Ki @ v1 / np.linalg.norm(Ki @ v1)
    u2 = Ki @ v2 / np.linalg.norm(Ki @ v2)
    ang = np.degrees(np.arccos(min(1, abs(u1 @ u2))))
    # axe long = direction des joints continus = famille la plus chargee (v1) ;
    # a oriente vers +x, b vers +y
    if a[0] < 0:
        a = -a
    n = np.cross(a, b)
    if n[2] < 0:
        b = -b
        n = -n
    R = np.vstack([a, b, n])
    Hr = R @ Ki  # image -> rayons dans le repere du sol (x = a, y = b, z = n)

    def projeter(pts):
        q = (Hr @ np.c_[pts, np.ones(len(pts))].T).T
        return q[:, :2] / q[:, 2:3]

    # echelle provisoire : densite de la zone centrale conservee
    c = np.array([[W * sc / 2, H * sc / 2], [W * sc / 2 + 1, H * sc / 2]])
    wc = projeter(c)
    s0 = 1 / np.linalg.norm(wc[1] - wc[0])
    coins = projeter(np.array([[0, 0], [W * sc, 0], [W * sc, H * sc], [0, H * sc]])) * s0
    ctr = projeter(np.array([[W * sc / 2, H * sc / 2]]))[0] * s0
    # etendue bornee (horizon lointain)
    x0, y0 = np.maximum(coins.min(0), ctr - [W * sc * 1.2, H * sc * 1.2])
    x1, y1 = np.minimum(coins.max(0), ctr + [W * sc * 1.2, H * sc * 1.2])
    T = np.array([[s0, 0, -x0], [0, s0, -y0], [0, 0, 1]]) @ Hr
    ow, oh = int(x1 - x0), int(y1 - y0)
    rs = cv2.warpPerspective(g, T, (ow, oh), flags=cv2.INTER_LINEAR, borderValue=0)
    valide = cv2.warpPerspective(np.full_like(g, 255), T, (ow, oh), borderValue=0) > 0
    # profil des joints : pixels sombres relatifs
    fond = cv2.medianBlur(rs, 31).astype(float)
    sombre = ((fond - rs) > 12) & valide
    prow = sombre.sum(1) / np.maximum(valide.sum(1), 1)
    pr = prow - prow.mean()
    ac = np.correlate(pr, pr, "full")[len(pr) - 1:]
    ac[:20] = 0
    rc = Ki @ np.array([W * sc / 2, H * sc / 2, 1.0])
    rc /= np.linalg.norm(rc)
    cz = abs(n @ rc)
    largeur_m = p.largeur_mm / 1000.0
    lo = int(largeur_m * f * sc * cz / p.distance_max_m)
    hi = int(largeur_m * f * sc * cz / p.distance_min_m)
    # 1) joints continus : lignes dont la fraction sombre est elevee sur toute la largeur
    ps = np.convolve(prow, np.ones(5) / 5, "same")
    forts = []
    for i in np.argsort(-ps):
        if ps[i] < 0.45:
            break
        if all(abs(i - j) > lo * 0.8 for j in forts):
            forts.append(i)
    forts = np.sort(forts)
    dd = np.diff(forts) if len(forts) > 1 else np.array([])
    dd = dd[(dd >= lo) & (dd <= hi)]
    if len(dd):
        # pas = plus petit ecart coherent (multiples elimines)
        base = np.min(dd)
        mult = dd / base
        ok = np.abs(mult - np.round(mult)) < 0.12
        Pr = int(np.median((dd / np.round(mult))[ok]))
        source_pas = "joints"
    else:
        Pr = lo + int(np.argmax(ac[lo:min(hi, len(ac) - 1)]))
        source_pas = "autocorr"
    rangees = _pics(prow, Pr * 0.6)
    centre = projeter(np.array([[W * sc / 2, H * sc / 2]]))[0] * s0
    cx, cy = centre[0] - x0, centre[1] - y0
    out.update(angle_pf=round(float(ang), 1), pas_rangee_px=Pr,
               n_rangees=len(rangees), source_pas=source_pas)
    # rangee qui porte l'inscription : densite de petits motifs sombres maximale
    cand = []
    for k in range(len(rangees) - 1):
        r0, r1 = rangees[k], rangees[k + 1]
        if 0.8 * Pr < r1 - r0 < 1.25 * Pr:
            cand.append((r0, r1))
    if not cand:
        out.update(ok=False, raison="rangees non trouvees")
        return out

    def score_texte(r0, r1, c0=0, c1=None):
        bande = sombre[int(r0 + 0.15 * (r1 - r0)):int(r1 - 0.15 * (r1 - r0)), c0:c1]
        return bande.mean() if bande.size else 0

    ts = [score_texte(*r) for r in cand]
    tmax = max(ts)
    cand = [r for r, t in zip(cand, ts) if t > 0.5 * tmax]
    cand.sort(key=lambda r: abs((r[0] + r[1]) / 2 - cy))
    r0, r1 = cand[0]
    bande = sombre[int(r0 + 0.1 * (r1 - r0)):int(r1 - 0.1 * (r1 - r0))]
    vbande = valide[int(r0 + 0.1 * (r1 - r0)):int(r1 - 0.1 * (r1 - r0))]
    pcol = bande.sum(0) / np.maximum(vbande.sum(0), 1)
    cols = _pics(np.where(pcol > 0.6, pcol, 0), Pr * 1.5)
    if len(cols):
        cols = cols[np.convolve(pcol, np.ones(3) / 3, "same")[cols] > 0.6]
    rapport = p.rapport_module
    cases = []
    for k in range(len(cols) - 1):
        c0, c1 = cols[k], cols[k + 1]
        if 0.8 * rapport * (r1 - r0) < c1 - c0 < 1.2 * rapport * (r1 - r0):
            cases.append((c0, c1))
    if not cases:
        # repli : un seul joint de bout (ou aucun) -> complete par le rapport connu du module
        L2 = rapport * (r1 - r0)
        bandt = sombre[int(r0 + 0.15 * (r1 - r0)):int(r1 - 0.15 * (r1 - r0))].astype(float)
        xs = np.nonzero(bandt.sum(0) > 0)[0]
        tx = (np.average(np.arange(bandt.shape[1]), weights=bandt.sum(0) + 1e-9)
              if len(xs) else cx)
        options = []
        for c in cols:
            for c_ in (c - L2, c + L2):
                lo_, hi_ = min(c, c_), max(c, c_)
                if lo_ <= tx <= hi_ and lo_ >= 0 and hi_ <= ow:
                    options.append((abs((lo_ + hi_) / 2 - tx), lo_, hi_))
        if options:
            _, c0, c1 = min(options)
            out.update(ok=True, ratio=rapport, mode=f"1 joint + rapport {rapport:g}:1")
        else:
            c0, c1 = tx - L2 / 2, tx + L2 / 2
            out.update(ok=True, ratio=rapport, mode="centre sur texte (aucun joint de bout)")
    else:
        tc = [score_texte(r0, r1, int(c[0]), int(c[1])) for c in cases]
        tm = max(tc)
        cases = [c for c, t in zip(cases, tc) if t > 0.5 * tm]
        cases.sort(key=lambda c: abs((c[0] + c[1]) / 2 - cx))
        c0, c1 = cases[0]
        out.update(ok=True, ratio=round(float((c1 - c0) / (r1 - r0)), 3), mode="4 joints")
    # coins du module (axes des joints) : vue redressee -> photo pleine resolution
    Q = np.array([[c0, r0], [c1, r0], [c1, r1], [c0, r1]], float)
    Ti = np.linalg.inv(T)
    q = (Ti @ np.c_[Q, np.ones(4)].T).T
    q = q[:, :2] / q[:, 2:3] / sc
    out["coins_image"] = np.round(q, 1).tolist()
    Wm, Hm = int(p.longueur_mm * p.px_par_mm), int(p.largeur_mm * p.px_par_mm)
    Hm_ = cv2.getPerspectiveTransform(q.astype(np.float32),
                                      np.float32([[0, 0], [Wm, 0], [Wm, Hm], [0, Hm]]))
    vue = cv2.warpPerspective(im, Hm_, (Wm, Hm), flags=cv2.INTER_CUBIC)
    dossier_vues = Path(dossier_vues)
    dossier_vues.mkdir(parents=True, exist_ok=True)
    chemin_vue = dossier_vues / nom_vue(photo)
    cv2.imwrite(str(chemin_vue), vue, [cv2.IMWRITE_JPEG_QUALITY, 92])
    out["vue"] = chemin_vue.name
    out["px_par_mm_source"] = round(float(np.linalg.norm(q[1] - q[0]) / p.longueur_mm), 2)
    if debug:
        d = cv2.cvtColor(rs, cv2.COLOR_GRAY2BGR)
        for y in rangees:
            cv2.line(d, (0, int(y)), (ow, int(y)), (0, 0, 255), 2)
        cv2.rectangle(d, (int(c0), int(r0)), (int(c1), int(r1)), (0, 255, 0), 4)
        cv2.imwrite(str(debug), cv2.resize(d, None, fx=0.5, fy=0.5))
    return out
