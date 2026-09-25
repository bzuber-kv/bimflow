# -*- coding: utf-8 -*-
"""bimflow_volumes - classement spatial et numerotation des volumes de zone.

LA REGLE, en trois niveaux. Le numero n'est pas decoratif : il suit
l'espace, pour qu'en lisant une nomenclature triee par nom on descende un
batiment colonne par colonne, et chaque colonne du bas vers le haut.

  niveau 1  par BAT - le PREFIXE de REF_Zone - ordre alphabetique JU, MI,
            SC, SE, puis EXT en dernier.

            ATTENTION, ce n'est PAS REF_Batiment. Les deux different des que
            la cle du nom surcharge le prefixe : mesure du 2026-09-24, HUIT
            zones portent des volumes affectes a deux batiments differents
            (MI_Bc_Ec_7m_1c est a la fois MI et SC). Trier sur REF_Batiment
            couperait ces zones en deux blocs de numeros non contigus, alors
            qu'une zone est UNE colonne - c'est elle qui devient un BUILDING
            en aval. REF_Batiment dit de quel batiment releve un volume ; il
            ne regroupe rien, et ne trie rien.
  niveau 2  a l'interieur d'un batiment, par COLONNE - une colonne est un
            REF_Zone distinct - triee sur le centre de son emprise,
            cle ( round(xc,1), round(yc,1) ) : d'abord x croissant
            (ouest -> est du projet), puis y croissant (sud -> nord).
  niveau 3  a l'interieur d'une colonne, par zmin croissant.

REPERE. xc, yc, zmin sont en COORDONNEES INTERNES REVIT - repere du nord
projet, AUCUNE rotation appliquee. C'est voulu : le tri doit suivre les
axes du modele, pas ceux du terrain. La rotation vers le SCS Ivion
appartient a la chaine site_model, et a elle seule.

NORD LOCAL. Un groupe de batiments peut avoir son propre nord (SE est a
6,6 deg du nord projet). NORD_LOCAL permet de faire pivoter les centres de
colonne de ce groupe AVANT le tri de niveau 2, pour que "ouest -> est"
suive le batiment et non le projet. Prevu, NON ACTIVE : personne n'a
mesure que cela ameliore l'ordre, et un tri qui change sans raison fait
changer tous les numeros.

PYTHON PUR, stdlib seulement : tourne sous IronPython 3.4 dans Revit et
sous CPython 3 hors Revit - c'est ce qui permet de rejouer exactement le
meme classement sur un audit JSON, sans Revit, avant de renommer quoi que
ce soit.

bimflow - Keovia Solutions inc. - 2026-09-24
"""

import math

from bimflow_noms import BATIMENTS, prefixe_de_zone

# Groupe -> angle en DEGRES du nord local par rapport au nord projet.
# Exemple d'emploi : {"SE": 6.6}. Laisse vide = inactif.
NORD_LOCAL = {}

DECIMALES_TRI = 1


def rang_batiment(batiment):
    """Ordre de parcours des batiments : celui de BATIMENTS, l'inconnu en
    fin de liste mais avant rien - il se verra au rapport."""
    if batiment in BATIMENTS:
        return BATIMENTS.index(batiment)
    return len(BATIMENTS)


def centre_colonne(volumes):
    """(xc, yc) d'une colonne : moyenne des centres de ses volumes.

    Les tranches d'une meme colonne partagent leur contour (regle R1), donc
    cette moyenne vaut le centre commun. La DISPERSION autour d'elle est
    rendue par dispersion_colonne() : si elle n'est pas nulle, la colonne
    n'est pas une colonne."""
    n = float(len(volumes))
    return (sum(v["xc"] for v in volumes) / n,
            sum(v["yc"] for v in volumes) / n)


def dispersion_colonne(volumes):
    """Plus grand ecart, en mm, entre le centre d'un volume et le centre de
    sa colonne. Un controle, pas un reglage : il ne corrige rien."""
    xc, yc = centre_colonne(volumes)
    return max([math.hypot(v["xc"] - xc, v["yc"] - yc) for v in volumes])


def _pivote(x, y, degres):
    t = math.radians(degres)
    return (x * math.cos(t) - y * math.sin(t),
            x * math.sin(t) + y * math.cos(t))


def cle_de_tri_colonne(batiment, xc, yc, nord_local=None):
    """Cle de tri du niveau 2, arrondie au dixieme de mm."""
    angles = NORD_LOCAL if nord_local is None else nord_local
    degres = angles.get(batiment)
    if degres:
        xc, yc = _pivote(xc, yc, -degres)
    return (round(xc, DECIMALES_TRI), round(yc, DECIMALES_TRI))


def classer(volumes, nord_local=None):
    """Ordonne les volumes et leur attribue un numero, de 1 a n.

    volumes : liste de dictionnaires portant au moins
        id, zone, etage, nature, cle, xc, yc, zmin
    Le BAT de tri est deduit ici, du PREFIXE de la zone - jamais lu dans le
    dictionnaire, pour qu'aucun appelant ne puisse lui passer REF_Batiment
    par megarde. Chaque volume recoit "bat" en plus de "numero".
    Rend (liste ordonnee, liste de colonnes). Chaque volume recoit
    "numero" ; chaque colonne est un dictionnaire batiment / zone / centre /
    dispersion / volumes.

    La fonction ne lit RIEN d'autre que ces champs : c'est ce qui permet de
    l'alimenter depuis Revit ou depuis un audit JSON et d'obtenir, au bit
    pres, le meme classement."""
    par_colonne = {}
    for v in volumes:
        v["bat"] = prefixe_de_zone(v["zone"])
        par_colonne.setdefault(v["zone"], []).append(v)

    colonnes = []
    for zone, membres in par_colonne.items():
        xc, yc = centre_colonne(membres)
        colonnes.append({
            "batiment": prefixe_de_zone(zone),
            "zone": zone,
            "xc": xc,
            "yc": yc,
            "dispersion": dispersion_colonne(membres),
            "volumes": sorted(membres, key=lambda v: (v["zmin"], v["id"])),
        })

    colonnes.sort(key=lambda c: (
        rang_batiment(c["batiment"]),
        cle_de_tri_colonne(c["batiment"], c["xc"], c["yc"], nord_local),
        c["zone"],
    ))

    ordonnes = []
    numero = 0
    for colonne in colonnes:
        for v in colonne["volumes"]:
            numero += 1
            v["numero"] = numero
            ordonnes.append(v)
    return ordonnes, colonnes
