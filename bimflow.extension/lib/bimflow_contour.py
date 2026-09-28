# -*- coding: utf-8 -*-
"""bimflow_contour - le contour en plan d'un volume de zone, et son aire.

UN SEUL ENDROIT reconstruit un contour. Trois appelants s'en servent :
  - le bouton AuditVolumes, dans Revit, qui controle CAR_Surface_sol ;
  - le bouton MajParamsVolumes, dans Revit, qui ecrit CAR_Surface_sol ;
  - tools/sitemodel/audit_to_zones.py, hors Revit, qui en tire les emprises
    du site_model.
Jusqu'au 2026-09-28, le chainage vivait dans audit_to_zones seul. Il en a
ete extrait tel quel, pour que la surface ecrite dans Revit et l'emprise
envoyee a Ivion sortent du MEME code.

L'ENTREE est la liste des faces telle que l'audit la publie dans son JSON
(bimflow_geometrie.decrire_face) : classe, normale, planaire, aire_m2, et
pour les faces VERTICALES leurs aretes deja projetees en XY (segments_xy).
Dans Revit comme hors Revit, c'est donc la meme donnee qui entre ici.

COMMENT LE CONTOUR EST RECONSTRUIT
  1. les faces VERTICALES donnent leurs aretes projetees en (x, y) ;
  2. les extremites sont fusionnees a la tolerance (1 mm), puis chainees en
     cycle : chaque sommet doit avoir exactement DEUX voisins, et le parcours
     doit revenir a son point de depart en consommant TOUTES les aretes.
     Sinon le contour est refuse - jamais repare.
  3. l'aire est celle du contour (formule du lacet), en projection
     horizontale : c'est la definition de CAR_Surface_sol.

FUSION DES SOMMETS, un point a connaitre. audit_to_zones partage UNE fusion
entre tous les volumes (un sommet vu sur un volume sert de reference au
voisin) ; contour_du_volume() en ouvre une NEUVE par volume, parce qu'une
surface ecrite sur un volume ne doit dependre ni de ses voisins ni de
l'ordre de lecture. Ecart mesure entre les deux sur la maquette centrale
thestudy_A_VOL (audit du 2026-09-24 18h14) : 0,0028 m2 au pire, 17 volumes
sur 202 au-dessus de 0,0001 m2.

PYTHON PUR, stdlib seulement : tourne sous IronPython 3.4 dans Revit et sous
CPython 3 hors Revit.

bimflow - Keovia Solutions inc. - 2026-09-28
"""

import math

TOL_SOMMET_MM = 1.0        # fusion de deux extremites d'aretes
DEC_SOMMET = 1             # arrondi de la cle d'un sommet, en dixieme de mm
TOL_CONTOUR_MM = 1.0       # ecart admis entre deux contours "egaux"

# Une face basse dont l'aire depasse la projection de plus que ceci est
# signalee : la surface au sol n'est alors PAS l'aire de la face basse.
TOL_FACE_BASSE_M2 = 0.01


def aire_lacet(anneau):
    """Aire algebrique d'un anneau ferme, en mm2 (positive si sens trigo)."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(anneau, anneau[1:]):
        s += x1 * y2 - x2 * y1
    return s / 2.0


class Sommets(object):
    """Fusionne les extremites proches en UN sommet canonique.

    Grille de TOL mm : pour un point donne, on ne compare qu'aux sommets des
    neuf cases voisines. Le cout reste lineaire, et la fusion ne depend pas
    de l'ordre de lecture a la tolerance pres."""

    def __init__(self, tol=TOL_SOMMET_MM):
        self.tol = tol
        self.cases = {}

    def _case(self, x, y):
        return (int(math.floor(x / self.tol)), int(math.floor(y / self.tol)))

    def canonique(self, x, y):
        cx, cy = self._case(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py in self.cases.get((cx + dx, cy + dy), []):
                    if math.hypot(px - x, py - y) <= self.tol:
                        return (px, py)
        point = (round(x, DEC_SOMMET), round(y, DEC_SOMMET))
        self.cases.setdefault(self._case(*point), []).append(point)
        return point


def chainer(segments, sommets):
    """(anneau ferme, None) ou (None, motif du refus).

    Un contour de volume est un cycle simple : chaque sommet a exactement
    deux voisins, et le parcours consomme toutes les aretes."""
    voisins = {}
    aretes = set()
    for (x1, y1), (x2, y2) in segments:
        a = sommets.canonique(x1, y1)
        b = sommets.canonique(x2, y2)
        if a == b:
            continue                      # arete degeneree apres fusion
        cle = (a, b) if a <= b else (b, a)
        if cle in aretes:
            continue                      # doublon : deja vue
        aretes.add(cle)
        voisins.setdefault(a, []).append(b)
        voisins.setdefault(b, []).append(a)

    if not aretes:
        return None, "aucune arete exploitable"

    degres = {}
    for point, liste in voisins.items():
        degres.setdefault(len(liste), 0)
        degres[len(liste)] += 1
    mauvais = [(p, len(v)) for p, v in voisins.items() if len(v) != 2]
    if mauvais:
        return None, ("contour non refermable : %d sommet(s) de degre != 2 "
                      "(degres observes : %s)"
                      % (len(mauvais),
                         ", ".join("%d->%dx" % (d, n)
                                   for d, n in sorted(degres.items()))))

    depart = min(voisins)
    anneau = [depart]
    precedent = None
    courant = depart
    vues = set()
    while True:
        suite = [v for v in voisins[courant] if v != precedent]
        if not suite:
            return None, "contour interrompu : cul-de-sac"
        suivant = suite[0]
        cle = (courant, suivant) if courant <= suivant else (suivant, courant)
        vues.add(cle)
        anneau.append(suivant)
        precedent, courant = courant, suivant
        if courant == depart:
            break
        if len(anneau) > len(aretes) + 1:
            return None, "contour interrompu : parcours non convergent"

    if len(vues) != len(aretes):
        return None, ("plusieurs contours fermes : %d arete(s) sur %d "
                      "parcourues - le volume porte-t-il plusieurs solides, "
                      "ou un trou ?" % (len(vues), len(aretes)))

    if aire_lacet(anneau) < 0:
        anneau.reverse()                  # sens trigonometrique, par convention
    return anneau, None


def contours_egaux(a, b):
    """Deux anneaux decrivent-ils le meme contour, a la tolerance pres ?"""
    ea = set(a[:-1])
    eb = set(b[:-1])
    if len(ea) != len(eb):
        return False
    for point in ea:
        if point in eb:
            continue
        if not any(math.hypot(point[0] - q[0], point[1] - q[1]) <= TOL_CONTOUR_MM
                   for q in eb):
            return False
    return True


def segments_verticaux(faces):
    """Aretes projetees en XY de toutes les faces VERTICALES, dans l'ordre
    des faces - l'ordre compte : c'est lui qui designe le sommet canonique."""
    segments = []
    for f in faces:
        if f.get("classe") == "VERTICALE":
            segments.extend(f.get("segments_xy") or [])
    return segments


def contour_du_volume(faces):
    """(anneau, aire en m2, None) ou (None, None, motif du refus).

    La fusion des sommets est propre a ce volume - voir l'en-tete."""
    if not faces:
        return None, None, "aucune face lue"
    segments = segments_verticaux(faces)
    if not segments:
        return None, None, "aucune face verticale : contour impossible a " \
                           "reconstruire"
    anneau, motif = chainer(segments, Sommets())
    if anneau is None:
        return None, None, motif
    return anneau, abs(aire_lacet(anneau)) / 1e6, None


def face_basse(faces, aire_contour_m2):
    """Ce que dit la face basse du volume, rapproche de sa projection.

    Rend un dictionnaire :
      aire_m2      somme des aires des faces tournees vers le bas (nz < 0),
                   verticales exclues ;
      inclinee     vrai si l'une d'elles est INCLINEE, ou horizontale mais
                   non plane ;
      ecart_m2     aire_m2 - aire du contour. Nulle a la tolerance pres pour
                   un fond plat ; positive pour un fond en pente, parce qu'une
                   face inclinee est plus grande que son ombre au sol.
    CAR_Surface_sol est la PROJECTION : c'est aire_contour_m2, jamais aire_m2.
    Ce qui est rendu ici sert a le dire, pas a le corriger."""
    basses = [f for f in faces
              if f.get("classe") != "VERTICALE"
              and (f.get("normale") or [0, 0, 0])[2] < 0]
    aire = sum([f.get("aire_m2") or 0.0 for f in basses])
    inclinee = any(f.get("classe") == "INCLINEE" or not f.get("planaire")
                   for f in basses)
    ecart = None if aire_contour_m2 is None else aire - aire_contour_m2
    return {
        "aire_m2": round(aire, 4),
        "nb_faces": len(basses),
        "inclinee": inclinee,
        "ecart_m2": None if ecart is None else round(ecart, 4),
    }
