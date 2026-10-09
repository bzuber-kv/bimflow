#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# path : tools/marquages/parametres.py
"""Lecture du fichier de parametres d'une surface marquee.

L'outil ne porte aucune valeur de surface en dur : le pas du module, la
focale, les seuils du controle et de l'empreinte viennent d'un fichier JSON
(exemple : parametres_dallage_300x600.json). Les cles qui commencent par
« _ » sont des notes et sont ignorees.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LigneLisible:
    capitale_min_mm: float
    lettres_min: int


@dataclass
class Parametres:
    largeur_mm: float
    longueur_mm: float
    px_par_mm: float
    focale_sur_diagonale: float
    distance_min_m: float
    distance_max_m: float
    contraste_joint_min: float
    joints_min: int
    lettres_coupees_max: int
    lettres_min_par_ligne: int
    capitale_max_mm: float
    lignes_lisibles: list[LigneLisible] = field(default_factory=list)
    points_sift: int = 4000
    rapport_lowe: float = 0.75
    tolerance_ransac_px: float = 4.0
    seuil_meme_pave: int = 25
    source: Path | None = None

    def __post_init__(self):
        if not 0 < self.largeur_mm <= self.longueur_mm:
            raise ValueError(f"module incoherent : largeur {self.largeur_mm} mm, "
                             f"longueur {self.longueur_mm} mm (0 < largeur <= longueur)")
        if self.px_par_mm <= 0:
            raise ValueError(f"px_par_mm doit etre positif : {self.px_par_mm}")
        if self.focale_sur_diagonale <= 0:
            raise ValueError(f"focale_sur_diagonale doit etre positive : {self.focale_sur_diagonale}")
        if not 0 < self.distance_min_m < self.distance_max_m:
            raise ValueError(f"distances de prise de vue incoherentes : "
                             f"{self.distance_min_m} - {self.distance_max_m} m")
        if not self.lignes_lisibles:
            raise ValueError("controle.lignes_lisibles est vide : aucune vue ne serait lisible")

    @property
    def rapport_module(self) -> float:
        """Longueur sur largeur du module (2,0 pour le dallage du pilote)."""
        return self.longueur_mm / self.largeur_mm

    @property
    def echelle(self) -> float:
        """Facteur entre la resolution des vues et celle du pilote (2 px/mm).

        Les tailles de fenetres en pixels du controle et de l'empreinte ont ete
        calees a 2 px/mm ; elles sont multipliees par ce facteur.
        """
        return self.px_par_mm / 2.0


def lire_parametres(chemin: Path | str) -> Parametres:
    """Lit et valide un fichier de parametres ; toute cle manquante est une erreur."""
    chemin = Path(chemin)
    d = json.loads(chemin.read_text(encoding="utf-8"))
    try:
        mod, vue, cam, ctl, emp = d["module"], d["vue"], d["camera"], d["controle"], d["empreinte"]
        return Parametres(
            largeur_mm=float(mod["largeur_mm"]),
            longueur_mm=float(mod["longueur_mm"]),
            px_par_mm=float(vue["px_par_mm"]),
            focale_sur_diagonale=float(cam["focale_sur_diagonale"]),
            distance_min_m=float(cam["distance_min_m"]),
            distance_max_m=float(cam["distance_max_m"]),
            contraste_joint_min=float(ctl["contraste_joint_min"]),
            joints_min=int(ctl["joints_min"]),
            lettres_coupees_max=int(ctl["lettres_coupees_max"]),
            lettres_min_par_ligne=int(ctl["lettres_min_par_ligne"]),
            capitale_max_mm=float(ctl["capitale_max_mm"]),
            lignes_lisibles=[LigneLisible(float(x["capitale_min_mm"]), int(x["lettres_min"]))
                             for x in ctl["lignes_lisibles"]],
            points_sift=int(emp["points_sift"]),
            rapport_lowe=float(emp["rapport_lowe"]),
            tolerance_ransac_px=float(emp["tolerance_ransac_px"]),
            seuil_meme_pave=int(emp["seuil_meme_pave"]),
            source=chemin,
        )
    except KeyError as e:
        raise ValueError(f"{chemin} : cle manquante {e}") from None
